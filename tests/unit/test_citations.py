"""
Unit tests for the case-agnostic evidence-citation system.

Covers the primitives in ``src.core.citations`` (id minting, evidence-map
round-trip, IoC-shape detection, deterministic verification + table), the
``verify_investigation_report`` activity, and the supervisor citation-coverage
gate helper.

All fixtures use synthetic RFC 5737 documentation addresses (203.0.113.x /
198.51.100.x) and invented identifiers so the tests remain fully decoupled from
any evaluation dataset.
"""

import pytest

from src.core.citations import (
    EV_ID_RE,
    EvidenceRecord,
    format_evidence_map,
    format_ev_id,
    format_verification_table,
    line_has_ioc,
    extract_ioc_tokens,
    parse_cited_ids,
    parse_evidence_map,
    strip_evidence_map,
    verify_citations,
)


# ── id formatting ────────────────────────────────────────────────
def test_format_ev_id_is_fixed_width_and_matches_pattern():
    ev = format_ev_id(123)
    assert ev == "EV-000123"
    assert EV_ID_RE.fullmatch(ev)


def test_format_ev_id_one_based_first_index():
    assert format_ev_id(1) == "EV-000001"


# ── evidence-map round-trip ──────────────────────────────────────
def _sample_records():
    return [
        EvidenceRecord("EV-000001", "auth.log", 12, "Failed password from 203.0.113.7"),
        EvidenceRecord("EV-000002", "proxy.log", 88, "GET http://malicious.example/x"),
        EvidenceRecord("EV-000003", "edr.log", 4, "hash d41d8cd98f00b204e9800998ecf8427e"),
    ]


def test_evidence_map_round_trip_preserves_records():
    records = _sample_records()
    block = format_evidence_map(records)
    parsed = parse_evidence_map(block)
    assert set(parsed.keys()) == {"EV-000001", "EV-000002", "EV-000003"}
    assert parsed["EV-000001"].source_file == "auth.log"
    assert parsed["EV-000001"].line_no == 12


def test_evidence_map_row_cap_marks_omission():
    records = [
        EvidenceRecord(format_ev_id(i), "f.log", i, f"line {i} from 203.0.113.{i % 200}")
        for i in range(1, 11)
    ]
    block = format_evidence_map(records, max_rows=3)
    parsed = parse_evidence_map(block)
    assert len(parsed) == 3
    assert "additional evidence records omitted" in block


def test_evidence_map_char_cap_truncates_long_text():
    long_text = "x" * 1000 + " 203.0.113.9"
    records = [EvidenceRecord("EV-000001", "big.log", 1, long_text)]
    block = format_evidence_map(records)
    parsed = parse_evidence_map(block)
    assert len(parsed["EV-000001"].text) <= 244  # 240 + ellipsis


def test_parse_evidence_map_skips_malformed_rows():
    block = (
        "```EVIDENCE_MAP\n"
        "EV-000001\tauth.log\t5\tgood row 203.0.113.4\n"
        "this is not a valid row\n"
        "```"
    )
    parsed = parse_evidence_map(block)
    assert list(parsed.keys()) == ["EV-000001"]


def test_strip_evidence_map_removes_block():
    text = "Narrative line.\n```EVIDENCE_MAP\nEV-000001\tf.log\t1\tx\n```\nMore."
    stripped = strip_evidence_map(text)
    assert "EVIDENCE_MAP" not in stripped
    assert "Narrative line." in stripped
    assert "More." in stripped


def test_parse_cited_ids_finds_all_references():
    text = "Attacker used EV-000004 and pivoted (EV-000009); see also EV-000004."
    assert parse_cited_ids(text) == {"EV-000004", "EV-000009"}


# ── IoC-shape detection (case-agnostic) ──────────────────────────
@pytest.mark.parametrize(
    "line",
    [
        "Outbound beacon to 203.0.113.55",
        "Hash observed d41d8cd98f00b204e9800998ecf8427e",
        "Exploited CVE-2026-12345 on host",
        "Callback to updates.malicious-example.biz",
        "Logon as CORP\\svc_worker",
        "Federated token for user@example.org",
    ],
)
def test_line_has_ioc_true_for_concrete_tokens(line):
    assert line_has_ioc(line)


@pytest.mark.parametrize(
    "line",
    [
        "The attacker escalated privileges quickly.",
        "Severity assessed as HIGH.",
        "See EV-000123 for details.",  # an EV id alone is not an IoC
    ],
)
def test_line_has_ioc_false_for_prose(line):
    assert not line_has_ioc(line)


def test_ev_id_not_counted_as_ioc_token():
    tokens = extract_ioc_tokens("Reference EV-000042 only")
    assert tokens == set()


def test_domain_folded_into_account_not_double_counted():
    tokens = extract_ioc_tokens("Token for admin@corp.example.com issued")
    # the email is captured; the bare realm should not appear separately
    assert "admin@corp.example.com" in tokens
    assert "corp.example.com" not in tokens


# ── verification ─────────────────────────────────────────────────
def _evidence_map():
    return parse_evidence_map(
        format_evidence_map(
            [
                EvidenceRecord("EV-000001", "auth.log", 5, "login from 203.0.113.7"),
                EvidenceRecord("EV-000002", "proxy.log", 9, "beacon to 198.51.100.23"),
            ]
        )
    )


def test_verify_citations_pass_when_all_grounded_and_cited():
    report = (
        "## Findings\n"
        "Initial access from 203.0.113.7 [EV-000001].\n"
        "C2 beacon to 198.51.100.23 [EV-000002].\n"
    )
    result = verify_citations(report, _evidence_map())
    assert result.verdict == "pass"
    assert result.missing_ids == []
    assert result.coverage == 1.0


def test_verify_citations_fail_on_fabricated_id():
    report = "Beacon to 198.51.100.23 [EV-000999]."
    result = verify_citations(report, _evidence_map())
    assert result.verdict == "fail"
    assert "EV-000999" in result.missing_ids


def test_verify_citations_warn_on_uncited_claim():
    report = (
        "Initial access from 203.0.113.7 [EV-000001].\n"
        "Lateral movement to 198.51.100.23 with no citation.\n"
    )
    result = verify_citations(report, _evidence_map())
    assert result.verdict == "warn"
    assert result.uncited_claim_lines
    assert result.coverage < 1.0


def test_verify_citations_ignores_headers_and_tables():
    report = (
        "# Executive Summary\n"
        "| Column | Value |\n"
        "| :--- | :--- |\n"
        "Threat actor used 203.0.113.7 [EV-000001].\n"
    )
    result = verify_citations(report, _evidence_map())
    # only the one concrete claim line counts, and it is cited
    assert result.coverage == 1.0
    assert result.verdict == "pass"


def test_format_verification_table_lists_grounded_and_missing():
    report = "Access 203.0.113.7 [EV-000001]; beacon 198.51.100.23 [EV-000777]."
    emap = _evidence_map()
    result = verify_citations(report, emap)
    table = format_verification_table(report, emap, result)
    assert "## 🔍 Evidence Verification" in table
    assert "EV-000001" in table
    assert "grounded" in table
    assert "EV-000777" in table
    assert "MISSING" in table


# ── verify_investigation_report activity ─────────────────────────
@pytest.mark.asyncio
async def test_verify_investigation_report_skips_without_map():
    from src.orchestrator.activities import verify_investigation_report

    report = "No evidence map anywhere here."
    out = await verify_investigation_report(report, {"t1": "plain prose"})
    assert out["verdict"] == "skipped"
    assert out["report"] == report


@pytest.mark.asyncio
async def test_verify_investigation_report_annotates_and_grounds():
    from src.orchestrator.activities import verify_investigation_report

    t1_output = "Ingested logs.\n" + format_evidence_map(
        [
            EvidenceRecord("EV-000001", "auth.log", 5, "login from 203.0.113.7"),
            EvidenceRecord("EV-000002", "proxy.log", 9, "beacon to 198.51.100.23"),
        ]
    )
    report = (
        "Initial access from 203.0.113.7 [EV-000001].\n"
        "C2 beacon to 198.51.100.23 [EV-000002].\n"
    )
    out = await verify_investigation_report(report, {"t1": t1_output})
    assert out["verdict"] == "pass"
    assert out["grounded"] == 2
    assert out["missing"] == []
    assert "🔍 Evidence Verification" in out["report"]


@pytest.mark.asyncio
async def test_verify_investigation_report_flags_fabricated_id():
    from src.orchestrator.activities import verify_investigation_report

    t1_output = format_evidence_map(
        [EvidenceRecord("EV-000001", "auth.log", 5, "login from 203.0.113.7")]
    )
    report = "Beacon to 198.51.100.23 [EV-000404]."
    out = await verify_investigation_report(report, {"t1": t1_output})
    assert out["verdict"] == "fail"
    assert "EV-000404" in out["missing"]


# ── supervisor citation-coverage gate ────────────────────────────
def test_citation_coverage_full_when_all_cited():
    from src.orchestrator.activities import citation_coverage

    text = (
        "Access from 203.0.113.7 [EV-000001].\n"
        "Beacon to 198.51.100.23 [EV-000002].\n"
    )
    total, cited, coverage = citation_coverage(text)
    assert total == 2
    assert cited == 2
    assert coverage == 1.0


def test_citation_coverage_low_when_uncited():
    from src.orchestrator.activities import citation_coverage

    text = (
        "Access from 203.0.113.7 [EV-000001].\n"
        "Beacon to 198.51.100.23 no citation.\n"
        "Lateral move to 203.0.113.9 also uncited.\n"
    )
    total, cited, coverage = citation_coverage(text)
    assert total == 3
    assert cited == 1
    assert coverage < 0.5


def test_citation_coverage_excludes_evidence_map_rows():
    from src.orchestrator.activities import citation_coverage

    # Raw IoCs inside the EVIDENCE_MAP block must not be counted as uncited claims.
    text = "No claims here.\n" + format_evidence_map(
        [EvidenceRecord("EV-000001", "auth.log", 5, "login from 203.0.113.7")]
    )
    total, cited, coverage = citation_coverage(text)
    assert total == 0
    assert coverage == 1.0
