"""
UAOS Meta-Planner

The brain of the system. Takes raw user input and produces a structured
TaskDAG via a single LLM call. Includes:
  - Retry-with-error-feedback for local LLM JSON reliability
  - JSON extraction from various LLM output formats
  - DAG integrity validation (missing deps, cycles)
  - Graceful fallback to single-task mode
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from src.brain.prompts import (
    CLARIFICATION_GENERATOR_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    REPLAN_SYSTEM_PROMPT,
)
from src.core.config import get_settings
from src.core.exceptions import JSONParseError
from src.core.llm_client import LocalLLMClient
from src.core.models import (
    ClarificationManifest,
    ClarificationQuestion,
    MissionEnvironmentManifest,
    Task,
    TaskDAG,
)

logger = logging.getLogger(__name__)

MAX_ROSTER_AGENTS = 15


class MetaPlanner:
    """Decomposes any user query into a TaskDAG.

    Uses a local LLM to analyze the problem, identify sub-tasks,
    determine dependencies, and assign abstract skill requirements.
    The planner never sees concrete tools — only skill names from
    the ToolRegistry.
    """

    def __init__(
        self,
        llm: LocalLLMClient,
        available_skills: list[str],
        max_retries: int = 3,
        agents: list[dict] | None = None,
        default_agent_id: str = "",
    ):
        self.llm = llm
        self.available_skills = available_skills
        self.max_retries = max_retries
        self.agents = (agents or [])[:MAX_ROSTER_AGENTS]
        self.default_agent_id = default_agent_id

    def _agents_section(self) -> str:
        if not self.agents:
            return ""
        default = f" ('{self.default_agent_id}')" if self.default_agent_id else ""
        lines = [
            "\n\n## Available Agents",
            'Each task may set "agent_id" to the agent that should run it. Pick the agent whose skills cover the '
            f'task\'s required_skills; omit "agent_id" to use the default agent{default}. Never invent agent ids.',
        ]
        for a in self.agents:
            skills = ", ".join(a.get("skills", [])[:25]) or "all skills"
            lines.append(f"- {a['id']} ({a.get('name', a['id'])}): {a.get('description', '')[:160]} Skills: {skills}")
        return "\n".join(lines)

    def _check_agents(self, dag: TaskDAG) -> TaskDAG:
        known = {a["id"] for a in self.agents}
        for task in dag.tasks:
            if task.agent_id and task.agent_id not in known:
                logger.warning("Planner assigned unknown agent '%s' to task '%s'; using the default",
                               task.agent_id, task.id)
                task.agent_id = None
            elif task.agent_id == self.default_agent_id:
                task.agent_id = None
        return dag

    async def plan(self, user_query: str) -> TaskDAG:
        """Generate a TaskDAG from a user query.

        Includes retry-with-error-feedback: if the LLM produces
        invalid JSON, the error is fed back so the model can
        self-correct. Falls back to single-task mode after all
        retries are exhausted.

        Args:
            user_query: The raw user request.

        Returns:
            A validated TaskDAG ready for execution.
        """
        last_error: str | None = None

        for attempt in range(self.max_retries):
            logger.info(
                "Planning attempt %d/%d for query: %s",
                attempt + 1,
                self.max_retries,
                user_query[:100],
            )

            system_content = PLANNER_SYSTEM_PROMPT.format(
                available_skills=json.dumps(
                    self.available_skills, indent=2
                )
            ) + self._agents_section()
            settings = get_settings()
            if getattr(settings, "enable_memory", False):
                try:
                    from src.memory.retriever import get_memory_retriever
                    mem_ctx = get_memory_retriever().build_context(user_query)
                    if mem_ctx:
                        system_content += f"\n\n=== RELEVANT LONG-TERM MEMORY ===\n{mem_ctx}\n================================"
                except Exception as e:
                    logger.debug("Memory retrieval in planner failed: %s", e)

            if getattr(settings, "enable_skill_learning", False):
                try:
                    from src.skills.manager import get_skill_manager
                    approved_skills = get_skill_manager().get_known_skills_summary()
                    if approved_skills:
                        skills_desc = "\n".join([f"- {s['name']}: {s['description']}" for s in approved_skills[:5]])
                        system_content += f"\n\n=== REUSABLE DISTILLED SKILLS ===\n{skills_desc}\n================================"
                except Exception as e:
                    logger.debug("Failed to inject distilled skills into planner: %s", e)

            messages = [
                {
                    "role": "system",
                    "content": system_content,
                },
                {"role": "user", "content": user_query},
            ]

            # On retry, feed the parse error back so LLM can self-correct
            if last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous output had this error:\n"
                            f"{last_error}\n\n"
                            f"Fix the JSON and try again. Return ONLY "
                            f"valid JSON, nothing else."
                        ),
                    }
                )

            try:
                response = await self.llm.chat(messages)
                json_str = self._extract_json(response)
                dag = TaskDAG.model_validate(json.loads(json_str))
                dag.validate_integrity()
                self._check_agents(dag)

                # Multi-phase enforcement for operational/benchmark queries
                if len(dag.tasks) < 2 and any(k in user_query.lower() for k in ["benchmark", "investigate", "audit", "and report", "and verify", "and benchmark", "inspect and"]):
                    if attempt + 1 < self.max_retries:
                        last_error = (
                            "The query requires a multi-phase pipeline (e.g. Phase 1: Execution/Computation, Phase 2: Verification/Benchmark Profiling). "
                            "You MUST return at least 2 tasks in the 'tasks' array."
                        )
                        logger.warning(
                            "Plan attempt %d had only 1 task for multi-phase query. Re-prompting for decomposition...",
                            attempt + 1,
                        )
                        continue

                logger.info(
                    "Planning succeeded: %d tasks, goal='%s'",
                    len(dag.tasks),
                    dag.goal[:80],
                )
                return dag

            except JSONParseError as e:
                last_error = (
                    "Your reply contained no complete JSON object (it was empty or cut off). "
                    "Return only the JSON plan, with short descriptions."
                )
                logger.warning(
                    "Plan attempt %d: no JSON in reply (%d chars): %s",
                    attempt + 1,
                    len(response or ""),
                    e.raw_output[-200:] if getattr(e, "raw_output", "") else "empty reply",
                )

            except json.JSONDecodeError as e:
                last_error = f"Invalid JSON: {e}"
                logger.warning(
                    "Plan attempt %d: JSON parse error: %s",
                    attempt + 1,
                    e,
                )

            except ValidationError as e:
                last_error = f"Schema validation error: {e}"
                logger.warning(
                    "Plan attempt %d: Pydantic validation error: %s",
                    attempt + 1,
                    e,
                )

            except ValueError as e:
                # DAG integrity error (cycles, missing deps)
                last_error = f"DAG integrity error: {e}"
                logger.warning(
                    "Plan attempt %d: DAG validation error: %s",
                    attempt + 1,
                    e,
                )

            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.exception(
                    "Plan attempt %d: Unexpected error",
                    attempt + 1,
                )

        # All retries exhausted — fall back to single task
        logger.warning(
            "All %d planning attempts failed. Falling back to single-task mode.",
            self.max_retries,
        )
        return self._fallback(user_query)

    async def replan(
        self,
        original_query: str,
        completed: dict[str, str],
        failed: dict[str, str],
    ) -> TaskDAG:
        """Create a new plan after partial failure.

        Incorporates what succeeded and what failed so the new plan
        can build on completed work and avoid repeating failures.

        Args:
            original_query: The user's original request.
            completed: {task_id: output} of successfully completed tasks.
            failed: {task_id: error_message} of failed tasks.

        Returns:
            A new TaskDAG that addresses the remaining work.
        """
        completed_summary = json.dumps(
            {tid: output[:200] for tid, output in completed.items()},
            indent=2,
        )
        failed_summary = json.dumps(failed, indent=2)

        system_content = REPLAN_SYSTEM_PROMPT.format(
            original_query=original_query,
            completed_summary=completed_summary,
            failed_summary=failed_summary,
            available_skills=json.dumps(self.available_skills),
        ) + self._agents_section()
        settings = get_settings()
        if getattr(settings, "enable_memory", False):
            try:
                from src.memory.retriever import get_memory_retriever
                mem_ctx = get_memory_retriever().build_context(original_query)
                if mem_ctx:
                    system_content += f"\n\n=== RELEVANT LONG-TERM MEMORY ===\n{mem_ctx}\n================================"
            except Exception as e:
                logger.debug("Memory retrieval in replan failed: %s", e)

        if getattr(settings, "enable_skill_learning", False):
            try:
                from src.skills.manager import get_skill_manager
                approved_skills = get_skill_manager().get_known_skills_summary()
                if approved_skills:
                    skills_desc = "\n".join([f"- {s['name']}: {s['description']}" for s in approved_skills[:5]])
                    system_content += f"\n\n=== REUSABLE DISTILLED SKILLS ===\n{skills_desc}\n================================"
            except Exception as e:
                logger.debug("Failed to inject distilled skills into replan: %s", e)

        messages = [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": (
                    f"Create a new execution plan to complete the "
                    f"remaining work for: {original_query}"
                ),
            },
        ]

        try:
            response = await self.llm.chat(messages)
            json_str = self._extract_json(response)
            dag = TaskDAG.model_validate(json.loads(json_str))
            dag.validate_integrity()
            self._check_agents(dag)

            logger.info(
                "Re-plan succeeded: %d new tasks", len(dag.tasks)
            )
            return dag

        except Exception as e:
            logger.error("Re-plan failed: %s. Falling back.", e)
            return self._fallback(original_query)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response.

        Handles common local LLM output quirks:
        - Raw JSON (ideal)
        - JSON wrapped in ```json ... ``` code blocks
        - JSON with leading/trailing text
        - Multiple JSON objects (takes the first complete one)

        Raises:
            JSONParseError: If no valid JSON can be extracted.
        """
        text = text.strip()

        # Try 1: Direct parse (ideal case)
        if text.startswith("{"):
            # Find the matching closing brace
            brace_count = 0
            for i, char in enumerate(text):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return text[: i + 1]

        # Try 2: Extract from markdown code blocks
        code_block_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL
        )
        if code_block_match:
            return code_block_match.group(1)

        # Try 3: Find first { to its matching }
        start = text.find("{")
        if start != -1:
            brace_count = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    brace_count += 1
                elif text[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return text[start : i + 1]

        raise JSONParseError(
            raw_output=text[:500],
            parse_error="No valid JSON object found in LLM response",
        )

    def _fallback(self, query: str) -> TaskDAG:
        """Create a single catch-all task when decomposition fails.

        This ensures the system NEVER deadlocks. Worst case, it
        behaves as a single-agent chatbot.
        """
        return TaskDAG(
            goal=query,
            reasoning=(
                "Automatic fallback: task decomposition failed after "
                "maximum retries. Executing as a single direct task."
            ),
            tasks=[
                Task(
                    id="t1",
                    name="Direct Execution",
                    description=(
                        f"Respond to the following user request directly, "
                        f"using any available tools as needed:\n\n{query}"
                    ),
                    required_skills=["general_reasoning"],
                    expected_output="A complete response to the user's request",
                    dependencies=[],
                )
            ],
        )

    async def generate_clarification_questions(
        self,
        prompt: str,
        env_manifest: MissionEnvironmentManifest | None = None,
        session_id: str = "",
    ) -> ClarificationManifest:
        """Analyze mission prompt & environment to generate targeted pre-flight clarifying questions."""
        tools_summary = "None detected"
        files_summary = "None attached"

        if env_manifest:
            active_c = [c.name for c in env_manifest.active_connectors if c.readiness.value == "ready"]
            matched_t = [t.name for t in env_manifest.matched_tools[:8]]
            tools_summary = f"Active Connectors: {', '.join(active_c) or 'None'} | Matched Tools: {', '.join(matched_t) or 'Standard'}"
            if env_manifest.available_files:
                files_summary = ", ".join(env_manifest.available_files[:10])

        system_prompt = CLARIFICATION_GENERATOR_PROMPT.format(
            prompt=prompt,
            tools_summary=tools_summary,
            files_summary=files_summary,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze this mission and determine if pre-flight clarification is needed: {prompt}"},
        ]

        try:
            response = await self.llm.chat(messages)
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            manifest = ClarificationManifest.model_validate(data)
            manifest.session_id = session_id or "default"
            if env_manifest:
                manifest.discovered_tools_count = len(env_manifest.matched_tools)
            return manifest
        except Exception as e:
            logger.info("Pre-flight clarification check produced no questions (error or clean bypass: %s)", e)
            return ClarificationManifest(
                session_id=session_id or "default",
                needs_clarification=False,
                detected_mission_type="general_operation",
                recommended_workflow_topology="sequential",
                discovered_tools_count=len(env_manifest.matched_tools) if env_manifest else 0,
                questions=[],
            )

