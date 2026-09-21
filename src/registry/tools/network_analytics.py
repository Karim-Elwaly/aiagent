"""
UAOS Network & Endpoint Behaviour Analytics

Deterministic detection of behavioural patterns that a language model cannot
reliably see by reading log text:

  * ``analyze_traffic_patterns`` — periodic callbacks (beaconing), volume
    outliers and large egress transfers, computed arithmetically per flow.
  * ``detect_lolbin_activity`` — dual-use system binaries and abuse idioms,
    driven entirely by ``data/baselines/lolbins.yaml``.

Both read the run's evidence store, work on any log source that has a field
mapping, and return citation ids for every claim.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any

from src.core.analytics_util import (
    cite,
    empty_store_message,
    intervals_seconds,
    json_block,
    load_baseline,
    mean,
    stddev,
    timed_events,
)
from src.core.config import get_settings
from src.core.evidence import EvidenceEvent, get_store
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


# ── analyze_traffic_patterns ─────────────────────────────


async def analyze_traffic_patterns(dst_ip: str = "", host: str = "", _run_id: str = "") -> str:
    """Find beaconing, volume outliers and large transfers in network evidence."""
    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("traffic pattern analysis")

    flows: dict[tuple[str, str, int | None], list[EvidenceEvent]] = defaultdict(list)
    network_events = 0

    for event in store.iter_events():
        if not event.dst_ip:
            continue
        if dst_ip and event.dst_ip != dst_ip:
            continue
        if host and host.lower() not in f"{event.host} {event.src_ip}".lower():
            continue
        network_events += 1
        flows[(event.src_ip, event.dst_ip, event.dst_port)].append(event)

    if not network_events:
        return (
            "No network flow events (events carrying a destination address) were found "
            "in the evidence store for the given filters. Report this as 'no network "
            "telemetry available', not as 'no suspicious traffic'."
        )

    settings = get_settings()
    beacons = _detect_beacons(flows)
    transfers, volume_stats = _detect_transfers(flows)

    payload = {
        "analysis": "traffic_pattern_analysis",
        "network_events_examined": network_events,
        "distinct_flows": len(flows),
        "thresholds": {
            "beacon_min_events": settings.beacon_min_events,
            "beacon_max_jitter_ratio": settings.beacon_max_jitter_ratio,
            "beacon_max_interval_seconds": settings.beacon_max_interval_seconds,
            "transfer_outlier_sigma": settings.transfer_outlier_sigma,
            "transfer_min_bytes": settings.transfer_min_bytes,
        },
        "volume_baseline": volume_stats,
        "beaconing": beacons,
        "transfers": transfers,
        "note": (
            "Periodicity indicates automation, not necessarily malice — software "
            "updaters and telemetry agents also beacon. Corroborate the destination "
            "and the initiating process before attributing it to an adversary."
        ),
    }
    return json_block(payload)


def _detect_beacons(
    flows: dict[tuple[str, str, int | None], list[EvidenceEvent]],
) -> list[dict[str, Any]]:
    """A flow is a beacon when its inter-event gaps are machine-regular."""
    settings = get_settings()
    results: list[dict[str, Any]] = []

    for (src, dst, port), events in flows.items():
        pairs = timed_events(events)
        if len(pairs) < settings.beacon_min_events:
            continue

        gaps = intervals_seconds([t for t, _ in pairs])
        if not gaps:
            continue

        average = mean(gaps)
        if average <= 0 or average > settings.beacon_max_interval_seconds:
            continue

        jitter = stddev(gaps) / average
        if jitter > settings.beacon_max_jitter_ratio:
            continue

        results.append(
            {
                "pattern": "periodic_beaconing",
                "src_ip": src,
                "dst_ip": dst,
                "dst_port": port,
                "callbacks": len(pairs),
                "mean_interval_seconds": round(average, 1),
                "jitter_ratio": round(jitter, 4),
                "first_seen": pairs[0][0].isoformat(),
                "last_seen": pairs[-1][0].isoformat(),
                "total_bytes_sent": sum(e.bytes_sent or 0 for e in events),
                "description": (
                    f"{len(pairs)} connections from {src} to {dst}"
                    f"{':' + str(port) if port else ''} spaced {round(average)}s apart "
                    f"(jitter {round(jitter * 100, 1)}%). Regularity at this level is "
                    "machine-scheduled, not human-driven."
                ),
                "evidence": cite(events),
            }
        )

    results.sort(key=lambda r: r["jitter_ratio"])
    return results


def _detect_transfers(
    flows: dict[tuple[str, str, int | None], list[EvidenceEvent]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Outbound volume outliers, measured against this dataset's own baseline."""
    settings = get_settings()
    totals: dict[tuple[str, str, int | None], int] = {
        key: sum(e.bytes_sent or 0 for e in events) for key, events in flows.items()
    }
    values = [v for v in totals.values() if v > 0]
    if not values:
        return [], {
            "flows_with_byte_counts": 0,
            "note": "No byte counts present in the ingested evidence; volume analysis skipped.",
        }

    average = mean(values)
    deviation = stddev(values)
    cutoff = average + settings.transfer_outlier_sigma * deviation

    results: list[dict[str, Any]] = []
    for key, total in totals.items():
        if total < settings.transfer_min_bytes:
            continue
        if deviation > 0 and total < cutoff:
            continue
        src, dst, port = key
        events = flows[key]
        pairs = timed_events(events)
        results.append(
            {
                "pattern": "large_outbound_transfer",
                "src_ip": src,
                "dst_ip": dst,
                "dst_port": port,
                "bytes_sent": total,
                "megabytes_sent": round(total / 1_000_000, 2),
                "connections": len(events),
                "first_seen": pairs[0][0].isoformat() if pairs else "unknown",
                "last_seen": pairs[-1][0].isoformat() if pairs else "unknown",
                "description": (
                    f"{round(total / 1_000_000, 2)} MB sent from {src} to {dst}"
                    f"{':' + str(port) if port else ''} across {len(events)} connection(s) — "
                    f"above the {settings.transfer_outlier_sigma}-sigma outlier cutoff for "
                    "this dataset. Assess whether this represents data exfiltration."
                ),
                "evidence": cite(events),
            }
        )

    results.sort(key=lambda r: r["bytes_sent"], reverse=True)
    stats = {
        "flows_with_byte_counts": len(values),
        "mean_bytes_per_flow": round(average, 1),
        "stddev_bytes_per_flow": round(deviation, 1),
        "outlier_cutoff_bytes": round(cutoff, 1),
    }
    return results, stats


TRAFFIC_PATTERN_SPEC = ToolSpec(
    tool_id="analyze_traffic_patterns_v1",
    name="analyze_traffic_patterns",
    description=(
        "Statistically analyse network flows in the evidence store: detect periodic "
        "beaconing (regular callback intervals with low jitter), and identify large or "
        "outlier outbound transfers that may represent data exfiltration. Requires "
        "ingest_logs first. Returns citation ids for every flow reported."
    ),
    skills_provided=["traffic_analysis", "network_analysis", "anomaly_detection", "exfiltration_analysis"],
    parameters={
        "dst_ip": {
            "type": "string",
            "description": "Optional destination IP filter. Omit to analyse all destinations.",
        },
        "host": {
            "type": "string",
            "description": "Optional source host or IP filter.",
        },
    },
    function=analyze_traffic_patterns,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── detect_lolbin_activity ───────────────────────────────


async def detect_lolbin_activity(host: str = "", _run_id: str = "") -> str:
    """Identify dual-use system binaries and known abuse idioms in process evidence."""
    store = get_store(_run_id)
    if store.count() == 0:
        return empty_store_message("living-off-the-land binary detection")

    catalogue = load_baseline("lolbins")
    binaries: dict[str, dict[str, Any]] = catalogue.get("binaries") or {}
    suspicious_args: list[str] = [
        str(a).lower() for a in (catalogue.get("suspicious_arguments") or [])
    ]
    if not binaries:
        return (
            "Error: data/baselines/lolbins.yaml is missing or empty, so no detection "
            "catalogue is available. No conclusions can be drawn."
        )

    process_events = 0
    hits: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for event in store.iter_events():
        if not (event.process or event.command_line):
            continue
        if host and host.lower() not in event.host.lower():
            continue
        process_events += 1

        name = os.path.basename(event.process.strip().strip('"')).lower()
        command = event.command_line.lower()

        matched = name if name in binaries else ""
        if not matched:
            matched = next((b for b in binaries if command.startswith(b) or f" {b}" in command or f"\\{b}" in command), "")
        if not matched:
            continue

        flagged_args = [a for a in suspicious_args if a in command]
        hits[matched].append(
            {
                "host": event.host,
                "user": event.user,
                "timestamp": event.timestamp,
                "parent_process": event.parent_process,
                "command_line": event.command_line,
                "suspicious_arguments": flagged_args,
                "evidence": event.ev_id,
            }
        )

    if not process_events:
        return (
            "No process-execution events were found in the evidence store. Report this "
            "as 'no endpoint process telemetry available', not as 'no tool abuse'."
        )

    detections = []
    for binary, occurrences in sorted(hits.items()):
        meta = binaries.get(binary) or {}
        with_args = [o for o in occurrences if o["suspicious_arguments"]]
        detections.append(
            {
                "binary": binary,
                "capabilities": meta.get("capabilities", []),
                "why_dual_use": meta.get("note", ""),
                "executions": len(occurrences),
                "executions_with_abuse_indicators": len(with_args),
                "occurrences": occurrences[:25],
                "assessment": (
                    "Abuse indicators present in the command line."
                    if with_args
                    else "Binary is dual-use; no abuse idiom observed in the arguments. "
                    "Judge by parent process and context before reporting it as malicious."
                ),
            }
        )

    detections.sort(key=lambda d: d["executions_with_abuse_indicators"], reverse=True)
    payload = {
        "analysis": "lolbin_detection",
        "process_events_examined": process_events,
        "catalogue_size": len(binaries),
        "detections": detections,
        "note": (
            "These binaries ship with the operating system and are used legitimately "
            "every day. A detection here is a lead, not a verdict."
        ),
    }
    return json_block(payload)


LOLBIN_DETECTION_SPEC = ToolSpec(
    tool_id="detect_lolbin_activity_v1",
    name="detect_lolbin_activity",
    description=(
        "Scan process-execution evidence for living-off-the-land binaries (signed "
        "system tools with download, execution, persistence or credential-access "
        "capability) and for known abuse idioms in their command lines. Catalogue is "
        "data-driven and covers ingress transfer, proxy execution, persistence and "
        "discovery tooling. Returns citation ids."
    ),
    skills_provided=["lolbin_detection", "endpoint_analysis", "malware_analysis"],
    parameters={
        "host": {
            "type": "string",
            "description": "Optional hostname filter. Omit to analyse all hosts.",
        },
    },
    function=detect_lolbin_activity,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)
