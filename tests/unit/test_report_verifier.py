"""
Unit tests for the report verifier.

Fixtures are synthetic: RFC 5737 documentation addresses, invented hostnames and
accounts, and hashes generated for these tests. They exercise the verification
mechanics, not any particular dataset.
"""

from __future__ import annotations

from src.core.evidence import EvidenceEvent, get_store
from src.core.report_verifier import (
    format_verification_section,
    verify_report,
)

REAL_IP = "192.0.2.77"
REAL_HASH = "a" * 64
FAKE_IP = "198.51.100.202"
FAKE_HASH = "b" * 64


def seeded_store(run: str):
    store = get_store(run)
    store.append(
        [
            EvidenceEvent(
                timestamp="2031-07-01T08:00:00+00:00",
                host="SRV-SYNTH-11",
                user="dcorriveau",
                src_ip="10.70.3.14",
                dst_ip=REAL_IP,
                dst_port=8080,
                hashes={"sha256": REAL_HASH},
                raw_excerpt=f"conn 10.70.3.14 -> {REAL_IP}:8080",
                source_type="synthetic_firewall",
            )
        ]
    )
    return store


# ── baseline ─────────────────────────────────────────────


def test_empty_report_fails():
    result = verify_report("", store=seeded_store("vr-empty-report"))
    assert result.verdict == "fail"
    assert result.issues[0].kind == "empty_report"


def test_empty_store_fails_every_report():
    result = verify_report("The host contacted 192.0.2.77 at 08:00.", run_id="vr-no-evidence")
    assert result.verdict == "fail"
    assert result.issues[0].kind == "no_evidence"


def test_fully_grounded_report_passes():
    store = seeded_store("vr-clean")
    report = (
        "## Findings\n"
        f"Host SRV-SYNTH-11 connected to {REAL_IP} on port 8080 at 08:00 UTC [EV-000001].\n"
    )
    result = verify_report(report, store=store)
    assert result.verdict == "pass"
    assert result.citations_found == 1
    assert not result.issues


def test_unicode_dashes_in_citations_still_verify():
    """LLMs emit typographic dashes inside identifiers (EV\u2011000001).

    Regression: a fully cited real report scored 0% citation coverage because
    every id used U+2011 instead of ASCII '-', producing a false FAIL.
    """
    store = seeded_store("vr-dash")
    report = (
        "## Findings\n"
        f"Host SRV\u2011SYNTH\u201111 connected to {REAL_IP} on port 8080 at 08:00 [EV\u2011000001].\n"
    )
    result = verify_report(report, store=store)
    assert result.citations_found == 1
    assert not result.invalid_citations
    assert result.verdict == "pass"
    # The annotated output carries the normalized, greppable form.
    assert "EV-000001" in result.annotated_report


def test_domain_qualified_account_is_grounded():
    """'DOMAIN\\user' refers to the same principal the evidence stores bare."""
    store = seeded_store("vr-domain-user")
    report = (
        "## Containment\n"
        "- Reset password for `SYNTHCORP\\dcorriveau` [EV-000001]\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(i.kind == "ungrounded_remediation_target" for i in result.issues)


def test_hostname_short_form_is_grounded():
    """A short hostname matches its fully-qualified evidence form and vice versa."""
    store = get_store("vr-fqdn")
    store.append(
        [
            EvidenceEvent(
                timestamp="2031-07-01T08:00:00+00:00",
                host="srv-synth-11.corp.example.test",
                user="dcorriveau",
                source_type="synthetic",
                raw_excerpt="logon srv-synth-11.corp.example.test",
            )
        ]
    )
    report = "## Containment\n- Isolate `SRV-SYNTH-11` [EV-000001]\n"
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(i.kind == "ungrounded_remediation_target" for i in result.issues)


def test_unknown_qualified_account_still_fails():
    """Normalization must not grant a pass to a genuinely absent principal."""
    store = seeded_store("vr-unknown-principal")
    report = "## Containment\n- Reset password for `SYNTHCORP\\nobody_real` [EV-000001]\n"
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert any(
        i.kind == "ungrounded_remediation_target" and "nobody_real" in i.value
        for i in result.issues
    )


def test_grounded_destination_ip_in_remediation_is_not_flagged():
    """Regression: a dst_ip present in the store, when backticked inside a
    remediation section, was checked against the accounts/hosts pools instead
    of the ips pool and falsely FAILed as an ungrounded remediation target."""
    store = seeded_store("vr-remediation-ip")
    report = (
        "## Containment\n"
        f"- Validate outbound flows to `{REAL_IP}` before blocking [EV-000001]\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(
        i.kind == "ungrounded_remediation_target" for i in result.issues
    ), [i.value for i in result.issues]


def test_unknown_ip_in_remediation_still_flagged_once():
    """An absent IP in remediation must still fail — as ungrounded_ip — but
    must not be double-reported as an ungrounded remediation target too."""
    store = seeded_store("vr-remediation-fake-ip")
    report = f"## Containment\n- Block `{FAKE_IP}` at the perimeter [EV-000001]\n"
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert any(i.kind == "ungrounded_ip" and i.value == FAKE_IP for i in result.issues)
    assert not any(i.kind == "ungrounded_remediation_target" for i in result.issues)


# ── entity grounding ─────────────────────────────────────


def test_ungrounded_ip_in_narrative_warns():
    store = seeded_store("vr-warn-ip")
    report = f"## Findings\nThe attacker staged data on {FAKE_IP} during the 08:00 window.\n"
    result = verify_report(report, store=store)
    assert result.verdict == "warn"
    assert any(i.kind == "ungrounded_ip" and i.value == FAKE_IP for i in result.issues)


def test_ungrounded_hash_reported():
    store = seeded_store("vr-hash")
    report = f"## Findings\nThe dropped binary had SHA-256 {FAKE_HASH} observed at 08:00.\n"
    result = verify_report(report, store=store)
    assert any(i.kind == "ungrounded_hash" for i in result.issues)


def test_known_hash_accepted():
    store = seeded_store("vr-hash-ok")
    report = f"## Findings\nThe binary hash {REAL_HASH} was recorded at 08:00 [EV-000001].\n"
    result = verify_report(report, store=store)
    assert not any(i.kind == "ungrounded_hash" for i in result.issues)


# ── remediation grounding (hard fail) ────────────────────


def test_invented_ip_in_containment_section_hard_fails():
    store = seeded_store("vr-remediation")
    report = (
        "## Findings\n"
        f"Traffic reached {REAL_IP} at 08:00 [EV-000001].\n\n"
        "## Containment Actions\n"
        "```powershell\n"
        "```\n"
        f"Block outbound traffic to {FAKE_IP} and isolate the affected subnet immediately.\n"
    )
    result = verify_report(report, store=store)
    assert result.verdict == "fail"
    failure = next(i for i in result.issues if i.value == FAKE_IP)
    assert failure.severity == "fail"
    assert "never implicated" in failure.detail


def test_invented_host_named_as_remediation_target_hard_fails():
    store = seeded_store("vr-remediation-host")
    report = (
        "## Findings\n"
        f"Observed traffic to {REAL_IP} at 08:00 [EV-000001].\n\n"
        "## Remediation\n"
        "Immediately isolate `WS-DOES-NOT-EXIST` from the corporate network.\n"
    )
    result = verify_report(report, store=store)
    assert result.verdict == "fail"
    assert any(i.kind == "ungrounded_remediation_target" for i in result.issues)


def test_real_host_named_as_remediation_target_accepted():
    store = seeded_store("vr-remediation-ok")
    report = (
        "## Findings\n"
        f"Observed traffic to {REAL_IP} at 08:00 [EV-000001].\n\n"
        "## Remediation\n"
        "Isolate `SRV-SYNTH-11` and reset credentials for `dcorriveau` within 1 hour.\n"
    )
    result = verify_report(report, store=store)
    assert not any(i.kind == "ungrounded_remediation_target" for i in result.issues)


def test_remediation_section_ends_at_next_heading():
    store = seeded_store("vr-section-end")
    report = (
        "## Containment\n"
        "Isolate `SRV-SYNTH-11` immediately, within the first 60 minutes.\n\n"
        "## Appendix\n"
        f"For reference the staging address was {FAKE_IP} at 09:00.\n"
    )
    result = verify_report(report, store=store)
    issue = next(i for i in result.issues if i.value == FAKE_IP)
    assert issue.severity == "warn", "outside the containment section this is a warning"


# ── citations ────────────────────────────────────────────


def test_fabricated_citation_hard_fails():
    store = seeded_store("vr-bad-citation")
    report = f"## Findings\nConnection to {REAL_IP} recorded at 08:00 [EV-999999].\n"
    result = verify_report(report, store=store)
    assert result.verdict == "fail"
    assert result.invalid_citations == ["EV-999999"]


def test_low_citation_coverage_warns():
    store = seeded_store("vr-coverage")
    report = (
        "## Findings\n"
        "The intrusion began at 08:00 and continued for 4 hours across 3 hosts.\n"
        "A total of 12 accounts showed anomalous behaviour during that window.\n"
        "Approximately 40 connections were observed in the 08:00 to 12:00 period.\n"
    )
    result = verify_report(report, store=store)
    assert any(i.kind == "low_citation_coverage" for i in result.issues)
    assert result.citation_coverage < 0.5


def test_unverified_marker_counts_as_acknowledged():
    store = seeded_store("vr-unverified")
    report = (
        "## Findings\n"
        "The intrusion began at 08:00 and lasted roughly 4 hours [UNVERIFIED].\n"
    )
    result = verify_report(report, store=store)
    assert result.cited_claim_sentences == result.claim_sentences


# ── annotation & rendering ───────────────────────────────


def test_annotation_marks_ungrounded_values_inline():
    store = seeded_store("vr-annotate")
    report = f"## Findings\nData was sent to {FAKE_IP} at 08:00.\n"
    result = verify_report(report, store=store)
    assert f"{FAKE_IP} [UNVERIFIED: not in evidence]" in result.annotated_report


def test_verification_section_renders_verdict():
    store = seeded_store("vr-render")
    report = f"## Findings\nTraffic to {FAKE_IP} at 08:00 was observed.\n"
    section = format_verification_section(verify_report(report, store=store))
    assert "## Evidence Verification" in section
    assert "Citation coverage" in section


def test_result_serializes_for_transport():
    store = seeded_store("vr-serialize")
    report = f"## Findings\nTraffic to {REAL_IP} at 08:00 [EV-000001].\n"
    data = verify_report(report, store=store).as_dict()
    assert data["verdict"] == "pass"
    assert data["evidence_events"] == 1
    assert isinstance(data["issues"], list)
