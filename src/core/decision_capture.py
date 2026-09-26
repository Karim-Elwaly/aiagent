"""
Capture of constrained-choice LLM decisions for offline evaluation.

The system asks the LLM to pick from a fixed set of answers in several places
(supervisor verdict: pass/needs_retry/abort; planner risk level: low/medium/
high/critical). Today only the *result* of those calls is retained, in
``supervisor_evaluations``. That is enough to display a verdict but not enough
to answer the questions that matter:

  - How often would the answer change if the options were listed in a different
    order? (position bias)
  - Does a reported confidence of 0.9 actually correspond to being right 90% of
    the time? (calibration)
  - How often does the response fail to parse at all?

Answering those requires replaying the *inputs*. This module appends each
decision's inputs and outputs to a JSONL file so a corpus can be built from real
traffic, hand-labelled once, and replayed against any candidate implementation.

Disabled by default (``decision_capture_enabled``). When disabled, every entry
point here is a cheap no-op. Capture must never affect the run: all failures are
logged at debug level and swallowed.

Privacy: captured records contain task descriptions and worker output, which in
a SOC deployment includes log evidence. Files are written under
``data/decision_capture/`` (git-ignored) and should be treated as sensitive.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR, get_settings

logger = logging.getLogger(__name__)

CAPTURE_DIR = ROOT_DIR / "data" / "decision_capture"

# Decision kinds. Each gets its own file so corpora stay separable.
KIND_SUPERVISOR = "supervisor_verdict"
KIND_RISK_LEVEL = "risk_level"

# Appends happen from activity threads; serialise them so concurrent tasks
# cannot interleave partial lines within a single process.
_write_lock = threading.Lock()


def is_enabled() -> bool:
    """Whether decision capture is currently turned on."""
    try:
        return bool(getattr(get_settings(), "decision_capture_enabled", False))
    except Exception:
        # Settings are unavailable inside a Temporal workflow sandbox, and during
        # some test setups. Absence of config means "off".
        return False


def _max_chars() -> int:
    try:
        return int(getattr(get_settings(), "decision_capture_max_field_chars", 8000))
    except Exception:
        return 8000


def _clip(value: Any, limit: int) -> Any:
    """Bound a captured field, recording that truncation occurred.

    Fields are clipped rather than dropped so a record stays replayable. The
    supervisor prompt itself only uses the first 2500 characters of worker
    output, so the default limit preserves the full prompt input with room to
    spare.
    """
    if not isinstance(value, str):
        return value
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n...[capture-truncated, original {len(value)} chars]"


def _fingerprint(payload: dict[str, Any]) -> str:
    """Stable id for a decision's inputs, for dedup and label bookkeeping."""
    try:
        blob = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        blob = repr(payload)
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()[:16]


def _path_for(kind: str) -> Path:
    safe_kind = "".join(c for c in kind if c.isalnum() or c in ("_", "-")) or "decision"
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return CAPTURE_DIR / f"{safe_kind}-{day}.jsonl"


def _append(kind: str, record: dict[str, Any]) -> None:
    path = _path_for(kind)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _write_lock:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())


def capture_supervisor_decision(
    *,
    task_dict: dict[str, Any],
    worker_output: str,
    user_query: str,
    prior_completed: dict[str, str],
    raw_response: str | None,
    decision: str,
    confidence: float | None,
    degraded: bool,
    workflow_id: str | None = None,
) -> None:
    """Record one supervisor verdict, inputs included, for offline replay.

    ``raw_response`` is the unparsed model output. It is the only way to tell a
    malformed response apart from a transport failure after the fact, and is
    what a parser change would need to be re-tested against.
    """
    if not is_enabled():
        return

    try:
        limit = _max_chars()
        inputs = {
            "user_query": _clip(user_query, limit),
            "task_id": task_dict.get("id", ""),
            "task_name": task_dict.get("name", ""),
            "task_description": _clip(task_dict.get("description", ""), limit),
            "expected_output": _clip(task_dict.get("expected_output", ""), limit),
            "required_skills": task_dict.get("required_skills", []),
            "worker_output": _clip(worker_output, limit),
            "worker_output_full_chars": len(worker_output or ""),
            # Only ids and lengths: the prompt reduces prior context to a short
            # per-task summary, and retaining every upstream output would balloon
            # the corpus for little replay value.
            "prior_task_ids": sorted(prior_completed.keys()) if prior_completed else [],
        }

        record = {
            "schema": 1,
            "kind": KIND_SUPERVISOR,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "workflow_id": workflow_id or "",
            "fingerprint": _fingerprint(inputs),
            "options": ["pass", "needs_retry", "abort"],
            "inputs": inputs,
            "observed": {
                "decision": decision,
                "confidence": confidence,
                "degraded": degraded,
                "raw_response": _clip(raw_response, limit) if raw_response else None,
            },
            # Filled in by hand later; the point of the corpus.
            "label": None,
        }
        _append(KIND_SUPERVISOR, record)
    except Exception as e:
        logger.debug("Decision capture failed (supervisor): %s", e)


def capture_risk_level_decision(
    *,
    user_query: str,
    task: dict[str, Any],
    workflow_id: str | None = None,
) -> None:
    """Record one planner-assigned task risk level, for offline replay.

    Unlike the supervisor verdict, risk level is produced as a single field
    inside a larger DAG generation, so there is no isolated response to store —
    only the task the planner produced and the level it chose.
    """
    if not is_enabled():
        return

    try:
        limit = _max_chars()
        inputs = {
            "user_query": _clip(user_query, limit),
            "task_id": task.get("id", ""),
            "task_name": task.get("name", ""),
            "task_description": _clip(task.get("description", ""), limit),
            "required_skills": task.get("required_skills", []),
            "expected_output": _clip(task.get("expected_output", ""), limit),
        }
        risk = task.get("risk_level", "")
        record = {
            "schema": 1,
            "kind": KIND_RISK_LEVEL,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "workflow_id": workflow_id or "",
            "fingerprint": _fingerprint(inputs),
            "options": ["low", "medium", "high", "critical"],
            "inputs": inputs,
            "observed": {
                "decision": getattr(risk, "value", risk),
                "confidence": None,  # planner never reports one for risk
                "degraded": False,
                "raw_response": None,
            },
            "label": None,
        }
        _append(KIND_RISK_LEVEL, record)
    except Exception as e:
        logger.debug("Decision capture failed (risk_level): %s", e)


def load_records(kind: str) -> list[dict[str, Any]]:
    """Read every captured record of a kind, newest file last.

    Malformed lines are skipped rather than raising: a corpus half-written by an
    interrupted run should still be usable.
    """
    records: list[dict[str, Any]] = []
    if not CAPTURE_DIR.exists():
        return records

    safe_kind = "".join(c for c in kind if c.isalnum() or c in ("_", "-"))
    for path in sorted(CAPTURE_DIR.glob(f"{safe_kind}-*.jsonl")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed capture line %s:%d", path, line_no)
        except Exception as e:
            logger.debug("Failed reading capture file %s: %s", path, e)
    return records


def summarize(kind: str) -> dict[str, Any]:
    """Report corpus size, label progress, and the observed decision mix.

    The decision mix matters before labelling: a corpus that is 98% ``pass``
    cannot demonstrate anything about the retry or abort boundaries, no matter
    how many rows it has.
    """
    records = load_records(kind)
    unique = {r.get("fingerprint") for r in records if r.get("fingerprint")}
    labelled = [r for r in records if r.get("label")]

    observed_counts: dict[str, int] = {}
    degraded = 0
    for r in records:
        obs = r.get("observed") or {}
        decision = str(obs.get("decision", "unknown"))
        observed_counts[decision] = observed_counts.get(decision, 0) + 1
        if obs.get("degraded"):
            degraded += 1

    return {
        "kind": kind,
        "total": len(records),
        "unique": len(unique),
        "labelled": len(labelled),
        "unlabelled": len(records) - len(labelled),
        "observed_decisions": observed_counts,
        "degraded": degraded,
    }
