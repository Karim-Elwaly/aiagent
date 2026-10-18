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
    def __init__(self, directory: Path | None = None, max_age_seconds: float = 300.0):
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

    def purge_stale(self, max_age: float | None = None) -> int:
        """Remove JSON records of runs older than max_age."""
        limit = self.max_age_seconds if max_age is None else max_age
        count = 0
        now = time.time()
        try:
            for p in self.directory.glob("*.json"):
                try:
                    entry = json.loads(p.read_text(encoding="utf-8"))
                    if now - float(entry.get("started_at", 0)) > limit:
                        p.unlink(missing_ok=True)
                        count += 1
                except Exception:
                    p.unlink(missing_ok=True)
                    count += 1
        except OSError:
            pass
        return count

    def clear_all(self) -> int:
        """Remove all active run trackers (e.g. on clean worker boot)."""
        count = 0
        try:
            for p in self.directory.glob("*.json"):
                try:
                    p.unlink(missing_ok=True)
                    count += 1
                except OSError:
                    pass
        except OSError:
            pass
        self.touch()
        return count

    def active_profiles(self) -> set[str]:
        """Set of profile names with an ongoing run."""
        self.purge_stale()
        try:
            return {p.stem for p in self.directory.glob("*.json") if self.get(p.stem)}
        except OSError:
            return set()

    def any_active(self, quiet_seconds: float = 0.0) -> bool:
        """A Hermes run of any profile is in progress, or ended less than ``quiet_seconds`` ago."""
        self.purge_stale()
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

