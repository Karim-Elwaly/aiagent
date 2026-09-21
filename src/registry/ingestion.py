"""
UAOS Universal Log Ingestion

Normalizes heterogeneous log sources into :class:`EvidenceEvent` records.

Design goal: adding support for a new log source must require **no code** —
only a declarative YAML mapping under ``data/log_mappings/``. Detection,
parsing and field extraction are all driven by those mapping files, so the
analytics layer works against any source the moment a mapping exists.

Supported container formats:
  ``json`` (array or object with a record path), ``jsonl``, ``csv``,
  ``syslog`` (regex-driven), ``xml``, ``evtx``, and ``text`` (line fallback).

Nothing is ever truncated during ingestion: every record in the source becomes
a citable event. Volume is managed downstream by querying, not by dropping
evidence at parse time.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree

import yaml

from src.core.config import ROOT_DIR
from src.core.evidence import DeviceContext, EvidenceEvent, GeoContext, parse_timestamp

logger = logging.getLogger(__name__)

MAPPINGS_DIR = ROOT_DIR / "data" / "log_mappings"

# Sample size used for format sniffing and mapping selection.
_SNIFF_BYTES = 8192

# Fields that live inside nested EvidenceEvent sub-models.
_DEVICE_FIELDS = {"os", "browser", "user_agent", "device_id", "is_managed", "is_compliant"}
_GEO_FIELDS = {"city", "country", "latitude", "longitude", "asn", "isp"}
_INT_FIELDS = {"src_port", "dst_port", "bytes_sent", "bytes_received", "line_no"}
_FLOAT_FIELDS = {"session_duration", "latitude", "longitude"}
_BOOL_FIELDS = {"is_managed", "is_compliant"}


@dataclass
class LogMapping:
    """A declarative description of how to read one log source."""

    id: str
    fmt: str
    description: str = ""
    filename_patterns: list[str] = field(default_factory=list)
    content_patterns: list[str] = field(default_factory=list)
    record_path: str = ""  # dotted path to the record array inside a JSON doc
    record_pattern: str = ""  # regex with named groups (syslog/text)
    record_element: str = ""  # element tag holding one record (xml)
    line_prefix_pattern: str = ""  # regex stripped from each line before parsing (csv)
    columns: list[str] = field(default_factory=list)  # column names for headerless csv
    fields: dict[str, Any] = field(default_factory=dict)
    value_maps: dict[str, dict[str, str]] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)
    priority: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LogMapping":
        match = data.get("match", {}) or {}
        return cls(
            id=str(data.get("id", "")),
            fmt=str(data.get("format", "text")).lower(),
            description=str(data.get("description", "")),
            filename_patterns=list(match.get("filename_patterns", []) or []),
            content_patterns=list(match.get("content_patterns", []) or []),
            record_path=str(data.get("record_path", "") or ""),
            record_pattern=str(data.get("record_pattern", "") or ""),
            record_element=str(data.get("record_element", "") or ""),
            line_prefix_pattern=str(data.get("line_prefix_pattern", "") or ""),
            columns=list(data.get("columns", []) or []),
            fields=dict(data.get("fields", {}) or {}),
            value_maps=dict(data.get("value_maps", {}) or {}),
            constants=dict(data.get("constants", {}) or {}),
            priority=int(data.get("priority", 0) or 0),
        )


def load_mappings(directory: Path | None = None) -> list[LogMapping]:
    """Load every YAML mapping from disk. Malformed files are skipped loudly."""
    base = directory or MAPPINGS_DIR
    mappings: list[LogMapping] = []
    if not base.exists():
        logger.warning("Log mapping directory not found: %s", base)
        return mappings

    for path in sorted(base.glob("*.y*ml")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            mapping = LogMapping.from_dict(data)
            if not mapping.id:
                logger.warning("Mapping %s has no id; skipping", path.name)
                continue
            mappings.append(mapping)
        except Exception as exc:
            logger.warning("Failed to load mapping %s: %s", path.name, exc)

    return mappings


# ── Format detection ─────────────────────────────────────


def detect_format(path: Path, sample: str = "") -> str:
    """Sniff the container format from the extension and a content sample."""
    suffix = path.suffix.lower()
    if suffix == ".evtx":
        return "evtx"
    if suffix in (".xml", ".sysmon"):
        return "xml"
    if suffix in (".jsonl", ".ndjson"):
        return "jsonl"

    text = (sample or _read_sample(path)).lstrip()
    if not text:
        return "text"

    if text.startswith("<"):
        return "xml"
    if text.startswith("["):
        return "json"
    if text.startswith("{"):
        # A stream of objects (one per line) is JSONL; a single document is JSON.
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) > 1 and lines[1].lstrip().startswith("{"):
            return "jsonl"
        return "json"

    first_line = text.splitlines()[0] if text.splitlines() else ""
    if suffix == ".csv" or (first_line.count(",") >= 3 and not _looks_like_syslog(first_line)):
        return "csv"
    if _looks_like_syslog(first_line):
        return "syslog"
    return "text"


def _looks_like_syslog(line: str) -> bool:
    """Heuristic: syslog lines lead with a timestamp or a priority/tag marker."""
    return bool(
        re.match(r"^<\d+>", line)
        or re.match(r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}", line)
        or re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", line)
        or "%" in line[:40]
    )


def _read_sample(path: Path, size: int = _SNIFF_BYTES) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(size)
    except OSError:
        return ""


def select_mapping(
    path: Path, mappings: list[LogMapping], sample: str = ""
) -> tuple[LogMapping | None, str]:
    """Pick the best mapping for a file.

    Scoring favours explicit content signatures over filename patterns so that
    a renamed file is still recognised. Returns the mapping (or ``None`` when
    nothing matches) alongside the detected container format.
    """
    text = sample or _read_sample(path)
    fmt = detect_format(path, text)
    lowered = text.lower()
    name = path.name.lower()

    best: LogMapping | None = None
    best_score = 0

    for mapping in mappings:
        score = 0
        for pattern in mapping.content_patterns:
            if pattern.lower() in lowered:
                score += 3
        for pattern in mapping.filename_patterns:
            if _fnmatch(name, pattern.lower()):
                score += 2

        # Priority and format agreement are tie-breakers between candidates
        # that already matched — never evidence of a match on their own.
        if score:
            if mapping.fmt == fmt or _same_family(mapping.fmt, fmt):
                score += 1
            score += mapping.priority

        if score > best_score:
            best, best_score = mapping, score

    # A bare format match is not evidence of a mapping; require a real signal.
    if best_score < 2:
        return None, fmt
    return best, fmt


# Container formats that parse compatibly, so a mapping declaring one may be
# applied to a file detected as the other.
_FORMAT_FAMILIES = ({"json", "jsonl"}, {"xml", "evtx"}, {"syslog", "text"})


def _same_family(left: str, right: str) -> bool:
    return any(left in family and right in family for family in _FORMAT_FAMILIES)


def _fnmatch(name: str, pattern: str) -> bool:
    from fnmatch import fnmatch

    return fnmatch(name, pattern)


# ── Record iteration ─────────────────────────────────────


def iter_records(path: Path, fmt: str, mapping: LogMapping | None) -> Iterator[tuple[int, str, Any]]:
    """Yield ``(line_no, raw_text, record)`` triples for a file.

    ``record`` is a dict for structured formats, or the raw line for text-like
    formats where extraction is regex-driven.
    """
    if fmt == "json":
        yield from _iter_json(path, mapping)
    elif fmt == "jsonl":
        yield from _iter_jsonl(path)
    elif fmt == "csv":
        yield from _iter_csv(path, mapping)
    elif fmt == "xml":
        yield from _iter_xml(path, mapping)
    elif fmt == "evtx":
        yield from _iter_evtx(path, mapping)
    else:  # syslog / text
        yield from _iter_lines(path)


def _iter_json(path: Path, mapping: LogMapping | None) -> Iterator[tuple[int, str, Any]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            doc = json.load(fh)
    except Exception as exc:
        # A document-level parse failure usually means the file is really a
        # stream of objects. Retry line-wise so the evidence is not lost.
        logger.debug("Whole-document JSON parse failed for %s (%s); trying JSONL", path.name, exc)
        yield from _iter_jsonl(path)
        return

    records = doc
    if mapping and mapping.record_path:
        records = _dig(doc, mapping.record_path)
    elif isinstance(doc, dict):
        # Common envelope shapes: {"value": [...]}, {"records": [...]}
        for key in ("value", "records", "events", "data", "items"):
            if isinstance(doc.get(key), list):
                records = doc[key]
                break

    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        return

    for index, record in enumerate(records, start=1):
        yield index, json.dumps(record, ensure_ascii=False), record


def _iter_jsonl(path: Path) -> Iterator[tuple[int, str, Any]]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, line, json.loads(line)
            except json.JSONDecodeError:
                yield line_no, line, {"_raw": line}


def _iter_csv(path: Path, mapping: LogMapping | None = None) -> Iterator[tuple[int, str, Any]]:
    """Yield CSV records, tolerating real-world export shapes.

    Exports routinely wrap each CSV record in a syslog header and start with
    ``#`` banner lines. Comments are documentation, not events; ingesting them
    inflates counts and pollutes the citable record set. A mapping may declare
    ``line_prefix_pattern`` (stripped before parsing, while the verbatim line
    is preserved as evidence) and ``columns`` (names for headerless data —
    positional keys like "0", "7" would make declarative field mapping
    impossible).
    """
    prefix_re = None
    if mapping and mapping.line_prefix_pattern:
        try:
            prefix_re = re.compile(mapping.line_prefix_pattern)
        except re.error as exc:
            logger.warning(
                "Invalid line_prefix_pattern in mapping %s: %s", mapping.id, exc
            )

    columns = list(mapping.columns) if mapping and mapping.columns else []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw_lines = fh.read().splitlines()

    data_rows: list[tuple[int, str, str]] = []  # (line_no, verbatim, csv_body)
    for line_no, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        body = stripped
        if prefix_re:
            m = prefix_re.match(body)
            if m:
                body = body[m.end():].lstrip()
        data_rows.append((line_no, line, body))

    if not data_rows:
        return

    if columns:
        for line_no, verbatim, body in data_rows:
            row = next(csv.reader(io.StringIO(body)), [])
            if not row:
                continue
            record = {name: value for name, value in zip(columns, row)}
            yield line_no, verbatim, record
        return

    has_header = not _looks_like_data_row(data_rows[0][2])
    if has_header:
        header = next(csv.reader(io.StringIO(data_rows[0][2])), [])
        for line_no, verbatim, body in data_rows[1:]:
            row = next(csv.reader(io.StringIO(body)), [])
            if not row:
                continue
            record = {name: value for name, value in zip(header, row)}
            yield line_no, verbatim, record
    else:
        for line_no, verbatim, body in data_rows:
            row = next(csv.reader(io.StringIO(body)), [])
            if not row:
                continue
            record = {str(i): value for i, value in enumerate(row)}
            yield line_no, verbatim, record


def _looks_like_data_row(line: str) -> bool:
    """A header row has no bare timestamps or IP literals in it."""
    return bool(
        re.search(r"\d{4}-\d{2}-\d{2}", line)
        or re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", line)
    )


def _iter_xml(path: Path, mapping: LogMapping | None) -> Iterator[tuple[int, str, Any]]:
    try:
        tree = ElementTree.parse(path)
    except Exception as exc:
        logger.warning("Unreadable XML %s: %s", path.name, exc)
        return

    root = tree.getroot()
    tag = (mapping.record_element if mapping else "") or "Event"
    elements = [el for el in root.iter() if _localname(el.tag) == tag]
    if not elements:
        elements = list(root)

    for index, element in enumerate(elements, start=1):
        yield index, _element_text(element), _flatten_element(element)


def _iter_evtx(path: Path, mapping: LogMapping | None) -> Iterator[tuple[int, str, Any]]:
    try:
        from Evtx.Evtx import Evtx  # type: ignore
    except ImportError:
        logger.warning("python-evtx not installed; cannot parse %s", path.name)
        return

    try:
        with Evtx(str(path)) as log:
            for index, record in enumerate(log.records(), start=1):
                xml_text = record.xml()
                try:
                    element = ElementTree.fromstring(xml_text)
                except Exception:
                    continue
                yield index, xml_text, _flatten_element(element)
    except Exception as exc:
        logger.warning("Unreadable EVTX %s: %s", path.name, exc)


def _iter_lines(path: Path) -> Iterator[tuple[int, str, Any]]:
    """Yield non-empty, non-comment lines.

    Log exports routinely start with a banner of ``#``-prefixed description
    lines. Ingesting those as evidence records inflates event counts and puts
    non-events into the citable record set, so they are skipped. Line numbers
    still reflect true file positions.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            yield line_no, line, line


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _element_text(element: Any) -> str:
    try:
        return ElementTree.tostring(element, encoding="unicode")
    except Exception:
        return ""


def _flatten_element(element: Any) -> dict[str, Any]:
    """Flatten an XML element into a lookup dict.

    Produces entries for attributes, child tags, and the Windows/Sysmon
    ``<Data Name="X">value</Data>`` convention so mappings can reference either
    ``EventID`` or ``Data.CommandLine`` style keys.
    """
    out: dict[str, Any] = {}

    for child in element.iter():
        name = _localname(child.tag)
        text = (child.text or "").strip()

        if name == "Data":
            data_name = child.get("Name") or child.get("name")
            if data_name:
                out[f"Data.{data_name}"] = text
                out.setdefault(data_name, text)
        elif text:
            out.setdefault(name, text)

        for attr_key, attr_value in child.attrib.items():
            if attr_key in ("Name", "name") and name == "Data":
                continue
            out.setdefault(f"{name}.{attr_key}", attr_value)
            out.setdefault(attr_key, attr_value)

    return out


# ── Field extraction ─────────────────────────────────────


def _dig(data: Any, path: str) -> Any:
    """Resolve a dotted path, tolerating missing intermediate keys.

    A literal key containing dots wins over path traversal: flattened XML
    records legitimately hold keys such as ``Data.CommandLine``.
    """
    if isinstance(data, dict) and path in data:
        return data[path]

    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            if part in current:
                current = current[part]
                continue
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
                continue
            except (ValueError, IndexError):
                return None
        return None
    return current


def _extract(record: Any, spec: Any) -> Any:
    """Resolve one field spec against a record.

    A spec may be a dotted path, a list of alternative paths (first non-empty
    wins), or a dict supporting ``path``/``paths``, ``regex`` + ``group``, and
    ``const``.
    """
    if spec is None:
        return None

    if isinstance(spec, str):
        if isinstance(record, dict):
            value = _dig(record, spec)
            if value not in (None, ""):
                return value
            return None
        return None

    if isinstance(spec, list):
        for alternative in spec:
            value = _extract(record, alternative)
            if value not in (None, ""):
                return value
        return None

    if isinstance(spec, dict):
        if "const" in spec:
            return spec["const"]

        paths = spec.get("paths") or ([spec["path"]] if spec.get("path") else [])
        value = None
        for candidate in paths:
            value = _extract(record, candidate)
            if value not in (None, ""):
                break

        source = value if value not in (None, "") else (record if isinstance(record, str) else None)
        pattern = spec.get("regex")
        if pattern and source is not None:
            match = re.search(pattern, str(source))
            if not match:
                return None
            group = spec.get("group", 1)
            try:
                return match.group(group)
            except (IndexError, KeyError):
                return None
        return value

    return None


def _coerce(name: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if name in _BOOL_FIELDS:
        text = str(value).strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
        return None
    if name in _INT_FIELDS:
        try:
            return int(str(value).strip())
        except ValueError:
            return None
    if name in _FLOAT_FIELDS:
        try:
            return float(str(value).strip())
        except ValueError:
            return None
    return str(value).strip()


def build_event(
    record: Any,
    raw_text: str,
    line_no: int,
    source_file: str,
    mapping: LogMapping | None,
    fallback_source_type: str = "unmapped",
    default_year: int | None = None,
) -> EvidenceEvent:
    """Apply a mapping to a single record, producing an EvidenceEvent.

    When no mapping matches, a generic best-effort extraction still records the
    raw line so the evidence is preserved and citable rather than discarded.

    ``default_year`` is used for yearless syslog timestamps; callers pass the
    year of the source file so the assumption comes from the evidence.
    """
    event = EvidenceEvent(
        source_file=source_file,
        source_type=mapping.id if mapping else fallback_source_type,
        line_no=line_no,
        raw_excerpt=raw_text,
    )

    # Regex-driven records (syslog/text) expose named groups as a dict.
    working: Any = record
    if mapping and mapping.record_pattern and isinstance(record, str):
        match = re.search(mapping.record_pattern, record)
        if match:
            groups = {k: v for k, v in match.groupdict().items() if v is not None}
            working = {**groups, "_raw": record}
        else:
            working = {"_raw": record}

    device_values: dict[str, Any] = {}
    geo_values: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    specs = dict(mapping.fields) if mapping else {}
    for target, spec in specs.items():
        raw_value = _extract(working, spec)
        if raw_value in (None, "") and isinstance(record, str):
            raw_value = _extract(record, spec)

        value_map = (mapping.value_maps.get(target) if mapping else None) or {}
        if raw_value is not None and value_map:
            raw_value = value_map.get(str(raw_value), value_map.get("*", raw_value))

        value = _coerce(target, raw_value)
        if value is None:
            continue

        if target == "timestamp":
            event.timestamp = parse_timestamp(value, default_year=default_year)
        elif target.startswith("hashes."):
            event.hashes[target.split(".", 1)[1]] = str(value)
        elif target.startswith("extra."):
            extra[target.split(".", 1)[1]] = value
        elif target in _DEVICE_FIELDS:
            device_values[target] = value
        elif target in _GEO_FIELDS:
            geo_values[target] = value
        elif hasattr(event, target):
            setattr(event, target, value)
        else:
            extra[target] = value

    for target, constant in (mapping.constants if mapping else {}).items():
        if hasattr(event, target) and not getattr(event, target):
            setattr(event, target, constant)

    if device_values:
        event.device = DeviceContext(**device_values)
    if geo_values:
        event.geo = GeoContext(**geo_values)
    if extra:
        event.extra = extra

    if not mapping:
        _apply_generic_extraction(event, raw_text)

    return event


_IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b")
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")


def _apply_generic_extraction(event: EvidenceEvent, raw_text: str) -> None:
    """Minimal extraction for unmapped sources.

    Only unambiguous, literally-present values are captured — an unmapped log
    must still never produce invented structure.
    """
    timestamp = _TS_RE.search(raw_text)
    if timestamp:
        event.timestamp = parse_timestamp(timestamp.group(0))

    ips = _IP_RE.findall(raw_text)
    if ips:
        event.src_ip = ips[0]
        if len(ips) > 1:
            event.dst_ip = ips[1]


# ── File / directory ingestion ───────────────────────────


@dataclass
class IngestionResult:
    """Outcome of ingesting one file, including why it was interpreted that way."""

    source_file: str
    detected_format: str
    mapping_id: str
    event_count: int
    error: str = ""


def ingest_file(
    path: Path, mappings: list[LogMapping] | None = None
) -> tuple[list[EvidenceEvent], IngestionResult]:
    """Parse a single file into evidence events. No record limit is applied."""
    catalog = mappings if mappings is not None else load_mappings()
    sample = _read_sample(path)
    mapping, fmt = select_mapping(path, catalog, sample)

    # Sniffed container format wins, because it reflects the bytes actually on
    # disk. A mapping's declared format only applies when detection was a
    # low-confidence text fallback (e.g. a regex-driven syslog variant).
    if mapping and mapping.fmt and fmt == "text" and mapping.fmt != "text":
        fmt = mapping.fmt

    events: list[EvidenceEvent] = []
    error = ""

    # Yearless syslog lines inherit the year of the file they came from, which
    # is evidence-derived rather than a guess from the current clock.
    try:
        default_year = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).year
    except Exception:
        default_year = None

    try:
        for line_no, raw_text, record in iter_records(path, fmt, mapping):
            events.append(
                build_event(
                    record=record,
                    raw_text=raw_text,
                    line_no=line_no,
                    source_file=path.name,
                    mapping=mapping,
                    default_year=default_year,
                )
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.warning("Ingestion failed for %s: %s", path.name, error)

    return events, IngestionResult(
        source_file=path.name,
        detected_format=fmt,
        mapping_id=mapping.id if mapping else "unmapped",
        event_count=len(events),
        error=error,
    )


def discover_log_files(target: Path, recursive: bool = True) -> list[Path]:
    """List candidate log files under a path (or the path itself if a file)."""
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []

    pattern = "**/*" if recursive else "*"
    return sorted(p for p in target.glob(pattern) if p.is_file())
