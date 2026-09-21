"""
Unit tests for the investigation discipline tools.

Fixtures are synthetic and independently authored (RFC 5737 addresses, invented
hostnames and accounts).
"""

from __future__ import annotations

import json

from src.core.evidence import DeviceContext, EvidenceEvent, get_store
from src.registry.tools.investigation_tools import (
    TACTIC_SEQUENCE,
    build_attack_hypothesis,
    check_benign_baseline,
    verify_claims_against_evidence,
)


def store_with(events: list[EvidenceEvent], run: str):
    get_store(run).append(events)


def payload(result: str) -> dict:
    return json.loads(result.split("```json", 1)[1].rsplit("```", 1)[0])


# ── build_attack_hypothesis ──────────────────────────────


async def test_hypothesis_covers_every_tactic():
    store_with(
        [EvidenceEvent(timestamp="2031-08-01T10:00:00+00:00", host="WS-SYNTH-20")],
        "hyp-full-run",
    )

    data = payload(await build_attack_hypothesis(_run_id="hyp-full-run"))
    tactics = [s["tactic"] for s in data["kill_chain"]]
    assert tactics == TACTIC_SEQUENCE
    assert "Exfiltration" in tactics, "the most-missed stage must always be listed"


async def test_unaddressed_stages_are_marked():
    store_with(
        [EvidenceEvent(timestamp="2031-08-01T10:00:00+00:00", host="WS-SYNTH-21")],
        "hyp-gap-run",
    )

    data = payload(
        await build_attack_hypothesis("We established Initial Access.", _run_id="hyp-gap-run")
    )
    by_tactic = {s["tactic"]: s["status"] for s in data["kill_chain"]}
    assert by_tactic["Initial Access"] == "claimed_by_investigation"
    assert by_tactic["Exfiltration"] == "not_yet_established"


async def test_capability_reflects_available_telemetry():
    store_with(
        [
            EvidenceEvent(
                timestamp="2031-08-01T10:00:00+00:00",
                user="bkowalski",
                status="success",
                device=DeviceContext(os="Windows", is_managed=True),
            )
        ],
        "hyp-capability-run",
    )

    data = payload(await build_attack_hypothesis(_run_id="hyp-capability-run"))
    capability = data["analysis_capability"]
    assert capability["authentication"] is True
    assert capability["device_posture"] is True
    # No process or flow telemetry was ingested, so those questions are unanswerable.
    assert capability["process_execution"] is False
    assert capability["network_flow"] is False


async def test_hypothesis_requires_evidence():
    result = await build_attack_hypothesis(_run_id="hyp-empty-run")
    assert "ingest_logs" in result


# ── verify_claims_against_evidence ───────────────────────


def seeded(run: str):
    store_with(
        [
            EvidenceEvent(
                timestamp="2031-08-01T10:00:00+00:00",
                host="SRV-SYNTH-30",
                user="ahartmann",
                src_ip="10.80.1.5",
                dst_ip="192.0.2.140",
                raw_excerpt="flow 10.80.1.5 -> 192.0.2.140",
                source_type="synthetic_firewall",
            )
        ],
        run,
    )


async def test_grounded_draft_passes():
    seeded("verify-ok-run")
    draft = "Host SRV-SYNTH-30 connected to 192.0.2.140 at 10:00 UTC [EV-000001]."
    result = await verify_claims_against_evidence(draft, _run_id="verify-ok-run")
    assert "Verification verdict: PASS" in result


async def test_invented_containment_target_fails_and_explains():
    seeded("verify-fail-run")
    draft = (
        "## Findings\nTraffic reached 192.0.2.140 at 10:00 [EV-000001].\n\n"
        "## Containment\nBlock all traffic to 198.51.100.55 across the perimeter now.\n"
    )
    result = await verify_claims_against_evidence(draft, _run_id="verify-fail-run")
    assert "Verification verdict: FAIL" in result
    assert "uninvolved system" in result


async def test_empty_draft_is_rejected():
    seeded("verify-empty-draft-run")
    result = await verify_claims_against_evidence("", _run_id="verify-empty-draft-run")
    assert "required" in result


async def test_verification_needs_evidence():
    result = await verify_claims_against_evidence("Anything.", _run_id="verify-no-ev-run")
    assert "ingest_logs" in result


# ── check_benign_baseline ────────────────────────────────


async def test_benign_rules_have_invalidating_conditions():
    data = payload(await check_benign_baseline(_run_id="benign-run"))
    assert data["rules"], "benign rules must be available"
    for rule in data["rules"]:
        assert rule["check"].strip()
        assert rule["invalidated_by"].strip(), (
            "every benign rule must state what would disprove it, "
            "otherwise it becomes a blanket allowlist"
        )


async def test_benign_rules_contain_no_literal_allowlist():
    """Rules must describe shapes, never specific addresses (charter R2)."""
    import re

    result = await check_benign_baseline(_run_id="benign-literal-run")
    assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", result)


async def test_benign_guidance_favours_escalation_on_doubt():
    data = payload(await check_benign_baseline(_run_id="benign-principle-run"))
    joined = " ".join(data["principles"]).lower()
    assert "evidenced" in joined
    assert "escalate" in joined
