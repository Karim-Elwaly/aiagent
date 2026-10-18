"""
aiagent skills as Hermes skills.

Each Hermes profile gets aiagent's skills as ``SKILL.md`` folders in ``data/hermes/skills/<profile>/``, which the
profile reads through ``skills.external_dirs`` (Hermes treats those as externally owned and does not edit them):

* every tool of aiagent that serves a skill the agent is curated with (all tools for an agent without curation)
  becomes one skill naming its ``mcp__aiagent__`` tool and parameters, tagged with the skills it provides;
* every skill document imported into ``data/hermes_skills/`` that the agent's skills cover is copied as written.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from src.core.config import ROOT_DIR
from src.registry.hermes.hermes_adapter import hermes_skill_to_tool_spec
from src.registry.hermes.hermes_loader import HERMES_SKILLS_DIR
from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

SKILL_FILE = "SKILL.md"
MCP_PREFIX = "mcp__aiagent__"
# Skill documents imported from Hermes: Hermes already has them, so they are not exported back.
HERMES_ORIGIN_FILE = ROOT_DIR / "data" / "hermes" / "hermes_origin_skills.json"
# Tool sources that are not real aiagent tools over MCP (skill-document echoes, simulated hermes_* tools).
NON_MCP_SOURCES = frozenset({"skill", "hermes"})
_DESCRIPTION_LIMIT = 900


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "skill"


def flat_parameters(spec: ToolSpec) -> dict[str, Any]:
    """``{name: {type, required, ...}}`` for both parameter styles: flat (native tools) and JSON schema (connectors)."""
    params = spec.parameters or {}
    if not isinstance(params.get("properties"), dict):
        return params
    required = set(params.get("required") or [])
    return {
        name: {**prop, "required": name in required} if isinstance(prop, dict) else prop
        for name, prop in params["properties"].items()
    }


def _param_lines(spec: ToolSpec) -> list[str]:
    lines = []
    for pname, raw in flat_parameters(spec).items():
        prop = raw if isinstance(raw, dict) else {}
        flags = [str(prop.get("type", "any"))]
        if prop.get("required"):
            flags.append("required")
        if "default" in prop:
            flags.append(f"default {json.dumps(prop['default'])}")
        desc = str(prop.get("description", "")).strip()
        lines.append(f"- `{pname}` ({', '.join(flags)})" + (f": {desc}" if desc else ""))
    return lines or ["- no parameters"]


def capability_skill(tool: ToolSpec, skills: list[str]) -> str:
    """A Hermes ``SKILL.md`` for one aiagent MCP tool, tagged with the aiagent skills it provides."""
    full_name = f"{MCP_PREFIX}{tool.name}"
    description = f"aiagent MCP tool {full_name} (skills: {', '.join(skills)})."
    lead = tool.description.strip().split("\n")[0]
    if lead:
        description += f" {lead}"
    frontmatter = "\n".join([
        "---",
        f"name: {json.dumps('aiagent-' + slug(tool.name))}",
        f"description: {json.dumps(description[:_DESCRIPTION_LIMIT])}",
        "version: 1.0.0",
        "author: aiagent",
        "metadata:",
        "  hermes:",
        f"    tags: {json.dumps(['aiagent', *skills])}",
        "  aiagent:",
        f"    tool: {json.dumps(tool.name)}",
        "---",
    ])
    body = [
        f"# {tool.name} (aiagent)",
        "",
        "aiagent provides this tool through its MCP server `aiagent`. Call it directly; it runs on "
        "the aiagent host and returns real data. A tool the agent is not approved for asks the operator first.",
        "",
        f"## {full_name}",
        "",
        tool.description.strip(),
        "",
        f"Risk: {tool.risk_level.value}. Parameters:",
        *_param_lines(tool),
    ]
    return frontmatter + "\n\n" + "\n".join(body) + "\n"


def imported_skill(content: str, name: str, description: str) -> str:
    """An imported skill document, as written when its frontmatter is valid Hermes frontmatter, otherwise with
    a valid frontmatter (name, description) in front of its instructions."""
    text = content.strip()
    raw, body = None, text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            raw, body = parts[1], parts[2].strip()
    if raw is not None:
        try:
            meta = yaml.safe_load(raw)
        except yaml.YAMLError:
            meta = None
        if isinstance(meta, dict) and meta.get("name") and meta.get("description"):
            return content if content.endswith("\n") else content + "\n"
        found = re.search(r"^description:\s*(.+)$", raw, re.MULTILINE)
        if found:
            description = found.group(1).strip().strip("\"'")
    frontmatter = "\n".join([
        "---",
        f"name: {json.dumps(slug(name))}",
        f"description: {json.dumps(description[:_DESCRIPTION_LIMIT])}",
        "version: 1.0.0",
        "author: aiagent",
        "---",
    ])
    return f"{frontmatter}\n\n{body}\n"


def hermes_origin_skills() -> set[str]:
    try:
        return set(json.loads(HERMES_ORIGIN_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return set()


def mark_hermes_origin(name: str) -> None:
    names = hermes_origin_skills() | {name}
    HERMES_ORIGIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    HERMES_ORIGIN_FILE.write_text(json.dumps(sorted(names)), encoding="utf-8")


def skill_documents(
    agent: Any,
    registry: ToolRegistry | None,
    imported_dir: Path | None = None,
    focus_tools: set[str] | None = None,
    focus_skills: set[str] | None = None,
) -> dict[str, str]:
    """``{folder name: SKILL.md content}`` for an agent (``None`` = tasks without an agent).

    ``focus_tools``/``focus_skills`` (one task's tools and required skills) keep only the documents that task can use;
    leaving both ``None`` returns everything the agent is curated for.
    """
    curated = set(getattr(agent, "curated_skills", None) or [])
    docs: dict[str, str] = {}

    if registry is not None:
        for spec in sorted(registry.get_all_tools(), key=lambda t: t.name):
            if spec.source_type in NON_MCP_SOURCES:
                continue
            if focus_tools is not None and spec.name not in focus_tools:
                continue
            provided = [s for s in spec.skills_provided if not curated or s in curated]
            if provided:
                docs[f"aiagent-{slug(spec.name)}"] = capability_skill(spec, provided)

    source = imported_dir or HERMES_SKILLS_DIR
    from_hermes = hermes_origin_skills()
    for path in sorted(source.glob("*.md")) if source.is_dir() else []:
        if path.stem in from_hermes:
            continue
        try:
            content = path.read_text(encoding="utf-8")
            spec = hermes_skill_to_tool_spec(content, name_override=path.stem)
        except Exception as exc:  # a broken document must not stop the run
            logger.warning("Skipping skill document '%s': %s", path.name, exc)
            continue
        if curated and spec.name not in curated and not curated & set(spec.skills_provided):
            continue
        if focus_tools is not None and spec.name not in focus_tools and not focus_tools & set(spec.skills_provided):
            continue
        if focus_skills is not None and spec.name not in focus_skills and not focus_skills & set(spec.skills_provided):
            continue
        docs.setdefault(slug(path.stem), imported_skill(content, path.stem, spec.description))
    return docs


def write_skills(dest: Path, docs: dict[str, str]) -> bool:
    """Make ``dest`` hold exactly ``docs`` (one folder per skill); True when anything changed."""
    dest.mkdir(parents=True, exist_ok=True)
    changed = False
    for folder, content in docs.items():
        path = dest / folder / SKILL_FILE
        try:
            if path.read_text(encoding="utf-8") == content:
                continue
        except OSError:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        changed = True
    for child in dest.iterdir():
        if child.is_dir() and child.name not in docs and (child / SKILL_FILE).exists():
            shutil.rmtree(child)
            changed = True
    return changed
