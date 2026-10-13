"""
UAOS Temporal Activities

Activities are the units of work that Temporal executes. Each activity
is automatically retried on failure according to its retry policy.

The key insight: execute_task is the SAME function for every task type.
The persona + tools make it specialized. This is where the
"no hardcoded agents" principle is enforced.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from src.brain.meta_planner import MetaPlanner
from src.brain.prompts import (
    ASSEMBLER_SYSTEM_PROMPT,
    SUPERVISOR_EVALUATION_PROMPT,
    format_decision_options,
)
from src.core import decision_capture
from src.core.config import get_settings
from src.core.exceptions import TransientLLMError
from src.core.llm_client import LocalLLMClient
from src.core.models import Task, TaskDAG
from src.orchestrator.event_bus import get_event_bus
from src.persona.synthesizer import PersonaSynthesizer
from src.registry.auto_discover import register_all_tools
from src.registry.tool_registry import ToolRegistry
from src.workers.factory import create_worker, resolve_engine

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
    max_tokens = max(settings.llm_max_tokens, settings.planner_max_tokens)
    if (
        _planner_llm is None
        or _planner_llm.base_url != settings.llm_base_url
        or _planner_llm.model != settings.llm_model
        or _planner_llm.max_tokens != max_tokens
    ):
        _planner_llm = LocalLLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=max_tokens,
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

    planner = MetaPlanner(
        llm=llm,
        available_skills=available_skills,
        max_retries=settings.planner_max_retries,
    )

    dag = await planner.plan(user_query)

    logger.info(
        "Plan created: %d tasks, goal='%s'",
        len(dag.tasks),
        dag.goal[:80],
    )

    serialized = dag.to_serializable()

    # Record each task's assigned risk level for offline evaluation. This is the
    # value that fires the human approval gate, and the planner emits it as one
    # field inside a large DAG with no confidence attached. No-op unless
    # decision_capture_enabled.
    for task in serialized.get("tasks", []):
        decision_capture.capture_risk_level_decision(
            user_query=user_query,
            task=task,
        )

    # Re-score each task's risk as a focused typed decision and compare against
    # the planner's own value. Records the comparison; the planner's value still
    # stands. No-op unless decision_shadow_enabled.
    try:
        from src.core import decision_shadow

        for task in serialized.get("tasks", []):
            await decision_shadow.shadow_risk_level(
                user_query=user_query,
                task=task,
            )
    except Exception as shadow_err:
        logger.debug("Shadow risk comparison failed: %s", shadow_err)

    return serialized


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
    task_id = task_dict.get("id", "unknown")
    try:
        task = Task.model_validate(task_dict)
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
        engine = resolve_engine(profile, settings)
        protocol = "hermes" if engine == "hermes" else "legacy"
        synthesizer = PersonaSynthesizer(
            max_context_chars=settings.worker_max_context_chars
        )
        if profile:
            persona = synthesizer.synthesize_from_profile(
                profile=profile,
                task=task,
                tools=tools,
                upstream_context=upstream_outputs if upstream_outputs else None,
                protocol=protocol,
            )
        else:
            persona = synthesizer.synthesize(
                task=task,
                tools=tools,
                upstream_context=upstream_outputs if upstream_outputs else None,
                protocol=protocol,
            )

        # Component 4: Worker Agent — universal ReAct loop or Hermes function calling
        worker = create_worker(engine, worker_llm, settings, agent=profile, registry=registry)
        logger.info("Task '%s' runs on the %s worker engine", task.id, engine)

        # Temporal Native Heartbeat Checkpointing
        resume_checkpoint = None
        try:
            details = activity.info().heartbeat_details
            if details and isinstance(details[0], dict) and "messages" in details[0]:
                checkpoint_engine = details[0].get("engine", "universal")
                if checkpoint_engine == engine:
                    resume_checkpoint = details[0]
                    logger.info(
                        "Temporal Activity '%s' restoring state from server heartbeat details (step %s)",
                        task.id,
                        resume_checkpoint.get("step", 0),
                    )
                else:
                    logger.info(
                        "Task '%s' ignoring %s checkpoint: now running on the %s engine",
                        task.id,
                        checkpoint_engine,
                        engine,
                    )
        except Exception:
            pass

        # Connect streaming event bus
        bus = get_event_bus()
        wf_id = task_dict.get("_workflow_id")
        if not wf_id:
            try:
                wf_id = activity.info().workflow_id
            except Exception:
                wf_id = "default"
        bus.publish(wf_id, {"type": "worker_engine", "task_id": task.id, "engine": engine})

        def handle_token(token: str) -> None:
            bus.publish(wf_id, {"type": "token", "task_id": task.id, "content": token})

        def handle_event(ev: dict) -> None:
            bus.publish(wf_id, ev)

        def handle_heartbeat(checkpoint_data: dict[str, Any] | None = None) -> None:
            try:
                if checkpoint_data:
                    activity.heartbeat(checkpoint_data)
                else:
                    activity.heartbeat("react_step", task.id)
            except Exception:
                pass

        user_query = task_dict.get("_user_query", "")

        # Continuous background heartbeat to protect against LLM latency timeouts
        heartbeat_stop = asyncio.Event()

        async def _periodic_heartbeat() -> None:
            while not heartbeat_stop.is_set():
                try:
                    await asyncio.sleep(5.0)
                    activity.heartbeat("keepalive", task.id)
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        hb_task = asyncio.create_task(_periodic_heartbeat())

        continuation: dict[str, Any] = {}
        if engine == "hermes" and task_dict.get("_hermes_session_id"):
            continuation = {
                "continue_session": task_dict["_hermes_session_id"],
                "review_feedback": task_dict.get("_supervisor_feedback", ""),
            }

        try:
            result = await worker.execute(
                task=task,
                persona=persona,
                tools=tools,
                upstream_context=upstream_outputs if upstream_outputs else None,
                user_query=user_query,
                on_token=handle_token,
                on_event=handle_event,
                on_heartbeat=handle_heartbeat,
                resume_checkpoint=resume_checkpoint,
                workflow_id=wf_id,
                **continuation,
            )
        finally:
            heartbeat_stop.set()
            hb_task.cancel()

        logger.info(
            "Task '%s' result: status=%s, tools_used=%s, time=%dms",
            task.id,
            result.status.value,
            result.tool_calls_made,
            result.execution_time_ms or 0,
        )

        return result.to_serializable()

    except TransientLLMError as exc:
        # Surfaced as an activity failure so Temporal retries from the last heartbeat.
        logger.warning("Task '%s' hit a transient LLM fault: %s", task_id, exc)
        raise ApplicationError(str(exc), type="TransientLLMError") from exc

    except Exception as exc:
        logger.exception("Task '%s' execution crashed with exception: %s", task_id, exc)
        return {
            "task_id": task_id,
            "status": "failed",
            "output": "",
            "error": f"Task execution error ({type(exc).__name__}): {exc}",
            "tool_calls_made": [],
            "execution_time_ms": 0,
        }


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

    # Record episode to long-term memory store if enabled
    settings = get_settings()
    if getattr(settings, "enable_memory", False):
        try:
            from src.memory.store import Episode, get_memory_store
            store = get_memory_store()
            store.record_episode(
                Episode(
                    run_id=wf_id,
                    query=user_query,
                    goal=dag.goal or user_query,
                    dag_json=json.dumps(dag_dict),
                    outcome="accurate",
                    score=1.0,
                    tool_trace=json.dumps([{"task_id": tid, "output_preview": out[:200]} for tid, out in completed.items()]),
                )
            )
            logger.info("Recorded episode %s in long-term memory store", wf_id)
        except Exception as mem_err:
            logger.debug("Failed to record episode in memory store: %s", mem_err)

    # Autonomous Skill Distillation (Gap 5)
    if getattr(settings, "enable_skill_learning", False):
        try:
            from src.skills.distiller import SkillDistiller
            distiller = SkillDistiller(llm=llm)
            # Reconstruct tool trace from tasks in dag_dict
            full_trace = []
            for t in dag_dict.get("tasks", []):
                for tc in t.get("tool_calls_made", []):
                    full_trace.append({"tool": tc, "args": {}, "result": completed.get(t.get("id"), "")[:200]})
            if len(full_trace) >= 2:
                await distiller.distill(
                    goal=dag.goal or user_query,
                    tool_trace=full_trace,
                    supervisor_score=1.0,
                    workflow_id=wf_id,
                )
        except Exception as distill_err:
            logger.debug("Skill distillation check failed: %s", distill_err)

    return response


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


def parse_supervisor_response(
    resp: str,
) -> tuple[str, float | None, str, list]:
    """Extract a verdict from the supervisor's generated text.

    Raises on unparseable input so the caller can record the failure rather than
    inventing a verdict. Shared with the offline replay tooling so measured
    behaviour is the behaviour that actually runs.

    Returns ``(decision, confidence, feedback, missing_info)`` where confidence
    is ``None`` when the model reported none or reported a non-numeric value.
    """
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

    # Self-reported and uncalibrated: treat as a hint, never as a threshold.
    # A malformed value must not invalidate an otherwise usable verdict, so this
    # cast is guarded separately from the JSON parse above.
    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        confidence = None

    return decision, confidence, data.get("feedback", ""), data.get("missing_info", [])


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

    prior_summary = "\n".join(
        f"- Task {tid}: {out[:150]}..."
        for tid, out in prior_completed.items()
        if tid != task_id
    )

    prompt = SUPERVISOR_EVALUATION_PROMPT.format(
        user_query=user_query,
        task_name=task_name,
        task_description=task_desc,
        expected_output=expected_output or "Complete actionable task results",
        prior_context=prior_summary or "None",
        worker_output=worker_output[:2500],
        decision_options=format_decision_options(),
    )

    # Tracks whether we obtained a genuine supervisor verdict. When False the
    # output was never actually reviewed, and must not be reported as approved.
    degraded = False
    # Raw model response, retained for offline decision capture. Distinguishes a
    # malformed response from a transport failure after the fact.
    raw_response: str | None = None

    # Hybrid readout path (Phase 4). When a typed readout has been promoted and
    # clears its gate, it supplies the verdict. A confident "pass" needs no
    # further text, so the generation call is skipped entirely; anything else
    # still generates, because the retry path needs feedback prose that a choice
    # cannot provide. Inert unless decision_act_on_readout is enabled.
    readout_verdict = None
    try:
        from src.core import decision_shadow

        candidate = await decision_shadow.read_decision(
            "Did the worker adequately fulfil this task's expected output?",
            ["pass", "needs_retry", "abort"],
            (
                f"Goal: {user_query}\n"
                f"Task: {task_name}\n"
                f"Task description: {task_desc}\n"
                f"Expected output: {expected_output}\n\n"
                f"Worker output:\n{worker_output[:2500]}"
            ),
        )
        allowed, gate_reason = decision_shadow.evaluate_gate(candidate)
        if allowed and candidate is not None:
            readout_verdict = candidate
            logger.info(
                "Supervisor verdict from typed readout on '%s': %s (%s, p=%.3f)",
                task_name,
                candidate.decision,
                candidate.level,
                candidate.confidence or 0.0,
            )
        elif candidate is not None:
            logger.debug(
                "Typed readout not acted on for '%s': %s", task_name, gate_reason
            )
    except Exception as readout_err:
        logger.debug("Typed readout unavailable: %s", readout_err)

    if readout_verdict is not None and readout_verdict.decision == "pass":
        # Confident pass: no feedback text is needed, so nothing is generated.
        decision = "pass"
        confidence = readout_verdict.confidence
        feedback = ""
        missing_info = []
        raw_response = None
    else:
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
            raw_response = resp

            decision, confidence, feedback, missing_info = parse_supervisor_response(resp)
        except Exception as e:
            logger.warning(
                "Supervisor evaluation unavailable for task '%s': %s", task_name, e
            )
            # A verdict we could not obtain or parse is evidence of a problem, not
            # of success. Previously this defaulted to "pass", so an unparseable
            # (or entirely absent) response silently approved unreviewed work.
            degraded = True
            decision = "unreviewed"
            confidence = None
            feedback = (
                f"Supervisor evaluation was unavailable ({type(e).__name__}), so this "
                "output has NOT been reviewed. Treat the result as unverified."
            )
            missing_info = []

        if readout_verdict is not None:
            # The promoted readout decides; the generation call above ran only to
            # supply the feedback prose the retry path needs.
            decision = readout_verdict.decision
            confidence = readout_verdict.confidence
            degraded = False

    # Domain-agnostic circuit breaker: evaluate if critical discovery yielded 0 target artifacts
    is_initial_discovery = task_id in ("t1", "T1", "task-1") or any(
        s in task_dict.get("required_skills", [])
        for s in ("file_tree", "filesystem_inspection", "file_enumeration", "directory_listing", "evidence_collection")
    )
    low_output = worker_output.lower()
    has_concrete_data = any(
        marker in low_output
        for marker in (
            "total_bytes",
            "free_bytes",
            "total_gigabytes",
            "directory tree",
            "files and directories",
            "items enumerated",
            "items found",
            "host disk partition",
            "host drive / volume",
            "total capacity",
        )
    )
    has_missing_target = any(
        marker in low_output
        for marker in (
            "0 items enumerated",
            "0 files enumerated",
            "0 total log records",
            "total: 0 items",
            "does not exist on disk",
            "directory not found",
            "path not a file / 0 files found",
        )
    )
    if is_initial_discovery and has_missing_target and not has_concrete_data:
        decision = "abort"
        feedback = (
            "Target directory or logs yielded 0 items or could not be accessed. "
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
        "degraded": degraded,
    }

    # Record inputs + verdict for offline evaluation. Captured after the
    # override heuristics above so the stored decision is the one the system
    # actually acted on. No-op unless decision_capture_enabled.
    decision_capture.capture_supervisor_decision(
        task_dict=task_dict,
        worker_output=worker_output,
        user_query=user_query,
        prior_completed=prior_completed,
        raw_response=raw_response,
        decision=decision,
        confidence=confidence,
        degraded=degraded,
        workflow_id=wf_id,
    )

    # Compare against a typed readout of the same choice. Records the
    # comparison and acts on nothing. No-op unless decision_shadow_enabled.
    try:
        from src.core import decision_shadow

        await decision_shadow.shadow_supervisor_decision(
            task_dict=task_dict,
            worker_output=worker_output,
            user_query=user_query,
            generated_decision=decision,
            generated_confidence=confidence,
            workflow_id=wf_id,
        )
    except Exception as shadow_err:
        logger.debug("Shadow decision comparison failed: %s", shadow_err)

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
                "degraded": degraded,
            },
        )
    except Exception as eb_err:
        logger.debug("Failed to publish supervisor verdict: %s", eb_err)

    logger.info(
        "Supervisor verdict on '%s': %s (confidence: %s)",
        task_name,
        decision.upper(),
        f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "unmeasured",
    )

    return eval_result


