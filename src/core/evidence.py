"""
UAOS Evidence Store

A per-run, append-only store of normalized forensic events.

Purpose
-------
Investigation accuracy depends on the agent reporting ONLY what the raw data
actually contains. Prior to this module, log parsers returned truncated prose
directly to the LLM, which then reconstructed findings from memory — producing
fabricated hashes, impossible timestamps and invented remediation targets.

The evidence store fixes this structurally:

  1. Parsers persist EVERY normalized event (no record caps) to disk.
  2. Each event receives a stable citation id (``EV-000001``).
  3. Tools return compact summaries plus citation ids — the agent retrieves
     detail on demand via ``query_evidence`` / ``get_evidence`` instead of
     receiving one giant truncated dump.
  4. A verification pass can later assert that every claim in the final report
     maps to a real stored event.

The schema is deliberately source-agnostic: network, endpoint, identity and
device telemetry all normalize into the same ``EvidenceEvent`` shape so that
analytics work against any log source that has a field mapping.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field

from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)


def _evidence_root() -> Path:
    """Base directory for per-run evidence.

    Overridable via ``UAOS_EVIDENCE_DIR`` so tests and CI can redirect writes
    away from the repository, and so deployments can place evidence on a
    dedicated (ideally write-once) volume.
    """
    override = os.environ.get("UAOS_EVIDENCE_DIR", "").strip()
    return Path(override) if override else ROOT_DIR / "data" / "evidence"


EVIDENCE_ROOT = _evidence_root()

# Citation ids look like EV-000001. Used by the report verifier to find claims.
EVIDENCE_ID_PATTERN = re.compile(r"\bEV-\d{6}\b")

_DEFAULT_RUN_ID = "adhoc"


class DeviceContext(BaseModel):
    """Device posture attributes, mostly populated by identity providers."""

    os: str = ""
    browser: str = ""
    user_agent: str = ""
    device_id: str = ""
    is_managed: bool | None = None
    is_compliant: bool | None = None


class GeoContext(BaseModel):
    """Geolocation attributes.

    Values are only populated when the source log carries them (or a locally
    configured geo database resolves them). They are never guessed from an IP
    literal — an unknown location stays empty so downstream analytics can say
    "unknown" rather than inventing a country.
    """

    city: str = ""
    country: str = ""
    latitude: float | None = None
    longitude: float | None = None
    asn: str = ""
    isp: str = ""


class EvidenceEvent(BaseModel):
    """A single normalized event extracted from a log source.

    Every field is optional because sources differ wildly; analytics tools
    operate on whichever fields are present rather than on raw log text.
    """

    ev_id: str = ""

    # ── Provenance ───────────────────────────────────────
    source_file: str = ""
    source_type: str = ""  # mapping id, e.g. "cisco_asa_syslog"
    line_no: int = 0
    raw_excerpt: str = ""

    # ── Time ─────────────────────────────────────────────
    timestamp: str = ""  # ISO-8601 UTC when parseable, else raw string

    # ── Host / process ───────────────────────────────────
    host: str = ""
    process: str = ""
    parent_process: str = ""
    command_line: str = ""
    hashes: dict[str, str] = Field(default_factory=dict)

    # ── Identity ─────────────────────────────────────────
    user: str = ""
    account_domain: str = ""

    # ── Network ──────────────────────────────────────────
    src_ip: str = ""
    src_port: int | None = None
    dst_ip: str = ""
    dst_port: int | None = None
    protocol: str = ""
    app_id: str = ""
    bytes_sent: int | None = None
    bytes_received: int | None = None
    session_duration: float | None = None

    # ── Outcome ──────────────────────────────────────────
    event_code: str = ""  # e.g. "4688", "%ASA-6-113015", "500121"
    action: str = ""  # e.g. "logon", "process_create", "allow"
    status: str = ""  # e.g. "success", "failure"
    error_code: str = ""

    # ── Context ──────────────────────────────────────────
    device: DeviceContext = Field(default_factory=DeviceContext)
    geo: GeoContext = Field(default_factory=GeoContext)
    extra: dict[str, Any] = Field(default_factory=dict)

    def summary(self, max_chars: int = 220) -> str:
        """One-line human/LLM readable summary prefixed with the citation id."""
        bits: list[str] = []
        if self.timestamp:
            bits.append(self.timestamp)
        if self.event_code:
            bits.append(f"code={self.event_code}")
        if self.host:
            bits.append(f"host={self.host}")
        if self.user:
            bits.append(f"user={self.user}")
        if self.process:
            bits.append(f"proc={self.process}")
        if self.src_ip:
            bits.append(f"src={self.src_ip}")
        if self.dst_ip:
            dst = self.dst_ip if self.dst_port is None else f"{self.dst_ip}:{self.dst_port}"
            bits.append(f"dst={dst}")
        if self.status:
            bits.append(f"status={self.status}")
        if self.action:
            bits.append(f"action={self.action}")

        line = f"[{self.ev_id}] " + " | ".join(bits)
        if len(line) > max_chars:
            line = line[: max_chars - 3] + "..."
        return line


def parse_timestamp(value: Any) -> str:
    """Best-effort normalization of a timestamp into ISO-8601.

    Returns the original string when the format is unrecognized — an unparseable
    timestamp is still evidence and must not be silently dropped or invented.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return ""

    candidate = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate).isoformat()
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%b %d %Y %H:%M:%S",
        "%b %d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue

    return text


class EvidenceStore:
    """Append-only JSONL store scoped to a single investigation run.

    Thread-safe for append; reads re-scan the file so concurrent activities
    always observe previously persisted evidence.
    """

    def __init__(self, run_id: str, root: Path | None = None):
        self.run_id = _sanitize_run_id(run_id)
        base = root or _evidence_root()
        self.dir = base / self.run_id
        self.events_path = self.dir / "events.jsonl"
        self.index_path = self.dir / "index.json"
        self._lock = threading.Lock()

    # ── Write ────────────────────────────────────────────

    def append(self, events: Iterable[EvidenceEvent]) -> list[EvidenceEvent]:
        """Persist events, assigning citation ids. Returns the stored events."""
        batch = [e for e in events if e is not None]
        if not batch:
            return []

        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            next_index = self._count_unlocked() + 1

            stored: list[EvidenceEvent] = []
            with open(self.events_path, "a", encoding="utf-8") as fh:
                for event in batch:
                    if not event.ev_id:
                        event.ev_id = f"EV-{next_index:06d}"
                        next_index += 1
                    fh.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
                    stored.append(event)

        logger.info(
            "Evidence store '%s': appended %d events (total %d)",
            self.run_id,
            len(stored),
            self.count(),
        )
        return stored

    # ── Read ─────────────────────────────────────────────

    def iter_events(self) -> Iterable[EvidenceEvent]:
        """Yield every stored event in insertion order."""
        if not self.events_path.exists():
            return
        with open(self.events_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield EvidenceEvent(**json.loads(line))
                except Exception as exc:  # corrupt line must not kill the run
                    logger.warning("Skipping unreadable evidence line: %s", exc)

    def all_events(self) -> list[EvidenceEvent]:
        return list(self.iter_events())

    def count(self) -> int:
        with self._lock:
            return self._count_unlocked()

    def _count_unlocked(self) -> int:
        if not self.events_path.exists():
            return 0
        with open(self.events_path, "r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    def get(self, ev_ids: Iterable[str]) -> list[EvidenceEvent]:
        """Fetch specific events by citation id, preserving the requested order."""
        wanted = {eid.strip().upper() for eid in ev_ids if eid and eid.strip()}
        if not wanted:
            return []
        found = {e.ev_id: e for e in self.iter_events() if e.ev_id in wanted}
        return [found[eid] for eid in wanted if eid in found]

    def query(
        self,
        *,
        user: str = "",
        host: str = "",
        ip: str = "",
        dst_port: int | None = None,
        event_code: str = "",
        status: str = "",
        source_type: str = "",
        source_file: str = "",
        keyword: str = "",
        time_from: str = "",
        time_to: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EvidenceEvent], int]:
        """Filter stored events. Returns (page, total_matches).

        All filters are AND-combined and case-insensitive. ``ip`` matches either
        source or destination. Pagination lets the agent walk large result sets
        instead of receiving a truncated dump.
        """
        matches: list[EvidenceEvent] = []

        for event in self.iter_events():
            if user and user.lower() not in _joined(event.user, event.account_domain):
                continue
            if host and host.lower() not in event.host.lower():
                continue
            if ip and ip not in (event.src_ip, event.dst_ip):
                continue
            if dst_port is not None and event.dst_port != dst_port:
                continue
            if event_code and event_code.lower() not in event.event_code.lower():
                continue
            if status and status.lower() not in event.status.lower():
                continue
            if source_type and source_type.lower() not in event.source_type.lower():
                continue
            if source_file and source_file.lower() not in event.source_file.lower():
                continue
            if time_from and event.timestamp and event.timestamp < time_from:
                continue
            if time_to and event.timestamp and event.timestamp > time_to:
                continue
            if keyword and keyword.lower() not in _searchable_text(event):
                continue
            matches.append(event)

        total = len(matches)
        start = max(0, offset)
        page = matches[start : start + max(1, limit)]
        return page, total

    # ── Aggregates ───────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Authoritative counts for the run.

        Every numeric claim in a report ("N records", "N failures") must be
        traceable to figures like these rather than estimated by the model.
        """
        by_source: dict[str, int] = {}
        by_source_file: dict[str, int] = {}
        by_status: dict[str, int] = {}
        hosts: set[str] = set()
        users: set[str] = set()
        src_ips: set[str] = set()
        dst_ips: set[str] = set()
        timestamps: list[str] = []
        total = 0

        for event in self.iter_events():
            total += 1
            if event.source_type:
                by_source[event.source_type] = by_source.get(event.source_type, 0) + 1
            if event.source_file:
                by_source_file[event.source_file] = by_source_file.get(event.source_file, 0) + 1
            if event.status:
                key = event.status.lower()
                by_status[key] = by_status.get(key, 0) + 1
            if event.host:
                hosts.add(event.host)
            if event.user:
                users.add(event.user)
            if event.src_ip:
                src_ips.add(event.src_ip)
            if event.dst_ip:
                dst_ips.add(event.dst_ip)
            if event.timestamp:
                timestamps.append(event.timestamp)

        timestamps.sort()
        return {
            "run_id": self.run_id,
            "total_events": total,
            "events_by_source_type": by_source,
            "events_by_source_file": by_source_file,
            "events_by_status": by_status,
            "distinct_hosts": sorted(hosts),
            "distinct_users": sorted(users),
            "distinct_source_ips": sorted(src_ips),
            "distinct_destination_ips": sorted(dst_ips),
            "earliest_timestamp": timestamps[0] if timestamps else "",
            "latest_timestamp": timestamps[-1] if timestamps else "",
        }

    def write_index(self) -> dict[str, Any]:
        """Persist the aggregate index alongside the events for auditability."""
        data = self.stats()
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        return data

    def known_entities(self) -> dict[str, set[str]]:
        """Entity sets used by the report verifier to detect fabrications."""
        ips: set[str] = set()
        hosts: set[str] = set()
        users: set[str] = set()
        hashes: set[str] = set()
        timestamps: set[str] = set()

        for event in self.iter_events():
            for value in (event.src_ip, event.dst_ip):
                if value:
                    ips.add(value)
            if event.host:
                hosts.add(event.host.lower())
            if event.user:
                users.add(event.user.lower())
            for digest in event.hashes.values():
                if digest:
                    hashes.add(digest.lower())
            if event.timestamp:
                timestamps.add(event.timestamp)

        return {
            "ips": ips,
            "hosts": hosts,
            "users": users,
            "hashes": hashes,
            "timestamps": timestamps,
        }


# ── Helpers ──────────────────────────────────────────────


def _joined(*values: str) -> str:
    return " ".join(v.lower() for v in values if v)


def _searchable_text(event: EvidenceEvent) -> str:
    return " ".join(
        str(v).lower()
        for v in (
            event.raw_excerpt,
            event.command_line,
            event.process,
            event.parent_process,
            event.user,
            event.host,
            event.src_ip,
            event.dst_ip,
            event.event_code,
            event.action,
            event.status,
            event.error_code,
            event.app_id,
            " ".join(event.hashes.values()),
            json.dumps(event.extra, default=str),
        )
        if v
    )


def _sanitize_run_id(run_id: str) -> str:
    """Make a workflow id safe to use as a directory name."""
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(run_id or "")).strip("-")
    return clean or _DEFAULT_RUN_ID


_stores: dict[str, EvidenceStore] = {}
_stores_lock = threading.Lock()


def get_store(run_id: str | None = None) -> EvidenceStore:
    """Return the cached store for a run id, creating it on first use."""
    if not run_id:
        # Every real execution path supplies a workflow id. Falling back to the
        # shared ad-hoc store means two unrelated investigations could read each
        # other's evidence, which would make citations meaningless — so make the
        # fallback loud rather than silent.
        logger.warning(
            "get_store() called without a run_id; using the shared '%s' store. "
            "Evidence from different investigations may be co-mingled.",
            _DEFAULT_RUN_ID,
        )
    key = _sanitize_run_id(run_id or _DEFAULT_RUN_ID)
    with _stores_lock:
        store = _stores.get(key)
        if store is None:
            store = EvidenceStore(key)
            _stores[key] = store
        return store
