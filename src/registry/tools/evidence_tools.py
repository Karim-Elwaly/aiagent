"""
UAOS Evidence Tools

The agent-facing surface of the evidence store.

These tools replace the previous pattern of dumping truncated log text into the
model's context. Instead:

  * ``ingest_logs`` parses every record of every file into the run's evidence
    store and reports what it found (and what it could not map).
  * ``query_evidence`` filters and paginates that store, so large result sets
    are navigated rather than truncated.
  * ``get_evidence`` returns verbatim raw lines for specific citation ids, so a
    claim can always be backed by the exact source text.
  * ``evidence_coverage_report`` states authoritative counts and highlights
    data that has not been examined yet.

All tools return strings (with embedded JSON) because the worker's ReAct loop
and its tests expect textual tool results. Every returned record carries its
``EV-xxxxxx`` citation id.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.core.evidence import EvidenceEvent, get_store
from src.core.models import RiskLevel
from src.core.path_utils import resolve_target_path
from src.registry.ingestion import discover_log_files, ingest_file, load_mappings
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

# How many full records to render inline before switching to summary lines.
_MAX_DETAIL_RECORDS = 25


def _json_block(payload: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n```"


def _render(events: list[EvidenceEvent], detail: bool) -> str:
    if not events:
        return "(no matching events)"
    if detail and len(events) <= _MAX_DETAIL_RECORDS:
        return _json_block({"events": [e.model_dump(exclude_defaults=True) for e in events]})
    return "\n".join(e.summary() for e in events)


# ── ingest_logs ──────────────────────────────────────────


async def ingest_logs(
    target_path: str, recursive: bool = True, force: bool = False, _run_id: str = ""
) -> str:
    """Parse every log file under a path into the run's evidence store."""
    resolved = resolve_target_path(target_path)
    if resolved is None or not Path(resolved).exists():
        return (
            f"Error: path not found: '{target_path}'. "
            f"No evidence was ingested, so no findings can be reported for it."
        )

    files = discover_log_files(Path(resolved), recursive=recursive)
    if not files:
        return f"No files found under '{resolved}'. Nothing to ingest."

    store = get_store(_run_id)
    mappings = load_mappings()

    # Ingestion must be idempotent. A second call on the same path — a retry, or
    # a directory call following a per-file call — would otherwise duplicate
    # every record, inflating counts and making a 4-event burst look like 8.
    already: dict[str, int] = {}
    if not force:
        already = dict(store.stats().get("events_by_source_file") or {})

    results: list[dict[str, Any]] = []
    unmapped: list[str] = []
    skipped: list[str] = []
    total = 0

    for file_path in files:
        if not force and already.get(file_path.name):
            skipped.append(file_path.name)
            continue

        events, outcome = ingest_file(file_path, mappings)
        stored = store.append(events)
        total += len(stored)

        first_id = stored[0].ev_id if stored else ""
        last_id = stored[-1].ev_id if stored else ""
        results.append(
            {
                "file": outcome.source_file,
                "detected_format": outcome.detected_format,
                "mapping": outcome.mapping_id,
                "events": outcome.event_count,
                "evidence_id_range": f"{first_id}..{last_id}" if stored else "",
                "error": outcome.error,
            }
        )
        if outcome.mapping_id == "unmapped":
            unmapped.append(outcome.source_file)

    store.write_index()

    lines = [
        "# Log Ingestion Complete",
        "",
        f"Ingested **{total}** new events from **{len(results)}** file(s) into the evidence store. "
        f"The store now holds **{store.count()}** events in total.",
        "Every record is citable by its EV-xxxxxx id. Use `query_evidence` to filter "
        "and `get_evidence` to retrieve verbatim source lines.",
        "",
        _json_block({"files": results, "new_events": total, "store_total": store.count()}),
    ]

    if skipped:
        lines += [
            "",
            "## Already ingested (skipped)",
            "These files were already in the evidence store and were NOT ingested again, "
            "so counts stay accurate: " + ", ".join(skipped),
        ]

    if unmapped:
        lines += [
            "",
            "## Unmapped sources",
            "These files had no vendor mapping, so only generic fields were extracted. "
            "Their raw lines are still stored and searchable by keyword: "
            + ", ".join(unmapped),
        ]

    return "\n".join(lines)


INGEST_LOGS_SPEC = ToolSpec(
    tool_id="ingest_logs_v1",
    name="ingest_logs",
    description=(
        "Parse ALL log files in a directory or a single file into the structured evidence "
        "store. Handles JSON, JSONL, CSV, syslog, XML, EVTX and plain text automatically. "
        "No records are truncated or dropped. Always run this FIRST in an investigation; "
        "every later analysis and citation depends on it."
    ),
    skills_provided=[
        "evidence_gathering",
        "log_ingestion",
        "log_forensics",
        "log_parsing",
    ],
    parameters={
        "target_path": {
            "type": "string",
            "description": "Directory or file path containing the logs to ingest.",
        },
        "recursive": {
            "type": "boolean",
            "description": "Search sub-directories. Defaults to true.",
        },
    },
    function=ingest_logs,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── query_evidence ───────────────────────────────────────


async def query_evidence(
    user: str = "",
    host: str = "",
    ip: str = "",
    event_code: str = "",
    status: str = "",
    keyword: str = "",
    source_file: str = "",
    time_from: str = "",
    time_to: str = "",
    limit: int = 50,
    offset: int = 0,
    _run_id: str = "",
) -> str:
    """Filter the evidence store. Filters combine with AND."""
    store = get_store(_run_id)
    if store.count() == 0:
        return (
            "The evidence store is empty. Run `ingest_logs` on the target path first — "
            "no findings can be reported without ingested evidence."
        )

    try:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        limit, offset = 50, 0

    events, total = store.query(
        user=user,
        host=host,
        ip=ip,
        event_code=event_code,
        status=status,
        keyword=keyword,
        source_file=source_file,
        time_from=time_from,
        time_to=time_to,
        limit=limit,
        offset=offset,
    )

    filters = {
        k: v
        for k, v in {
            "user": user,
            "host": host,
            "ip": ip,
            "event_code": event_code,
            "status": status,
            "keyword": keyword,
            "source_file": source_file,
            "time_from": time_from,
            "time_to": time_to,
        }.items()
        if v
    }

    shown_to = min(offset + len(events), total)
    header = [
        "# Evidence Query Result",
        "",
        f"Filters: {json.dumps(filters) if filters else '(none — all events)'}",
        f"Matched **{total}** event(s). Showing {offset + 1 if events else 0}-{shown_to}.",
    ]

    if total > shown_to:
        header.append(
            f"More results available: re-run with offset={shown_to} to continue. "
            f"Do not draw conclusions from a partial page."
        )

    header += ["", _render(events, detail=True)]
    return "\n".join(header)


QUERY_EVIDENCE_SPEC = ToolSpec(
    tool_id="query_evidence_v1",
    name="query_evidence",
    description=(
        "Search the ingested evidence store with AND-combined filters (user, host, ip, "
        "event_code, status, keyword, source_file, time range) and pagination. Use this "
        "to investigate specific entities or to page through large result sets instead of "
        "guessing. Returns events with their EV-xxxxxx citation ids."
    ),
    skills_provided=["evidence_query", "log_search", "evidence_analysis"],
    parameters={
        "user": {"type": "string", "description": "Filter by username (substring match)."},
        "host": {"type": "string", "description": "Filter by hostname (substring match)."},
        "ip": {"type": "string", "description": "Filter by source OR destination IP (exact)."},
        "event_code": {"type": "string", "description": "Filter by event/message id."},
        "status": {"type": "string", "description": "Filter by outcome, e.g. success or failure."},
        "keyword": {"type": "string", "description": "Free-text search across the raw record."},
        "source_file": {"type": "string", "description": "Filter by originating file name."},
        "time_from": {"type": "string", "description": "ISO-8601 lower bound (inclusive)."},
        "time_to": {"type": "string", "description": "ISO-8601 upper bound (inclusive)."},
        "limit": {"type": "integer", "description": "Page size, max 500. Defaults to 50."},
        "offset": {"type": "integer", "description": "Records to skip for pagination."},
    },
    function=query_evidence,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── get_evidence ─────────────────────────────────────────


async def get_evidence(evidence_ids: str, _run_id: str = "") -> str:
    """Return the verbatim source records behind specific citation ids."""
    store = get_store(_run_id)
    requested = [part.strip() for part in str(evidence_ids).replace(",", " ").split() if part.strip()]
    if not requested:
        return "Error: provide one or more evidence ids, e.g. 'EV-000012 EV-000013'."

    events = store.get(requested)
    found_ids = {e.ev_id for e in events}
    missing = [eid for eid in requested if eid.upper() not in found_ids]

    blocks = [
        "# Evidence Detail",
        "",
    ]
    for event in events:
        blocks += [
            f"## {event.ev_id} — {event.source_file}:{event.line_no}",
            "```",
            event.raw_excerpt or "(no raw text captured)",
            "```",
            _json_block(event.model_dump(exclude_defaults=True)),
            "",
        ]

    if missing:
        blocks += [
            "## Not found",
            "These ids do not exist in the evidence store and must NOT be cited: "
            + ", ".join(missing),
        ]

    return "\n".join(blocks)


GET_EVIDENCE_SPEC = ToolSpec(
    tool_id="get_evidence_v1",
    name="get_evidence",
    description=(
        "Retrieve the verbatim raw log lines behind one or more EV-xxxxxx citation ids. "
        "Use this to confirm the exact wording, timestamp or hash before asserting a "
        "finding, so that every claim quotes real source data."
    ),
    skills_provided=["evidence_retrieval", "evidence_query", "citation_lookup"],
    parameters={
        "evidence_ids": {
            "type": "string",
            "description": "Space or comma separated ids, e.g. 'EV-000012, EV-000013'.",
        }
    },
    function=get_evidence,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)


# ── evidence_coverage_report ─────────────────────────────


async def evidence_coverage_report(_run_id: str = "") -> str:
    """Report authoritative counts and the shape of the ingested evidence."""
    store = get_store(_run_id)
    stats = store.stats()

    if not stats["total_events"]:
        return (
            "# Evidence Coverage\n\n"
            "The evidence store is EMPTY. No logs have been ingested for this run, so no "
            "finding can be supported. Run `ingest_logs` on the target path first."
        )

    lines = [
        "# Evidence Coverage Report",
        "",
        "These figures are authoritative. Any count stated in the final report must match "
        "them — do not estimate record or event counts.",
        "",
        f"- Total events ingested: **{stats['total_events']}**",
        f"- Time span covered: {stats['earliest_timestamp'] or 'unknown'} "
        f"→ {stats['latest_timestamp'] or 'unknown'}",
        f"- Distinct hosts: {len(stats['distinct_hosts'])}",
        f"- Distinct users/accounts: {len(stats['distinct_users'])}",
        f"- Distinct source IPs: {len(stats['distinct_source_ips'])}",
        f"- Distinct destination IPs: {len(stats['distinct_destination_ips'])}",
    ]

    inventory = stats.get("event_inventory") or []
    if inventory:
        lines += [
            "",
            "## Event Inventory — every row must be examined",
            "",
            "Each row is a distinct behaviour type present in this data. The "
            "investigation is not complete until every row has either been analysed "
            "or explicitly ruled benign with a citation. Rows are ordered rarest "
            "first: rare, state-changing events (account management, service "
            "installation, privilege changes) are routinely the highest-signal "
            "records in a corpus and the ones most often missed.",
            "",
            "| Action | Event code | Status | Count | Example evidence ids |",
            "| :--- | :--- | :--- | ---: | :--- |",
        ]
        for row in inventory:
            examples = ", ".join(row["example_ids"])
            lines.append(
                f"| {row['action'] or '(none)'} | {row['event_code'] or '(none)'} "
                f"| {row.get('status') or '(none)'} | {row['count']} | {examples} |"
            )

    flows = stats.get("top_flows_by_bytes") or []
    if flows:
        lines += [
            "",
            "## Network flows by transfer volume (authoritative byte counts)",
            "",
            "These totals come directly from the ingested records. Transfer volume "
            "IS quantifiable for these flows — never report byte counts as "
            "unavailable when this table is present. Large asymmetric outbound "
            "totals (sent >> received) to external destinations demand analysis. "
            "The app, account and policy-rule columns are how a sanctioned bulk "
            "transfer (e.g. a backup job under a backup rule) is distinguished "
            "from exfiltration — weigh them before classifying.",
            "",
            "| Source | Destination | Port | App | User | Rule | Geo | Sessions | Bytes sent | Bytes received | Example ids |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | :--- |",
        ]
        for flow in flows:
            examples = ", ".join(flow["example_ids"])
            lines.append(
                f"| {flow['src_ip'] or '(none)'} | {flow['dst_ip']} | {flow['dst_port'] or '-'} "
                f"| {flow.get('app_id') or '-'} | {flow.get('user') or '-'} "
                f"| {flow.get('rule') or '-'} | {flow.get('geo') or '-'} "
                f"| {flow['sessions']} | {flow['bytes_sent']:,} | {flow['bytes_received']:,} "
                f"| {examples} |"
            )

    spans = stats.get("time_span_by_source_file") or {}
    if spans:
        lines += [
            "",
            "## Time span per source",
            "",
            "A source whose span is much narrower than the overall window is a "
            "telemetry blind spot — say so rather than assuming the activity did "
            "not happen.",
            "",
            "| Source file | Earliest | Latest |",
            "| :--- | :--- | :--- |",
        ]
        for name, span in spans.items():
            lines.append(f"| {name} | {span['earliest']} | {span['latest']} |")

    lines += [
        "",
        _json_block(stats),
    ]

    untyped = stats["events_by_source_type"].get("unmapped", 0)
    if untyped:
        lines += [
            "",
            "## Coverage gap",
            f"{untyped} event(s) came from sources with no vendor mapping, so only generic "
            f"fields were extracted. Search them by keyword before concluding that a "
            f"behaviour is absent.",
        ]

    return "\n".join(lines)


EVIDENCE_COVERAGE_SPEC = ToolSpec(
    tool_id="evidence_coverage_v1",
    name="evidence_coverage_report",
    description=(
        "Report what evidence was actually ingested: authoritative event counts, the time "
        "span covered, and the distinct hosts, accounts and addresses present. Use it to "
        "state accurate totals and to identify data that has not been examined yet."
    ),
    skills_provided=["evidence_coverage", "evidence_query", "coverage_audit"],
    parameters={},
    function=evidence_coverage_report,
    risk_level=RiskLevel.LOW,
    needs_run_context=True,
)
