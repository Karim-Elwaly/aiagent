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

    async def distill_skill_from_task_solution(
        self,
        user_query: str,
        task_name: str,
        task_description: str,
        solution_output: str,
        tools_used: list[str] | None = None,
    ) -> SkillGenerateResponse:
        """Abstract a successful workflow task execution into a reusable, parameterized Python ToolSpec."""
        system_prompt = """You are an elite Python tool architect for the UAOS Universal Agent Orchestration System.
An agent successfully executed a task to solve a user problem. Your job is to extract and abstract the core reusable procedure into a permanent, self-contained Python tool.

You MUST respond with a single valid JSON object with NO markdown wrapping:
{
  "tool_name": "clean_snake_case_name",
  "tool_code": "complete Python code defining the function and ToolSpec instance",
  "skill_names": ["skill1", "skill2"],
  "risk_level": "low|medium|high",
  "explanation": "Brief explanation of how this tool automates this procedure"
}

Code Requirements:
1. Import RiskLevel and ToolSpec:
   `from src.core.models import RiskLevel`
   `from src.registry.tool_registry import ToolSpec`
2. Implement an async function with full type hints.
3. Expose a ToolSpec constant named `<TOOL_NAME>_SPEC`.
4. The tool must be generalized with parameters so it can handle similar requests in the future, not just hardcoded values.
"""
        user_content = (
            f"Original User Goal: {user_query}\n"
            f"Task: {task_name}\n"
            f"Task Description: {task_description}\n"
            f"Tools Used During Run: {', '.join(tools_used) if tools_used else 'None'}\n"
            f"Successful Output/Result:\n{solution_output[:2500]}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        logger.info("Distilling reusable skill from successful task '%s'", task_name)
        raw_resp = await self.llm.chat(messages)
        return self._parse_skill_response(raw_resp, f"Auto-distilled tool for {task_name}", task_name)


    async def generate_agent_profile(
        self,
        description: str,
        available_skills: list[str],
    ) -> AgentGenerateResponse:
        """Synthesize a complete agent profile (name, persona, skills, prompt) from a description."""
        system_prompt = f"""You are an elite AI architect designing a specialized agent persona for UAOS.
Given a user requirement, synthesize an optimal agent configuration tailored specifically to their domain.

Available system skills:
{json.dumps(available_skills)}

You MUST respond with a single valid JSON object with EXACTLY this structure:
{{
  "suggested_name": "Concise Professional Agent Name (e.g. 'Pitch Deck Strategist')",
  "suggested_description": "1-2 sentence overview of the agent's core mission and domain expertise",
  "suggested_icon": "A single representative emoji (e.g. 📊, 🎯, 💡, 🛡️, ⚡)",
  "suggested_system_prompt_template": "Crisp, authoritative persona instructions for the agent detailing its tone, domain methodology, and execution strategy. Use placeholders: {{task_name}}, {{task_description}}, {{tools}}, {{expected_output}}",
  "suggested_skills": ["relevant_skill_1", "relevant_skill_2"],
  "suggested_tags": ["tag1", "tag2", "tag3"]
}}

Rules:
1. ONLY select skills from the 'Available system skills' list above that are directly relevant.
2. Return ONLY the raw JSON object. Do not include markdown fences or conversational text.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Agent Requirement:\n{description}"},
        ]

        logger.info("Calling LLM to generate agent profile for: %s", description)
        raw_resp = await self.llm.chat(messages)
        logger.info("Received LLM agent response (%d chars)", len(raw_resp) if raw_resp else 0)
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
        """Extract valid JSON dict from text that might contain code blocks, reasoning tags, or chatter."""
        if not text:
            raise ValueError("Empty or None text received for JSON extraction")

        cleaned = str(text).strip()

        # 1. Strip reasoning/thinking tags emitted by models like Qwen or DeepSeek
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE).strip()

        # 2. Strip markdown code fences if present
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        # 3. Direct parse with strict=False (allows unescaped control chars like raw newlines in strings)
        try:
            return json.loads(cleaned, strict=False)
        except Exception:
            pass

        # 4. Try extracting substring between outermost { and }
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            substring = cleaned[first : last + 1]
            try:
                return json.loads(substring, strict=False)
            except Exception:
                pass

            # 5. Fix common LLM JSON syntax errors (trailing commas, unescaped newlines)
            fixed = re.sub(r",\s*([\]}])", r"\1", substring)
            try:
                return json.loads(fixed, strict=False)
            except Exception:
                pass

        # 6. Fallback: regex key-value extraction for known schema fields
        result: dict[str, Any] = {}
        name_m = re.search(r'"suggested_name"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned)
        if name_m:
            result["suggested_name"] = name_m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")

        desc_m = re.search(r'"suggested_description"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned)
        if desc_m:
            result["suggested_description"] = desc_m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")

        icon_m = re.search(r'"suggested_icon"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned)
        if icon_m:
            result["suggested_icon"] = icon_m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")

        prompt_m = re.search(r'"suggested_system_prompt_template"\s*:\s*"([\s\S]*?)"(?=\s*,\s*"suggested_|\s*})', cleaned)
        if prompt_m:
            result["suggested_system_prompt_template"] = prompt_m.group(1)

        skills_m = re.search(r'"suggested_skills"\s*:\s*\[([\s\S]*?)\]', cleaned)
        if skills_m:
            skills_raw = skills_m.group(1)
            result["suggested_skills"] = [s.strip().strip('"\'') for s in skills_raw.split(",") if s.strip().strip('"\'')]

        tags_m = re.search(r'"suggested_tags"\s*:\s*\[([\s\S]*?)\]', cleaned)
        if tags_m:
            tags_raw = tags_m.group(1)
            result["suggested_tags"] = [t.strip().strip('"\'') for t in tags_raw.split(",") if t.strip().strip('"\'')]

        # For tool extraction fallback
        tool_name_m = re.search(r'"tool_name"\s*:\s*"([^"]+)"', cleaned)
        if tool_name_m:
            result["tool_name"] = tool_name_m.group(1)

        if result:
            return result

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
                suggested_name=data.get("suggested_name") or "Specialist Agent",
                suggested_description=data.get("suggested_description") or description,
                suggested_icon=data.get("suggested_icon") or "🤖",
                suggested_system_prompt_template=data.get("suggested_system_prompt_template") or (
                    f"You are a dedicated specialist focusing on: {description}.\n"
                    "Execute the assigned task with high precision.\n\n"
                    "# Your Task\n{task_name}\n{task_description}\n\n"
                    "# Expected Output\n{expected_output}\n\n"
                    "# Available Tools\n{tools}"
                ),
                suggested_skills=data.get("suggested_skills") or (available_skills[:3] if available_skills else []),
                suggested_tags=data.get("suggested_tags") or ["custom"],
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

