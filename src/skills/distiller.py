"""
UAOS Autonomous Skill Distiller (Gap 5)

Extracts reusable composite skills from successful multi-step workflow traces.
Validates code safety via AST parsing and sandbox compilation before saving as candidate.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from src.core.config import get_settings
from src.core.llm_client import LocalLLMClient
from src.core.models import RiskLevel
from src.orchestrator.event_bus import emit_skill_candidate, get_event_bus
from src.skills.manager import SkillCandidate, get_skill_manager

logger = logging.getLogger(__name__)

FORBIDDEN_CALLS = frozenset({"eval", "exec", "__import__", "breakpoint", "input", "compile"})
FORBIDDEN_MODULES = frozenset({
    "pty", "ctypes", "subprocess", "commands", "multiprocessing", "pickle", "socket"
})


def validate_skill_ast(code: str) -> tuple[bool, str]:
    """Inspect AST to guarantee distilled skill code contains no dangerous calls or imports.

    Returns:
        (is_safe, error_or_reason)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError in skill code: {e}"

    for node in ast.walk(tree):
        # Disallowed imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg in FORBIDDEN_MODULES:
                    return False, f"Disallowed import: '{alias.name}'"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                if root_pkg in FORBIDDEN_MODULES:
                    return False, f"Disallowed import from: '{node.module}'"

        # Disallowed calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALLS:
                    return False, f"Forbidden function call: '{node.func.id}()'"

    return True, "AST validation passed"


class SkillDistiller:
    """Distills successful multi-step executions into reusable skills."""

    def __init__(self, llm: LocalLLMClient | None = None):
        self.llm = llm

    def _sanitize_name(self, goal: str) -> str:
        """Create a clean python identifier from a task goal."""
        words = re.findall(r"[a-zA-Z0-9]+", goal.lower())
        slug = "_".join(words[:4]) or "custom_skill"
        return f"distilled_{slug}"

    async def distill(
        self,
        goal: str,
        tool_trace: list[dict[str, Any]],
        supervisor_score: float = 1.0,
        workflow_id: str = "",
    ) -> SkillCandidate | None:
        """Attempt to distill an execution trace into a reusable SkillCandidate.

        Args:
            goal: The task goal or problem solved.
            tool_trace: Sequence of tool calls made: [{"tool": name, "args": {...}, "result": "..."}].
            supervisor_score: Quality score from supervisor evaluation.
            workflow_id: Workflow execution ID.

        Returns:
            SkillCandidate if successfully distilled and validated, else None.
        """
        settings = get_settings()
        if not getattr(settings, "enable_skill_learning", False):
            logger.debug("Skill learning is disabled (enable_skill_learning=False)")
            return None

        # Trace quality filters
        min_score = getattr(settings, "skill_min_score", 0.9)
        if supervisor_score < min_score:
            logger.debug("Supervisor score %.2f below threshold %.2f for distillation", supervisor_score, min_score)
            return None

        if len(tool_trace) < 2:
            logger.debug("Tool trace length %d < 2; skipping distillation of single tool call", len(tool_trace))
            return None

        skill_name = self._sanitize_name(goal)
        func_name = f"run_{skill_name}"
        spec_name = f"{skill_name.upper()}_SPEC"

        # Generate distilled skill code
        code = await self._generate_skill_code(skill_name, func_name, spec_name, goal, tool_trace)
        if not code:
            return None

        # Safety & AST check
        is_safe, reason = validate_skill_ast(code)
        if not is_safe:
            logger.warning("Distilled skill '%s' rejected by AST safety check: %s", skill_name, reason)
            return None

        # Sandbox compile test
        try:
            compile(code, f"<distilled_{skill_name}>", "exec")
        except Exception as e:
            logger.warning("Distilled skill '%s' failed compilation: %s", skill_name, e)
            return None

        candidate = SkillCandidate(
            id=f"skill_{skill_name}",
            name=skill_name,
            goal=goal,
            description=f"Automated distilled skill for: {goal}",
            code=code,
            parameters={
                "input_query": {
                    "type": "string",
                    "description": "Optional input parameters or task query to process.",
                    "required": False,
                }
            },
            skills_provided=[skill_name, "distilled_skill"],
            author="autonomous_distiller",
            source_workflow=workflow_id,
            supervisor_score=supervisor_score,
            tool_trace_len=len(tool_trace),
            status="approved" if getattr(settings, "skill_auto_promote", False) else "pending_approval",
        )

        manager = get_skill_manager()
        manager.save_candidate(candidate)

        # Emit telemetry
        emit_skill_candidate(workflow_id, candidate.id, skill_name, supervisor_score)

        logger.info("Successfully distilled skill '%s' (status: %s)", skill_name, candidate.status)
        return candidate

    async def _generate_skill_code(
        self,
        skill_name: str,
        func_name: str,
        spec_name: str,
        goal: str,
        tool_trace: list[dict[str, Any]],
    ) -> str:
        """Synthesize executable python skill code for the trace."""
        # Clean trace summary
        trace_summary = []
        for step in tool_trace[:6]:
            t_name = step.get("tool") or step.get("name") or "unknown"
            t_args = step.get("args") or step.get("arguments") or {}
            trace_summary.append({"tool": t_name, "args": t_args})

        # Try LLM distillation if LLM client is available
        if self.llm:
            try:
                prompt = (
                    f"Synthesize a standalone, robust Python async function and ToolSpec for this composite agent skill.\n\n"
                    f"Skill Name: {skill_name}\n"
                    f"Goal: {goal}\n"
                    f"Tool Sequence:\n{json.dumps(trace_summary, indent=2)}\n\n"
                    f"Requirements:\n"
                    f"1. Define `async def {func_name}(input_query: str = '') -> str:`\n"
                    f"2. Use existing registry tools or standard libraries. Do NOT import forbidden modules (ctypes, subprocess, pty).\n"
                    f"3. Define `{spec_name} = ToolSpec(...)` with risk_level=RiskLevel.LOW\n"
                    f"4. Return ONLY valid Python code block."
                )
                resp = await self.llm.chat([
                    {"role": "system", "content": "You are a code synthesis assistant specializing in safe agent skills."},
                    {"role": "user", "content": prompt},
                ])
                # Extract code from ```python ... ```
                code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", resp, re.DOTALL)
                if code_match:
                    return code_match.group(1).strip()
            except Exception as e:
                logger.debug("LLM skill synthesis failed, falling back to deterministic template: %s", e)

        # Deterministic fallback template
        steps_code = []
        for idx, step in enumerate(trace_summary):
            t_name = step["tool"]
            t_args_str = json.dumps(step["args"])
            steps_code.append(
                f"    # Step {idx + 1}: Execute {t_name}\n"
                f"    step_{idx + 1}_res = await execute_subtool('{t_name}', {t_args_str})\n"
                f"    results.append(f'[{t_name}]: {{step_{idx + 1}_res}}')"
            )

        joined_steps = "\n".join(steps_code)

        template = f'''"""
Distilled Skill: {skill_name}
Goal: {goal}
Generated by UAOS Autonomous Distiller.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolSpec

logger = logging.getLogger(__name__)


async def execute_subtool(tool_name: str, args: dict[str, Any]) -> str:
    """Helper to dispatch subtool calls."""
    try:
        from src.orchestrator.activities import _get_registry
        reg = _get_registry()
        spec = reg.get(tool_name)
        if spec and spec.function:
            import inspect
            if inspect.iscoroutinefunction(spec.function):
                return str(await spec.function(**args))
            return str(spec.function(**args))
        return f"Tool {{tool_name}} not found in registry"
    except Exception as e:
        return f"Error executing {{tool_name}}: {{e}}"


async def {func_name}(input_query: str = "") -> str:
    """Automated composite workflow for: {goal}"""
    results = []
{joined_steps}
    return "\\n".join(results)


{spec_name} = ToolSpec(
    tool_id="distilled_{skill_name}_v1",
    name="{skill_name}",
    description="Automated composite workflow: {goal}",
    skills_provided=["{skill_name}", "distilled_skill"],
    parameters={{
        "input_query": {{
            "type": "string",
            "description": "Optional parameters or goal refinement.",
            "required": False,
        }}
    }},
    function={func_name},
    risk_level=RiskLevel.LOW,
    source_type="distilled",
    server_or_host="in_process",
)
'''
        return template
