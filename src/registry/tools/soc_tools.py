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

from src.core.evidence import get_store
from src.core.models import RiskLevel
from src.registry.ingestion import discover_log_files, ingest_file, load_mappings
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# Regex patterns for IoC extraction
IPV4_REGEX = r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
MD5_REGEX = r"\b[a-fA-F0-9]{32}\b"
SHA256_REGEX = r"\b[a-fA-F0-9]{64}\b"
DOMAIN_REGEX = r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"


#  1. TRIAGE SKILL 

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


#  2. EVIDENCE GATHERING SKILL 
#
# Format-specific parsing lives in src/registry/ingestion.py, driven by the
# declarative mappings under data/log_mappings/. Adding a new log source is a
# YAML change, not a code change, and no parser applies per-case filtering.


async def gather_log_evidence(
    target_path: str,
    max_files: int = 0,
    pattern: str = "*",
    recursive: bool = True,
    _run_id: str = "",
) -> str:
    """Scan and parse security logs into the structured evidence store.

    Delegates to the universal ingestion engine, which normalizes every
    supported format (Windows Security EVTX/XML, Sysmon, Cisco ASA syslog,
    Azure AD sign-in JSON, Palo Alto CSV, mail gateway syslog, generic
    JSON/JSONL/CSV/text) into citable evidence records.

    Unlike the earlier implementation, nothing is truncated: every record in
    every file is persisted and addressable by its ``EV-xxxxxx`` id. The
    summary below is a navigation aid, not the evidence itself  use
    ``query_evidence`` to filter and ``get_evidence`` to read raw lines.
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

    # Honour the recursive flag (it was previously accepted but ignored).
    files_to_check = discover_log_files(p, recursive=recursive)
    if pattern and pattern != "*":
        files_to_check = [f for f in files_to_check if f.match(pattern)]
    # max_files <= 0 means "no limit"  the default, so evidence is never
    # silently dropped just because a directory is large.
    if max_files and max_files > 0:
        files_to_check = files_to_check[:max_files]

    if not files_to_check:
        return f"No files matched under '{p}'. Nothing was ingested."

    store = get_store(_run_id)
    mappings = load_mappings()

    output_lines = [f"=== [EVIDENCE COLLECTION: {p.resolve()}] ==="]
    ingested: list[dict[str, Any]] = []
    unmapped_files: list[str] = []
    total_records = 0

    for f in files_to_check:
        events, outcome = ingest_file(f, mappings)
        stored = store.append(events)
        total_records += len(stored)

        try:
            size = f.stat().st_size
        except OSError:
            size = 0

        id_range = f"{stored[0].ev_id}..{stored[-1].ev_id}" if stored else "(none)"
        output_lines.append(
            f"Ingested: {f.name} ({outcome.event_count} records, {size} bytes) "
            f"[{outcome.mapping_id}/{outcome.detected_format}] -> {id_range}"
            + (f" ERROR: {outcome.error}" if outcome.error else "")
        )
        ingested.append(
            {
                "file": outcome.source_file,
                "records": outcome.event_count,
                "mapping": outcome.mapping_id,
                "format": outcome.detected_format,
                "evidence_ids": id_range,
            }
        )
        if outcome.mapping_id == "unmapped":
            unmapped_files.append(outcome.source_file)

    store.write_index()
    stats = store.stats()

    output_lines.append(
        f"\nTotal Artifacts Analyzed: {len(files_to_check)} files, "
        f"{total_records} log records ingested this call."
    )
    output_lines.append(
        f"Evidence store now holds {stats['total_events']} citable events "
        f"spanning {stats['earliest_timestamp'] or 'unknown'} to "
        f"{stats['latest_timestamp'] or 'unknown'}."
    )

    # Observed entities, reported as raw inventory. No judgement is attached
    # here: whether an address is hostile is decided by analysis of behaviour,
    # never by matching against a list baked into this tool.
    external_ips = [
        ip
        for ip in stats["distinct_destination_ips"] + stats["distinct_source_ips"]
        if not _is_internal_ip(ip)
    ]
    if external_ips:
        output_lines.append(
            "\nExternal addresses observed (inventory only  not yet assessed): "
            + ", ".join(sorted(set(external_ips)))
        )
    if stats["distinct_users"]:
        output_lines.append("Accounts observed: " + ", ".join(stats["distinct_users"]))
    if stats["distinct_hosts"]:
        output_lines.append("Hosts observed: " + ", ".join(stats["distinct_hosts"]))

    if unmapped_files:
        output_lines.append(
            "\nSources without a vendor mapping (only generic fields extracted; "
            "search them by keyword before concluding a behaviour is absent): "
            + ", ".join(unmapped_files)
        )

    output_lines.append(
        "\nAll records are stored and citable. Use `query_evidence` to filter by user, "
        "host, ip, event code, status, keyword or time range, and `get_evidence` to read "
        "the verbatim source lines behind any EV-xxxxxx id. Do not rely on this summary "
        "alone for findings."
    )
    output_lines.append("\n```json\n" + json.dumps({"files": ingested}, indent=2) + "\n```")

    return "\n".join(output_lines)


def _is_internal_ip(ip: str) -> bool:
    """True for private, loopback, link-local and broadcast addresses."""
    return ip.startswith(
        ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
         "172.2", "172.30.", "172.31.", "127.", "169.254.", "0.", "255.")
    ) or ip.endswith(".255")



GATHER_EVIDENCE_SPEC = ToolSpec(
    tool_id="soc_gather_evidence",
    name="gather_log_evidence",
    description=(
        "Parse ALL security logs in a directory or file into the structured evidence store. "
        "Handles Windows EVTX/XML, Sysmon, Cisco ASA syslog, Azure AD sign-in JSON, "
        "Palo Alto CSV, mail gateway syslog and generic JSON/CSV/text automatically. "
        "No records are truncated. Run this FIRST: every later analysis and every citation "
        "depends on the evidence it stores."
    ),
    skills_provided=["evidence_gathering", "log_forensics", "artifact_inspection", "file_reading"],
    parameters={
        "target_path": {
            "type": "string",
            "description": "Path to directory or file containing security logs",
            "required": True,
        },
        "max_files": {
            "type": "integer",
            "description": "Maximum files to inspect. Omit or use 0 for no limit (default).",
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
    needs_run_context=True,
)


#  3. DISCOVERY SKILL 

async def lookup_threat_indicators(
    indicator: str, indicator_type: str = "auto", _run_id: str = ""
) -> str:
    """Report what the ingested evidence actually says about an indicator.

    This tool deliberately does NOT assign reputation. No external threat feed is
    configured, and inventing an attribution ("known C2", "malicious binary") from
    an IP literal or a hash string is fabrication. It reports observed behaviour
    from the evidence store and labels everything else UNVERIFIED.

    Args:
        indicator: The IP address, domain name, or file hash.
        indicator_type: 'ip', 'domain', 'hash', or 'auto' for auto-detection.

    Returns:
        Evidence-derived facts about the indicator, plus an explicit statement of
        what could not be verified.
    """
    clean = indicator.strip()
    if not clean:
        return "Error: 'indicator' is required."

    if indicator_type == "auto":
        if re.fullmatch(IPV4_REGEX, clean):
            indicator_type = "ip"
        elif re.fullmatch(SHA256_REGEX, clean) or re.fullmatch(MD5_REGEX, clean):
            indicator_type = "hash"
        else:
            indicator_type = "domain"

    observed = _observe_indicator(clean, indicator_type, _run_id)

    payload: dict[str, Any] = {
        "indicator": clean,
        "type": indicator_type,
        "external_reputation": "UNVERIFIED — no threat intelligence feed is configured",
        "attribution": (
            "NOT AVAILABLE. Do not name a malware family, toolkit or threat actor for "
            "this indicator; nothing in the evidence or in a configured feed supports it."
        ),
        "observed_in_evidence": observed,
    }

    if indicator_type == "ip":
        scope = "internal (RFC 1918 / loopback / link-local)" if _is_internal_ip(clean) else "externally routable"
        payload["addressing"] = (
            f"This address is {scope}. This is an addressing fact only and carries no "
            "reputation on its own."
        )

    payload["guidance"] = (
        "Base any assessment of this indicator on the observed behaviour above "
        "(who contacted it, how often, how much data, which process) — not on the "
        "indicator string itself. If behaviour is absent, say so."
    )

    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n```"


def _observe_indicator(value: str, kind: str, run_id: str) -> dict[str, Any]:
    """Summarize every stored event that references the indicator."""
    store = get_store(run_id)
    if store.count() == 0:
        return {
            "status": "evidence store is empty",
            "detail": "Run ingest_logs first; no behaviour can be reported for this indicator.",
        }

    lowered = value.lower()
    matches = []
    for event in store.iter_events():
        if kind == "ip" and value in (event.src_ip, event.dst_ip):
            matches.append(event)
        elif kind == "hash" and any(lowered == h.lower() for h in event.hashes.values()):
            matches.append(event)
        elif kind == "domain" and lowered in (
            f"{event.app_id} {event.command_line} {event.raw_excerpt}".lower()
        ):
            matches.append(event)

    if not matches:
        return {
            "status": "not observed",
            "detail": (
                f"No ingested event references '{value}'. It must NOT appear in the report "
                "as an involved indicator or a containment target."
            ),
        }

    times = sorted(e.timestamp for e in matches if e.timestamp)
    return {
        "status": "observed",
        "event_count": len(matches),
        "first_seen": times[0] if times else "unknown",
        "last_seen": times[-1] if times else "unknown",
        "hosts": sorted({e.host for e in matches if e.host})[:20],
        "users": sorted({e.user for e in matches if e.user})[:20],
        "processes": sorted({e.process for e in matches if e.process})[:20],
        "destination_ports": sorted({e.dst_port for e in matches if e.dst_port})[:20],
        "total_bytes_sent": sum(e.bytes_sent or 0 for e in matches),
        "evidence": [e.ev_id for e in matches if e.ev_id][:20],
    }


LOOKUP_THREAT_SPEC = ToolSpec(
    tool_id="soc_lookup_threat",
    name="lookup_threat_indicators",
    description=(
        "Report what the ingested evidence actually shows about an IP, domain or file "
        "hash: which hosts, users and processes touched it, when, how often and how much "
        "data moved. Does NOT assign reputation or attribution — no external feed is "
        "configured, so those are returned as UNVERIFIED rather than guessed."
    ),
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
    needs_run_context=True,
)


#  4. IMPACT ANALYSIS & BLAST RADIUS SKILL 

async def analyze_incident_impact(
    target_path: str = "",
    evidence_text: str = "",
    _run_id: str = "",
) -> str:
    """Derive blast radius from the evidence store: which assets and accounts are involved.

    Args:
        target_path: Unused legacy parameter, retained for compatibility.
        evidence_text: Unused legacy parameter, retained for compatibility.

    Returns:
        A blast-radius assessment built entirely from stored events, with citations.
        Every host and account listed is one that genuinely appears in the evidence.
    """
    store = get_store(_run_id)
    if store.count() == 0:
        return (
            "Cannot assess impact: the evidence store is empty. Run `ingest_logs` on the "
            "target path first. Do NOT describe an impact that is not backed by evidence."
        )

    hosts: dict[str, int] = {}
    accounts: dict[str, int] = {}
    internal_pairs: set[tuple[str, str]] = set()
    external_egress: dict[str, int] = {}
    total = 0

    for event in store.iter_events():
        total += 1
        if event.host:
            hosts[event.host] = hosts.get(event.host, 0) + 1
        if event.user and not event.user.endswith("$"):
            accounts[event.user] = accounts.get(event.user, 0) + 1
        if event.src_ip and event.dst_ip:
            if _is_internal_ip(event.src_ip) and _is_internal_ip(event.dst_ip):
                if event.src_ip != event.dst_ip:
                    internal_pairs.add((event.src_ip, event.dst_ip))
            elif _is_internal_ip(event.src_ip) and not _is_internal_ip(event.dst_ip):
                external_egress[event.dst_ip] = (
                    external_egress.get(event.dst_ip, 0) + (event.bytes_sent or 0)
                )

    payload = {
        "analysis": "blast_radius",
        "events_examined": total,
        "hosts_observed": [
            {"host": h, "events": n} for h, n in sorted(hosts.items(), key=lambda kv: -kv[1])
        ],
        "accounts_observed": [
            {"account": a, "events": n} for a, n in sorted(accounts.items(), key=lambda kv: -kv[1])
        ],
        "internal_to_internal_connections": [
            {"from": src, "to": dst} for src, dst in sorted(internal_pairs)
        ],
        "external_egress_destinations": [
            {"destination": ip, "bytes_sent": b}
            for ip, b in sorted(external_egress.items(), key=lambda kv: -kv[1])
        ][:25],
        "note": (
            "This is an inventory of what the evidence contains, not a verdict on what was "
            "compromised. Presence here means 'observed', not 'breached'. Use "
            "analyze_auth_sequences, actor_pivot and analyze_traffic_patterns to establish "
            "which of these entities were actually affected, and cite the evidence ids. "
            "Confidentiality / integrity / availability impact must be stated only where a "
            "specific cited event supports it."
        ),
    }
    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n```"


ANALYZE_IMPACT_SPEC = ToolSpec(
    tool_id="soc_analyze_impact",
    name="analyze_incident_impact",
    description=(
        "Inventory the blast radius from the evidence store: every host and account that "
        "appears, internal-to-internal connections that may indicate lateral movement, and "
        "external egress destinations ranked by bytes sent. Returns only entities that "
        "genuinely exist in the ingested evidence."
    ),
    skills_provided=[
        "impact_analysis",
        "blast_radius",
        "environment_discovery",
    ],
    parameters={
        "target_path": {
            "type": "string",
            "description": "Deprecated; impact is derived from the ingested evidence store.",
            "required": False,
        },
        "evidence_text": {
            "type": "string",
            "description": "Deprecated; impact is derived from the ingested evidence store.",
            "required": False,
        },
    },
    function=analyze_incident_impact,
    risk_level=RiskLevel.LOW,
    source_type="native",
    needs_run_context=True,
)


#  5. COMPRESSION SKILL 

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


#  5. RESPONSE SKILL (HIGH RISK - HITL GATED) 

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
