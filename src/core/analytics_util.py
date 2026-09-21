"""
UAOS Analytics Utilities

Shared, source-agnostic helpers for the detection analytics tools.

Design rules (Phase 0 charter):
  * Analytics read normalized ``EvidenceEvent`` fields only — never a specific
    vendor's raw line format. Adding a log source is a YAML mapping, and every
    analytic works against it immediately.
  * Lexical vocabularies (what counts as a "failure", which binaries are
    living-off-the-land candidates) live in ``data/baselines/*.yaml`` so they
    can be extended without code changes.
  * Nothing here guesses. Missing geo, missing timestamps and unmappable
    statuses stay explicitly unknown.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from src.core.config import ROOT_DIR
from src.core.evidence import EvidenceEvent

logger = logging.getLogger(__name__)

BASELINE_DIR = ROOT_DIR / "data" / "baselines"


# ── Data-driven vocabularies ─────────────────────────────


@lru_cache(maxsize=None)
def load_baseline(name: str) -> dict[str, Any]:
    """Load ``data/baselines/<name>.yaml``. Missing file yields an empty dict."""
    path = BASELINE_DIR / f"{name}.yaml"
    if not path.exists():
        logger.warning("Baseline data file not found: %s", path)
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.error("Failed to parse baseline '%s': %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _markers(name: str, key: str) -> tuple[str, ...]:
    values = load_baseline(name).get(key) or []
    return tuple(str(v).lower() for v in values if str(v).strip())


def is_success(event: EvidenceEvent) -> bool:
    """True when the event's outcome fields read as a successful operation."""
    return _matches_outcome(event, "success_markers") and not _matches_outcome(
        event, "failure_markers"
    )


def is_failure(event: EvidenceEvent) -> bool:
    """True when the event's outcome fields read as a denied/failed operation."""
    return _matches_outcome(event, "failure_markers")


def _matches_outcome(event: EvidenceEvent, key: str) -> bool:
    markers = _markers("auth_signals", key)
    if not markers:
        return False
    haystack = " ".join(
        part.lower() for part in (event.status, event.action, event.error_code) if part
    )
    return any(m in haystack for m in markers)


def is_auth_event(event: EvidenceEvent) -> bool:
    """True when the event describes an authentication attempt.

    Requires an identity: a network flow without a user cannot be scored as an
    authentication outcome.
    """
    if not event.user:
        return False
    markers = _markers("auth_signals", "auth_action_markers")
    if not markers:
        return bool(event.status)
    haystack = " ".join(
        part.lower()
        for part in (event.action, event.event_code, event.source_type, event.status)
        if part
    )
    return any(m in haystack for m in markers)


def is_mfa_denial(event: EvidenceEvent) -> bool:
    """True when a second-factor prompt was rejected rather than a password failing."""
    markers = _markers("auth_signals", "mfa_denial_markers")
    if not markers:
        return False
    haystack = " ".join(
        part.lower()
        for part in (event.status, event.action, event.error_code, event.raw_excerpt)
        if part
    )
    return any(m in haystack for m in markers)


# ── Time ─────────────────────────────────────────────────


def event_time(event: EvidenceEvent) -> datetime | None:
    """Parse an event timestamp into an aware UTC datetime, or None.

    Events without a usable timestamp are excluded from time-series analytics
    rather than being assigned a fabricated time.
    """
    if not event.timestamp:
        return None
    text = event.timestamp.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timed_events(events: Iterable[EvidenceEvent]) -> list[tuple[datetime, EvidenceEvent]]:
    """Return (time, event) pairs with parseable timestamps, sorted ascending."""
    pairs = [(t, e) for e in events if (t := event_time(e)) is not None]
    pairs.sort(key=lambda pair: pair[0])
    return pairs


# ── Statistics ───────────────────────────────────────────


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stddev(values: Sequence[float]) -> float:
    """Population standard deviation. Zero for fewer than two samples."""
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))


def intervals_seconds(times: Sequence[datetime]) -> list[float]:
    """Gaps in seconds between consecutive (already sorted) timestamps."""
    return [
        (times[i] - times[i - 1]).total_seconds()
        for i in range(1, len(times))
    ]


# ── Geography ────────────────────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two coordinates."""
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def has_coordinates(event: EvidenceEvent) -> bool:
    return event.geo.latitude is not None and event.geo.longitude is not None


# ── Rendering ────────────────────────────────────────────


def json_block(payload: dict[str, Any]) -> str:
    """Render a result payload as a fenced JSON block for the ReAct loop."""
    return (
        "```json\n"
        + json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        + "\n```"
    )


def empty_store_message(analysis: str) -> str:
    return (
        f"Cannot run {analysis}: the evidence store is empty. "
        "Run `ingest_logs` on the target path first. "
        "Do NOT report findings that are not backed by ingested evidence."
    )


def no_findings_message(analysis: str, examined: int) -> str:
    return (
        f"{analysis}: no qualifying pattern found across {examined} examined event(s). "
        "This is a negative result — report it as 'not observed', not as an absence of logs."
    )


def cite(events: Iterable[EvidenceEvent], limit: int = 12) -> list[str]:
    """Citation ids for the supporting events, capped for readability."""
    ids = [e.ev_id for e in events if e.ev_id]
    return ids[:limit]


def ensure_baseline_dir() -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    return BASELINE_DIR
