"""
Which aiagent task each Hermes profile is running right now.

Hermes sends no run id with MCP tool calls, so the MCP server maps a call to its task through the calling profile.
The worker writes ``data/hermes/active/<profile>.json`` for the length of the run (one run per profile at a time);
a file keeps this working when the worker runs in Temporal's process and the MCP server in the API's.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from src.hermes.profiles import STATE_DIR


class ActiveRuns:
    def __init__(self, directory: Path | None = None, max_age_seconds: float = 4 * 3600):
        self.directory = directory or STATE_DIR / "active"
        self.max_age_seconds = max_age_seconds

    def _path(self, profile: str) -> Path:
        return self.directory / f"{profile}.json"

    @property
    def _last_activity(self) -> Path:
        return self.directory.parent / f"{self.directory.name}_last.json"

    def touch(self) -> None:
        self._last_activity.parent.mkdir(parents=True, exist_ok=True)
        self._last_activity.write_text(json.dumps({"at": time.time()}), encoding="utf-8")

    def set(self, profile: str, entry: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(profile)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({**entry, "started_at": time.time()}), encoding="utf-8")
        os.replace(tmp, path)
        self.touch()

    def get(self, profile: str) -> dict[str, Any] | None:
        try:
            entry = json.loads(self._path(profile).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - float(entry.get("started_at", 0)) > self.max_age_seconds:
            return None
        return entry

    def any_active(self, quiet_seconds: float = 0.0) -> bool:
        """A Hermes run of any profile is in progress, or ended less than ``quiet_seconds`` ago: a workflow is
        usually between two runs then (supervisor check, next task), and a gateway restart would break it."""
        try:
            profiles = [p.stem for p in self.directory.glob("*.json")]
        except OSError:
            return False
        if any(self.get(p) for p in profiles):
            return True
        try:
            last = float(json.loads(self._last_activity.read_text(encoding="utf-8")).get("at", 0))
        except (OSError, ValueError, AttributeError):
            return False
        return time.time() - last < quiet_seconds

    def clear(self, profile: str) -> None:
        try:
            self._path(profile).unlink()
        except FileNotFoundError:
            pass
        self.touch()
