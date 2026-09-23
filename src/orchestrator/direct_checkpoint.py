"""
Disk-based checkpoints for the in-process ("direct") execution engine.

The direct engine runs when Temporal is unavailable. Unlike Temporal — which
persists every workflow step to its own datastore — the direct engine holds run
state in process memory, so a uvicorn/VM restart would lose an in-flight
investigation. These checkpoints close that gap: after each task completes, the
run's progress is written atomically to ``data/checkpoints/<workflow_id>.json``.

On startup (when Temporal is offline) the API scans for checkpoints still marked
``running`` and re-dispatches them; the engine skips already-completed tasks and
continues from the first pending one. Granularity is task-level (a task that was
mid-flight when the process died re-runs from its start), which is the
lightweight, dependency-free contract for this fallback path.

All writes are atomic (temp file + ``os.replace``) so a crash mid-write can never
corrupt an existing checkpoint.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = ROOT_DIR / "data" / "checkpoints"

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def _ensure_dir() -> Path:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return CHECKPOINT_DIR


def _path_for(workflow_id: str) -> Path:
    # workflow_id is generated as ``uaos-<hex>`` — safe as a filename, but guard
    # against any path separators just in case a caller passes something odd.
    safe = str(workflow_id).replace("/", "_").replace("\\", "_")
    return CHECKPOINT_DIR / f"{safe}.json"


def save_checkpoint(state: dict[str, Any]) -> None:
    """Atomically persist a direct-engine run's state.

    ``state`` must contain at least ``workflow_id``. Failures are logged and
    swallowed — a checkpointing problem must never crash a running workflow.
    """
    workflow_id = state.get("workflow_id")
    if not workflow_id:
        logger.debug("save_checkpoint called without workflow_id; skipping")
        return
    try:
        _ensure_dir()
        target = _path_for(workflow_id)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(CHECKPOINT_DIR), prefix=f".{workflow_id}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        finally:
            # If os.replace succeeded the temp file is gone; clean up otherwise.
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
    except Exception as exc:
        logger.warning("Failed to save checkpoint for %s: %s", workflow_id, exc)


def load_checkpoint(workflow_id: str) -> dict[str, Any] | None:
    """Load a single checkpoint, or None if missing/unreadable."""
    try:
        path = _path_for(workflow_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load checkpoint for %s: %s", workflow_id, exc)
        return None


def delete_checkpoint(workflow_id: str) -> None:
    """Remove a checkpoint file (best-effort)."""
    try:
        path = _path_for(workflow_id)
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.debug("Failed to delete checkpoint for %s: %s", workflow_id, exc)


def mark_status(workflow_id: str, status: str) -> None:
    """Update just the ``status`` field of an existing checkpoint."""
    state = load_checkpoint(workflow_id)
    if state is None:
        return
    state["status"] = status
    save_checkpoint(state)


def list_resumable() -> list[dict[str, Any]]:
    """Return all checkpoints still marked ``running`` (candidates to resume)."""
    resumable: list[dict[str, Any]] = []
    if not CHECKPOINT_DIR.exists():
        return resumable
    for path in CHECKPOINT_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("status") == STATUS_RUNNING:
                resumable.append(state)
        except Exception as exc:
            logger.debug("Skipping unreadable checkpoint %s: %s", path.name, exc)
    return resumable
