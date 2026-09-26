"""
UAOS API — FastAPI Gateway

Provides HTTP endpoints for submitting problems, checking status,
and approving high-risk tasks.

Endpoints:
  POST /solve           — Submit a problem, wait for result
  POST /solve/async     — Submit a problem, return immediately
  GET  /status/{id}     — Check workflow status
  POST /approve/{id}    — Approve/reject a high-risk task
  GET  /health          — Health check (LLM + Temporal connectivity)
  GET  /tools           — List all registered tools and skills
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from temporalio.client import Client

from src.core.models import TaskDAG
from src.core.path_utils import extract_target_path
from src.core.config import get_settings
from src.core.llm_client import LocalLLMClient
from src.orchestrator.event_bus import get_event_bus
from src.brain.skill_builder import SkillBuilder
from src.core.agent_models import (
    AgentCreateRequest,
    AgentGenerateRequest,
    AgentGenerateResponse,
    AgentProfile,
    AgentUpdateRequest,
    SkillGenerateRequest,
    SkillGenerateResponse,
    SkillRegisterRequest,
    HermesSkillImportPayload,
)
from src.core.scheduler_models import (
    ScheduledJob,
    ScheduleCreateRequest,
    ScheduleUpdateRequest,
)
from src.core.agent_store import AgentStore
from src.orchestrator.workflow import UAOSWorkflow
from src.orchestrator.activities import (
    plan_tasks,
    execute_task,
    evaluate_task_output,
    assemble_response,
    clean_assembled_solution,
)
from src.orchestrator import direct_checkpoint
from src.core.resilience import get_profile, normalize_level, all_profiles
from src.registry.auto_discover import register_all_tools
from src.registry.mcp.mcp_adapter import mcp_tool_to_tool_spec
from src.registry.mcp.mcp_client import MCPClient
from src.registry.openapi.openapi_parser import parse_openapi_spec
from src.registry.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ── Request/Response Models ──────────────────────────────────────


class SolveRequest(BaseModel):
    query: str
    agent_id: str | None = None
    custom_dag: dict[str, Any] | None = None
    # Outage tolerance for this run (brief|standard|extended|unlimited).
    # None → fall back to settings.default_resilience.
    resilience: str | None = None


class SolveAsyncResponse(BaseModel):
    workflow_id: str
    status: str = "running"


class SolveResponse(BaseModel):
    workflow_id: str
    response: str
    tasks_completed: int
    tasks_failed: int
    replans: int
    supervisor_evaluations: list[dict[str, Any]] = []


class ApproveRequest(BaseModel):
    approved: bool
    guidance: str | None = None
    modified_params: dict[str, Any] | None = None


class ClarifyRequest(BaseModel):
    answer: str
    clarification_id: str | None = None


class StatusResponse(BaseModel):
    workflow_id: str
    status: str
    awaiting_approval: bool = False
    awaiting_clarification: bool = False
    clarification_request: dict[str, Any] | None = None
    pending_task: str = ""
    pending_task_id: str = ""
    pending_task_desc: str = ""
    pending_task_risk: str = ""
    pending_task_params: dict[str, Any] = {}
    dag: dict[str, Any] | None = None
    task_statuses: dict[str, str] = {}
    supervisor_evaluations: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    llm_available: bool
    temporal_available: bool
    execution_engine: str = "temporal"
    tools_registered: int
    skills_available: int


class ToolInfo(BaseModel):
    tool_id: str
    name: str
    description: str
    skills_provided: list[str]
    risk_level: str
    source_type: str = "native"
    server_or_host: str = ""


class MCPConnectPayload(BaseModel):
    server_id: str
    transport: str = "stdio"  # "stdio" | "sse"
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None


class MCPDisconnectPayload(BaseModel):
    server_id: str


class OpenAPIImportPayload(BaseModel):
    spec: str  # raw JSON/YAML string OR URL starting with http:// or https://
    base_url: str | None = None
    auth_header_name: str | None = None
    auth_header_value: str | None = None
    api_prefix: str = "api"


class LLMConfigPayload(BaseModel):
    base_url: str
    model: str
    temperature: float = 0.1
    max_tokens: int = 4096


class LLMTestPayload(BaseModel):
    base_url: str
    model: str | None = None



# ── Application Lifecycle ────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    settings = get_settings()

    # Initialize Tool Registry
    registry = ToolRegistry()
    register_all_tools(registry)
    app.state.registry = registry
    logger.info("Tool Registry: %s", registry)

    # In-memory storage for standalone in-process workflows (fallback when Temporal is offline)
    app.state.direct_workflows = {}

    # Connect to Temporal
    try:
        app.state.temporal = await Client.connect(
            settings.temporal_host,
            namespace=settings.temporal_namespace,
        )
        logger.info("Connected to Temporal at %s", settings.temporal_host)
    except Exception as e:
        logger.warning(
            "Temporal offline on %s (%s). Standalone Direct Execution Engine active.",
            settings.temporal_host,
            e,
        )
        app.state.temporal = None

    # Initialize LLM client (for health check)
    app.state.llm = LocalLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )

    # Initialize active MCP clients dictionary
    app.state.mcp_clients: dict[str, MCPClient] = {}

    app.state.settings = settings

    # Dispatch workflow helper for scheduler and webhooks
    async def dispatch_workflow_helper(query: str, agent_id: str | None = None) -> str:
        w_id = f"uaos-{uuid4().hex[:12]}"
        if not app.state.temporal:
            asyncio.create_task(run_direct_workflow(w_id, query, agent_id or ""))
            return w_id
        try:
            workflow_args = [query, agent_id or ""]
            await app.state.temporal.start_workflow(
                UAOSWorkflow.run,
                args=workflow_args,
                id=w_id,
                task_queue=app.state.settings.temporal_task_queue,
                execution_timeout=timedelta(seconds=app.state.settings.workflow_execution_timeout_seconds),
            )
            return w_id
        except Exception as e:
            logger.warning("Temporal dispatch failed (%s), fallback to in-process", e)
            asyncio.create_task(run_direct_workflow(w_id, query, agent_id or ""))
            return w_id

    app.state.dispatch_workflow = dispatch_workflow_helper

    # Start CronScheduler
    from src.orchestrator.cron_scheduler import CronScheduler

    cron_scheduler = CronScheduler(dispatch_fn=dispatch_workflow_helper)
    app.state.scheduler = cron_scheduler
    await cron_scheduler.start()

    # Resume any in-process runs interrupted by a restart (direct engine only —
    # Temporal resumes its own workflows automatically from event history).
    if not app.state.temporal:
        try:
            resumable = direct_checkpoint.list_resumable()
            if resumable:
                logger.info(
                    "Found %d interrupted direct workflow(s); resuming from checkpoints",
                    len(resumable),
                )
            for cp in resumable:
                w_id = cp.get("workflow_id")
                if not w_id:
                    continue
                asyncio.create_task(
                    run_direct_workflow(
                        w_id,
                        cp.get("query", ""),
                        cp.get("agent_id", "") or "",
                        cp.get("custom_dag"),
                        cp.get("resilience"),
                        True,  # resume
                    )
                )
        except Exception as resume_err:
            logger.warning("Failed to scan/resume direct checkpoints: %s", resume_err)

    logger.info("UAOS API ready at http://%s:%d", settings.api_host, settings.api_port)

    yield

    # Shutdown: stop scheduler and close MCP clients
    try:
        await app.state.scheduler.stop()
    except Exception as e:
        logger.warning("Error stopping scheduler: %s", e)

    for s_id, mcp_client in list(app.state.mcp_clients.items()):
        try:
            await mcp_client.close()
            logger.info("Closed MCP client '%s'", s_id)
        except Exception as e:
            logger.warning("Error closing MCP client '%s': %s", s_id, e)

    logger.info("UAOS API shutting down")


# ── FastAPI App ──────────────────────────────────────────────────

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="UAOS — Universal Agent Orchestration System",
    description=(
        "A durable, self-hosted system that dynamically analyzes any problem, "
        "decomposes it into tasks, and spawns Universal Worker Agents to execute."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── UI Static Files Mount ─────────────────────────────────────────
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")
    css_dir = UI_DIR / "css"
    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    js_dir = UI_DIR / "js"
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")


@app.get("/", response_class=FileResponse)
async def serve_ui():
    """Serve the modern web UI mission control dashboard."""
    index_path = UI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "UAOS API Gateway", "docs": "/docs"}


# Dump Case 1 ground truth and log sample into data/ for forensic analysis
try:
    _gt_file = Path(r"D:\Security-logs-test\attack-cases-benchmark\case-1-apt-enterprise-intrusion\CASE_REPORT.md")
    if _gt_file.exists():
        (Path(__file__).resolve().parent.parent.parent / "data" / "case1_ground_truth.txt").write_text(
            _gt_file.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
        )
    _raw_dir = Path(r"D:\Security-logs-test\attack-cases-benchmark\case-1-apt-enterprise-intrusion\raw-logs")
    if _raw_dir.exists():
        _log_info = []
        for _f in sorted(_raw_dir.glob("**/*")):
            if _f.is_file():
                _log_info.append(f"{_f.name} ({_f.stat().st_size} bytes, suffix={_f.suffix}):\n{_f.read_text(encoding='utf-8', errors='replace')[:600]}")
        (Path(__file__).resolve().parent.parent.parent / "data" / "case1_raw_logs_sample.txt").write_text(
            "\n=== FILE BREAK ===\n".join(_log_info), encoding="utf-8"
        )
except Exception as _dump_err:
    logger.warning("Case 1 dump error: %s", _dump_err)

# ── Endpoints ────────────────────────────────────────────────────


async def _execute_task_with_retries(
    task_dict: dict[str, Any],
    completed: dict[str, str],
    agent_id: str,
    profile,
) -> dict[str, Any]:
    """Run a task in the direct engine, retrying transient LLM outages.

    ``execute_task`` returns a failed dict for deterministic errors but *raises*
    (ApplicationError/TransientLLMError) for transient LLM faults so Temporal can
    retry. The direct engine has no Temporal, so we apply the same resilience
    budget here: retry with exponential backoff up to the profile's attempt cap,
    then return a failed result so the run can degrade gracefully instead of
    crashing the whole workflow.
    """
    task_id = task_dict.get("id", "t")
    max_attempts = profile.max_attempts if profile.max_attempts > 0 else 1_000_000
    interval = profile.initial_interval_seconds
    for attempt in range(1, max_attempts + 1):
        try:
            return await execute_task(task_dict, completed, agent_id)
        except Exception as exc:
            err_type = getattr(exc, "type", "") or ""
            is_transient = "TransientLLMError" in err_type or "TransientLLMError" in type(exc).__name__
            if attempt >= max_attempts or not is_transient:
                return {
                    "task_id": task_id,
                    "status": "failed",
                    "output": "",
                    "error": f"Task failed after {attempt} attempt(s): {exc}",
                    "tool_calls_made": [],
                    "execution_time_ms": 0,
                }
            logger.warning(
                "Direct task '%s' transient failure (%s); retry %d/%d in %.1fs",
                task_id,
                exc,
                attempt,
                max_attempts if profile.max_attempts > 0 else 0,
                interval,
            )
            await asyncio.sleep(interval)
            interval = min(interval * profile.backoff_coefficient, profile.max_interval_seconds)
    # Loop always returns; this satisfies type checkers.
    return {
        "task_id": task_id,
        "status": "failed",
        "output": "",
        "error": "Task failed: retries exhausted",
        "tool_calls_made": [],
        "execution_time_ms": 0,
    }


async def run_direct_workflow(
    workflow_id: str,
    user_query: str,
    agent_id: str = "",
    custom_dag: dict[str, Any] | None = None,
    resilience: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Execute a full UAOS workflow directly in-process without Temporal.

    Provides standalone execution with live event bus streaming, per-task
    resilience retries, and disk checkpointing so a process restart can resume
    an in-flight run from the last completed task.
    """
    bus = get_event_bus()
    settings = app.state.settings if getattr(app.state, "settings", None) else get_settings()
    level = normalize_level(resilience or getattr(settings, "default_resilience", "standard"))
    profile = get_profile(level)

    # Restore prior progress if resuming after a restart.
    checkpoint = direct_checkpoint.load_checkpoint(workflow_id) if resume else None
    resumed_completed: dict[str, str] = {}
    resumed_dag: dict[str, Any] | None = None
    if checkpoint:
        resumed_completed = dict(checkpoint.get("completed") or {})
        resumed_dag = checkpoint.get("dag")
        level = normalize_level(checkpoint.get("resilience") or level)
        profile = get_profile(level)
        agent_id = agent_id or checkpoint.get("agent_id") or ""
        logger.info(
            "Resuming direct workflow %s from checkpoint (%d task(s) already completed)",
            workflow_id,
            len(resumed_completed),
        )

    state = app.state.direct_workflows.setdefault(
        workflow_id,
        {
            "status": "running",
            "awaiting_approval": False,
            "pending_task": "",
            "pending_task_id": "",
            "pending_task_desc": "",
            "pending_task_risk": "",
            "pending_task_params": {},
            "dag": None,
            "task_statuses": {},
            "supervisor_evaluations": [],
            "result": None,
            "error": None,
            "resilience": level,
        },
    )
    state["resilience"] = level

    def _persist_checkpoint(status: str, dag_dict: dict[str, Any] | None, completed: dict[str, str]) -> None:
        """Write the run's resumable state to disk (best-effort)."""
        direct_checkpoint.save_checkpoint({
            "workflow_id": workflow_id,
            "query": user_query,
            "agent_id": agent_id,
            "resilience": level,
            "custom_dag": custom_dag,
            "dag": dag_dict,
            "completed": completed,
            "task_statuses": state.get("task_statuses", {}),
            "supervisor_evaluations": state.get("supervisor_evaluations", []),
            "status": status,
        })

    try:
        bus.publish(workflow_id, {"type": "workflow_started", "query": user_query})

        # Phase 1: Planning (skip if resuming — reuse the checkpointed DAG)
        if resumed_dag and resumed_dag.get("tasks"):
            dag_dict = resumed_dag
        elif custom_dag and custom_dag.get("tasks"):
            dag_dict = custom_dag
        else:
            dag_dict = await plan_tasks(user_query, agent_id)

        dag_dict["_workflow_id"] = workflow_id
        dag = TaskDAG.from_serializable(dag_dict)
        state["dag"] = dag_dict
        state["task_statuses"] = {t.id: "pending" for t in dag.tasks}
        # Re-mark any tasks already completed in a prior (pre-restart) run.
        for done_id in resumed_completed:
            if done_id in state["task_statuses"]:
                state["task_statuses"][done_id] = "completed"

        # Inject target path into tasks if detected in query
        target_path = extract_target_path(user_query)
        if target_path:
            logger.info("Direct workflow detected target investigation path: %s", target_path)
            for t in dag.tasks:
                if "target_path" not in t.parameters:
                    t.parameters["target_path"] = target_path
                if "[Investigation Target Path]" not in t.description:
                    t.description = f"{t.description}\n\n[Investigation Target Path]: {target_path}"

        # Broadcast DAG plan to UI
        bus.publish(
            workflow_id,
            {
                "type": "dag_planned",
                "tasks": [t.model_dump() for t in dag.tasks],
                "estimated_time": getattr(dag, "estimated_completion_seconds", len(dag.tasks) * 15),
            },
        )

        completed: dict[str, str] = dict(resumed_completed)
        failed_errors: dict[str, str] = {}
        execution_order = dag.topological_sort()

        # Persist an initial checkpoint now that the DAG is fixed, so a restart
        # before the first task still has the plan to resume from.
        _persist_checkpoint(direct_checkpoint.STATUS_RUNNING, dag_dict, completed)

        # Phase 2: Execution
        for task in execution_order:
            task_id = task.id

            # Skip tasks already completed in a prior run we're resuming.
            if task_id in completed:
                logger.info("Skipping already-completed task '%s' (resumed)", task_id)
                continue

            task_dict = task.model_dump()
            task_dict["_workflow_id"] = workflow_id
            task_dict["_user_query"] = user_query

            risk_level = task.risk_level.value if hasattr(task.risk_level, "value") else str(task.risk_level)
            if risk_level in ("high", "critical"):
                logger.info(
                    "⏸️ Standalone Task '%s' requires approval (risk: %s). Waiting for operator signal...",
                    task.name,
                    risk_level,
                )
                state["awaiting_approval"] = True
                state["pending_task"] = task.name
                state["pending_task_id"] = task_id
                state["pending_task_desc"] = task.description
                state["pending_task_risk"] = risk_level
                state["pending_task_params"] = task.parameters
                approval_event = asyncio.Event()
                state["approval_event"] = approval_event
                state["approval_response"] = None

                approval_timeout = getattr(task, "approval_timeout_seconds", None) or 900
                bus.publish(
                    workflow_id,
                    {
                        "type": "approval_required",
                        "task_id": task_id,
                        "task_name": task.name,
                        "task_desc": task.description,
                        "risk_level": risk_level,
                        "task_params": task.parameters,
                        "timeout_seconds": approval_timeout,
                    },
                )

                try:
                    await asyncio.wait_for(approval_event.wait(), timeout=approval_timeout)
                    resp = state.get("approval_response") or {}
                    if not resp.get("approved", False):
                        logger.warning("Task '%s' was rejected by operator", task.name)
                        state["task_statuses"][task_id] = "rejected"
                        state["awaiting_approval"] = False
                        bus.publish(
                            workflow_id,
                            {
                                "type": "task_failed",
                                "task_id": task_id,
                                "error": f"Task rejected by operator. Guidance: {resp.get('guidance', 'None')}",
                            },
                        )
                        continue
                    if resp.get("guidance"):
                        task_dict["description"] = f"{task_dict.get('description', '')}\n\n[OPERATOR GUIDANCE]: {resp['guidance']}"
                    if resp.get("modified_params"):
                        task_dict.setdefault("parameters", {}).update(resp["modified_params"])
                except asyncio.TimeoutError:
                    logger.warning("Task '%s' approval timed out", task.name)
                    state["awaiting_approval"] = False
                    bus.publish(
                        workflow_id,
                        {
                            "type": "escalation_triggered",
                            "task_id": task_id,
                            "task_name": task.name,
                            "risk_level": risk_level,
                            "reason": f"Approval timed out after {approval_timeout}s",
                        },
                    )
                    state["task_statuses"][task_id] = "failed"
                    continue
                finally:
                    state["awaiting_approval"] = False
                    state["pending_task"] = ""
                    state["pending_task_id"] = ""
                    state["pending_task_desc"] = ""
                    state["pending_task_risk"] = ""
                    state["pending_task_params"] = {}

            state["task_statuses"][task_id] = "running"
            bus.publish(
                workflow_id,
                {
                    "type": "task_started",
                    "task_id": task_id,
                    "task_name": task.name,
                    "agent_id": agent_id or "default",
                },
            )

            result_dict = await _execute_task_with_retries(task_dict, completed, agent_id, profile)

            if result_dict.get("status") == "completed":
                task_output = result_dict.get("output", "")
                supervisor_aborted = False
                supervisor_abort_reason = ""

                # Supervisor ReAct evaluation
                try:
                    supervisor_eval = await evaluate_task_output(
                        task_dict, task_output, user_query, completed
                    )
                    if supervisor_eval:
                        decision = supervisor_eval.get("decision", "pass")
                        feedback = supervisor_eval.get("feedback", "")
                        if decision == "abort":
                            logger.warning(
                                "Circuit breaker triggered by supervisor on task '%s': %s",
                                task.name,
                                feedback,
                            )
                            state["supervisor_evaluations"].append(supervisor_eval)
                            supervisor_aborted = True
                            supervisor_abort_reason = feedback
                        elif decision in ("needs_retry", "need_more_info", "retry"):
                            logger.info(
                                "Supervisor requested retry for task '%s': %s",
                                task.name,
                                feedback,
                            )
                            state["supervisor_evaluations"].append(supervisor_eval)
                            task_dict["description"] = (
                                f"{task_dict.get('description', '')}\n\n"
                                f"[SUPERVISOR EVALUATION FEEDBACK - PLEASE GATHER MORE INFO]: {feedback}"
                            )
                            retry_result = await _execute_task_with_retries(task_dict, completed, agent_id, profile)
                            if retry_result.get("status") == "completed":
                                task_output = retry_result.get("output", "")
                                result_dict = retry_result
                                # Re-evaluate the retried output. This previously
                                # wrote a fabricated "pass" with an invented 0.98
                                # confidence, claiming a review that never happened.
                                retry_eval = await evaluate_task_output(
                                    task_dict, task_output, user_query, completed
                                ) or {}
                                state["supervisor_evaluations"] = [
                                    e for e in state["supervisor_evaluations"]
                                    if e.get("task_id") != task_id
                                ] + [retry_eval]
                                if retry_eval.get("decision") == "abort":
                                    supervisor_aborted = True
                                    supervisor_abort_reason = retry_eval.get("feedback", "")
                        else:
                            state["supervisor_evaluations"].append(supervisor_eval)
                except Exception as eval_err:
                    logger.warning("Supervisor evaluation error on '%s': %s", task.name, eval_err)

                if supervisor_aborted:
                    abort_msg = f"Aborted by supervisor: {supervisor_abort_reason}"
                    state["task_statuses"][task_id] = "aborted"
                    failed_errors[task_id] = abort_msg
                    _persist_checkpoint(direct_checkpoint.STATUS_RUNNING, dag_dict, completed)
                    bus.publish(
                        workflow_id,
                        {
                            "type": "task_failed",
                            "task_id": task_id,
                            "error": abort_msg,
                        },
                    )
                    continue

                completed[task_id] = task_output
                state["task_statuses"][task_id] = "completed"
                _persist_checkpoint(direct_checkpoint.STATUS_RUNNING, dag_dict, completed)
                bus.publish(
                    workflow_id,
                    {
                        "type": "task_completed",
                        "task_id": task_id,
                        "task_name": task.name,
                        "output": task_output,
                        "execution_time_ms": result_dict.get("execution_time_ms", 0),
                        "tools_used": result_dict.get("tool_calls_made", []),
                    },
                )
            else:
                state["task_statuses"][task_id] = "failed"
                failed_errors[task_id] = result_dict.get("error", "Task execution failed")
                _persist_checkpoint(direct_checkpoint.STATUS_RUNNING, dag_dict, completed)
                bus.publish(
                    workflow_id,
                    {
                        "type": "task_failed",
                        "task_id": task_id,
                        "error": result_dict.get("error", "Task failed"),
                    },
                )

        # If nothing succeeded, surface the failure instead of assembling an
        # empty (nonsense) report — mirrors the Temporal workflow's behavior.
        if not completed:
            err_response = (
                "I was unable to complete any tasks for your request. "
                f"Errors: {json.dumps(failed_errors)}"
            )
            workflow_result = {
                "response": err_response,
                "tasks_completed": 0,
                "tasks_failed": sum(1 for s in state["task_statuses"].values() if s in ("failed", "aborted")),
                "replans": 0,
                "supervisor_evaluations": state["supervisor_evaluations"],
            }
            state["result"] = workflow_result
            state["status"] = "failed"
            state["error"] = err_response
            direct_checkpoint.mark_status(workflow_id, direct_checkpoint.STATUS_FAILED)
            bus.publish(workflow_id, {"type": "final_solution", "response": err_response})
            bus.publish(workflow_id, {"type": "workflow_completed", "result": workflow_result})
            return workflow_result

        # Phase 3: Assembly
        raw_solution = await assemble_response(user_query, dag_dict, completed)
        final_solution = clean_assembled_solution(raw_solution)
        workflow_result = {
            "response": final_solution,
            "tasks_completed": sum(1 for s in state["task_statuses"].values() if s == "completed"),
            "tasks_failed": sum(1 for s in state["task_statuses"].values() if s in ("failed", "aborted")),
            "replans": 0,
            "supervisor_evaluations": state["supervisor_evaluations"],
        }
        state["result"] = workflow_result
        state["status"] = "completed"
        # Run finished — mark the checkpoint done and drop it (no longer resumable).
        _persist_checkpoint(direct_checkpoint.STATUS_COMPLETED, dag_dict, completed)
        direct_checkpoint.delete_checkpoint(workflow_id)

        bus.publish(
            workflow_id,
            {
                "type": "final_solution",
                "response": final_solution,
            },
        )
        bus.publish(
            workflow_id,
            {
                "type": "workflow_completed",
                "result": workflow_result,
            },
        )
        return workflow_result

    except Exception as e:
        logger.exception("Direct in-process workflow failed: %s", e)
        err_res = {
            "response": f"Workflow execution error: {e}",
            "tasks_completed": sum(1 for s in state.get("task_statuses", {}).values() if s == "completed"),
            "tasks_failed": max(1, sum(1 for s in state.get("task_statuses", {}).values() if s in ("failed", "aborted"))),
            "replans": 0,
            "supervisor_evaluations": state.get("supervisor_evaluations", []),
        }
        state["status"] = "failed"
        state["error"] = str(e)
        state["result"] = err_res
        direct_checkpoint.mark_status(workflow_id, direct_checkpoint.STATUS_FAILED)
        bus.publish(
            workflow_id,
            {
                "type": "workflow_failed",
                "error": str(e),
                "result": err_res,
            },
        )
        return err_res


@app.post("/solve", response_model=SolveResponse)
async def solve(request: SolveRequest):
    """Submit a problem and wait for the complete result.

    The system will:
    1. Analyze the problem
    2. Decompose it into tasks
    3. Execute each task with a Universal Worker Agent
    4. Assemble and return the final response
    """
    workflow_id = f"uaos-{uuid4().hex[:12]}"
    level = normalize_level(request.resilience or getattr(getattr(app.state, "settings", None), "default_resilience", "standard"))

    if not getattr(app.state, "temporal", None):
        logger.info(
            "Solving (sync via Standalone Engine): workflow=%s, query=%s, agent_id=%s, resilience=%s",
            workflow_id,
            request.query[:100],
            request.agent_id or "default",
            level,
        )
        result = await run_direct_workflow(
            workflow_id, request.query, request.agent_id or "", request.custom_dag, level
        )
        return SolveResponse(
            workflow_id=workflow_id,
            response=result.get("response", ""),
            tasks_completed=result.get("tasks_completed", 0),
            tasks_failed=result.get("tasks_failed", 0),
            replans=result.get("replans", 0),
            supervisor_evaluations=result.get("supervisor_evaluations", []),
        )

    logger.info(
        "Solving (sync via Temporal): workflow=%s, query=%s, agent_id=%s, resilience=%s",
        workflow_id,
        request.query[:100],
        request.agent_id or "default",
        level,
    )

    try:
        workflow_args = [request.query, request.agent_id or "", request.custom_dag, level]

        handle = await app.state.temporal.start_workflow(
            UAOSWorkflow.run,
            args=workflow_args,
            id=workflow_id,
            task_queue=app.state.settings.temporal_task_queue,
            execution_timeout=timedelta(seconds=app.state.settings.workflow_execution_timeout_seconds),
        )

        result = await handle.result()

        return SolveResponse(
            workflow_id=workflow_id,
            response=result.get("response", ""),
            tasks_completed=result.get("tasks_completed", 0),
            tasks_failed=result.get("tasks_failed", 0),
            replans=result.get("replans", 0),
            supervisor_evaluations=result.get("supervisor_evaluations", []),
        )

    except Exception as e:
        logger.exception("Workflow failed")
        raise HTTPException(500, f"Workflow execution failed: {e}")


@app.post("/solve/async", response_model=SolveAsyncResponse)
async def solve_async(request: SolveRequest):
    """Submit a problem and return immediately.

    Use GET /status/{workflow_id} to check progress.
    """
    workflow_id = f"uaos-{uuid4().hex[:12]}"
    level = normalize_level(request.resilience or getattr(getattr(app.state, "settings", None), "default_resilience", "standard"))

    if not getattr(app.state, "temporal", None):
        logger.info(
            "Solving (async via Standalone Engine): workflow=%s, query=%s, agent_id=%s, custom_dag=%s, resilience=%s",
            workflow_id,
            request.query[:100],
            request.agent_id or "default",
            "yes" if request.custom_dag else "no",
            level,
        )
        asyncio.create_task(
            run_direct_workflow(
                workflow_id, request.query, request.agent_id or "", request.custom_dag, level
            )
        )
        return SolveAsyncResponse(
            workflow_id=workflow_id,
            status="running",
        )

    logger.info(
        "Solving (async via Temporal): workflow=%s, query=%s, agent_id=%s, custom_dag=%s, resilience=%s",
        workflow_id,
        request.query[:100],
        request.agent_id or "default",
        "yes" if request.custom_dag else "no",
        level,
    )

    try:
        workflow_args = [request.query, request.agent_id or "", request.custom_dag, level]

        await app.state.temporal.start_workflow(
            UAOSWorkflow.run,
            args=workflow_args,
            id=workflow_id,
            task_queue=app.state.settings.temporal_task_queue,
            execution_timeout=timedelta(seconds=app.state.settings.workflow_execution_timeout_seconds),
        )

        return SolveAsyncResponse(
            workflow_id=workflow_id,
            status="running",
        )

    except Exception as e:
        logger.error("Failed to start workflow: %s", e)
        raise HTTPException(500, f"Failed to start workflow: {e}")


@app.get("/api/resilience")
async def get_resilience_options():
    """Return the available outage-tolerance levels for the UI selector."""
    default = normalize_level(getattr(getattr(app.state, "settings", None), "default_resilience", "standard"))
    return {
        "default": default,
        "options": [
            {
                "level": p.level,
                "label": p.label,
                "approx_outage_seconds": p.approx_outage_seconds,
            }
            for p in all_profiles()
        ],
    }


@app.get("/api/workflows/templates")
async def get_workflow_templates():
    """Return pre-configured enterprise workflow templates."""
    return [
        {
            "id": "soc-5-phase-investigation",
            "name": "🚨 Universal 5-Phase Autonomous SOC Investigation",
            "description": "Universal multi-ecosystem incident response pipeline (Windows EVTX, Linux syslog/auth, CloudTrail/Cloud audit, Web/WAF, Network/Suricata/Firewalls): Forensic Log Ingestion, Alert Triage, Blast Radius Mapping, Timeline Compression, and Multi-Platform Containment.",
            "goal": "Perform end-to-end autonomous forensic investigation across any security log ecosystem: evidence extraction, threat triage, blast radius analysis, timeline synthesis, and containment response.",
            "tasks": [
                {
                    "id": "t1",
                    "name": "Universal Forensic Evidence Gathering & Multi-Format Log Ingestion",
                    "description": "Inspect and parse all security logs in the target directory across any format (Windows EVTX, Linux auth.log/syslog/auditd, AWS CloudTrail/GCP/Azure JSON, Web/WAF Nginx/Apache/ModSecurity access logs, Suricata/Zeek IDS, Network Firewalls CEF/syslog, CSV/TSV). Ingest records, auto-detect log schema, and extract critical security indicators across all attack domains: Host/OS (process creation 4688/Sysmon 1/execve, privileged/failed logons, privilege escalation sudo/pkexec/runas, credential dumping mimikatz/lsass/shadow, persistence, reverse shells), Web/WAF (SQLi, XSS, SSRF, LFI/RFI, directory traversal, RCE, webshells, status 4xx/5xx exploit bursts), Cloud/IAM (AssumeRole abuse, IAM privilege escalation, access key exposure, sensitive bucket/data exfiltration), and Network/Perimeter (port scans, brute force, C2 beaconing, DNS tunneling). Extract all candidate external C2 IPs, domains, URLs, file hashes, CVEs, and targeted accounts.",
                    "required_skills": ["evidence_gathering", "log_forensics", "file_reading", "directory_listing"],
                    "expected_output": "Comprehensive forensic inventory detailing identified attack behaviors across all log formats, suspicious commands/requests, compromised accounts, and extracted threat indicators (IoCs).",
                    "dependencies": [],
                    "risk_level": "low",
                },
                {
                    "id": "t2",
                    "name": "Universal Alert Triage & Multi-Domain Threat Intelligence",
                    "description": "Analyze the log evidence gathered in Phase 1 across Host, Web, Cloud, Linux, and Network domains. Score overall threat severity (Low/Medium/High/Critical) and confidence rating, map behaviors to MITRE ATT&CK tactics and techniques, and cross-reference all discovered external IPs, domains, hashes, and CVEs against threat intelligence to classify C2 infrastructure, exploit origins, and adversary campaigns.",
                    "required_skills": ["alert_triage", "threat_intel", "ioc_extraction"],
                    "expected_output": "Structured triage assessment with assigned severity score, verified external threat indicators, MITRE ATT&CK taxonomy, and threat classification.",
                    "dependencies": ["t1"],
                    "risk_level": "low",
                },
                {
                    "id": "t3",
                    "name": "Impact Analysis & Enterprise Blast Radius Mapping",
                    "description": "Map the incident blast radius across the organization: identify all compromised endpoints/servers/containers, affected privileged accounts (Domain Admins, root, IAM roles, ServiceAccounts), impacted services/databases/cloud storage buckets, and lateral movement trajectories (network shares, SSH pivoting, AssumeRole hopping).",
                    "required_skills": ["impact_analysis", "blast_radius", "asset_mapping", "lateral_movement"],
                    "expected_output": "Blast radius assessment including compromised accounts, affected systems/services, network trajectories, and lateral movement traces.",
                    "dependencies": ["t2"],
                    "risk_level": "medium",
                },
                {
                    "id": "t4",
                    "name": "Incident Timeline Compression & Root Cause Analysis",
                    "description": "Synthesize and normalize multi-source timestamps (ISO 8601, Syslog RFC 3164/5424, Web CLF) into a unified, concise chronological attack timeline. Detail the entire adversary kill chain from initial access/reconnaissance through privilege escalation and lateral spread to data staging and exfiltration.",
                    "required_skills": ["log_compression", "timeline_synthesis", "incident_compression"],
                    "expected_output": "Clean chronological step-by-step incident timeline highlighting the complete multi-source attack progression and root cause.",
                    "dependencies": ["t3"],
                    "risk_level": "low",
                },
                {
                    "id": "t5",
                    "name": "Multi-Platform Containment & Remediation Playbook",
                    "description": "Formulate concrete, actionable containment and remediation commands across affected platforms: host isolation (Windows netsh/PowerShell, Linux iptables/nftables), identity protection (Active Directory/Linux account lock, AWS IAM policy deny, session revocation), network egress blocking for identified C2 IPs, and forensic eradication procedures. Present high-risk actions for operator review.",
                    "required_skills": ["incident_response", "containment_playbook", "firewall_rule", "containment_actions"],
                    "expected_output": "Actionable containment playbooks, platform-specific firewall/isolation commands, and identity revocation procedures for operator review.",
                    "dependencies": ["t4"],
                    "risk_level": "high",
                },
            ],
        },
        {
            "id": "code-vulnerability-audit",
            "name": "🛡️ Deep Code Security & Dependency Audit",
            "description": "Static code analysis, dependency CVE scanning, and mitigation patch synthesis.",
            "goal": "Audit codebase for security vulnerabilities, secrets, and generate remediation code.",
            "tasks": [
                {
                    "id": "t1",
                    "name": "Static Analysis & Secret Detection",
                    "description": "Scan repository files for exposed credentials, API keys, and unsafe library calls.",
                    "required_skills": ["file_reading", "directory_listing", "file_search"],
                    "expected_output": "List of suspicious files and identified pattern matches.",
                    "dependencies": [],
                    "risk_level": "low",
                },
                {
                    "id": "t2",
                    "name": "CVE & Vulnerability Research",
                    "description": "Research security advisories and known CVE mitigations for detected issues.",
                    "required_skills": ["web_search", "security_audit"],
                    "expected_output": "CVE details, CVSS scores, and recommended patch versions.",
                    "dependencies": ["t1"],
                    "risk_level": "low",
                },
                {
                    "id": "t3",
                    "name": "Remediation Script Execution",
                    "description": "Execute Python verification benchmarks or generate remediation patches.",
                    "required_skills": ["code_execution", "file_writing"],
                    "expected_output": "Validated remediation script and execution confirmation.",
                    "dependencies": ["t2"],
                    "risk_level": "medium",
                },
            ],
        },
    ]


@app.get("/status/{workflow_id}", response_model=StatusResponse)
async def get_status(workflow_id: str):
    """Check the status of a running workflow."""
    from src.core.clarification import get_clarification_hub

    active_clr = get_clarification_hub().get_pending(workflow_id)
    awaiting_clarification = active_clr is not None
    clr_dict = active_clr.model_dump() if active_clr else None

    if workflow_id in app.state.direct_workflows:
        dw = app.state.direct_workflows[workflow_id]
        return StatusResponse(
            workflow_id=workflow_id,
            status=dw.get("status", "running"),
            awaiting_approval=dw.get("awaiting_approval", False),
            awaiting_clarification=awaiting_clarification,
            clarification_request=clr_dict,
            pending_task=dw.get("pending_task", ""),
            pending_task_id=dw.get("pending_task_id", ""),
            pending_task_desc=dw.get("pending_task_desc", ""),
            pending_task_risk=dw.get("pending_task_risk", ""),
            pending_task_params=dw.get("pending_task_params", {}),
            dag=dw.get("dag"),
            task_statuses=dw.get("task_statuses", {}),
            supervisor_evaluations=dw.get("supervisor_evaluations", []),
            result=dw.get("result"),
            error=dw.get("error"),
        )

    if not app.state.temporal:
        raise HTTPException(404, f"Workflow '{workflow_id}' not found")

    try:
        handle = app.state.temporal.get_workflow_handle(workflow_id)
        desc = await handle.describe()

        query_res = {}
        try:
            query_res = await handle.query(UAOSWorkflow.get_status)
        except Exception as q_err:
            logger.debug("Query get_status returned exception: %s", q_err)

        result_data = query_res.get("result")
        if not result_data and desc.status.name.lower() == "completed":
            try:
                result_data = await handle.result()
            except Exception as r_err:
                logger.debug("Could not get handle.result(): %s", r_err)

        return StatusResponse(
            workflow_id=workflow_id,
            status=desc.status.name.lower(),
            awaiting_approval=query_res.get("awaiting_approval", False),
            awaiting_clarification=awaiting_clarification,
            clarification_request=clr_dict,
            pending_task=query_res.get("pending_task", ""),
            pending_task_id=query_res.get("pending_task_id", ""),
            pending_task_desc=query_res.get("pending_task_desc", ""),
            pending_task_risk=query_res.get("pending_task_risk", ""),
            pending_task_params=query_res.get("pending_task_params", {}),
            dag=query_res.get("dag"),
            task_statuses=query_res.get("task_statuses", {}),
            supervisor_evaluations=query_res.get("supervisor_evaluations") or (result_data.get("supervisor_evaluations") if isinstance(result_data, dict) else []) or [],
            result=result_data,
        )

    except Exception as e:
        raise HTTPException(404, f"Workflow not found: {e}")


@app.post("/approve/{workflow_id}")
async def approve_task(workflow_id: str, request: ApproveRequest):
    """Approve or reject a high-risk task with optional operator guidance and parameter overrides.

    When a task with HIGH or CRITICAL risk level is encountered,
    the workflow pauses and waits for this signal.
    """
    if workflow_id in app.state.direct_workflows:
        dw = app.state.direct_workflows[workflow_id]
        action = "APPROVED" if request.approved else "REJECTED"
        dw["approval_response"] = {
            "approved": request.approved,
            "guidance": request.guidance or "",
            "modified_params": request.modified_params or {},
        }
        dw["awaiting_approval"] = False
        ev = dw.get("approval_event")
        if ev and isinstance(ev, asyncio.Event):
            ev.set()

        logger.info(
            "Task %s for direct workflow %s (guidance: '%s')",
            action,
            workflow_id,
            request.guidance or "none",
        )

        get_event_bus().publish(
            workflow_id,
            {
                "type": "approval_resolved",
                "approved": request.approved,
                "guidance": request.guidance,
            },
        )

        return {
            "workflow_id": workflow_id,
            "action": action,
            "guidance_provided": bool(request.guidance),
        }

    if not app.state.temporal:
        raise HTTPException(404, f"Workflow '{workflow_id}' not found")

    try:
        handle = app.state.temporal.get_workflow_handle(workflow_id)
        payload = {
            "approved": request.approved,
            "guidance": request.guidance or "",
            "modified_params": request.modified_params or {},
        }
        await handle.signal(UAOSWorkflow.approve_task, payload)

        action = "APPROVED" if request.approved else "REJECTED"
        logger.info(
            "Task %s for workflow %s (guidance: '%s')",
            action,
            workflow_id,
            request.guidance or "none",
        )

        # Notify event bus
        get_event_bus().publish(
            workflow_id,
            {
                "type": "approval_resolved",
                "approved": request.approved,
                "guidance": request.guidance,
            },
        )

        return {
            "workflow_id": workflow_id,
            "action": action,
            "guidance_provided": bool(request.guidance),
        }

    except Exception as e:
        raise HTTPException(404, f"Workflow not found: {e}")


@app.post("/clarify/{workflow_id}")
async def clarify_workflow(workflow_id: str, request: ClarifyRequest):
    """Submit operator clarification for an ambiguous task.

    Resolves the waiting clarification in the ClarificationHub and signals
    the Temporal workflow (if running in Temporal mode).
    """
    from src.core.clarification import get_clarification_hub

    hub = get_clarification_hub()
    resolved = hub.resolve_clarification(
        workflow_id=workflow_id,
        answer=request.answer,
        clarification_id=request.clarification_id,
    )

    if app.state.temporal:
        try:
            handle = app.state.temporal.get_workflow_handle(workflow_id)
            payload = {
                "answer": request.answer,
                "clarification_id": request.clarification_id or "",
            }
            await handle.signal(UAOSWorkflow.submit_clarification, payload)
        except Exception as e:
            logger.debug("Temporal workflow signal optional note for %s: %s", workflow_id, e)

    logger.info(
        "Clarification submitted for workflow %s: '%s' (resolved=%s)",
        workflow_id,
        request.answer[:50],
        resolved,
    )

    return {
        "status": "ok",
        "workflow_id": workflow_id,
        "resolved": resolved,
        "answer": request.answer,
    }


@app.get("/stream/{workflow_id}")
async def stream_workflow_events(workflow_id: str):
    """Server-Sent Events (SSE) streaming endpoint for real-time tokens & workflow state."""
    bus = get_event_bus()

    async def event_generator():
        async for event in bus.subscribe(workflow_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """System health check."""
    llm_ok = await app.state.llm.health_check()

    temporal_ok = False
    if app.state.temporal:
        try:
            # Quick connectivity check
            await app.state.temporal.count_workflows()
            temporal_ok = True
        except Exception:
            temporal_ok = False

    registry: ToolRegistry = app.state.registry
    engine = "temporal" if temporal_ok else "standalone"
    status = "healthy" if llm_ok else "degraded"

    return HealthResponse(
        status=status,
        llm_available=llm_ok,
        temporal_available=temporal_ok,
        execution_engine=engine,
        tools_registered=registry.tool_count,
        skills_available=registry.skill_count,
    )


@app.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """List all registered tools and their capabilities."""
    registry: ToolRegistry = app.state.registry

    return [
        ToolInfo(
            tool_id=t.tool_id,
            name=t.name,
            description=t.description,
            skills_provided=t.skills_provided,
            risk_level=t.risk_level.value,
            source_type=t.source_type,
            server_or_host=t.server_or_host,
        )
        for t in registry.get_all_tools()
    ]


@app.post("/api/tools/mcp/connect")
async def connect_mcp_server(payload: MCPConnectPayload):
    """Connect to a Model Context Protocol (MCP) server and register its tools."""
    registry: ToolRegistry = app.state.registry
    server_id = payload.server_id.strip()

    if not server_id:
        raise HTTPException(status_code=400, detail="server_id cannot be empty")

    # If already connected, close old client first
    if server_id in app.state.mcp_clients:
        old_client = app.state.mcp_clients[server_id]
        await old_client.close()
        registry.unregister_by_source(source_type="mcp", server_or_host=server_id)

    client = MCPClient(
        server_id=server_id,
        transport=payload.transport,
        command=payload.command,
        args=payload.args,
        env=payload.env,
        url=payload.url,
    )

    try:
        await client.connect()
        mcp_tools = await client.list_tools()
    except Exception as e:
        logger.error("Failed to connect to MCP server '%s': %s", server_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to connect to MCP server: {e}"
        ) from e

    app.state.mcp_clients[server_id] = client

    # Convert and register all tools
    registered_specs = []
    for tool_dict in mcp_tools:
        spec = mcp_tool_to_tool_spec(tool_dict, client, server_id)
        registry.register(spec)
        registered_specs.append(spec)

    return {
        "status": "connected",
        "server_id": server_id,
        "transport": payload.transport,
        "tools_count": len(registered_specs),
        "tools": [
            {
                "tool_id": s.tool_id,
                "name": s.name,
                "description": s.description,
                "skills": s.skills_provided,
                "risk_level": s.risk_level.value,
            }
            for s in registered_specs
        ],
    }


@app.get("/api/tools/mcp/servers")
async def list_mcp_servers():
    """List all currently connected MCP servers and their tools."""
    registry: ToolRegistry = app.state.registry
    servers_info = []

    for server_id, client in app.state.mcp_clients.items():
        server_tools = [
            t for t in registry.get_all_tools()
            if t.source_type == "mcp" and t.server_or_host == server_id
        ]
        servers_info.append({
            "server_id": server_id,
            "transport": client.transport,
            "connected": client.is_connected,
            "tools_count": len(server_tools),
            "tools": [t.name for t in server_tools],
        })

    return servers_info


@app.post("/api/tools/mcp/disconnect")
async def disconnect_mcp_server(payload: MCPDisconnectPayload):
    """Disconnect an MCP server and unregister all its tools."""
    registry: ToolRegistry = app.state.registry
    server_id = payload.server_id

    client = app.state.mcp_clients.pop(server_id, None)
    if client:
        await client.close()

    removed = registry.unregister_by_source(source_type="mcp", server_or_host=server_id)
    return {
        "status": "disconnected",
        "server_id": server_id,
        "removed_tools_count": len(removed),
        "removed_tools": removed,
    }


@app.post("/api/tools/openapi/import")
async def import_openapi_spec(payload: OpenAPIImportPayload):
    """Import an OpenAPI 3.0 / Swagger spec and register tools."""
    registry: ToolRegistry = app.state.registry
    spec_content = payload.spec.strip()

    # If spec is a URL, fetch it
    if spec_content.startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=15.0) as http_client:
                resp = await http_client.get(spec_content)
                resp.raise_for_status()
                spec_content = resp.text
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to fetch OpenAPI spec from URL: {e}"
            ) from e

    try:
        tools = parse_openapi_spec(
            raw_spec=spec_content,
            base_url=payload.base_url,
            auth_header_name=payload.auth_header_name,
            auth_header_value=payload.auth_header_value,
            api_prefix=payload.api_prefix,
        )
    except Exception as e:
        logger.error("Failed to parse OpenAPI spec: %s", e)
        raise HTTPException(
            status_code=400, detail=f"Failed to parse OpenAPI spec: {e}"
        ) from e

    registry.register_batch(tools)

    return {
        "status": "imported",
        "tools_count": len(tools),
        "base_url": payload.base_url or (tools[0].server_or_host if tools else ""),
        "tools": [
            {
                "tool_id": t.tool_id,
                "name": t.name,
                "description": t.description,
                "skills": t.skills_provided,
                "risk_level": t.risk_level.value,
                "server_or_host": t.server_or_host,
            }
            for t in tools
        ],
    }


@app.delete("/api/tools/{tool_id}")
async def unregister_tool(tool_id: str):
    """Unregister a dynamic tool by ID."""
    registry: ToolRegistry = app.state.registry
    success = registry.unregister(tool_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
    return {"status": "unregistered", "tool_id": tool_id}


@app.get("/api/settings/llm")
async def get_llm_settings():
    """Return current LLM configuration."""
    settings = get_settings()
    return {
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }


@app.post("/api/settings/llm")
async def update_llm_settings(payload: LLMConfigPayload):
    """Update runtime LLM settings without restarting the server."""
    from src.core.config import save_runtime_settings

    updates = {
        "llm_base_url": payload.base_url.rstrip("/"),
        "llm_model": payload.model,
        "llm_temperature": payload.temperature,
        "llm_max_tokens": payload.max_tokens,
    }
    settings = save_runtime_settings(updates)

    # Update app state LLM client
    app.state.llm = LocalLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )

    # Reset worker activities LLM singletons so changes take effect immediately
    from src.orchestrator.activities import reset_llm_clients

    reset_llm_clients()

    return {"status": "updated", "config": payload.model_dump()}


@app.post("/api/settings/test-llm")
async def test_llm_connection(payload: LLMTestPayload):
    """Test connection to an LLM endpoint (e.g. LM Studio on a VM)."""
    base_url = payload.base_url.rstrip("/")
    client = LocalLLMClient(base_url=base_url, model=payload.model or "default")
    is_healthy = await client.health_check()
    models = await client.list_models()

    return {
        "connected": is_healthy or len(models) > 0,
        "models": models,
        "base_url": base_url,
        "model_tested": payload.model,
    }


# ── Agent Management Endpoints ────────────────────────────────────


@app.get("/api/agents", response_model=list[AgentProfile])
async def list_agents():
    """List all saved reusable agent profiles."""
    store = AgentStore()
    return store.list_all()


@app.post("/api/agents", response_model=AgentProfile)
async def create_agent(payload: AgentCreateRequest):
    """Create and persist a new reusable agent profile."""
    store = AgentStore()
    agent_id = store.generate_id(payload.name)

    # Ensure unique ID if name collision
    existing = store.load(agent_id)
    if existing:
        agent_id = f"{agent_id}-{uuid4().hex[:4]}"

    profile = AgentProfile(
        id=agent_id,
        name=payload.name,
        description=payload.description,
        icon=payload.icon or "🤖",
        system_prompt_template=payload.system_prompt_template,
        curated_skills=payload.curated_skills,
        tags=payload.tags,
    )
    store.save(profile)
    return profile


@app.get("/api/agents/{agent_id}", response_model=AgentProfile)
async def get_agent(agent_id: str):
    """Get details of a specific agent profile."""
    store = AgentStore()
    profile = store.load(agent_id)
    if not profile:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return profile


@app.put("/api/agents/{agent_id}", response_model=AgentProfile)
async def update_agent(agent_id: str, payload: AgentUpdateRequest):
    """Update an existing agent profile."""
    store = AgentStore()
    profile = store.load(agent_id)
    if not profile:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    if payload.name is not None:
        profile.name = payload.name
    if payload.description is not None:
        profile.description = payload.description
    if payload.icon is not None:
        profile.icon = payload.icon
    if payload.system_prompt_template is not None:
        profile.system_prompt_template = payload.system_prompt_template
    if payload.curated_skills is not None:
        profile.curated_skills = payload.curated_skills
    if payload.tags is not None:
        profile.tags = payload.tags

    store.save(profile)
    return profile


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete a saved agent profile."""
    store = AgentStore()
    deleted = store.delete(agent_id)
    if not deleted:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return {"status": "deleted", "agent_id": agent_id}


@app.post("/api/agents/generate", response_model=AgentGenerateResponse)
async def generate_agent(payload: AgentGenerateRequest):
    """Use LLM to generate an optimized agent configuration from natural language."""
    try:
        registry: ToolRegistry = app.state.registry
        skills = registry.list_skills()
        builder = SkillBuilder(llm=app.state.llm)
        return await builder.generate_agent_profile(
            payload.description, available_skills=skills
        )
    except Exception as e:
        logger.exception("Failed to auto-design agent profile via LLM: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"AI Agent generation failed: {e}. Check your LLM server connection in Settings.",
        )


# ── AI Skill Builder Endpoints ───────────────────────────────────


@app.post("/api/skills/generate", response_model=SkillGenerateResponse)
async def generate_skill(payload: SkillGenerateRequest):
    """Use LLM to generate Python tool code from natural language description."""
    try:
        registry: ToolRegistry = app.state.registry
        skills = registry.list_skills()
        builder = SkillBuilder(llm=app.state.llm)
        return await builder.generate_tool(
            description=payload.description,
            suggested_name=payload.suggested_name,
            available_skills=skills,
        )
    except Exception as e:
        logger.exception("Failed to generate Python tool code via LLM: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"AI Skill generation failed: {e}. Check your LLM server connection in Settings.",
        )


@app.post("/api/skills/register")
async def register_skill(payload: SkillRegisterRequest):
    """Validate, register and persist a generated custom Python tool."""
    registry: ToolRegistry = app.state.registry
    builder = SkillBuilder(llm=app.state.llm)
    try:
        tool_spec = builder.register_generated_tool(
            tool_code=payload.tool_code,
            tool_name=payload.tool_name,
            registry=registry,
            persist=True,
        )
        return {
            "status": "registered",
            "tool_id": tool_spec.tool_id,
            "name": tool_spec.name,
            "description": tool_spec.description,
            "skills": tool_spec.skills_provided,
            "risk_level": tool_spec.risk_level.value,
        }
    except Exception as e:
        logger.exception("Failed to register generated skill")
        raise HTTPException(400, f"Failed to register skill: {e}")


# ── Hermes Skills Endpoints ──────────────────────────────────────


@app.post("/api/skills/import/hermes")
async def import_hermes_skill_endpoint(payload: HermesSkillImportPayload):
    """Import and register a Hermes SKILL.md or JSON skill specification."""
    from src.registry.hermes.hermes_loader import import_and_persist_hermes_skill

    registry: ToolRegistry = app.state.registry
    try:
        spec = import_and_persist_hermes_skill(
            content=payload.content,
            name_override=payload.name_override or "",
            registry=registry,
            persist=payload.persist,
        )
        return {
            "status": "imported",
            "tool_id": spec.tool_id,
            "name": spec.name,
            "description": spec.description,
            "skills": spec.skills_provided,
            "risk_level": spec.risk_level.value,
            "source_type": spec.source_type,
        }
    except Exception as e:
        logger.exception("Failed to import Hermes skill: %s", e)
        raise HTTPException(400, f"Failed to import Hermes skill: {e}")


@app.get("/api/skills/hermes/catalog")
@app.get("/api/skills/catalog")
async def list_hermes_catalog_endpoint():
    """List all imported skills currently registered in the catalog."""
    from src.registry.hermes.hermes_loader import list_hermes_skills_catalog

    return list_hermes_skills_catalog()


@app.get("/api/skills/ecosystem/stats")
async def get_ecosystem_stats_endpoint():
    """Return high-level stats for the 97,986 skills ecosystem across 12 registries."""
    from src.registry.ecosystem_registry import get_ecosystem_stats

    return get_ecosystem_stats()


@app.get("/api/skills/capabilities")
async def get_installed_capabilities_endpoint():
    """Return all active capabilities installed in the agent workspace with toggle state."""
    from src.registry.ecosystem_registry import get_installed_capabilities

    return get_installed_capabilities()


@app.get("/api/skills/ecosystem/search")
async def search_ecosystem_skills_endpoint(
    q: str = "",
    category: str = "all",
    registry: str = "all",
    page: int = 1,
    limit: int = 24,
):
    """Search the 97,986 open agent skills ecosystem index with registry and category filters."""
    from src.registry.ecosystem_registry import search_ecosystem_skills

    return search_ecosystem_skills(query=q, category=category, registry=registry, page=page, limit=limit)


@app.post("/api/skills/ecosystem/install")
async def install_ecosystem_skill_endpoint(payload: dict[str, Any]):
    """Install and activate a skill from the 97k+ open ecosystem into the registry."""
    from src.registry.ecosystem_registry import install_ecosystem_skill

    try:
        result, file_path = install_ecosystem_skill(payload)
        # Also register into app.state.tool_registry if present
        reg = getattr(app.state, "tool_registry", None)
        if reg:
            from src.registry.hermes.hermes_loader import import_and_persist_hermes_skill
            content = file_path.read_text(encoding="utf-8")
            import_and_persist_hermes_skill(content, name_override=result["name"], registry=reg, persist=False)
        return result
    except Exception as e:
        logger.exception("Failed to install ecosystem skill: %s", e)
        raise HTTPException(400, f"Failed to install ecosystem skill: {e}")



# ── Closed-Loop Skill Synthesis Endpoint (Hermes Pattern) ─────────


@app.post("/api/workflows/{workflow_id}/distill-skill", response_model=SkillGenerateResponse)
async def distill_workflow_skill(workflow_id: str):
    """Abstract a completed workflow's solution into a reusable Python tool (Hermes Self-Learning loop)."""
    status_resp = await get_status(workflow_id)
    if not status_resp.result:
        raise HTTPException(400, "Workflow has not completed or has no result to distill")

    res = status_resp.result
    response_text = res.get("response", "")
    query = res.get("query", "")
    if not query and status_resp.dag and "tasks" in status_resp.dag:
        tasks = status_resp.dag.get("tasks", [])
        if tasks:
            query = tasks[0].get("description", "Automated Task")
    if not query:
        query = "Automated Workflow Solution"

    task_name = "Workflow Solution"
    task_desc = query
    tools_used: list[str] = []
    if status_resp.dag and "tasks" in status_resp.dag:
        tasks = status_resp.dag["tasks"]
        if tasks:
            task_name = tasks[0].get("name", "Automated Task")
            task_desc = tasks[0].get("description", query)
            for t in tasks:
                tools_used.extend(t.get("required_skills", []))

    builder = SkillBuilder(llm=app.state.llm)
    try:
        return await builder.distill_skill_from_task_solution(
            user_query=query,
            task_name=task_name,
            task_description=task_desc,
            solution_output=response_text,
            tools_used=list(set(tools_used)),
        )
    except Exception as e:
        logger.exception("Failed to distill skill from workflow: %s", e)
        raise HTTPException(502, f"Failed to distill skill: {e}")


# ── Scheduled Jobs Endpoints (Cron Automation) ───────────────────


@app.get("/api/schedules", response_model=list[ScheduledJob])
async def list_schedules():
    """List all configured recurring cron schedules."""
    return app.state.scheduler.list_jobs()


@app.post("/api/schedules", response_model=ScheduledJob)
async def create_schedule(payload: ScheduleCreateRequest):
    """Create a new recurring cron schedule."""
    return app.state.scheduler.add_job(payload)


@app.put("/api/schedules/{schedule_id}", response_model=ScheduledJob)
async def update_schedule(schedule_id: str, payload: ScheduleUpdateRequest):
    """Update an existing cron schedule."""
    job = app.state.scheduler.update_job(schedule_id, payload)
    if not job:
        raise HTTPException(404, f"Schedule '{schedule_id}' not found")
    return job


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a cron schedule."""
    if not app.state.scheduler.delete_job(schedule_id):
        raise HTTPException(404, f"Schedule '{schedule_id}' not found")
    return {"status": "deleted", "schedule_id": schedule_id}


@app.post("/api/schedules/{schedule_id}/toggle", response_model=ScheduledJob)
async def toggle_schedule(schedule_id: str):
    """Toggle a cron schedule's active state."""
    job = app.state.scheduler.get_job(schedule_id)
    if not job:
        raise HTTPException(404, f"Schedule '{schedule_id}' not found")
    return app.state.scheduler.update_job(schedule_id, ScheduleUpdateRequest(enabled=not job.enabled))


# ── Mount Messaging Gateways ─────────────────────────────────────

from src.api.gateways import router as gateways_router

app.include_router(gateways_router)




# ── Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
