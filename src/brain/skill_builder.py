"""
UAOS Skill & Agent Builder

Leverages LLM capabilities to:
1. Auto-generate Python tool code from natural language descriptions.
2. Synthesize complete agent configurations (personas, curated skills, templates) from requirements.
3. Validate and register new custom tools dynamically with persistent storage in data/custom_tools/.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Any

from src.core.agent_models import (
    AgentGenerateResponse,
    SkillGenerateResponse,
)
from src.core.config import ROOT_DIR
from src.core.llm_client import LocalLLMClient
from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

DEFAULT_CUSTOM_TOOLS_DIR = ROOT_DIR / "data" / "custom_tools"


class SkillBuilder:
    """LLM-assisted generator and registrar for custom tools and agent configurations."""

    def __init__(
        self,
        llm: LocalLLMClient,
        custom_tools_dir: Path | str | None = None,
    ) -> None:
        self.llm = llm
        self.custom_tools_dir = (
            Path(custom_tools_dir) if custom_tools_dir else DEFAULT_CUSTOM_TOOLS_DIR
        )
        self.custom_tools_dir.mkdir(parents=True, exist_ok=True)

    async def generate_tool(
        self,
        description: str,
        suggested_name: str = "",
        available_skills: list[str] | None = None,
    ) -> SkillGenerateResponse:
        """Generate a Python tool function and ToolSpec declaration from natural language."""
        skills_hint = (
            f"Available system skills: {', '.join(available_skills)}"
            if available_skills
            else ""
        )
        name_hint = f"Suggested function name: {suggested_name}" if suggested_name else ""

        system_prompt = f"""You are an expert Python engineer generating a sandboxed tool for the UAOS Universal Agent Orchestration System.
You will receive a description of a tool to implement in Python.

Output MUST be a single raw valid JSON object with NO markdown formatting, NO backticks, NO explanations outside the JSON:
{{
  "tool_name": "snake_case_tool_name",
  "tool_code": "complete python code as a string",
  "skill_names": ["skill1", "skill2"],
  "risk_level": "low|medium|high",
  "explanation": "concise explanation of what the tool does"
}}

Code Requirements for 'tool_code':
1. Import `from src.core.models import RiskLevel` and `from src.registry.tool_registry import ToolSpec`.
2. Can use Python standard library (json, re, math, datetime, urllib, ssl, socket, etc.) or `httpx`.
3. Must define an `async def <tool_name>(...) -> str:` function.
4. Function MUST return a formatted string (or JSON string).
5. Must declare a module-level constant ending in `_SPEC`:
   `<UPPER_TOOL_NAME>_SPEC = ToolSpec(
       tool_id="<tool_name>_v1",
       name="<tool_name>",
       description="...",
       skills_provided=["skill1", "skill2"],
       parameters={{
           "param_name": {{
               "type": "string|integer|boolean",
               "description": "...",
               "required": True|False
           }}
       }},
       function=<tool_name>,
       risk_level=RiskLevel.<LOW|MEDIUM|HIGH>
   )`
6. The code must be self-contained and syntactically valid Python.
"""

        user_content = f"Tool Request:\n{description}\n{name_hint}\n{skills_hint}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        raw_resp = await self.llm.chat(messages)
        return self._parse_skill_response(raw_resp, description, suggested_name)

    async def generate_agent_profile(
        self,
        description: str,
        available_skills: list[str],
    ) -> AgentGenerateResponse:
        """Synthesize a complete agent profile (name, persona, skills, prompt) from a description."""
        system_prompt = f"""You are an AI architect designing a specialized agent persona for UAOS.
Given a description of what the user wants the agent to do, suggest an optimal configuration.

Available system skills:
{json.dumps(available_skills)}

Output MUST be a single raw JSON object with NO markdown wrapping:
{{
  "suggested_name": "Concise Professional Name",
  "suggested_description": "1-2 sentence description of domain specialty",
  "suggested_icon": "single emoji (e.g. 🛡️, 📊, ⚡, 🔍, 🧪)",
  "suggested_system_prompt_template": "Focused persona instructions for the agent. Placeholders available: {{task_name}}, {{task_description}}, {{tools}}, {{expected_output}}",
  "suggested_skills": ["selected_skill_1", "selected_skill_2"],
  "suggested_tags": ["tag1", "tag2"]
}}

Instructions:
- Only pick skills from the Available system skills list that are relevant.
- Make the system prompt template crisp, authoritative, and focused on the agent's specific domain.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Agent Requirement:\n{description}"},
        ]

        raw_resp = await self.llm.chat(messages)
        return self._parse_agent_response(raw_resp, description, available_skills)

    def register_generated_tool(
        self,
        tool_code: str,
        tool_name: str,
        registry: ToolRegistry,
        persist: bool = True,
    ) -> ToolSpec:
        """Validate, compile, register, and optionally persist generated tool code."""
        # 1. Syntax validation via AST
        try:
            ast.parse(tool_code)
        except SyntaxError as e:
            raise ValueError(f"Generated Python code has syntax errors: {e}") from e

        # 2. Execute code in dedicated namespace
        namespace: dict[str, Any] = {}
        try:
            exec(tool_code, namespace)  # noqa: S102
        except Exception as e:
            raise RuntimeError(f"Failed to execute generated tool code: {e}") from e

        # 3. Locate ToolSpec instance
        tool_spec: ToolSpec | None = None
        for key, val in namespace.items():
            if isinstance(val, ToolSpec):
                tool_spec = val
                break

        if not tool_spec:
            raise ValueError(
                "No ToolSpec instance found in generated code. Code must define a ToolSpec."
            )

        # 4. Register with runtime registry
        registry.register(tool_spec)

        # 5. Persist to disk for auto-discovery
        if persist:
            safe_name = re.sub(r"[^\w-]", "_", tool_name).lower()
            file_path = self.custom_tools_dir / f"{safe_name}.py"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(tool_code)
            logger.info("Persisted custom tool '%s' to %s", tool_spec.name, file_path)

        return tool_spec

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract valid JSON dict from text that might contain code blocks or chatter."""
        cleaned = text.strip()
        # Remove markdown code fences if present
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        # Try direct parse
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        # Try regex extract between first { and last }
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            substring = cleaned[first : last + 1]
            return json.loads(substring)

        raise ValueError(f"Could not extract valid JSON from LLM output: {text[:200]}")

    def _parse_skill_response(
        self, raw: str, description: str, suggested_name: str
    ) -> SkillGenerateResponse:
        try:
            data = self._extract_json(raw)
            name = data.get("tool_name") or suggested_name or "custom_tool"
            name = re.sub(r"[^\w_]", "", name.lower())
            code = data.get("tool_code", "")
            skills = data.get("skill_names", [name])
            risk = data.get("risk_level", "medium").lower()
            explanation = data.get("explanation", "Auto-generated tool")

            return SkillGenerateResponse(
                tool_name=name,
                tool_code=code,
                skill_names=skills,
                risk_level=risk,
                explanation=explanation,
            )
        except Exception as e:
            logger.warning("Falling back from failed LLM skill JSON parse: %s", e)
            fallback_name = re.sub(r"[^\w_]", "", (suggested_name or "custom_tool").lower())
            fallback_code = f'''from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

async def {fallback_name}() -> str:
    """{description}"""
    return "Executed {fallback_name}"

{fallback_name.upper()}_SPEC = ToolSpec(
    tool_id="{fallback_name}_v1",
    name="{fallback_name}",
    description="{description}",
    skills_provided=["{fallback_name}"],
    parameters={{}},
    function={fallback_name},
    risk_level=RiskLevel.LOW,
)
'''
            return SkillGenerateResponse(
                tool_name=fallback_name,
                tool_code=fallback_code,
                skill_names=[fallback_name],
                risk_level="low",
                explanation=f"Fallback template for: {description}",
            )

    def _parse_agent_response(
        self, raw: str, description: str, available_skills: list[str]
    ) -> AgentGenerateResponse:
        try:
            data = self._extract_json(raw)
            return AgentGenerateResponse(
                suggested_name=data.get("suggested_name", "Custom Agent"),
                suggested_description=data.get("suggested_description", description),
                suggested_icon=data.get("suggested_icon", "🤖"),
                suggested_system_prompt_template=data.get("suggested_system_prompt_template", ""),
                suggested_skills=data.get("suggested_skills", available_skills[:3]),
                suggested_tags=data.get("suggested_tags", ["custom"]),
            )
        except Exception as e:
            logger.warning("Falling back from failed LLM agent JSON parse: %s", e)
            return AgentGenerateResponse(
                suggested_name="Specialist Agent",
                suggested_description=description,
                suggested_icon="🤖",
                suggested_system_prompt_template=(
                    f"You are a dedicated specialist focusing on: {description}.\n"
                    "Execute the assigned task with high precision.\n\n"
                    "# Your Task\n{task_name}\n{task_description}\n\n"
                    "# Expected Output\n{expected_output}\n\n"
                    "# Available Tools\n{tools}"
                ),
                suggested_skills=available_skills[:4] if available_skills else [],
                suggested_tags=["assistant"],
            )
