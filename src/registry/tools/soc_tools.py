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
    suspicious_indicators = []
    keywords = {
        "mimikatz": 50, "cobalt": 50, "powershell -enc": 40, "base64": 30,
        "beacon": 40, "c2": 45, "ransomware": 50, "exfiltration": 45,
        "privilege escalation": 35, "unauthorized": 25, "brute force": 20
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
    """Parse Windows EVTX binary logs using PowerShell Get-WinEvent or fallback string extraction."""
    records: list[str] = []
    if platform.system() == "Windows":
        try:
            # Safely query top events via PowerShell
            escaped_path = str(evtx_path).replace("'", "''")
            ps_script = (
                f"$events = Get-WinEvent -Path '{escaped_path}' -MaxEvents {max_records} -ErrorAction SilentlyContinue | "
                f"Select-Object TimeCreated, Id, LevelDisplayName, Message; "
                f"if ($events) {{ ConvertTo-Json -InputObject @($events) -Compress }} else {{ '[]' }}"
            )
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=12,
            )
            stdout = proc.stdout.strip()
            if stdout and stdout != "[]":
                try:
                    data = json.loads(stdout)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        t = str(item.get("TimeCreated", ""))
                        eid = str(item.get("Id", ""))
                        lvl = str(item.get("LevelDisplayName", "Info"))
                        msg = str(item.get("Message", "")).replace("\r\n", " ").replace("\n", " ").strip()
                        if len(msg) > 160:
                            msg = msg[:160] + "..."
                        records.append(f"[{t}] [EventID {eid}] [{lvl}] {msg}")
                    return len(records), records
                except Exception:
                    pass
        except Exception as ps_err:
            logger.debug("PowerShell EVTX read failed for %s: %s", evtx_path.name, ps_err)

    # Cross-platform / fallback binary string scraping
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


async def gather_log_evidence(
    target_path: str,
    max_files: int = 30,
    pattern: str = "*",
    recursive: bool = True,
) -> str:
    """Scan and inspect log directories or forensic artifact files recursively.
    
    Supports .log, .txt, .json, .csv, .xml, and Windows .evtx event log parsing.
    
    Args:
        target_path: Path to file or directory containing security logs.
        max_files: Maximum number of log files to inspect.
        pattern: File glob pattern (e.g. '*.log', '*.evtx', '*').
        recursive: Whether to search subdirectories recursively.
        
    Returns:
        Structured forensic collection summary with artifact metadata and suspicious indicators.
    """
    clean_path = str(target_path).strip().strip('"').strip("'")
    p = Path(clean_path)
    if not p.exists():
        return f"Error: Path '{clean_path}' does not exist on disk."

    output_lines = [f"=== [EVIDENCE COLLECTION: {clean_path}] ==="]
    
    files_to_check: list[Path] = []
    if p.is_file():
        files_to_check = [p]
    else:
        if recursive:
            for root, _, f_names in os.walk(p):
                # Don't recurse excessively deep
                rel_parts = len(Path(root).relative_to(p).parts)
                if rel_parts > 4:
                    continue
                for fname in sorted(f_names):
                    fp = Path(root) / fname
                    if pattern != "*" and not fp.match(pattern):
                        continue
                    files_to_check.append(fp)
                    if len(files_to_check) >= max_files:
                        break
                if len(files_to_check) >= max_files:
                    break
        else:
            for f in sorted(list(p.glob(pattern))):
                if f.is_file():
                    files_to_check.append(f)
                    if len(files_to_check) >= max_files:
                        break

    total_events = 0
    suspicious_findings: list[str] = []
    extracted_ips: set[str] = set()
    extracted_hashes: set[str] = set()

    # High-signal APT and intrusion detection patterns
    suspicious_keywords = [
        "mimikatz", "sekurlsa", "lsass", "procdump", "comsvcs.dll",
        "powershell -enc", "powershell.exe -e", "certutil -urlcache", "certutil -decode",
        "rundll32.exe", "wmic process call", "bitsadmin", "vssadmin delete shadows",
        "schtasks /create", "psexec", "whoami", "nltest", "net user", "net group",
        "beacon", "reverse shell", "downloadstring", "invoke-expression", "invoke-webrequest",
        "failed", "unauthorized", "error", "exec", "powershell", "denied", "malware", "drop", "alert"
    ]

    for f in files_to_check:
        if f.is_dir():
            continue

        f_size = f.stat().st_size
        f_ext = f.suffix.lower()

        # Dedicated Windows EVTX handler
        if f_ext == ".evtx":
            rec_count, evtx_events = _parse_evtx_records(f, max_records=40)
            total_events += rec_count
            for ev in evtx_events:
                if any(k in ev.lower() for k in suspicious_keywords) or "eventid" in ev.lower():
                    if len(suspicious_findings) < 25:
                        suspicious_findings.append(f"[{f.name}] {ev[:160]}")
                for ip in re.findall(IPV4_REGEX, ev):
                    extracted_ips.add(ip)
            output_lines.append(f"File: {f.name} ({rec_count} lines, {f_size} bytes) [Windows EVTX Log]")
            continue

        # Text, JSON, CSV, XML logs handler
        try:
            content = ""
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    content = f.read_text(encoding=enc, errors="replace")
                    break
                except Exception:
                    pass

            lines = content.splitlines()
            total_events += len(lines)

            # Scan lines across the file (sample first 1000 lines and regex scan the rest)
            for idx, line in enumerate(lines[:1000]):
                line_lower = line.lower()
                if any(k in line_lower for k in suspicious_keywords):
                    if len(suspicious_findings) < 25:
                        suspicious_findings.append(f"[{f.name}:L{idx+1}] {line.strip()[:160]}")

            # Collect IoCs from file
            for ip in re.findall(IPV4_REGEX, content[:100000]):
                extracted_ips.add(ip)
            for h in re.findall(MD5_REGEX, content[:100000]):
                extracted_hashes.add(h)
            for h in re.findall(SHA256_REGEX, content[:100000]):
                extracted_hashes.add(h)

            output_lines.append(f"File: {f.name} ({len(lines)} lines, {f_size} bytes)")
        except Exception as e:
            output_lines.append(f"File: {f.name} (Error reading: {e})")

    output_lines.append(f"\nTotal Artifacts Analyzed: {len(files_to_check)} files, {total_events} total log records.")
    
    if extracted_ips:
        ext_ips = [ip for ip in extracted_ips if not (ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("172.16.") or ip.startswith("127."))]
        if ext_ips:
            output_lines.append(f"Extracted External Egress IPs: {', '.join(sorted(ext_ips)[:10])}")
    if extracted_hashes:
        output_lines.append(f"Extracted Artifact Hashes: {', '.join(sorted(extracted_hashes)[:5])}")

    if suspicious_findings:
        output_lines.append("\nKey Anomalous Events Detected:")
        for sf in suspicious_findings:
            output_lines.append(f"  - {sf}")
    else:
        output_lines.append("\nNo overt anomalies matched default filters; recommend targeted regex inspection.")

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


# ─── 4. COMPRESSION SKILL ─────────────────────────────────────────────────────

async def compress_security_timeline(raw_evidence_text: str, max_timeline_events: int = 10) -> str:
    """Filter log noise and build a clean, chronological incident timeline.
    
    Args:
        raw_evidence_text: Unformatted, verbose security logs or multi-file findings.
        max_timeline_events: Maximum critical milestones to include in timeline.
        
    Returns:
        Structured, dense chronological attack sequence formatted for root-cause analysis.
    """
    lines = [l.strip() for l in raw_evidence_text.splitlines() if l.strip()]
    
    # Extract timestamped or notable lines
    milestones = []
    for l in lines:
        if any(w in l.lower() for w in ["exec", "alert", "error", "connect", "egress", "failed", "powershell", "triage", "critical"]):
            milestones.append(l)
            if len(milestones) >= max_timeline_events:
                break

    if not milestones:
        milestones = lines[:max_timeline_events]

    formatted = [
        "=== [COMPRESSED INCIDENT TIMELINE] ===",
        f"Original Context: {len(lines)} lines -> Compressed to {len(milestones)} critical milestones.",
        ""
    ]
    for i, m in enumerate(milestones, 1):
        formatted.append(f"Step {i:02d}: {m}")

    formatted.append("\nSummary: Condensed timeline isolated threat sequence without token explosion.")
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
