"""
UAOS Investigation Discipline Tools

Tools for the phases that exist to catch the investigation's own mistakes.

  * ``build_attack_hypothesis`` — walks the full MITRE ATT&CK tactic sequence
    and reports, for each stage, whether the evidence supports it, contradicts
    it or is simply silent. An investigation that only describes what it noticed
    will always miss the stage it never thought to look for.
  * ``verify_claims_against_evidence`` — runs the report verifier on draft text
    so the agent can correct itself before a human sees the report.
  * ``check_benign_baseline`` — supplies the generic benign-pattern rules and
    their invalidating conditions, so a suspicious-looking event is consciously
    accepted or rejected rather than reflexively escalated.

All three read the run's evidence store and are deliberately deterministic.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import yaml

from src.core.analytics_util import BASELINE_DIR, empty_store_message, json_block
from src.core.evidence import get_store
from src.core.models import RiskLevel
from src.core.report_verifier import format_verification_section, verify_report
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# The ATT&CK Enterprise tactic sequence. A kill-chain hypothesis walks all of
# these, including the ones nothing was found for.
TACTIC_SEQUENCE = [
    "Reconnaissance",
    "Resource Development",
    "Initial Access",
    "Execution",
    "Persistence",
    "Privilege Escalation",
    "Defense Evasion",
    "Credential Access",
    "Discovery",
    "Lateral Movement",
    "Collection",
    "Command and Control",
    "Exfiltration",
    "Impact",
]

# What to query for when a stage has no evidence yet. Phrased as investigative
# actions, not as expected answers.
TACTIC_PROBES: dict[str, str] = {
    "Reconnaissance": "Scanning or enumeration against externally facing services before the first successful access.",
    "Resource Development": "Infrastructure registered or staged by the actor. Rarely visible in defender telemetry; absence here is normal.",
    "Initial Access": "The FIRST successful authentication, delivery or exploitation. Query authentication successes and inbound sessions ordered by time.",
    "Execution": "Process creation events, script interpreters, and any parent process associated with document handling or a browser.",
    "Persistence": "New accounts, group additions, services, scheduled tasks or autostart entries created during the incident window.",
    "Privilege Escalation": "Privilege assignment events, elevation, and any account that gains rights it did not previously hold.",
    "Defense Evasion": "Log clearing, obfuscated or encoded command lines, proxy execution through signed binaries, security tooling changes.",
    "Credential Access": "Access to credential stores, authentication brute force or spraying, second-factor prompt abuse, token or ticket requests.",
    "Discovery": "Account, share, domain, network and host enumeration commands.",
    "Lateral Movement": "Authentication from one internal host to another, remote service creation, remote management and file-share sessions.",
    "Collection": "Staging activity: archive creation, bulk file reads, data gathered into a single location before movement.",
    "Command and Control": "Repeating outbound connections, connections to destinations not in the asset inventory, non-standard ports.",
    "Exfiltration": "Outbound transfers whose volume is an outlier against the host's own baseline, regardless of destination reputation.",
    "Impact": "Destruction, encryption, backup or shadow-copy deletion, account lockouts, service disruption.",
}


# ── build_attack_hypothesis ──────────────────────────────


async def build_attack_hypothesis(confirmed_findings: str = "", _run_id: str = "") -> str:
    """Produce a full kill-chain checklist and mark each stage evidenced or not."""
    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("attack hypothesis construction")

    declared = (confirmed_findings or "").lower()

    # Describe what telemetry is actually available, so an unevidenced stage can
    # be distinguished from an unobservable one.
    source_types: Counter[str] = Counter()
    capability = {
        "authentication": False,
        "process_execution": False,
        "network_flow": False,
        "byte_volume": False,
        "device_posture": False,
    }
    for event in store.iter_events():
        if event.source_type:
            source_types[event.source_type] += 1
        if event.user and (event.status or event.action):
            capability["authentication"] = True
        if event.process or event.command_line:
            capability["process_execution"] = True
        if event.dst_ip:
            capability["network_flow"] = True
        if event.bytes_sent or event.bytes_received:
            capability["byte_volume"] = True
        if event.device.os or event.device.is_managed is not None:
            capability["device_posture"] = True

    stages: list[dict[str, Any]] = []
    for tactic in TACTIC_SEQUENCE:
        mentioned = tactic.lower() in declared
        stages.append(
            {
                "tactic": tactic,
                "status": "claimed_by_investigation" if mentioned else "not_yet_established",
                "what_to_look_for": TACTIC_PROBES.get(tactic, ""),
                "required_before_reporting": (
                    "Cite the EV ids that evidence this stage, or record it explicitly as "
                    "'no evidence observed'."
                ),
            }
        )

    payload = {
        "analysis": "attack_hypothesis",
        "evidence_events": store.count(),
        "telemetry_sources": dict(source_types),
        "analysis_capability": capability,
        "kill_chain": stages,
        "instructions": (
            "Work through EVERY stage above. For each one either cite the evidence that "
            "establishes it, or state that no evidence was observed. A stage left silent "
            "is the single most common way an investigation misses the highest-impact "
            "event. Pay particular attention to stages your current findings do not "
            "mention at all — use query_evidence and the analytics tools to test them "
            "rather than assuming they did not occur."
        ),
        "caution": (
            "analysis_capability shows which questions this dataset can answer. A stage "
            "with no supporting telemetry must be reported as 'not observable with the "
            "available data', which is different from 'did not happen'."
        ),
    }
    return json_block(payload)


BUILD_HYPOTHESIS_SPEC = ToolSpec(
    tool_id="build_attack_hypothesis_v1",
    name="build_attack_hypothesis",
    description=(
        "Generate a complete MITRE ATT&CK kill-chain checklist for the investigation and "
        "mark which stages the current findings address and which remain untested. Also "
        "reports which analytical questions the ingested telemetry can actually answer. "
        "Use this to find the stage nobody thought to look for."
    ),
    skills_provided=["hypothesis_testing", "kill_chain_analysis", "investigation_planning"],
    parameters={
        "confirmed_findings": {
            "type": "string",
            "description": (
                "The findings established so far, so already-covered stages can be "
                "distinguished from untested ones."
            ),
        },
    },
    function=build_attack_hypothesis,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── verify_claims_against_evidence ───────────────────────


async def verify_claims_against_evidence(draft_report: str, _run_id: str = "") -> str:
    """Run the evidence verifier on draft text so it can be corrected pre-delivery."""
    if not (draft_report or "").strip():
        return (
            "Error: 'draft_report' is required. Pass the findings text you intend to "
            "publish so its claims can be checked against the evidence."
        )

    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("claim verification")

    result = verify_report(draft_report, _run_id)

    lines = [
        f"Verification verdict: {result.verdict.upper()}",
        "",
        format_verification_section(result),
        "",
    ]

    if result.verdict == "fail":
        lines.append(
            "Correct every FAIL item before finalising. Remove or replace values the "
            "evidence does not contain — especially in containment or remediation "
            "sections, where an invented host or address becomes an instruction to act "
            "on an uninvolved system. Re-run this tool after correcting."
        )
    elif result.verdict == "warn":
        lines.append(
            "Add the supporting EV citations for the flagged statements, or mark them "
            "[UNVERIFIED] so the reader knows the data does not establish them."
        )
    else:
        lines.append("All concrete claims in this draft are backed by ingested evidence.")

    return "\n".join(lines)


VERIFY_CLAIMS_SPEC = ToolSpec(
    tool_id="verify_claims_against_evidence_v1",
    name="verify_claims_against_evidence",
    description=(
        "Check a draft report against the evidence store: flags fabricated citations, "
        "addresses, hashes and remediation targets that do not exist in the ingested "
        "data, and measures citation coverage. Run this on your findings BEFORE "
        "finalising them, and correct whatever it flags."
    ),
    skills_provided=["report_verification", "evidence_analysis", "quality_assurance"],
    parameters={
        "draft_report": {
            "type": "string",
            "description": "The draft findings text to verify.",
            "required": True,
        },
    },
    function=verify_claims_against_evidence,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── check_benign_baseline ────────────────────────────────


async def check_benign_baseline(observation: str = "", _run_id: str = "") -> str:
    """Return the generic benign-pattern rules and their invalidating conditions."""
    path = BASELINE_DIR / "benign_services.yaml"
    if not path.exists():
        return (
            "Error: data/baselines/benign_services.yaml is missing. No benign-pattern "
            "rules are available, so no false-positive assessment can be made."
        )

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return f"Error: could not parse benign baseline rules: {exc}"

    rules = data.get("rules") or []
    principles = data.get("principles") or []

    payload = {
        "analysis": "benign_baseline_review",
        "observation_under_review": observation or "(all findings)",
        "rules": rules,
        "principles": principles,
        "how_to_use": (
            "For each finding you are about to report, check whether a rule's 'check' "
            "condition is satisfied BY THE EVIDENCE. If it is, and none of its "
            "'invalidated_by' conditions are present, the finding is a false positive — "
            "say so explicitly and cite the records that establish it. If any "
            "invalidating condition IS present, escalate and name it."
        ),
        "caution": (
            "These are shape-based rules, not an allowlist. No address, hostname or "
            "account is ever benign by identity alone."
        ),
    }
    return json_block(payload)


CHECK_BENIGN_SPEC = ToolSpec(
    tool_id="check_benign_baseline_v1",
    name="check_benign_baseline",
    description=(
        "Retrieve the generic benign-activity rules (cloud service traffic, OS "
        "maintenance, self-corrected password typos, mobile carrier address rotation, "
        "scheduled automation, administrative tooling in context) together with the "
        "conditions that invalidate each one. Use this to consciously accept or reject "
        "a suspicious-looking finding instead of escalating everything."
    ),
    skills_provided=["false_positive_analysis", "baseline_analysis", "triage"],
    parameters={
        "observation": {
            "type": "string",
            "description": "Optional description of the specific finding under review.",
        },
    },
    function=check_benign_baseline,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)
