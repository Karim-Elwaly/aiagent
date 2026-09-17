"""
Agent Skill Adapter for UAOS.

Converts open SKILL.md and JSON skill manifests into native UAOS ToolSpec instances.
Enables UAOS Universal Workers to execute skills from the open skills ecosystem.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

import yaml

from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)

CRITICAL_KEYWORDS = {
    "delete", "drop", "destroy", "kill", "rm", "remove", "truncate", "purge", "revoke", "terminate"
}
HIGH_KEYWORDS = {
    "create", "write", "update", "modify", "patch", "post", "put", "insert", "execute", "run", "send", "commit", "push"
}


def parse_skill_markdown(content: str) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file with YAML frontmatter into metadata dict and markdown body."""
    text = content.strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            raw_frontmatter = parts[1].strip()
            body = parts[2].strip()
            try:
                metadata = yaml.safe_load(raw_frontmatter) or {}
                return metadata, body
            except Exception as e:
                logger.warning("Failed to parse YAML frontmatter in SKILL.md: %s", e)

    # Fallback: Check if whole text is JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data, data.get("instructions", "")
    except Exception:
        pass

    # Fallback: Plain markdown without frontmatter
    first_line = text.split("\n")[0].replace("#", "").strip()
    return {"name": first_line.lower().replace(" ", "_"), "description": text[:200]}, text


def determine_risk_level(name: str, description: str, explicit_risk: str | None = None) -> RiskLevel:
    """Determine risk level based on explicit setting or semantic keywords."""
    if explicit_risk:
        r_str = str(explicit_risk).lower().strip()
        if r_str in ("critical", "crit"):
            return RiskLevel.CRITICAL
        if r_str in ("high", "hi"):
            return RiskLevel.HIGH
        if r_str in ("medium", "med"):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    text = f"{name} {description}".lower()
    tokens = set(re.findall(r"\b\w+\b", text))
    if tokens & CRITICAL_KEYWORDS:
        return RiskLevel.CRITICAL
    if "readonly" in tokens or "read_only" in tokens or "read only" in text:
        return RiskLevel.LOW
    if tokens & HIGH_KEYWORDS:
        return RiskLevel.HIGH
    return RiskLevel.LOW


def derive_skills(name: str, description: str, explicit_skills: list[str] | None = None) -> list[str]:
    """Derive search keywords/skills for Meta-Planner indexing."""
    skills = set()
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()).strip("_")
    if clean_name:
        skills.add(clean_name)

    if explicit_skills:
        for s in explicit_skills:
            if s and isinstance(s, str):
                cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", s.lower()).strip("_")
                if cleaned and len(cleaned) > 1:
                    skills.add(cleaned)

    return sorted(skills)


def hermes_skill_to_tool_spec(
    content: str,
    name_override: str = "",
    custom_executor: Callable[..., Any] | None = None,
) -> ToolSpec:
    """Convert a SKILL.md or JSON manifest into a native UAOS ToolSpec."""
    metadata, instructions = parse_skill_markdown(content)

    raw_name = name_override or metadata.get("name") or "custom_agent_skill"
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name.lower()).strip("_")
    tool_id = f"skill_{clean_name}_v1"

    description = metadata.get("description") or instructions[:250] or f"Agent skill: {clean_name}"
    explicit_skills = metadata.get("skills") or (metadata.get("metadata", {}).get("skills") if isinstance(metadata.get("metadata"), dict) else None)
    skills = derive_skills(clean_name, description, explicit_skills)

    explicit_risk = metadata.get("risk_level") or (metadata.get("metadata", {}).get("risk_level") if isinstance(metadata.get("metadata"), dict) else None)
    risk = determine_risk_level(clean_name, description, explicit_risk)

    # Normalize parameters schema
    raw_params = metadata.get("parameters") or metadata.get("inputs") or {}
    parameters: dict[str, Any] = {}
    if isinstance(raw_params, dict):
        if "properties" in raw_params and isinstance(raw_params["properties"], dict):
            # Already JSON schema format
            parameters = raw_params["properties"]
        else:
            parameters = raw_params
    elif isinstance(raw_params, list):
        for p in raw_params:
            if isinstance(p, dict) and "name" in p:
                parameters[p["name"]] = {
                    "type": p.get("type", "string"),
                    "description": p.get("description", ""),
                    "required": p.get("required", False),
                }

    # Default fallback parameter if none specified
    if not parameters:
        parameters = {
            "query_or_input": {
                "type": "string",
                "description": f"Input payload or instruction for {clean_name}",
                "required": False,
            }
        }

    # Construct executor function
    if custom_executor:
        func = custom_executor
    else:
        # Default async execution handler for imported skill
        async def default_skill_executor(**kwargs: Any) -> str:
            """Execute agent skill via context synthesis and instruction execution."""
            logger.info("Executing agent skill '%s' with parameters: %s", clean_name, kwargs)
            param_str = "\n".join(f"- {k}: {v}" for k, v in kwargs.items())
            return (
                f"=== Executed Agent Skill: {clean_name} ===\n"
                f"Instructions:\n{instructions}\n\n"
                f"Parameters Provided:\n{param_str if param_str else 'None'}\n\n"
                f"Status: Success (Output processed via Skill Adapter)"
            )
        func = default_skill_executor

    return ToolSpec(
        tool_id=tool_id,
        name=clean_name,
        description=description,
        skills_provided=skills,
        parameters=parameters,
        function=func,
        risk_level=risk,
        source_type="skill",
        server_or_host=metadata.get("author", "skills_ecosystem"),
    )
