"""
UAOS Tool Registry

Central catalog of all available tools/skills. Tools register themselves
with abstract skill names. The Skill/Tool Injector queries by skill
and gets back concrete tool implementations.

Architecture:
  - Tools declare what abstract skills they provide
  - The Meta-Planner sees only skill names (never tool internals)
  - The registry resolves skill → tool at execution time
  - Adding a new tool = one function + one ToolSpec. Zero orchestration changes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from src.core.models import RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    """Describes a registered tool and its capabilities.

    This is the contract between a tool implementation and the system.
    The Meta-Planner sees `skills_provided` as available capabilities.
    The Worker sees `name`, `description`, and `parameters` to know
    how to call it.
    """

    tool_id: str  # unique identifier, e.g. "web_search_v1"
    name: str  # function name the LLM will use in tool calls
    description: str  # human-readable, shown to LLM in worker prompt
    skills_provided: list[str]  # abstract skill names this tool satisfies
    parameters: dict[str, Any]  # JSON schema for function parameters
    function: Callable[..., Coroutine]  # the actual async function to call
    risk_level: RiskLevel = RiskLevel.LOW
    source_type: str = "native"  # "native" | "mcp" | "openapi"
    server_or_host: str = ""  # origin identifier (e.g., mcp server command, API base URL)


class ToolRegistry:
    """Central catalog of all available tools.

    Usage:
        registry = ToolRegistry()
        registry.register(my_tool_spec)

        # At planning time — feed skill names to the Meta-Planner
        skills = registry.list_skills()

        # At execution time — resolve skills to concrete tools
        tools = registry.resolve(["web_search", "summarization"])
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}  # tool_id → spec
        self._skill_index: dict[str, list[str]] = {}  # skill → [tool_ids]

    def register(self, spec: ToolSpec) -> None:
        """Register a tool with its skill mappings.

        Can be called at startup (auto-discovery) or dynamically at runtime.
        """
        if spec.tool_id in self._tools:
            logger.warning(
                "Overwriting existing tool registration: %s", spec.tool_id
            )
            # Remove from old skill index before updating
            self.unregister(spec.tool_id)

        self._tools[spec.tool_id] = spec

        for skill in spec.skills_provided:
            if skill not in self._skill_index:
                self._skill_index[skill] = []
            if spec.tool_id not in self._skill_index[skill]:
                self._skill_index[skill].append(spec.tool_id)

        logger.info(
            "Registered tool '%s' (%s) providing skills: %s",
            spec.tool_id,
            spec.source_type,
            spec.skills_provided,
        )

    def register_batch(self, specs: list[ToolSpec]) -> int:
        """Register multiple tools at once."""
        count = 0
        for spec in specs:
            self.register(spec)
            count += 1
        return count

    def unregister(self, tool_id: str) -> bool:
        """Unregister a tool and clean up its skill index entries.

        Returns True if tool was found and removed, False otherwise.
        """
        spec = self._tools.pop(tool_id, None)
        if not spec:
            return False

        # Clean up skill index
        for skill in spec.skills_provided:
            if skill in self._skill_index:
                self._skill_index[skill] = [
                    tid for tid in self._skill_index[skill] if tid != tool_id
                ]
                if not self._skill_index[skill]:
                    del self._skill_index[skill]

        logger.info("Unregistered tool '%s'", tool_id)
        return True

    def unregister_by_source(
        self, source_type: str, server_or_host: str | None = None
    ) -> list[str]:
        """Unregister all tools matching a source type and optional server/host.

        Returns list of removed tool IDs.
        """
        to_remove = [
            tid
            for tid, spec in self._tools.items()
            if spec.source_type == source_type
            and (server_or_host is None or spec.server_or_host == server_or_host)
        ]
        for tid in to_remove:
            self.unregister(tid)
        return to_remove

    def get_tools_by_source(self, source_type: str) -> list[ToolSpec]:
        """Return all tools matching a source type (e.g. 'mcp' or 'openapi')."""
        return [
            spec for spec in self._tools.values() if spec.source_type == source_type
        ]

    def resolve(self, required_skills: list[str]) -> list[ToolSpec]:
        """Resolve abstract skill names to concrete tool specs.

        Deduplicates — if one tool satisfies multiple requested skills,
        it's returned only once.

        Args:
            required_skills: Abstract skill names from a Task.

        Returns:
            List of ToolSpec instances that collectively cover the
            requested skills. May be shorter than required_skills if
            one tool covers multiple skills.
        """
        resolved: dict[str, ToolSpec] = {}
        unresolved: list[str] = []

        for skill in required_skills:
            tool_ids = list(self._skill_index.get(skill, []))
            if not tool_ids:
                # Fuzzy fallback: match by tool name or provided skills substring
                normalized = skill.lower().replace("-", "_").strip()
                for tid, spec in self._tools.items():
                    sname = spec.name.lower()
                    if (
                        normalized in sname
                        or sname in normalized
                        or any(normalized in s.lower() or s.lower() in normalized for s in spec.skills_provided)
                    ):
                        if tid not in tool_ids:
                            tool_ids.append(tid)

            if tool_ids:
                best_id = tool_ids[0]
                if best_id not in resolved:
                    resolved[best_id] = self._tools[best_id]
            else:
                unresolved.append(skill)

        if unresolved:
            logger.warning(
                "No tools found for skills: %s. Available skills: %s",
                unresolved,
                list(self._skill_index.keys()),
            )

        return list(resolved.values())

    def list_skills(self) -> list[str]:
        """Return all available abstract skill names.

        This is fed to the Meta-Planner's system prompt so the LLM
        knows what capabilities exist.
        """
        return sorted(self._skill_index.keys())

    def get_tool(self, tool_id: str) -> ToolSpec | None:
        """Look up a tool by its ID."""
        return self._tools.get(tool_id)

    def has_tool(self, tool_id_or_name: str) -> bool:
        """Check if a tool exists by its tool_id or name."""
        if tool_id_or_name in self._tools:
            return True
        return any(spec.name == tool_id_or_name for spec in self._tools.values())

    def get_all_tools(self) -> list[ToolSpec]:
        """Return all registered tools."""
        return list(self._tools.values())

    def format_tools_for_llm(self, tools: list[ToolSpec]) -> str:
        """Format tool descriptions for injection into a worker's prompt.

        Produces a clear, structured description that the LLM can use
        to understand how to call each tool.
        """
        if not tools:
            return "No tools available. Answer based on your knowledge only."

        lines = []
        for t in tools:
            param_descriptions = []
            for param_name, param_info in t.parameters.items():
                ptype = param_info.get("type", "any")
                desc = param_info.get("description", "")
                required = param_info.get("required", False)
                req_marker = " (required)" if required else " (optional)"
                param_descriptions.append(
                    f"    - {param_name} ({ptype}){req_marker}: {desc}"
                )

            params_block = "\n".join(param_descriptions) if param_descriptions else "    (no parameters)"

            lines.append(
                f"## {t.name}\n"
                f"{t.description}\n"
                f"Parameters:\n{params_block}"
            )

        return "\n\n".join(lines)

    @property
    def tool_count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)

    @property
    def skill_count(self) -> int:
        """Number of unique skills available."""
        return len(self._skill_index)

    def __repr__(self) -> str:
        return (
            f"ToolRegistry(tools={self.tool_count}, "
            f"skills={self.skill_count})"
        )
