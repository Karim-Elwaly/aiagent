"""
Agent Skills Loader and Persistence Manager.

Discovers, imports, and manages persistent agent skills stored in data/hermes_skills/.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR
from src.registry.hermes.hermes_adapter import hermes_skill_to_tool_spec, parse_skill_markdown
from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

HERMES_SKILLS_DIR = ROOT_DIR / "data" / "hermes_skills"


def get_hermes_skills_dir() -> Path:
    """Ensure and return the Hermes skills directory."""
    HERMES_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    return HERMES_SKILLS_DIR


def import_and_persist_hermes_skill(
    content: str,
    name_override: str = "",
    registry: ToolRegistry | None = None,
    persist: bool = True,
) -> ToolSpec:
    """Parse, convert, optionally register, and persist a Hermes skill."""
    spec = hermes_skill_to_tool_spec(content, name_override=name_override)

    if registry:
        registry.register(spec)
        logger.info("Registered Hermes skill '%s' into ToolRegistry", spec.name)

    if persist:
        skills_dir = get_hermes_skills_dir()
        file_path = skills_dir / f"{spec.name}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Persisted Hermes skill '%s' to %s", spec.name, file_path)

    return spec


def load_all_hermes_skills(registry: ToolRegistry) -> int:
    """Scan data/hermes_skills/ and register all valid skills into ToolRegistry."""
    skills_dir = get_hermes_skills_dir()
    count = 0
    for file_path in skills_dir.glob("*.md"):
        try:
            content = file_path.read_text(encoding="utf-8")
            spec = hermes_skill_to_tool_spec(content, name_override=file_path.stem)
            registry.register(spec)
            count += 1
            logger.info("Discovered Hermes skill '%s' from %s", spec.name, file_path.name)
        except Exception as e:
            logger.error("Failed to load Hermes skill file '%s': %s", file_path.name, e)

    return count


def list_hermes_skills_catalog() -> list[dict[str, Any]]:
    """Return summary metadata for all imported/persisted Hermes skills."""
    skills_dir = get_hermes_skills_dir()
    catalog = []
    for file_path in sorted(skills_dir.glob("*.md")):
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata, _ = parse_skill_markdown(content)
            catalog.append({
                "name": file_path.stem,
                "title": metadata.get("name", file_path.stem),
                "description": metadata.get("description", ""),
                "version": metadata.get("version", "1.0.0"),
                "author": metadata.get("author", "hermes_community"),
                "skills": metadata.get("skills", [file_path.stem]),
                "risk_level": metadata.get("risk_level", "low"),
                "file": file_path.name,
            })
        except Exception as e:
            logger.warning("Error reading metadata from '%s': %s", file_path.name, e)
    return catalog
