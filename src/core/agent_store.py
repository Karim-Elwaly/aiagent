"""
UAOS Agent Store

File-based persistence for AgentProfile definitions stored in data/agents/.
Each agent is stored in its own JSON file ({agent_id}.json) for clean separation,
matching the zero-dependency philosophy of UAOS.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from src.core.agent_models import AgentProfile
from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

DEFAULT_AGENTS_DIR = ROOT_DIR / "data" / "agents"


class AgentStore:
    """Manages storage, retrieval, and lifecycle of AgentProfile instances."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_AGENTS_DIR
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure storage directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_id(name: str) -> str:
        """Convert a display name into a URL-friendly, safe slug ID."""
        slug = name.strip().lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
        return slug or "custom-agent"

    def _get_file_path(self, agent_id: str) -> Path:
        clean_id = self.generate_id(agent_id)
        return self.storage_dir / f"{clean_id}.json"

    def save(self, profile: AgentProfile) -> AgentProfile:
        """Persist an agent profile to disk."""
        self._ensure_dir()
        profile.updated_at = datetime.now(timezone.utc).isoformat()
        file_path = self.storage_dir / f"{profile.id}.json"

        temp_path = file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(profile.model_dump(), f, indent=2, ensure_ascii=False)
            temp_path.replace(file_path)
            logger.info("Saved agent profile '%s' to %s", profile.id, file_path)
            return profile
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            logger.error("Failed to save agent '%s': %s", profile.id, e)
            raise

    def load(self, agent_id: str) -> AgentProfile | None:
        """Load an agent profile by ID from disk."""
        file_path = self.storage_dir / f"{agent_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AgentProfile.model_validate(data)
        except Exception as e:
            logger.error("Failed to load agent profile '%s': %s", agent_id, e)
            return None

    def list_all(self) -> list[AgentProfile]:
        """List all persisted agent profiles, sorted by name."""
        self._ensure_dir()
        profiles: list[AgentProfile] = []
        for file in self.storage_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                profiles.append(AgentProfile.model_validate(data))
            except Exception as e:
                logger.warning("Skipping corrupted agent file '%s': %s", file.name, e)

        profiles.sort(key=lambda p: p.name.lower())
        return profiles

    def delete(self, agent_id: str) -> bool:
        """Delete an agent profile by ID."""
        file_path = self.storage_dir / f"{agent_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info("Deleted agent profile '%s'", agent_id)
                return True
            except Exception as e:
                logger.error("Failed to delete agent '%s': %s", agent_id, e)
                return False
        return False
