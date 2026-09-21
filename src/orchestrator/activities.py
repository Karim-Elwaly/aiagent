"""
UAOS Temporal Activities

Activities are the units of work that Temporal executes. Each activity
is automatically retried on failure according to its retry policy.

The key insight: execute_task is the SAME function for every task type.
The persona + tools make it specialized. This is where the
"no hardcoded agents" principle is enforced.
"""

from __future__ import annotations

import json
import logging

from temporalio import activity

from src.brain.meta_planner import MetaPlanner
from src.brain.prompts import ASSEMBLER_SYSTEM_PROMPT, SUPERVISOR_EVALUATION_PROMPT
from src.core.config import get_settings
from src.core.llm_client import LocalLLMClient
from src.core.models import Task, TaskDAG
from src.core.report_verifier import format_verification_section, verify_report
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
    logger.info(
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
                logger.info(
                    "Restricted planner skills for agent '%s': %s",
                    agent_id,
                    available_skills,
                )
        except Exception as e:
            logger.warning(
                "Could not filter planner skills for agent '%s': %s", agent_id, e
            )

    # Give the planner a one-line purpose for each skill. Choosing between
    # "traffic_analysis" and "threat_intel" from bare names is guesswork.
    skill_descriptions: dict[str, str] = {}
    try:
        for spec in registry.get_all_tools():
            for skill in spec.skills_provided:
                if skill in skill_descriptions:
                    continue
                summary = (spec.description or "").strip().split(". ")[0]
                if summary:
                    skill_descriptions[skill] = summary[:200]
    except Exception as e:
        logger.debug("Could not build skill descriptions: %s", e)

    planner = MetaPlanner(
        llm=llm,
        available_skills=available_skills,
        max_retries=settings.planner_max_retries,
        skill_descriptions=skill_descriptions,
    )

    dag = await planner.plan(user_query)

    from src.core.path_utils import extract_target_path
    target_path = extract_target_path(user_query)
    if target_path:
        for t in dag.tasks:
            if not hasattr(t, "parameters") or t.parameters is None:
                t.parameters = {}
            if "target_path" not in t.parameters:
                t.parameters["target_path"] = target_path
            if "[Investigation Target Path]" not in t.description:
                t.description = f"{t.description}\n\n[Investigation Target Path]: {target_path}"

    logger.info(
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
    
    # Ensure target_path is propagated if present
    from src.core.path_utils import extract_target_path
    user_query = task_dict.get("_user_query", "")
    target_path = extract_target_path(user_query) or getattr(task, "parameters", {}).get("target_path", "")
    if target_path and "[Investigation Target Path]" not in task.description:
        task.description = f"{task.description}\n\n[Investigation Target Path]: {target_path}"

    logger.info(
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
                logger.info(
                    "Applying AgentProfile '%s' (%s) for task '%s'",
                    profile.name,
                    profile.id,
                    task.id,
                )
        except Exception as e:
            logger.warning("Failed to load AgentProfile '%s': %s", agent_id, e)

    # Component 2: Skill/Tool Injector — resolve abstract skills to tools
    if profile and profile.curated_skills:
        effective_skills = [
            s for s in task.required_skills if s in profile.curated_skills
        ]
        if task.required_skills and not effective_skills:
            # The profile curates none of the requested skills. Silently running
            # a toolless worker here is the worst outcome: it cannot gather any
            # evidence yet will still produce confident prose. Fall back to the
            # unfiltered skills so the task keeps its capabilities, and say so.
            logger.warning(
                "AgentProfile '%s' curates none of the required skills %s for task '%s'. "
                "Falling back to unfiltered skill resolution so the task is not left "
                "without tools. Consider adding these skills to the profile.",
                profile.id,
                task.required_skills,
                task.id,
            )
            effective_skills = list(task.required_skills)
        tools = registry.resolve(effective_skills)
    else:
        tools = registry.resolve(task.required_skills)

    if not tools and task.required_skills != ["general_reasoning"]:
        logger.warning(
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

    # Resolve the run identifier before constructing the worker: it scopes both
    # the streaming event bus and the per-run evidence store.
    wf_id = task_dict.get("_workflow_id")
    if not wf_id:
        try:
            wf_id = activity.info().workflow_id
        except Exception:
            wf_id = "default"

    # Component 4: Universal Worker Agent — execute with ReAct loop
    worker = UniversalWorkerAgent(
        llm=worker_llm,
        max_iterations=settings.worker_max_iterations,
        max_output_chars=settings.worker_max_output_chars,
        run_id=wf_id,
    )

    # Connect streaming event bus
    bus = get_event_bus()

    def handle_token(token: str) -> None:
        bus.publish(wf_id, {"type": "token", "task_id": task.id, "content": token})

    def handle_event(ev: dict) -> None:
        bus.publish(wf_id, ev)

    def handle_heartbeat() -> None:
        try:
            activity.heartbeat("react_step", task.id)
        except Exception:
            pass

    user_query = task_dict.get("_user_query", "")

    result = await worker.execute(
        task=task,
        persona=persona,
        tools=tools,
        upstream_context=upstream_outputs if upstream_outputs else None,
        user_query=user_query,
        on_token=handle_token,
        on_event=handle_event,
        on_heartbeat=handle_heartbeat,
    )

    logger.info(
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
    logger.info(
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

    logger.info(
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
    logger.info(
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

    response = clean_assembled_solution(response)

    logger.info(
        "Response assembled: %d chars", len(response)
    )

    wf_id = dag_dict.get("_workflow_id")
    if not wf_id:
        try:
            wf_id = activity.info().workflow_id
        except Exception:
            wf_id = "default"

    try:
        get_event_bus().publish(wf_id, {"type": "final_solution", "response": response})
    except Exception as bus_err:
        logger.debug("Failed to publish final solution event: %s", bus_err)

    return response


@activity.defn
async def verify_investigation_report(report: str, run_id: str = "") -> dict:
    """Check every concrete claim in the assembled report against the evidence store.

    This is the last gate before a report reaches a human. It does not rewrite
    conclusions — it annotates values the evidence cannot substantiate and
    returns a verdict, so nobody acts on an invented hostname or address.

    Runs are skipped silently when no evidence was ingested (for example a
    non-investigative workflow), because there is nothing to verify against.

    Args:
        report: The assembled final report.
        run_id: Workflow id used to locate the run's evidence store.

    Returns:
        A dict with the verdict, the issue list and the annotated report.
    """
    if not run_id:
        try:
            run_id = activity.info().workflow_id
        except Exception:
            run_id = "default"

    try:
        from src.core.evidence import get_store

        if get_store(run_id).count() == 0:
            logger.info("No evidence ingested for run '%s'; skipping verification", run_id)
            return {"verdict": "skipped", "report": report, "reason": "no evidence ingested"}

        result = verify_report(report, run_id)
    except Exception as exc:
        # Verification must never destroy a completed investigation.
        logger.error("Report verification failed for run '%s': %s", run_id, exc)
        return {"verdict": "error", "report": report, "reason": str(exc)}

    annotated = result.annotated_report + "\n" + format_verification_section(result)

    logger.info(
        "Report verification for run '%s': verdict=%s issues=%d coverage=%.0f%%",
        run_id,
        result.verdict,
        len(result.issues),
        result.citation_coverage * 100,
    )

    try:
        get_event_bus().publish(
            run_id,
            {
                "type": "report_verification",
                "verdict": result.verdict,
                "issues": [i.as_dict() for i in result.issues],
                "citation_coverage": round(result.citation_coverage, 3),
            },
        )
    except Exception as bus_err:
        logger.debug("Failed to publish verification event: %s", bus_err)

    payload = result.as_dict()
    payload["report"] = annotated
    return payload


def clean_assembled_solution(response: str) -> str:
    """Sanitize assembled response by removing apologetic meta-commentary, disclaimers, and awkward placeholders."""
    if not response:
        return ""
    import re

    # Strip apologetic sub-task disclaimers or single-run footnotes at the end
    response = re.sub(
        r"(?i)\n*---\s*\n*(?:\*{1,2})?Note:?(?:\*{1,2})?\s*(?:Only one sub[- ]task|All information above comes from|If you need a more detailed breakdown|Feel free to ask).*$",
        "",
        response,
        flags=re.DOTALL,
    )
    # Strip standalone trailing disclaimers
    response = re.sub(
        r"(?i)\n*(?:Note:\s*Only one sub[- ]task|All information above comes from that single run).*$",
        "",
        response,
        flags=re.DOTALL,
    )
    # Strip conversational trailing sign-offs
    response = re.sub(
        r"(?i)\n*(?:Let me know if you need|Feel free to ask).*$",
        "",
        response,
    )
    # Replace awkward task runner placeholders in tables
    response = response.replace("Measured by the task runner – see below", "Measured in Benchmark Details")
    response = response.replace("Measured by the task runner - see below", "Measured in Benchmark Details")
    return response.strip()


@activity.defn
async def escalate_approval(task_dict: dict, user_query: str) -> dict:
    """Escalation activity: triggers escalation alerts when human approval times out."""
    task_id = task_dict.get("id", "unknown")
    task_name = task_dict.get("name", "unknown")
    risk = task_dict.get("risk_level", "high")
    wf_id = task_dict.get("_workflow_id")
    if not wf_id:
        try:
            wf_id = activity.info().workflow_id
        except Exception:
            wf_id = "default"

    logger.warning(
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


def _context_digest(output: str, max_chars: int = 600) -> str:
    """Condense a prior task output for supervisor context.

    Keeps the head and the tail rather than clipping at a fixed offset: the
    conclusion of a task output is usually its most informative part, and the
    previous fixed 150-character clip discarded it entirely.
    """
    text = (output or "").strip()
    if len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head
    return f"{text[:head].rstrip()}\n[...]\n{text[-tail:].lstrip()}"


@activity.defn
async def evaluate_task_output(
    task_dict: dict,
    worker_output: str,
    user_query: str,
    prior_completed: dict[str, str],
) -> dict:
    """Supervisor ReAct activity: evaluates whether a completed task output is accurate or needs retry."""
    task_id = task_dict.get("id", "t")
    task_name = task_dict.get("name", "Task")
    task_desc = task_dict.get("description", "")
    expected_output = task_dict.get("expected_output", "")

    wf_id = task_dict.get("_workflow_id")
    if not wf_id:
        try:
            wf_id = activity.info().workflow_id
        except Exception:
            wf_id = "default"

    llm = _get_planner_llm()

    # Prior context is summarised structurally rather than by clipping each
    # output to a fixed character count, which used to cut evidence mid-sentence.
    prior_summary = "\n".join(
        f"- Task {tid}: {_context_digest(out)}"
        for tid, out in prior_completed.items()
        if tid != task_id
    )

    prompt = SUPERVISOR_EVALUATION_PROMPT.format(
        user_query=user_query,
        task_name=task_name,
        task_description=task_desc,
        expected_output=expected_output or "Complete actionable task results",
        prior_context=prior_summary or "None",
        worker_output=worker_output,
    )

    try:
        resp = await llm.chat([
            {
                "role": "system",
                "content": (
                    "You are a strict, objective Investigation Supervisor. "
                    "Output ONLY valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ])

        clean_json = resp.strip()
        if "```" in clean_json:
            clean_json = clean_json.split("```")[1]
            if clean_json.startswith("json"):
                clean_json = clean_json[4:].strip()

        start = clean_json.find("{")
        end = clean_json.rfind("}")
        if start != -1 and end != -1:
            clean_json = clean_json[start : end + 1]

        data = json.loads(clean_json)
        raw_decision = str(data.get("decision", "pass")).lower().strip()
        if raw_decision in ("pass", "accurate", "success", "completed", "approved"):
            decision = "pass"
        elif raw_decision in ("abort", "fatal_abort", "halt", "cancel"):
            decision = "abort"
        else:
            decision = "needs_retry"
        confidence = float(data.get("confidence", 0.9))
        feedback = data.get("feedback", "")
        missing_info = data.get("missing_info", [])
    except Exception as e:
        # A supervisor whose verdict could not be parsed has NOT approved
        # anything. Defaulting to "pass" here silently disabled the quality gate
        # whenever the model returned malformed JSON.
        logger.warning(
            "Supervisor evaluation could not be parsed for task '%s': %s - "
            "defaulting to retry rather than approval",
            task_name,
            e,
        )
        decision = "needs_retry"
        confidence = 0.0
        feedback = (
            "The supervisor's evaluation could not be parsed, so this output has not "
            "been reviewed. Re-state the findings clearly, citing the evidence ids that "
            "support each claim."
        )
        missing_info = []

    # Domain-agnostic circuit breaker: evaluate if critical discovery yielded 0 target artifacts
    is_initial_discovery = task_id in ("t1", "T1", "task-1") or any(
        s in task_dict.get("required_skills", [])
        for s in ("file_tree", "filesystem_inspection", "file_enumeration", "directory_listing", "evidence_collection")
    )
    low_output = worker_output.lower()

    # Check if files or log records were actually successfully ingested
    has_ingested_data = any(
        m in low_output
        for m in (
            "total artifacts analyzed:",
            "xml events",
            "total log records",
            "extracted forensic event telemetry",
            "json records",
            "ingested:",
        )
    ) and not any(
        m in low_output
        for m in (
            "0 total log records",
            "0 items enumerated",
            "0 files enumerated",
            "total artifacts analyzed: 0",
        )
    )

    has_missing_target = any(
        marker in low_output
        for marker in (
            "0 items enumerated",
            "0 files enumerated",
            "0 total log records",
            "total: 0 items",
            "total artifacts analyzed: 0 files",
            "directory not found",
            "path not a file / 0 files found",
        )
    ) or ("does not exist on disk" in low_output and not has_ingested_data)

    if is_initial_discovery and has_missing_target and not has_ingested_data:
        decision = "abort"
        feedback = (
            "Target log directory yielded 0 files or could not be accessed. "
            "Downstream analysis tasks aborted to prevent ungrounded hallucinations."
        )

    # Heuristic safety net: flag genuine agent refusals without misclassifying legitimate data reports
    refusal_cues = [
        "i'm sorry, but i cannot",
        "i am sorry, but i cannot",
        "i do not have access to the local filesystem",
        "as an ai language model",
        "i cannot fulfill this request",
        "prime list is missing",
    ]
    # If the output already contains tool results or disk/directory details, do not override
    has_concrete_data = any(marker in worker_output.lower() for marker in ["total_bytes", "free_bytes", "total_gigabytes", "directory tree", "files and directories", "items found"])
    if decision != "abort" and not has_concrete_data and any(cue in worker_output.lower() for cue in refusal_cues):
        decision = "needs_retry"
        if not feedback:
            feedback = "The worker reported inability to complete the task. Please execute the available tools to inspect the environment and fulfill the requirements."

    eval_result = {
        "task_id": task_id,
        "task_name": task_name,
        "decision": decision,
        "confidence": confidence,
        "feedback": feedback,
        "missing_info": missing_info,
    }

    # Broadcast supervisor verdict to UI
    try:
        get_event_bus().publish(
            wf_id,
            {
                "type": "supervisor_verdict",
                "task_id": task_id,
                "task_name": task_name,
                "decision": decision,
                "confidence": confidence,
                "feedback": feedback,
            },
        )
    except Exception as eb_err:
        logger.debug("Failed to publish supervisor verdict: %s", eb_err)

    logger.info(
        "Supervisor verdict on '%s': %s (confidence: %.2f)",
        task_name,
        decision.upper(),
        confidence,
    )

    return eval_result


