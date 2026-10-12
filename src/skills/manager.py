"""
UAOS Skill Manager (Gap 5)

Manages persistence, approval lifecycle (HITL), and ToolRegistry promotion
for autonomously distilled agent skills.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR

logger = logging.getLogger(__name__)

SKILLS_DIR = ROOT_DIR / "data" / "skills"
PENDING_DIR = SKILLS_DIR / "pending"
APPROVED_DIR = SKILLS_DIR / "approved"
REJECTED_DIR = SKILLS_DIR / "rejected"
CUSTOM_TOOLS_DIR = ROOT_DIR / "data" / "custom_tools"


@dataclass
class SkillCandidate:
    id: str
    name: str
    goal: str
    description: str
    code: str
    parameters: dict[str, Any]
    skills_provided: list[str]
    author: str = "autonomous_distiller"
    source_workflow: str = ""
    supervisor_score: float = 1.0
    tool_trace_len: int = 2
    status: str = "pending_approval"  # 'pending_approval' | 'approved' | 'rejected'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    rejection_reason: str = ""


class SkillManager:
    """Manages storage and lifecycle for distilled candidate skills."""

    def __init__(self, base_dir: Path = SKILLS_DIR):
        self.base_dir = base_dir
        self.pending_dir = base_dir / "pending"
        self.approved_dir = base_dir / "approved"
        self.rejected_dir = base_dir / "rejected"

        for d in [self.pending_dir, self.approved_dir, self.rejected_dir, CUSTOM_TOOLS_DIR]:
            d.mkdir(parents=True, exist_ok=True)

    def save_candidate(self, candidate: SkillCandidate) -> Path:
        """Persist a candidate skill to disk."""
        target_dir = self.approved_dir if candidate.status == "approved" else self.pending_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        meta_path = target_dir / f"{candidate.name}.json"
        code_path = target_dir / f"{candidate.name}.py"

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(asdict(candidate), f, indent=2)

        code_path.write_text(candidate.code, encoding="utf-8")

        # If already approved (auto-promote), also copy to custom_tools
        if candidate.status == "approved":
            tool_dest = CUSTOM_TOOLS_DIR / f"{candidate.name}.py"
            code_path_target = target_dir / f"{candidate.name}.py"
            shutil.copy2(code_path_target, tool_dest)
            logger.info("Auto-promoted skill '%s' to %s", candidate.name, tool_dest)

        return meta_path

    def list_pending(self) -> list[SkillCandidate]:
        """List all skills awaiting human operator review."""
        candidates = []
        for jf in self.pending_dir.glob("*.json"):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                candidates.append(SkillCandidate(**data))
            except Exception as e:
                logger.warning("Failed to load candidate %s: %s", jf.name, e)
        return candidates

    def list_approved(self) -> list[SkillCandidate]:
        """List all approved, active skills."""
        approved = []
        for jf in self.approved_dir.glob("*.json"):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                approved.append(SkillCandidate(**data))
            except Exception as e:
                logger.warning("Failed to load approved skill %s: %s", jf.name, e)
        return approved

    def approve(self, skill_name_or_id: str) -> bool:
        """Promote a pending skill to approved and hot-deploy to custom tools."""
        candidate = self._find_candidate(self.pending_dir, skill_name_or_id)
        if not candidate:
            logger.warning("Skill '%s' not found in pending skills", skill_name_or_id)
            return False

        candidate.status = "approved"

        # Remove from pending
        pending_meta = self.pending_dir / f"{candidate.name}.json"
        pending_py = self.pending_dir / f"{candidate.name}.py"
        if pending_meta.exists():
            pending_meta.unlink()
        if pending_py.exists():
            pending_py.unlink()

        # Save to approved and copy to custom_tools
        self.save_candidate(candidate)

        # Hot-load into active registry if available
        try:
            from src.orchestrator.activities import _get_registry
            reg = _get_registry()
            from src.registry.auto_discover import register_all_tools
            register_all_tools(reg)
            logger.info("Hot-reloaded tool registry with newly approved skill '%s'", candidate.name)
        except Exception as e:
            logger.debug("Live tool registry reload skipped or failed: %s", e)

        return True

    def reject(self, skill_name_or_id: str, reason: str = "") -> bool:
        """Reject a candidate skill."""
        candidate = self._find_candidate(self.pending_dir, skill_name_or_id)
        if not candidate:
            return False

        candidate.status = "rejected"
        candidate.rejection_reason = reason

        pending_meta = self.pending_dir / f"{candidate.name}.json"
        pending_py = self.pending_dir / f"{candidate.name}.py"
        if pending_meta.exists():
            pending_meta.unlink()
        if pending_py.exists():
            pending_py.unlink()

        # Save to rejected
        rej_meta = self.rejected_dir / f"{candidate.name}.json"
        with open(rej_meta, "w", encoding="utf-8") as f:
            json.dump(asdict(candidate), f, indent=2)

        return True

    def _find_candidate(self, search_dir: Path, identifier: str) -> SkillCandidate | None:
        ident_lower = identifier.lower().strip()
        for jf in search_dir.glob("*.json"):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cand = SkillCandidate(**data)
                if cand.id.lower() == ident_lower or cand.name.lower() == ident_lower:
                    return cand
            except Exception:
                pass
        return None

    def get_known_skills_summary(self) -> list[dict[str, Any]]:
        """Return compact metadata for all approved skills to provide to planner."""
        skills = self.list_approved()
        return [
            {
                "name": s.name,
                "description": s.description,
                "skills_provided": s.skills_provided,
                "goal": s.goal,
            }
            for s in skills
        ]


_SKILL_MANAGER: SkillManager | None = None


def get_skill_manager() -> SkillManager:
    global _SKILL_MANAGER
    if _SKILL_MANAGER is None:
        _SKILL_MANAGER = SkillManager()
    return _SKILL_MANAGER
