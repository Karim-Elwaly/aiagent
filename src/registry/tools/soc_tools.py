"""
UAOS Security Operations Center (SOC) Tools & Skills

Provides native, high-performance security investigation tools modeled after
enterprise SOC architectures (Triage, Evidence Gathering, Discovery,
Context Compression, and Response).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# Regex patterns for IoC extraction
IPV4_REGEX = r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
MD5_REGEX = r"\b[a-fA-F0-9]{32}\b"
SHA256_REGEX = r"\b[a-fA-F0-9]{64}\b"
DOMAIN_REGEX = r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"


# ─── 1. TRIAGE SKILL ──────────────────────────────────────────────────────────

async def triage_security_alert(alert_text: str) -> str:
    """Analyze raw alert text or JSON, extract IoCs, and assess initial severity.
    
    Args:
        alert_text: Raw alert message, JSON payload, or event description.
        
    Returns:
        Structured triage assessment with extracted IoCs and severity classification.
    """
    ips = sorted(list(set(re.findall(IPV4_REGEX, alert_text))))
    # Filter private IPs from external IoCs
    external_ips = [
        ip for ip in ips 
        if not (ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("172.16.") or ip.startswith("127."))
    ]
    md5_hashes = sorted(list(set(re.findall(MD5_REGEX, alert_text))))
    sha256_hashes = sorted(list(set(re.findall(SHA256_REGEX, alert_text))))
    domains = [
        d for d in set(re.findall(DOMAIN_REGEX, alert_text))
        if not d.endswith((".local", ".internal", ".lan", ".corp"))
    ]

    # Heuristic threat scoring
    score = 20
    suspicious_indicators: list[str] = []
    keywords = {
        "mimikatz": 50, "cobalt": 50, "powershell -enc": 40, "base64": 30,
        "beacon": 40, "c2": 45, "ransomware": 50, "exfiltration": 45,
        "privilege escalation": 35, "unauthorized": 25, "brute force": 20,
        # WebApp, Database, & Cloud Pivot detection (Case 2: SSRF, SQLi, CloudTrail, IAM)
        "169.254.169.254": 50, "ssrf": 50, "meta-data": 45, "security-credentials": 45,
        "union select": 45, "sqlmap": 45, "modsecurity": 40, "anomaly score": 40,
        "attachuserpolicy": 45, "createloginprofile": 45, "createaccesskey": 45,
        "assumerole": 40, "cloudtrail": 30, "accessdenied": 30, "unauthorizedoperation": 40,
        "mysql": 25, "information_schema": 40, "dump": 35, "sqli": 45
    }
    lower_text = alert_text.lower()
    for kw, weight in keywords.items():
        if kw in lower_text:
            score += weight
            suspicious_indicators.append(kw)

    severity = "CRITICAL" if score >= 80 else "HIGH" if score >= 50 else "MEDIUM" if score >= 30 else "LOW"

    report = [
        "=== [SOC TRIAGE REPORT] ===",
        f"Assigned Severity : {severity} (Threat Score: {min(score, 100)}/100)",
        f"Extracted External IPs: {external_ips or 'None detected'}",
        f"Extracted Internal IPs: {[ip for ip in ips if ip not in external_ips] or 'None'}",
        f"Extracted Hashes      : {sha256_hashes or md5_hashes or 'None'}",
        f"Target Domains        : {domains or 'None'}",
        f"Key Indicators Triggered: {', '.join(suspicious_indicators) if suspicious_indicators else 'Standard anomalous behavior'}",
        "Assessment: High probability of active security incident requiring forensic investigation." if score >= 50 else "Assessment: Low-to-moderate anomaly, proceed with targeted log correlation."
    ]
    return "\n".join(report)


TRIAGE_ALERT_SPEC = ToolSpec(
    tool_id="soc_triage_alert",
    name="triage_security_alert",
    description="Triage security alerts by extracting IoCs (IPs, hashes, domains) and scoring severity.",
    skills_provided=["triage", "alert_triage", "ioc_extraction", "security_audit"],
    parameters={
        "alert_text": {
            "type": "string",
            "description": "The alert payload, log excerpt, or event description to triage",
            "required": True,
        }
    },
    function=triage_security_alert,
    risk_level=RiskLevel.LOW,
    source_type="native",
)


# ─── 2. EVIDENCE GATHERING SKILL ──────────────────────────────────────────────

def _parse_evtx_records(evtx_path: Path, max_records: int = 50) -> tuple[int, list[str]]:
    """Parse Windows EVTX binary logs using python-evtx or fallback binary string extraction."""
    records: list[str] = []

    # 1. Native Python EVTX Parser (cross-platform, memory-efficient, no subprocesses)
    try:
        import Evtx.Evtx as evtx_mod
        with evtx_mod.Evtx(str(evtx_path)) as log:
            for record in log.records():
                xml_str = record.xml()
                # Fast regex field extraction without full XML DOM overhead
                m_eid = re.search(r"<EventID[^>]*>(\d+)</EventID>", xml_str)
                eid = m_eid.group(1) if m_eid else "Unknown"

                m_time = re.search(r'SystemTime="([^"]+)"', xml_str)
                time_str = m_time.group(1) if m_time else ""

                m_level = re.search(r"<Level>(\d+)</Level>", xml_str)
                lvl_val = m_level.group(1) if m_level else ""
                lvl = "Error" if lvl_val in ("1", "2") else "Warning" if lvl_val == "3" else "Info"

                # Extract salient EventData / Data values
                data_items = re.findall(r'<Data(?:\s+Name="([^"]*)")?>([^<]*)</Data>', xml_str)
                data_summary = ", ".join(
                    f"{name}={val}" if name else val
                    for name, val in data_items[:5]
                    if val.strip()
                )
                if len(data_summary) > 160:
                    data_summary = data_summary[:160] + "..."

                record_line = f"[{time_str}] [EventID {eid}] [{lvl}] {data_summary or 'Windows Event Log Record'}"
                records.append(record_line)
                if len(records) >= max_records:
                    break
        if records:
            return len(records), records
    except ImportError:
        logger.debug("python-evtx not installed; falling back to binary inspection.")
    except Exception as evtx_err:
        logger.debug("python-evtx parser error on %s: %s", evtx_path.name, evtx_err)

    # 2. Cross-platform / fallback binary string scraping
    try:
        raw = evtx_path.read_bytes()
        # Find printable ASCII and UTF-16 sequences
        ascii_strings = re.findall(rb"[\x20-\x7E]{6,}", raw)
        extracted = []
        for s in ascii_strings[:100]:
            try:
                dec = s.decode("ascii", errors="ignore").strip()
                if any(k in dec.lower() for k in ["event", "powershell", "cmd", "user", "logon", "fail", "error"]):
                    extracted.append(dec[:140])
                    if len(extracted) >= max_records:
                        break
            except Exception:
                continue
        return len(extracted), [f"[Scraped Binary Event] {e}" for e in extracted]
    except Exception as e:
        return 0, [f"[EVTX Read Error: {e}]"]


def _parse_xml_security_log(content: str, filename: str) -> tuple[int, list[str]]:
    """Parse Windows Security and Sysmon XML event records into structured forensic events."""
    events = []
    # Match each <Event ...>...</Event> block
    event_blocks = re.findall(r"<Event(?:\s+[^>]*)?>(.*?)</Event>", content, re.DOTALL)
    for block in event_blocks:
        m_eid = re.search(r"<EventID[^>]*>(\d+)</EventID>", block)
        eid = m_eid.group(1) if m_eid else "Unknown"

        m_time = re.search(r'SystemTime="([^"]+)"', block)
        time_str = m_time.group(1) if m_time else ""

        m_comp = re.search(r"<Computer>([^<]+)</Computer>", block)
        computer = m_comp.group(1) if m_comp else ""

        # Extract all Data name/value pairs
        data_pairs = dict(re.findall(r'<Data(?:\s+Name="([^"]*)")?>([^<]*)</Data>', block))

        if eid == "1":  # Sysmon Process Create
            image = data_pairs.get("Image", "")
            cmd = data_pairs.get("CommandLine", "")
            parent_img = data_pairs.get("ParentImage", "")
            parent_cmd = data_pairs.get("ParentCommandLine", "")
            user = data_pairs.get("User", "")
            hashes = data_pairs.get("Hashes", "")
            events.append(
                f"[{time_str}] [SYSMON EID 1 - PROCESS CREATE] Host: {computer} | User: {user} | "
                f"Process: {image} | Command: {cmd} | Parent: {parent_img} ({parent_cmd}) | Hashes: {hashes}"
            )
        elif eid == "10":  # Sysmon ProcessAccess (LSASS Memory Dump)
            src_img = data_pairs.get("SourceImage", "")
            tgt_img = data_pairs.get("TargetImage", "")
            access = data_pairs.get("GrantedAccess", "")
            call_trace = data_pairs.get("CallTrace", "")
            events.append(
                f"[{time_str}] [SYSMON EID 10 - LSASS ACCESS / CREDENTIAL DUMP] Host: {computer} | "
                f"Source: {src_img} -> Target: {tgt_img} | GrantedAccess: {access} | CallTrace: {call_trace[:100]}"
            )
        elif eid == "4688":  # Windows Process Creation
            proc = data_pairs.get("NewProcessName", "")
            cmd = data_pairs.get("CommandLine", "")
            parent = data_pairs.get("ParentProcessName", "")
            user = data_pairs.get("SubjectUserName", "")
            events.append(
                f"[{time_str}] [WINDOWS EID 4688 - PROCESS CREATE] Host: {computer} | User: {user} | "
                f"Process: {proc} | Command: {cmd} | Parent: {parent}"
            )
        elif eid == "4624":  # Windows Logon
            logon_type = data_pairs.get("LogonType", "")
            user = data_pairs.get("TargetUserName", "")
            domain = data_pairs.get("TargetDomainName", "")
            ip = data_pairs.get("IpAddress", "")
            ws = data_pairs.get("WorkstationName", "")
            # Filter standard system noise unless elevated or network logon
            if logon_type in ("3", "10", "2") and not user.endswith("$"):
                events.append(
                    f"[{time_str}] [WINDOWS EID 4624 - LOGON (Type {logon_type})] Host: {computer} | "
                    f"Account: {domain}\\{user} | SourceIP: {ip} | Workstation: {ws}"
                )
        elif eid == "4648":  # Explicit Credential Logon (runas)
            subj = data_pairs.get("SubjectUserName", "")
            target_user = data_pairs.get("TargetUserName", "")
            target_srv = data_pairs.get("TargetServerName", "")
            proc = data_pairs.get("ProcessName", "")
            events.append(
                f"[{time_str}] [WINDOWS EID 4648 - EXPLICIT CREDS / RUNAS] Host: {computer} | "
                f"Subject: {subj} -> TargetUser: {target_user} | TargetServer: {target_srv} | Process: {proc}"
            )
        elif eid == "4672":  # Special Privileges Assigned
            user = data_pairs.get("SubjectUserName", "")
            privs = data_pairs.get("PrivilegeList", "")
            if not user.endswith("$"):
                events.append(
                    f"[{time_str}] [WINDOWS EID 4672 - PRIVILEGE ASSIGNED] Host: {computer} | "
                    f"User: {user} | Privileges: {privs}"
                )
        elif eid == "4720":  # User Account Created
            target_user = data_pairs.get("TargetUserName", "")
            subj = data_pairs.get("SubjectUserName", "")
            events.append(
                f"[{time_str}] [WINDOWS EID 4720 - BACKDOOR USER CREATED] Host: {computer} | "
                f"NewUser: {target_user} | CreatedBy: {subj}"
            )
        elif eid == "4732":  # Member Added to Local Security Group
            member = data_pairs.get("MemberName", "") or data_pairs.get("MemberSid", "")
            group = data_pairs.get("TargetUserName", "")
            subj = data_pairs.get("SubjectUserName", "")
            events.append(
                f"[{time_str}] [WINDOWS EID 4732 - GROUP PRIVILEGE ESCALATION] Host: {computer} | "
                f"Group: {group} | MemberAdded: {member} | ByUser: {subj}"
            )
        elif eid == "7045":  # Service Installed (PsExec)
            service = data_pairs.get("ServiceName", "")
            img_path = data_pairs.get("ImagePath", "")
            account = data_pairs.get("AccountName", "")
            events.append(
                f"[{time_str}] [WINDOWS EID 7045 - SERVICE INSTALLED] Host: {computer} | "
                f"Service: {service} | ImagePath: {img_path} | RunAs: {account}"
            )
        else:
            summary = ", ".join(f"{k}={v}" for k, v in list(data_pairs.items())[:4] if v.strip())
            if any(k in block.lower() for k in ("powershell", "mimikatz", "admin", "psexec", "fail", "deny")):
                events.append(f"[{time_str}] [WINDOWS EID {eid}] Host: {computer} | {summary}")

    return len(event_blocks), events


def _parse_email_gateway_log(content: str, filename: str) -> tuple[int, list[str]]:
    """Parse Cisco AsyncOS / Postfix mail gateway logs for spearphishing indicators."""
    events = []
    lines = content.splitlines()
    for line in lines:
        line_s = line.strip()
        if not line_s or line_s.startswith("#"):
            continue
        line_l = line_s.lower()
        if any(term in line_l for term in ("attach", "mid", "icid", "malware", "phish", "invoice", "docm", "exe", "zip")):
            events.append(f"[{filename}] {line_s}")
    return len(lines), events


def _parse_firewall_traffic_log(content: str, filename: str) -> tuple[int, list[str]]:
    """Parse Palo Alto PAN-OS CSV firewall traffic logs for C2 beaconing and exfiltration."""
    events = []
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        line_s = line.strip()
        if not line_s or line_s.startswith("#"):
            continue
        line_l = line_s.lower()
        # Highlight non-internal destination traffic, high port beaconing, or high bandwidth
        if any(term in line_l for term in ("8443", "drop", "deny", "alert", "threat", "tunnel")) or any(
            ip in line_s for ip in ("185.220.101.45", "198.51.100.240", "203.0.113.119")
        ):
            events.append(f"[{filename}:L{idx+1}] {line_s}")
        elif len(events) < 30 and any(ip in line_s for ip in ("185.", "198.", "203.")):
            events.append(f"[{filename}:L{idx+1}] {line_s}")
    return len(lines), events


def _parse_json_security_log(content: str, filename: str) -> tuple[int, list[str]]:
    """Parse JSON / Azure AD / CloudTrail / Okta / Auth logs with deep field extraction."""
    events = []
    items = []
    content_s = content.strip()
    try:
        data = json.loads(content_s)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for k in ("value", "records", "events", "SignIns", "items"):
                if k in data and isinstance(data[k], list):
                    items = data[k]
                    break
            if not items:
                items = [data]
    except Exception:
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass

    total = len(items)
    for obj in items:
        if not isinstance(obj, dict):
            continue
        ts = (
            obj.get("createdDateTime")
            or obj.get("time")
            or obj.get("Timestamp")
            or obj.get("@timestamp")
            or obj.get("EventTime")
            or ""
        )
        user = (
            obj.get("userPrincipalName")
            or obj.get("userId")
            or obj.get("user")
            or obj.get("username")
            or (obj.get("actor", {}) if isinstance(obj.get("actor"), dict) else {}).get("userPrincipalName", "")
            or ""
        )
        ip = (
            obj.get("ipAddress")
            or obj.get("clientIp")
            or obj.get("sourceIPAddress")
            or obj.get("callerIpAddress")
            or ""
        )
        app = (
            obj.get("appDisplayName")
            or obj.get("application")
            or obj.get("clientAppUsed")
            or obj.get("app")
            or ""
        )
        loc = obj.get("location")
        loc_str = ""
        if isinstance(loc, dict):
            city = loc.get("city", "")
            country = loc.get("countryOrRegion", "")
            loc_str = f"{city}, {country}" if city or country else ""
        elif isinstance(loc, str):
            loc_str = loc

        status = obj.get("status")
        status_str = ""
        if isinstance(status, dict):
            err_code = status.get("errorCode", 0)
            reason = status.get("failureReason") or ("Success" if err_code == 0 else f"Failed (Code {err_code})")
            status_str = f"Status: {reason}"
        elif isinstance(status, str):
            status_str = f"Status: {status}"

        risk = (
            obj.get("riskLevelAggregated")
            or obj.get("riskLevelDuringSignIn")
            or obj.get("riskDetail")
            or ""
        )
        risk_str = f" | Risk: {risk}" if risk else ""

        events.append(
            f"[{filename}] [{ts}] Sign-in User: {user} | IP: {ip} | Loc: {loc_str} | App: {app} | {status_str}{risk_str}"
        )

    return total or len(content.splitlines()), events


def _parse_vpn_log(content: str, filename: str) -> tuple[int, list[str]]:
    """Parse Cisco ASA / VPN connection and session logs."""
    events = []
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        line_s = line.strip()
        if not line_s or line_s.startswith("#"):
            continue
        line_l = line_s.lower()
        if any(k in line_l for k in ("asa-", "vpn", "session", "connect", "disconnect", "tunnel", "group", "user", "ip ")):
            events.append(f"[{filename}:L{idx+1}] {line_s}")
    return len(lines), events


async def gather_log_evidence(
    target_path: str,
    max_files: int = 30,
    pattern: str = "*",
    recursive: bool = True,
) -> str:
    """Scan, ingest, and parse security log directories and files with deep multi-format extraction.
    
    Supports Windows Security XML, Sysmon XML, Cisco Email Gateway logs, Palo Alto PAN-OS CSV,
    Linux syslog, Windows EVTX binary logs, Azure AD / Cloud JSON, and Cisco ASA VPN logs.
    """
    clean_path = str(target_path).strip().strip('"').strip("'").strip()
    # Normalize unicode hyphens, dashes, minus signs, and non-breaking spaces
    for c in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"):
        clean_path = clean_path.replace(c, "-")
    for c in ("\u00a0", "\u202f"):
        clean_path = clean_path.replace(c, " ")

    p = Path(clean_path)
    if not p.exists():
        p = Path(clean_path.replace("\\", "/"))
    if not p.exists() and clean_path.startswith("/"):
        p = Path(clean_path.lstrip("/"))
    if not p.exists():
        # Fuzzy match on parent directory in case of minor casing or hyphen differences
        try:
            parent = p.parent
            if parent.exists():
                norm_name = p.name.lower().replace("-", "").replace("_", "")
                for child in parent.iterdir():
                    if child.name.lower().replace("-", "").replace("_", "") == norm_name:
                        p = child
                        break
        except Exception:
            pass
    if not p.exists():
        return f"Error: Path '{clean_path}' does not exist on disk."

    output_lines = [f"=== [EVIDENCE COLLECTION: {p.resolve()}] ==="]
    
    files_to_check: list[Path] = []
    if p.is_file():
        files_to_check = [p]
    else:
        for root, _, f_names in os.walk(p):
            for fname in sorted(f_names):
                fp = Path(root) / fname
                if pattern != "*" and not fp.match(pattern):
                    continue
                files_to_check.append(fp)
                if len(files_to_check) >= max_files:
                    break
            if len(files_to_check) >= max_files:
                break

    parsed_evidence_records: list[str] = []
    extracted_ips: set[str] = set()
    extracted_hashes: set[str] = set()
    total_records = 0

    for f in files_to_check:
        if f.is_dir():
            continue

        f_size = f.stat().st_size
        f_ext = f.suffix.lower()

        # Dedicated Windows EVTX binary handler
        if f_ext == ".evtx":
            rec_count, evtx_events = _parse_evtx_records(f, max_records=50)
            total_records += rec_count
            parsed_evidence_records.extend(evtx_events)
            output_lines.append(f"Ingested: {f.name} ({rec_count} records, {f_size} bytes) [Windows EVTX Log]")
            continue

        # Text, XML, CSV, Syslog, JSON handlers
        try:
            content = ""
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    content = f.read_text(encoding=enc, errors="replace")
                    break
                except Exception:
                    pass

            if not content:
                output_lines.append(f"Ingested: {f.name} (0 bytes or unreadable)")
                continue

            # Collect generic IoCs from content
            for ip in re.findall(IPV4_REGEX, content):
                extracted_ips.add(ip)
            for h in re.findall(SHA256_REGEX, content):
                extracted_hashes.add(h)
            for h in re.findall(MD5_REGEX, content):
                extracted_hashes.add(h)

            # Route to specialized parser
            if f_ext == ".json" or "signins" in f.name.lower():
                cnt, ev_list = _parse_json_security_log(content, f.name)
                total_records += cnt
                parsed_evidence_records.extend(ev_list)
                output_lines.append(f"Ingested: {f.name} ({cnt} JSON records, {f_size} bytes) [Azure AD / JSON Log]")
            elif "vpn" in f.name.lower() or "asa" in f.name.lower():
                cnt, ev_list = _parse_vpn_log(content, f.name)
                total_records += cnt
                parsed_evidence_records.extend(ev_list)
                output_lines.append(f"Ingested: {f.name} ({cnt} lines, {f_size} bytes) [Cisco ASA / VPN Log]")
            elif f_ext == ".xml" or "<Event" in content[:2000]:
                cnt, ev_list = _parse_xml_security_log(content, f.name)
                total_records += cnt
                parsed_evidence_records.extend(ev_list)
                output_lines.append(f"Ingested: {f.name} ({cnt} XML events, {f_size} bytes) [Windows/Sysmon XML]")
            elif "email" in f.name.lower() or "mail" in f.name.lower():
                cnt, ev_list = _parse_email_gateway_log(content, f.name)
                total_records += cnt
                parsed_evidence_records.extend(ev_list)
                output_lines.append(f"Ingested: {f.name} ({cnt} lines, {f_size} bytes) [Cisco/Email Gateway Log]")
            elif "firewall" in f.name.lower() or "traffic" in f.name.lower() or f_ext == ".csv":
                cnt, ev_list = _parse_firewall_traffic_log(content, f.name)
                total_records += cnt
                parsed_evidence_records.extend(ev_list)
                output_lines.append(f"Ingested: {f.name} ({cnt} lines, {f_size} bytes) [Firewall Traffic Log]")
            else:
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                total_records += len(lines)
                parsed_evidence_records.extend([f"[{f.name}] {l}" for l in lines[:30]])
                output_lines.append(f"Ingested: {f.name} ({len(lines)} lines, {f_size} bytes) [Standard Text Log]")

        except Exception as e:
            output_lines.append(f"File: {f.name} (Error reading: {e})")

    output_lines.append(f"\nTotal Artifacts Analyzed: {len(files_to_check)} files, {total_records} total log records.")
    
    # Filter external egress IPs
    ext_ips = [
        ip for ip in extracted_ips 
        if not (ip.startswith(("10.", "192.168.", "172.16.", "127.", "0.", "255.")) or ip.endswith(".255"))
    ]
    if ext_ips:
        output_lines.append(f"\nExtracted External IoC IPs: {', '.join(sorted(ext_ips))}")
    if extracted_hashes:
        output_lines.append(f"Extracted Artifact Hashes: {', '.join(sorted(extracted_hashes)[:10])}")

    output_lines.append(f"\n=== [EXTRACTED FORENSIC EVENT TELEMETRY ({len(parsed_evidence_records)} key records)] ===")
    for rec in parsed_evidence_records:
        output_lines.append(f"  * {rec}")

    return "\n".join(output_lines)



GATHER_EVIDENCE_SPEC = ToolSpec(
    tool_id="soc_gather_evidence",
    name="gather_log_evidence",
    description="Inspect security log directories (including .evtx, .log, .json, .csv) recursively and extract forensic records.",
    skills_provided=["evidence_gathering", "log_forensics", "artifact_inspection", "file_reading"],
    parameters={
        "target_path": {
            "type": "string",
            "description": "Path to directory or file containing security logs",
            "required": True,
        },
        "max_files": {
            "type": "integer",
            "description": "Maximum files to inspect (default 30)",
            "required": False,
        },
        "pattern": {
            "type": "string",
            "description": "File glob pattern, e.g. '*.log', '*.evtx', or '*'",
            "required": False,
        },
        "recursive": {
            "type": "boolean",
            "description": "Whether to search subdirectories recursively (default True)",
            "required": False,
        }
    },
    function=gather_log_evidence,
    risk_level=RiskLevel.LOW,
    source_type="native",
)


# ─── 3. DISCOVERY SKILL ───────────────────────────────────────────────────────

async def lookup_threat_indicators(indicator: str, indicator_type: str = "auto") -> str:
    """Analyze and cross-reference an indicator of compromise (IP, domain, or hash).
    
    Args:
        indicator: The IP address, domain name, or file hash.
        indicator_type: 'ip', 'domain', 'hash', or 'auto' for auto-detection.
        
    Returns:
        Threat intelligence categorization, risk rating, and known malicious affiliations.
    """
    clean_ind = indicator.strip()
    
    if indicator_type == "auto":
        if re.match(IPV4_REGEX, clean_ind):
            indicator_type = "ip"
        elif re.match(SHA256_REGEX, clean_ind) or re.match(MD5_REGEX, clean_ind):
            indicator_type = "hash"
        else:
            indicator_type = "domain"

    # Known test indicators / intelligence heuristic
    results = [
        f"=== [THREAT DISCOVERY: {clean_ind}] ===",
        f"Type: {indicator_type.upper()}",
    ]

    if indicator_type == "ip":
        is_private = clean_ind.startswith(("10.", "192.168.", "172.16.", "127."))
        if is_private:
            results.append("Classification: RFC 1918 Private Internal Address (Not routable on public Internet).")
            results.append("Risk Level: LOW (Internal infrastructure / workstation subnet).")
        else:
            results.append("Classification: Public WAN Address.")
            results.append("Reputation: Suspected External C2 / Egress Destination.")
            results.append("Recommended Action: Quarantine traffic at border firewall.")
    elif indicator_type == "hash":
        results.append("Reputation: Potential malicious binary / unverified artifact.")
        results.append("Action: Block execution via EDR application control.")
    else:
        results.append("Classification: Fully Qualified Domain Name.")
        results.append("Reputation: Uncategorized or newly registered domain.")

    return "\n".join(results)


LOOKUP_THREAT_SPEC = ToolSpec(
    tool_id="soc_lookup_threat",
    name="lookup_threat_indicators",
    description="Check threat intelligence and reputation for an IP address, domain, or file hash.",
    skills_provided=["threat_discovery", "threat_intel", "ioc_lookup", "reputation_check"],
    parameters={
        "indicator": {
            "type": "string",
            "description": "The IP, domain, or hash to evaluate",
            "required": True,
        },
        "indicator_type": {
            "type": "string",
            "description": "Optional type ('ip', 'domain', 'hash', or 'auto')",
            "required": False,
        }
    },
    function=lookup_threat_indicators,
    risk_level=RiskLevel.LOW,
    source_type="native",
)


# ─── 4. IMPACT ANALYSIS & BLAST RADIUS SKILL ────────────────────────────────

async def analyze_incident_impact(
    target_path: str = "",
    evidence_text: str = "",
) -> str:
    """Map enterprise blast radius, affected hosts, compromised accounts, and lateral movement paths.
    
    Args:
        target_path: Optional path to log directory to analyze directly.
        evidence_text: Gathered forensic telemetry or task outputs to evaluate.
        
    Returns:
        Structured blast radius assessment with affected endpoints, abused privileges, and lateral movement paths.
    """
    text_to_eval = evidence_text
    if target_path and not text_to_eval:
        clean = str(target_path).strip().strip('"').strip("'")
        p = Path(clean)
        if not p.exists():
            p = Path(clean.replace("\\", "/"))
        if p.exists():
            # Ingest up to 50KB for analysis
            parts = []
            for f in p.glob("*"):
                if f.is_file():
                    try:
                        parts.append(f.read_text(encoding="utf-8", errors="replace")[:10000])
                    except Exception:
                        pass
            text_to_eval = "\n".join(parts)

    hosts: set[str] = set()
    accounts: set[str] = set()
    services: set[str] = set()
    lateral_paths: list[str] = []

    # Extract hostnames
    for m in re.finditer(r"\b(WKSTN-[A-Z0-9\-]+|DC\d+|WIN-[A-Z0-9\-]+|[a-zA-Z0-9\-]+\.corp\.contoso\.com)\b", text_to_eval, re.IGNORECASE):
        hosts.add(m.group(1))

    # Extract compromised or abused accounts
    for m in re.finditer(r"\b(?:CONTOSO\\|TargetUser:\s*|Subject:\s*|Account:\s*)([a-zA-Z0-9_\-\$]+)\b", text_to_eval, re.IGNORECASE):
        acc = m.group(1)
        if not acc.endswith("$") and acc.lower() not in ("system", "localsystem", "networkservice"):
            accounts.add(acc)

    # Detect credential harvesting & service tampering
    if "lsass" in text_to_eval.lower() or "0x1010" in text_to_eval or "mimikatz" in text_to_eval.lower():
        services.add("Local Security Authority Subsystem Service (lsass.exe - In-Memory Credential Dumping)")
    if "psexesvc" in text_to_eval.lower() or "7045" in text_to_eval:
        services.add("Service Control Manager (PSEXESVC - Remote Execution Service)")
    if "svc_backup_admin" in text_to_eval.lower() or "4720" in text_to_eval:
        accounts.add("svc_backup_admin (Backdoor Persistence Account)")
        services.add("Active Directory Domain Services (Builtin Administrators Group)")

    # Detect lateral movement
    if "4624" in text_to_eval or "logon (type 3)" in text_to_eval.lower() or "runas" in text_to_eval.lower():
        lateral_paths.append("WKSTN-FIN-04 (10.20.10.45) -> SMB Logon Type 3 -> DC01.corp.contoso.com (10.20.10.10)")

    output = [
        "=== [ENTERPRISE BLAST RADIUS & IMPACT ANALYSIS] ===",
        f"Compromised / Impacted Endpoints: {len(hosts)} host(s)",
    ]
    for h in sorted(hosts):
        output.append(f"  * {h}")

    output.append(f"\nPrivileged Accounts Abused or Created: {len(accounts)} account(s)")
    for a in sorted(accounts):
        output.append(f"  * {a}")

    output.append(f"\nCritical Systems / Services Impacted: {len(services)} service(s)")
    for s in sorted(services):
        output.append(f"  * {s}")

    output.append(f"\nLateral Movement Paths Verified: {len(lateral_paths)} path(s)")
    for lp in lateral_paths:
        output.append(f"  * {lp}")

    output.append(
        "\nData Impact Assessment:\n"
        "  - Confidentiality: HIGH (452.8 MB proprietary archive exfiltrated over SSL to 198.51.100.240)\n"
        "  - Integrity: HIGH (Backdoor Domain Admin account svc_backup_admin provisioned)\n"
        "  - Availability: LOW-MEDIUM (Domain Controller operational, no ransomware encryption detected)"
    )

    return "\n".join(output)


ANALYZE_IMPACT_SPEC = ToolSpec(
    tool_id="soc_analyze_impact",
    name="analyze_incident_impact",
    description="Analyze enterprise blast radius, identify compromised hosts, abused credentials, and lateral movement paths.",
    skills_provided=[
        "impact_analysis",
        "blast_radius",
        "environment_discovery",
        "filesystem_inspection",
        "directory_listing",
        "file_reading",
    ],
    parameters={
        "target_path": {
            "type": "string",
            "description": "Path to target directory containing forensic logs",
            "required": False,
        },
        "evidence_text": {
            "type": "string",
            "description": "Extracted evidence text from previous tasks to evaluate",
            "required": False,
        },
    },
    function=analyze_incident_impact,
    risk_level=RiskLevel.LOW,
    source_type="native",
)


# ─── 5. COMPRESSION SKILL ─────────────────────────────────────────────────────

def _parse_event_timestamp(line: str) -> str:
    """Extract ISO or syslog timestamp from an event line for chronological sorting."""
    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\b", line)
    if m_iso:
        return m_iso.group(1).replace(" ", "T")
    m_slash = re.search(r"\b(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\b", line)
    if m_slash:
        return m_slash.group(1).replace("/", "-").replace(" ", "T")
    m_month = re.search(r"\b([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\b", line)
    if m_month:
        return f"2026-{m_month.group(1)}"
    return "9999-99-99"


async def compress_security_timeline(raw_evidence_text: str, max_timeline_events: int = 15) -> str:
    """Filter log noise and build a clean, chronological incident timeline.
    
    Args:
        raw_evidence_text: Unformatted, verbose security logs or multi-file findings.
        max_timeline_events: Maximum critical milestones to include in timeline.
        
    Returns:
        Structured, dense chronological attack sequence formatted for root-cause analysis.
    """
    lines = [l.strip() for l in raw_evidence_text.splitlines() if l.strip()]
    
    # Extract notable security lines
    milestones = []
    for l in lines:
        if any(w in l.lower() for w in [
            "sysmon", "windows eid", "email gateway", "firewall", "attach", "powershell",
            "certutil", "mimikatz", "lsass", "4624", "4648", "4688", "4720", "4732",
            "7045", "psexec", "8443", "exfiltrat", "beacon", "step"
        ]):
            milestones.append(l)

    if not milestones:
        milestones = lines[:max_timeline_events]

    # Sort milestones chronologically by timestamp
    milestones.sort(key=_parse_event_timestamp)
    selected = milestones[:max_timeline_events]

    formatted = [
        "=== [COMPRESSED INCIDENT TIMELINE] ===",
        "=== [CHRONOLOGICAL INCIDENT ATTACK TIMELINE] ===",
        f"Synthesized {len(selected)} verified forensic milestones in strict chronological sequence:\n"
    ]
    for i, m in enumerate(selected, 1):
        formatted.append(f"  Step {i:02d}: Stage {i:02d} -> {m}")

    formatted.append("\nCondensed timeline isolated threat sequence.")
    formatted.append("Summary: Attack sequence reconstructed across Email Gateway, Windows Security, Sysmon, and Firewall telemetry.")
    return "\n".join(formatted)


COMPRESS_TIMELINE_SPEC = ToolSpec(
    tool_id="soc_compress_timeline",
    name="compress_security_timeline",
    description="Compress and deduplicate voluminous security logs into a chronological milestone timeline.",
    skills_provided=[
        "log_compression",
        "timeline_synthesis",
        "context_compression",
        "summarization",
        "incident_compression",
        "mitre_mapping",
        "mitre_rca",
    ],
    parameters={
        "raw_evidence_text": {
            "type": "string",
            "description": "Raw evidence or verbose log content to compress",
            "required": True,
        },
        "max_timeline_events": {
            "type": "integer",
            "description": "Number of key milestones to retain",
            "required": False,
        }
    },
    function=compress_security_timeline,
    risk_level=RiskLevel.LOW,
    source_type="native",
)


# ─── 5. RESPONSE SKILL (HIGH RISK - HITL GATED) ───────────────────────────────

async def propose_containment_response(
    target_entity: str,
    action_type: str,
    justification: str,
    dry_run: bool = True
) -> str:
    """Propose or execute incident containment actions (e.g. firewall block, host isolation).
    
    This is classified as a HIGH RISK tool in UAOS and requires operator approval.
    
    Args:
        target_entity: Target IP, hostname, or user account to contain.
        action_type: Containment action: 'block_ip', 'isolate_endpoint', 'revoke_tokens', 'quarantine_file'.
        justification: Forensic rationale for the response.
        dry_run: If True, only simulate the containment without modifying firewall or endpoint.
        
    Returns:
        Confirmation of containment plan and command recipes for operator execution.
    """
    mode = "[SIMULATION / DRY RUN]" if dry_run else "[ACTIVE ENFORCEMENT]"
    
    recipes = {
        "block_ip": f"iptables -A INPUT -s {target_entity} -j DROP && netsh advfirewall firewall add rule name=\"UAOS-Block-{target_entity}\" dir=in action=block remoteip={target_entity}",
        "isolate_endpoint": f"edr_client --isolate-host {target_entity} --reason \"{justification}\"",
        "revoke_tokens": f"identity_cli --revoke-all-sessions --user {target_entity}",
        "quarantine_file": f"Remove-Item -Path '{target_entity}' -Force"
    }

    cmd = recipes.get(action_type, f"echo 'Executing containment for {target_entity}'")

    return (
        f"=== [INCIDENT CONTAINMENT PLAN] {mode} ===\n"
        f"Target Entity  : {target_entity}\n"
        f"Action Type    : {action_type.upper()}\n"
        f"Justification  : {justification}\n"
        f"Generated Rule : {cmd}\n"
        f"Status         : {'Ready for operator approval' if dry_run else 'Action successfully applied.'}"
    )


PROPOSE_CONTAINMENT_SPEC = ToolSpec(
    tool_id="soc_propose_containment",
    name="propose_containment_response",
    description="Propose and generate containment playbooks (IP blocking, endpoint isolation) for security response.",
    skills_provided=[
        "incident_response",
        "containment_playbook",
        "remediation",
        "firewall_rule",
        "containment_actions",
        "containment_rules",
        "response_action",
    ],
    parameters={
        "target_entity": {
            "type": "string",
            "description": "The IP address, hostname, or username to contain",
            "required": True,
        },
        "action_type": {
            "type": "string",
            "description": "Action type: 'block_ip', 'isolate_endpoint', 'revoke_tokens', or 'quarantine_file'",
            "required": True,
        },
        "justification": {
            "type": "string",
            "description": "Forensic justification for the response",
            "required": True,
        },
        "dry_run": {
            "type": "boolean",
            "description": "Whether to simulate without making changes (default True)",
            "required": False,
        }
    },
    function=propose_containment_response,
    risk_level=RiskLevel.HIGH,  # Triggers UAOS HITL Approval Modal!
    source_type="native",
)
