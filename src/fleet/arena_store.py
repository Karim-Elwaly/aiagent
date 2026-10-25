"""
Fleet Arena Store — Persistent JSON Storage for Fleet Arena Manifests

Stores arena manifests as JSON files under ``data/fleet_arenas/`` so they
survive process restarts and can be listed, loaded, and updated across
the plan → provision → attach → execute lifecycle.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR
from src.core.models import FleetArenaManifest

logger = logging.getLogger(__name__)

ARENA_DIR = ROOT_DIR / "data" / "fleet_arenas"


class FleetArenaStore:
    """CRUD operations for Fleet Arena manifests persisted as JSON files."""

    def __init__(self, root: Path | None = None):
        self.root = root or ARENA_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, arena_id: str) -> Path:
        safe_id = arena_id.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe_id}.json"

    def save(self, manifest: FleetArenaManifest) -> None:
        """Save or update a Fleet Arena manifest to disk."""
        manifest.updated_at = time.time()
        path = self._path(manifest.arena_id)
        data = manifest.to_serializable()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        logger.info("Saved Fleet Arena manifest '%s' (status=%s)", manifest.arena_id, manifest.status)

    def load(self, arena_id: str) -> FleetArenaManifest | None:
        """Load a Fleet Arena manifest by its ID. Returns None if not found."""
        path = self._path(arena_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return FleetArenaManifest.model_validate(data)
        except Exception as exc:
            logger.warning("Could not load Fleet Arena manifest '%s': %s", arena_id, exc)
            return None

    def delete(self, arena_id: str) -> bool:
        """Delete a Fleet Arena manifest."""
        path = self._path(arena_id)
        if path.is_file():
            path.unlink(missing_ok=True)
            logger.info("Deleted Fleet Arena manifest '%s'", arena_id)
            return True
        return False

    def list_all(self) -> list[FleetArenaManifest]:
        """List all stored Fleet Arena manifests, sorted by created_at descending."""
        manifests: list[FleetArenaManifest] = []
        if not self.root.is_dir():
            return manifests
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                manifests.append(FleetArenaManifest.model_validate(data))
            except Exception as exc:
                logger.warning("Skipping malformed arena manifest '%s': %s", path.name, exc)
        manifests.sort(key=lambda m: m.created_at, reverse=True)
        return manifests

    def update_status(self, arena_id: str, status: str, **extra: Any) -> FleetArenaManifest | None:
        """Convenience: update an arena's status and optional fields, then save."""
        manifest = self.load(arena_id)
        if manifest is None:
            return None
        manifest.status = status
        for key, value in extra.items():
            if hasattr(manifest, key):
                setattr(manifest, key, value)
        self.save(manifest)
        return manifest
