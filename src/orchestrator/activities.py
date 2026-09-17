"""
UAOS Temporal Activities

Activities are the units of work that Temporal executes. Each activity
is automatically retried on failure according to its retry policy.

The key insight: execute_task is the SAME function for every task type.
The persona + tools make it specialized. This is where the
"no hardcoded agents" principle is enforced.
"""

from __future__ import annotations

import logging

from temporalio import activity

from src.brain.meta_planner import MetaPlanner
from src.brain.prompts import ASSEMBLER_SYSTEM_PROMPT
from src.core.config import get_settings
from src.core.llm_client import LocalLLMClient
from src.core.models import Task, TaskDAG
from src.orchestrator.event_bus import get_event_bus
from src.persona.synthesizer import PersonaSynthesizer
from src.registry.auto_discover import register_all_tools
from src.registry.tool_registry import ToolRegistry
from src.workers.universal_worker import UniversalWorkerAgent

logger = logging.getLogger(__name__)

# ── Singleton Initialization ─────────────────────────────────────
# These are initialized once per worker process and reused across
# activity executions. This is safe because activities are stateless.

_registry: ToolRegistry | None = None
_planner_llm: LocalLLMClient | None = None
_worker_llm: LocalLLMClient | None = None


def reset_llm_clients() -> None:
    """Reset LLM singletons so updated settings take effect immediately."""
    global _planner_llm, _worker_llm
    _planner_llm = None
    _worker_llm = None
    logger.info("LLM clients reset for reconfiguration")


def _get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        register_all_tools(_registry)
        logger.info("Tool registry initialized: %s", _registry)
    return _registry


def _get_planner_llm() -> LocalLLMClient:
    global _planner_llm
    settings = get_settings()
    if (
        _planner_llm is None
        or _planner_llm.base_url != settings.llm_base_url
        or _planner_llm.model != settings.llm_model
    ):
        _planner_llm = LocalLLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
        logger.info("Planner LLM initialized: %s", _planner_llm)
    return _planner_llm


def _get_worker_llm() -> LocalLLMClient:
    global _worker_llm
    settings = get_settings()
    # Use separate worker model if configured, otherwise same as planner
    model = settings.worker_llm_model or settings.llm_model
    if (
        _worker_llm is None
        or _worker_llm.base_url != settings.llm_base_url
        or _worker_llm.model != model
    ):
        _worker_llm = LocalLLMClient(
            base_url=settings.llm_base_url,
            model=model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
        logger.info("Worker LLM initialized: %s", _worker_llm)
    return _worker_llm


# ── Activities ───────────────────────────────────────────────────


@activity.defn
async def plan_tasks(user_query: str, agent_id: str = "") -> dict:
    """Meta-Planner activity: decompose user query into TaskDAG.

    This is the most critical LLM call in the system. It determines
    the entire execution plan.

    Args:
        user_query: Raw user request.
        agent_id: Optional AgentProfile ID to restrict skills during planning.

    Returns:
        TaskDAG as a plain dict (Temporal requires serializable types).
    """
    activity.logger.info(
        "Planning tasks for: %s (agent_id: %s)",
        user_query[:100],
        agent_id or "default",
    )

    registry = _get_registry()
    llm = _get_planner_llm()
    settings = get_settings()

    available_skills = registry.list_skills()
    if agent_id:
        try:
            from src.core.agent_store import AgentStore

            store = AgentStore()
            profile = store.load(agent_id)
            if profile and profile.curated_skills:
                available_skills = [
                    s for s in available_skills if s in profile.curated_skills
                ]
                activity.logger.info(
                    "Restricted planner skills for agent '%s': %s",
                    agent_id,
                    available_skills,
                )
        except Exception as e:
            activity.logger.warning(
                "Could not filter planner skills for agent '%s': %s", agent_id, e
            )

    planner = MetaPlanner(
        llm=llm,
        available_skills=available_skills,
        max_retries=settings.planner_max_retries,
    )

    dag = await planner.plan(user_query)

    activity.logger.info(
        "Plan created: %d tasks, goal='%s'",
        len(dag.tasks),
        dag.goal[:80],
    )

    return dag.to_serializable()


@activity.defn
async def execute_task(
    task_dict: dict, upstream_outputs: dict[str, str], agent_id: str = ""
) -> dict:
    """Universal Worker activity: execute a single task.

    THIS IS THE SAME FUNCTION FOR EVERY TASK TYPE.
    The persona (from PersonaSynthesizer) and tools (from ToolRegistry)
    are what make it behave differently for different tasks.

    Args:
        task_dict: Task as a plain dict.
        upstream_outputs: {task_id: output} from completed dependencies.
        agent_id: Optional AgentProfile ID to steer persona and restrict tools.

    Returns:
        TaskResult as a plain dict.
    """
    task = Task.model_validate(task_dict)
    activity.logger.info(
        "Executing task '%s' (%s), skills: %s (agent_id: %s)",
        task.name,
        task.id,
        task.required_skills,
        agent_id or "default",
    )

    registry = _get_registry()
    settings = get_settings()
    worker_llm = _get_worker_llm()

    # Load agent profile if specified
    profile = None
    if agent_id:
        try:
            from src.core.agent_store import AgentStore

            store = AgentStore()
            profile = store.load(agent_id)
            if profile:
                activity.logger.info(
                    "Applying AgentProfile '%s' (%s) for task '%s'",
                    profile.name,
                    profile.id,
                    task.id,
                )
        except Exception as e:
            activity.logger.warning("Failed to load AgentProfile '%s': %s", agent_id, e)

    # Component 2: Skill/Tool Injector — resolve abstract skills to tools
    if profile and profile.curated_skills:
        effective_skills = [
            s for s in task.required_skills if s in profile.curated_skills
        ]
        tools = registry.resolve(effective_skills)
    else:
        tools = registry.resolve(task.required_skills)

    if not tools and task.required_skills != ["general_reasoning"]:
        activity.logger.warning(
            "No tools resolved for skills %s. "
            "Worker will operate without tools.",
            task.required_skills,
        )

    # Component 3: Persona Synthesizer — generate system prompt
    synthesizer = PersonaSynthesizer(
        max_context_chars=settings.worker_max_context_chars
    )
    if profile:
        persona = synthesizer.synthesize_from_profile(
            profile=profile,
            task=task,
            tools=tools,
            upstream_context=upstream_outputs if upstream_outputs else None,
        )
    else:
        persona = synthesizer.synthesize(
            task=task,
            tools=tools,
            upstream_context=upstream_outputs if upstream_outputs else None,
        )

    # Component 4: Universal Worker Agent — execute with ReAct loop
    worker = UniversalWorkerAgent(
        llm=worker_llm,
        max_iterations=settings.worker_max_iterations,
        max_output_chars=settings.worker_max_output_chars,
    )

    # Connect streaming event bus
    bus = get_event_bus()
    try:
        wf_id = activity.info().workflow_id
    except Exception:
        wf_id = "default"

    def handle_token(token: str) -> None:
        bus.publish(wf_id, {"type": "token", "task_id": task.id, "content": token})

    def handle_event(ev: dict) -> None:
        bus.publish(wf_id, ev)

    result = await worker.execute(
        task=task,
        persona=persona,
        tools=tools,
        on_token=handle_token,
        on_event=handle_event,
    )

    activity.logger.info(
        "Task '%s' result: status=%s, tools_used=%s, time=%dms",
        task.id,
        result.status.value,
        result.tool_calls_made,
        result.execution_time_ms or 0,
    )

    return result.to_serializable()


@activity.defn
async def replan_tasks(
    user_query: str,
    completed: dict[str, str],
    failed: dict[str, str],
) -> dict:
    """Re-plan activity: create a new plan after partial failure.

    Incorporates completed work and avoids failed approaches.

    Args:
        user_query: Original user request.
        completed: {task_id: output} of successful tasks.
        failed: {task_id: error} of failed tasks.

    Returns:
        New TaskDAG as a plain dict.
    """
    activity.logger.info(
        "Re-planning: %d completed, %d failed",
        len(completed),
        len(failed),
    )

    registry = _get_registry()
    llm = _get_planner_llm()

    planner = MetaPlanner(
        llm=llm,
        available_skills=registry.list_skills(),
        max_retries=2,  # fewer retries on replan
    )

    dag = await planner.replan(
        original_query=user_query,
        completed=completed,
        failed=failed,
    )

    activity.logger.info(
        "Re-plan created: %d new tasks", len(dag.tasks)
    )

    return dag.to_serializable()


@activity.defn
async def assemble_response(
    user_query: str,
    dag_dict: dict,
    completed: dict[str, str],
) -> str:
    """Response Assembler activity: synthesize final output.

    Uses the LLM to combine all task outputs into a single,
    coherent response to the user.

    Args:
        user_query: Original user request.
        dag_dict: The executed TaskDAG.
        completed: {task_id: output} of all completed tasks.

    Returns:
        The final assembled response string.
    """
    activity.logger.info(
        "Assembling response from %d task outputs", len(completed)
    )

    llm = _get_planner_llm()
    dag = TaskDAG.from_serializable(dag_dict)

    # Build a structured summary of all task outputs
    task_outputs_parts = []
    for task_id, output in completed.items():
        task = dag.get_task_by_id(task_id)
        task_name = task.name if task else task_id
        task_outputs_parts.append(
            f"## Task: {task_name} ({task_id})\n{output}"
        )

    task_outputs = "\n\n---\n\n".join(task_outputs_parts)

    response = await llm.chat(
        [
            {"role": "system", "content": ASSEMBLER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"# Original User Query\n{user_query}\n\n"
                    f"# Task Results\n{task_outputs}"
                ),
            },
        ]
    )

    activity.logger.info(
        "Response assembled: %d chars", len(response)
    )

    try:
        wf_id = activity.info().workflow_id
        get_event_bus().publish(wf_id, {"type": "final_solution", "response": response})
    except Exception as bus_err:
        activity.logger.debug("Failed to publish final solution event: %s", bus_err)

    return response


@activity.defn
async def escalate_approval(task_dict: dict, user_query: str) -> dict:
    """Escalation activity: triggers escalation alerts when human approval times out."""
    task_id = task_dict.get("id", "unknown")
    task_name = task_dict.get("name", "unknown")
    risk = task_dict.get("risk_level", "high")
    try:
        wf_id = activity.info().workflow_id
    except Exception:
        wf_id = "default"

    activity.logger.warning(
        "ESCALATION ALERT: Task '%s' (%s, risk: %s) timed out waiting for approval. Workflow: %s",
        task_name,
        task_id,
        risk,
        wf_id,
    )

    # Publish escalation event to event bus
    get_event_bus().publish(
        wf_id,
        {
            "type": "escalation_triggered",
            "task_id": task_id,
            "task_name": task_name,
            "risk_level": risk,
            "reason": "Approval timed out after 15 minutes",
        },
    )

    return {
        "escalated": True,
        "task_id": task_id,
        "task_name": task_name,
    }


@activity.defn
async def notify_approval_required(task_dict: dict) -> bool:
    """Notify subscribers that human approval is required for a high-risk task."""
    task_id = task_dict.get("id", "unknown")
    task_name = task_dict.get("name", "unknown")
    risk = task_dict.get("risk_level", "high")
    desc = task_dict.get("description", "")
    params = task_dict.get("parameters", {})
    timeout = task_dict.get("approval_timeout_seconds", 900)

    try:
        wf_id = activity.info().workflow_id
    except Exception:
        wf_id = "default"

    get_event_bus().publish(
        wf_id,
        {
            "type": "approval_required",
            "task_id": task_id,
            "task_name": task_name,
            "task_desc": desc,
            "risk_level": risk,
            "task_params": params,
            "timeout_seconds": timeout,
        },
    )
    return True

