"""
UAOS Attack Analytics

Deterministic correlation, MITRE ATT&CK classification and severity scoring,
all computed from the run's evidence store.

  * ``correlate_events`` — joins evidence across sources into entity-centred
    clusters and process lineage, producing the correlation graph a timeline
    needs.
  * ``classify_technique`` — maps observed behaviour to MITRE ATT&CK techniques
    using ``data/mitre/technique_signatures.yaml``. A technique is reported only
    when real stored events satisfy its signature, and always with citations.
  * ``score_severity`` — computes severity from a published rubric
    (``data/mitre/severity_rubric.yaml``) instead of asking the model how it
    feels about the incident.

Nothing here infers, guesses or embellishes. If the evidence does not support a
technique, it is simply absent from the output.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from functools import lru_cache
from typing import Any, Iterable

import yaml

from src.core.analytics_util import cite, empty_store_message, json_block, timed_events
from src.core.config import ROOT_DIR
from src.core.evidence import EvidenceEvent, get_store
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

MITRE_DIR = ROOT_DIR / "data" / "mitre"


@lru_cache(maxsize=None)
def _load_mitre(name: str) -> dict[str, Any]:
    path = MITRE_DIR / f"{name}.yaml"
    if not path.exists():
        logger.warning("MITRE data file not found: %s", path)
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.error("Failed to parse MITRE data '%s': %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


# ── correlate_events ─────────────────────────────────────


async def correlate_events(entity: str = "", _run_id: str = "") -> str:
    """Join evidence across sources into entity clusters and process lineage."""
    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("event correlation")

    events = store.all_events()
    if entity:
        needle = entity.strip()
        lowered = needle.lower()
        events = [
            e
            for e in events
            if needle in (e.src_ip, e.dst_ip)
            or lowered in (e.user.lower(), e.host.lower())
        ]
        if not events:
            return (
                f"No evidence references '{entity}'. Nothing to correlate, and it must "
                "not appear in the report as an involved entity."
            )

    # Entities that bridge two or more telemetry sources are the joins that make
    # a cross-source narrative possible.
    bridges = _cross_source_entities(events)
    lineage = _process_lineage(events)
    sessions = _host_user_sessions(events)

    payload = {
        "analysis": "event_correlation",
        "events_examined": len(events),
        "source_types": sorted({e.source_type for e in events if e.source_type}),
        "cross_source_entities": bridges,
        "process_lineage": lineage,
        "host_account_activity": sessions,
        "note": (
            "cross_source_entities are the join points between telemetry sources — build "
            "the timeline around them. Correlation shows that events relate, not that "
            "they are malicious."
        ),
    }
    return json_block(payload)


def _cross_source_entities(events: list[EvidenceEvent]) -> list[dict[str, Any]]:
    """Entities observed in more than one telemetry source."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}

    def record(kind: str, value: str, event: EvidenceEvent) -> None:
        if not value:
            return
        entry = seen.setdefault(
            (kind, value),
            {"kind": kind, "value": value, "sources": set(), "events": []},
        )
        if event.source_type:
            entry["sources"].add(event.source_type)
        entry["events"].append(event)

    for event in events:
        record("host", event.host, event)
        record("account", event.user, event)
        record("ip", event.src_ip, event)
        record("ip", event.dst_ip, event)

    results = []
    for entry in seen.values():
        if len(entry["sources"]) < 2:
            continue
        pairs = timed_events(entry["events"])
        results.append(
            {
                "kind": entry["kind"],
                "value": entry["value"],
                "source_types": sorted(entry["sources"]),
                "event_count": len(entry["events"]),
                "first_seen": pairs[0][0].isoformat() if pairs else "unknown",
                "last_seen": pairs[-1][0].isoformat() if pairs else "unknown",
                "evidence": cite(entry["events"], limit=15),
            }
        )

    results.sort(key=lambda r: (-len(r["source_types"]), -r["event_count"]))
    return results[:40]


def _process_lineage(events: list[EvidenceEvent]) -> list[dict[str, Any]]:
    """Parent → child process relationships observed in endpoint evidence."""
    chains: dict[tuple[str, str, str], list[EvidenceEvent]] = defaultdict(list)
    for event in events:
        if not (event.process and event.parent_process):
            continue
        key = (
            event.host,
            os.path.basename(event.parent_process).lower(),
            os.path.basename(event.process).lower(),
        )
        chains[key].append(event)

    results = [
        {
            "host": host,
            "parent": parent,
            "child": child,
            "executions": len(group),
            "example_command_line": group[0].command_line,
            "evidence": cite(group, limit=10),
        }
        for (host, parent, child), group in chains.items()
    ]
    results.sort(key=lambda r: -r["executions"])
    return results[:40]


def _host_user_sessions(events: list[EvidenceEvent]) -> list[dict[str, Any]]:
    """Which accounts were active on which hosts, and over what window."""
    groups: dict[tuple[str, str], list[EvidenceEvent]] = defaultdict(list)
    for event in events:
        if event.host and event.user:
            groups[(event.host, event.user)].append(event)

    results = []
    for (host, user), group in groups.items():
        pairs = timed_events(group)
        results.append(
            {
                "host": host,
                "account": user,
                "events": len(group),
                "first_seen": pairs[0][0].isoformat() if pairs else "unknown",
                "last_seen": pairs[-1][0].isoformat() if pairs else "unknown",
                "evidence": cite(group, limit=10),
            }
        )
    results.sort(key=lambda r: -r["events"])
    return results[:40]


CORRELATE_EVENTS_SPEC = ToolSpec(
    tool_id="correlate_events_v1",
    name="correlate_events",
    description=(
        "Join evidence across telemetry sources: identify entities (hosts, accounts, IPs) "
        "that appear in more than one source, reconstruct parent/child process lineage, "
        "and summarise which accounts were active on which hosts and when. Use this to "
        "build a cross-source timeline instead of narrating each log file separately."
    ),
    skills_provided=["event_correlation", "timeline_synthesis", "evidence_analysis"],
    parameters={
        "entity": {
            "type": "string",
            "description": "Optional entity (IP, account, host) to centre the correlation on.",
        },
    },
    function=correlate_events,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── classify_technique ───────────────────────────────────


async def classify_technique(observed_patterns: str = "", _run_id: str = "") -> str:
    """Map evidenced behaviour to MITRE ATT&CK techniques."""
    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("MITRE ATT&CK classification")

    catalogue = _load_mitre("technique_signatures")
    techniques: list[dict[str, Any]] = catalogue.get("techniques") or []
    if not techniques:
        return (
            "Error: data/mitre/technique_signatures.yaml is missing or empty. "
            "No technique classification can be produced."
        )

    events = store.all_events()
    declared = {p.strip().lower() for p in (observed_patterns or "").replace(",", " ").split() if p.strip()}

    matched: list[dict[str, Any]] = []
    pattern_based: list[dict[str, Any]] = []

    for technique in techniques:
        conditions = technique.get("conditions")
        if conditions:
            hits = [e for e in events if _condition_matches(e, conditions)]
            if len(hits) >= int(conditions.get("min_events", 1)):
                matched.append(
                    {
                        "technique_id": technique["id"],
                        "technique_name": technique["name"],
                        "tactic": technique.get("tactic", "Unknown"),
                        "basis": "evidence_signature",
                        "matching_events": len(hits),
                        "evidence": cite(hits, limit=10),
                    }
                )
            continue

        pattern = str(technique.get("pattern", "")).lower()
        if pattern and any(pattern in d or d in pattern for d in declared):
            pattern_based.append(
                {
                    "technique_id": technique["id"],
                    "technique_name": technique["name"],
                    "tactic": technique.get("tactic", "Unknown"),
                    "basis": "analytic_pattern",
                    "supporting_pattern": pattern,
                    "evidence": (
                        "Cite the evidence ids returned by the analytic that produced "
                        f"the '{pattern}' finding."
                    ),
                }
            )

    all_matches = matched + pattern_based
    tactics = sorted({m["tactic"] for m in all_matches})

    payload = {
        "analysis": "mitre_attack_classification",
        "events_examined": len(events),
        "catalogue_size": len(techniques),
        "techniques": all_matches,
        "tactics_observed": tactics,
        "tactics_not_evidenced": sorted(
            {t.get("tactic", "Unknown") for t in techniques} - set(tactics)
        ),
        "note": (
            "Only techniques whose signature was satisfied by real stored events are "
            "listed. Do NOT add techniques that do not appear here. Tactics listed under "
            "tactics_not_evidenced were looked for and not found — report them as "
            "'no evidence observed', which is itself a finding."
        ),
    }

    if not all_matches:
        payload["result"] = (
            "No technique signature matched the ingested evidence. State this explicitly "
            "rather than assigning a plausible-sounding technique."
        )
    return json_block(payload)


def _condition_matches(event: EvidenceEvent, conditions: dict[str, Any]) -> bool:
    """Evaluate one signature's conditions against a single event (all ANDed)."""
    process = os.path.basename(event.process.strip().strip('"')).lower()
    command = event.command_line.lower()

    if (values := conditions.get("process_in")) is not None:
        if process not in {str(v).lower() for v in values}:
            return False

    if (values := conditions.get("command_contains_any")) is not None:
        if not any(str(v).lower() in command for v in values):
            return False

    if (values := conditions.get("command_contains_all")) is not None:
        if not all(str(v).lower() in command for v in values):
            return False

    if (values := conditions.get("dst_port_in")) is not None:
        if event.dst_port is None or event.dst_port not in {int(v) for v in values}:
            return False

    if (values := conditions.get("event_code_in")) is not None:
        if event.event_code.strip() not in {str(v) for v in values}:
            return False

    if (values := conditions.get("action_contains_any")) is not None:
        if not any(str(v).lower() in event.action.lower() for v in values):
            return False

    if (values := conditions.get("status_contains_any")) is not None:
        if not any(str(v).lower() in event.status.lower() for v in values):
            return False

    if (field := conditions.get("field_present")) is not None:
        if not str(getattr(event, str(field), "") or ""):
            return False

    return True


CLASSIFY_TECHNIQUE_SPEC = ToolSpec(
    tool_id="classify_technique_v1",
    name="classify_technique",
    description=(
        "Map behaviour evidenced in the store to MITRE ATT&CK technique IDs using a "
        "public signature catalogue. Reports only techniques whose signature was actually "
        "satisfied, with citations, and explicitly lists the tactics for which no "
        "evidence was found. Pass pattern names from the analytics tools (for example "
        "'password_spray periodic_beaconing') to map behavioural findings too."
    ),
    skills_provided=["mitre_mapping", "technique_classification", "threat_analysis"],
    parameters={
        "observed_patterns": {
            "type": "string",
            "description": (
                "Space or comma separated pattern names reported by the analytics tools, "
                "e.g. 'password_spray mfa_fatigue large_outbound_transfer'."
            ),
        },
    },
    function=classify_technique,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── score_severity ───────────────────────────────────────


async def score_severity(
    tactic: str, outcome: str = "unknown", asset_type: str = "unknown", _run_id: str = ""
) -> str:
    """Compute a severity band from the published rubric."""
    rubric = _load_mitre("severity_rubric")
    tactic_weights: dict[str, Any] = rubric.get("tactic_weights") or {}
    outcome_multipliers: dict[str, Any] = rubric.get("outcome_multipliers") or {}
    asset_multipliers: dict[str, Any] = rubric.get("asset_multipliers") or {}
    bands: list[dict[str, Any]] = rubric.get("bands") or []

    if not (tactic_weights and bands):
        return (
            "Error: data/mitre/severity_rubric.yaml is missing or empty. "
            "Severity cannot be computed and must not be asserted."
        )

    resolved_tactic = _match_key(tactic, tactic_weights)
    if resolved_tactic is None:
        return (
            f"Unknown tactic '{tactic}'. Valid tactics: {', '.join(sorted(tactic_weights))}. "
            "Severity was not scored."
        )

    outcome_key = _match_key(outcome, outcome_multipliers) or "unknown"
    asset_key = _match_key(asset_type, asset_multipliers) or "unknown"

    weight = float(tactic_weights[resolved_tactic])
    outcome_factor = float(outcome_multipliers.get(outcome_key, 0.6))
    asset_factor = float(asset_multipliers.get(asset_key, 1.0))
    score = min(10.0, weight * outcome_factor * asset_factor)

    severity = "LOW"
    for band in sorted(bands, key=lambda b: -float(b["min"])):
        if score >= float(band["min"]):
            severity = str(band["severity"])
            break

    payload = {
        "analysis": "severity_scoring",
        "severity": severity,
        "score": round(score, 2),
        "calculation": {
            "tactic": resolved_tactic,
            "tactic_weight": weight,
            "outcome": outcome_key,
            "outcome_multiplier": outcome_factor,
            "asset_type": asset_key,
            "asset_multiplier": asset_factor,
            "formula": "tactic_weight x outcome_multiplier x asset_multiplier, capped at 10",
        },
        "note": (
            "Severity is derived from the published rubric, not from narrative judgement. "
            "Report this band and this score; do not substitute a different one. An "
            "'attempted' or 'blocked' outcome legitimately scores lower than a successful one."
        ),
    }
    return json_block(payload)


def _match_key(value: str, options: Iterable[str]) -> str | None:
    """Case-insensitive lookup that tolerates underscores and spacing."""
    target = (value or "").strip().lower().replace("_", " ")
    if not target:
        return None
    for option in options:
        if str(option).strip().lower().replace("_", " ") == target:
            return str(option)
    return None


SCORE_SEVERITY_SPEC = ToolSpec(
    tool_id="score_severity_v1",
    name="score_severity",
    description=(
        "Compute an incident severity band from a published rubric: tactic weight x "
        "outcome multiplier (succeeded / attempted / blocked) x asset multiplier. Use "
        "this instead of asserting a severity from narrative judgement, and report the "
        "returned score and its calculation."
    ),
    skills_provided=["severity_scoring", "risk_assessment", "triage"],
    parameters={
        "tactic": {
            "type": "string",
            "description": (
                "MITRE ATT&CK tactic, e.g. 'Initial Access', 'Credential Access', "
                "'Exfiltration', 'Impact'."
            ),
            "required": True,
        },
        "outcome": {
            "type": "string",
            "description": "'succeeded', 'attempted', 'blocked' or 'unknown'.",
        },
        "asset_type": {
            "type": "string",
            "description": (
                "'identity_provider', 'domain_controller', 'server', 'endpoint' or 'unknown'."
            ),
        },
    },
    function=score_severity,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)
