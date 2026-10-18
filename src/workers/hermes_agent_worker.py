"""
UAOS Hermes Agent Worker

Runs a task inside Hermes Agent instead of aiagent's own ReAct loop: the persona becomes the run's instructions,
the task becomes its input, and Hermes calls the model and the tools (aiagent's over MCP, plus the Hermes built-ins
the agent is allowed). Hermes's tool and approval events are relayed to aiagent's event bus.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from src.core.agent_models import AgentProfile
from src.core.exceptions import TransientLLMError
from src.core.models import Task, TaskResult, TaskStatus
from src.hermes.active_runs import ActiveRuns
from src.hermes.bundles import select_bundle
from src.hermes.client import (
    MODEL_ERROR,
    MODEL_ERROR_RETRIES,
    TERMINAL_EVENTS,
    HermesAPIError,
    HermesClient,
)
from src.hermes.profiles import MCP_SERVER_NAME, HermesError, HermesProfiles
from src.hermes.skills import skill_documents
from src.persona.synthesizer import format_upstream_context
from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

ENGINE = "hermes"
# Hermes 0.21.5 registers MCP tools as mcp__<server>__<tool>.
MCP_TOOL_PREFIX = f"mcp__{MCP_SERVER_NAME}__"
MCP_READY_TIMEOUT_SECONDS = 180
CONFIG_PICKUP_SECONDS = 20
PARAMETERS_LIMIT = 2000
APPROVAL_LABELS = {
    "once": "Allow once",
    "session": "Allow for this run",
    "always": "Always allow",
    "deny": "Deny",
}
_profile_locks: dict[str, asyncio.Lock] = {}
_gateway_lock = asyncio.Lock()
_gateway_restarted_at = float("-inf")
_gateway_restarted_wall = 0.0  # time.time() of the last restart: older tool listings came from the previous gateway


def display_tool_name(name: str) -> str:
    return name[len(MCP_TOOL_PREFIX):] if name.startswith(MCP_TOOL_PREFIX) else name


def _mark_gateway_restarted(wall: float) -> None:
    global _gateway_restarted_at, _gateway_restarted_wall
    _gateway_restarted_at, _gateway_restarted_wall = time.monotonic(), wall


async def _default_ask(question: str, choices: list[str], workflow_id: str, task_id: str, timeout: int) -> str | None:
    from src.core.clarification import get_clarification_hub

    return await get_clarification_hub().ask_choice(question, choices, workflow_id, task_id, timeout)


class HermesAgentWorker:
    """Executes one task as a Hermes Agent run on the agent's ``aiagent-<agent>`` profile."""

    engine = ENGINE

    def __init__(
        self,
        settings: Any,
        agent: AgentProfile | None = None,
        client: HermesClient | None = None,
        profiles: HermesProfiles | None = None,
        active: ActiveRuns | None = None,
        ask: Callable[..., Any] | None = None,
        registry: ToolRegistry | None = None,
    ):
        self.settings = settings
        self.agent = agent
        self.client = client or HermesClient(settings.hermes_api_url)
        self.profiles = profiles or HermesProfiles(settings)
        self.active = active or ActiveRuns()
        self.ask = ask or _default_ask
        self.registry = registry

    async def execute(
        self,
        task: Task,
        persona: str,
        tools: list[ToolSpec],
        upstream_context: dict[str, str] | None = None,
        user_query: str = "",
        on_token: Callable[[str], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        on_heartbeat: Callable[..., None] | None = None,
        resume_checkpoint: dict[str, Any] | None = None,
        workflow_id: str = "",
        continue_session: str | None = None,
        review_feedback: str | None = None,
        approval_tools: list[ToolSpec] | None = None,
        continue_profile: str | None = None,
        dynamic_profile: str | None = None,
    ) -> TaskResult:
        start = time.monotonic()
        agent_id = self.agent.id if self.agent else None
        toolsets = list(self.agent.hermes_toolsets) if self.agent else []
        approval = approval_tools or []
        dyn_prof = dynamic_profile or getattr(task, "hermes_profile", None)
        bundle = None if dyn_prof else self._ready_bundle(tools, approval)

        def prepare() -> Any:
            # Skills are written later, under the profile lock, so a parallel task can't swap them mid-run.
            if dyn_prof:
                self.profiles.state.touch_profile(dyn_prof)
                return self.profiles.ensure(
                    None,
                    dynamic_tools=[t.name for t in [*tools, *approval]],
                    profile_name_override=dyn_prof,
                )
            if bundle:
                return self.profiles.ensure(None, [], None, bundle=bundle)
            return self.profiles.ensure(agent_id, toolsets, None, agent=self.agent)

        try:
            info = await asyncio.to_thread(prepare)
        except HermesError as exc:
            return self._failed(task, start, f"Could not prepare the Hermes profile: {exc}")

        if info.restarted_at:
            _mark_gateway_restarted(info.restarted_at)
        dyn_prefix = getattr(self.settings, "hermes_profile_prefix_dynamic", "aiagent-dyn-")
        is_dynamic = info.name.startswith(dyn_prefix)
        if not is_dynamic and not self._mcp_ready(info.name):
            # Hermes reconnects a known server by itself (e.g. after aiagent restarts); a new or
            # reconfigured profile is only picked up by a gateway restart.
            if not await self._wait_for_mcp(info.name, CONFIG_PICKUP_SECONDS):
                await self._restart_gateway(info.name)
            if not await self._wait_for_mcp(info.name, MCP_READY_TIMEOUT_SECONDS):
                return self._failed(task, start, (
                    f"Hermes has not connected aiagent's tools on profile '{info.name}' within "
                    f"{MCP_READY_TIMEOUT_SECONDS}s. Check that the Hermes gateway is running "
                    f"(hermes gateway restart) and can reach {self.settings.hermes_mcp_url}."
                ))
        if self._restart_recent() or is_dynamic:
            await self._wait_for_api(MCP_READY_TIMEOUT_SECONDS)

        if continue_session and continue_profile and continue_profile != info.name:
            # Hermes sessions are per profile; the task description already carries the reviewer's feedback.
            logger.info("Task '%s' moved from profile '%s' to '%s'; running it fresh instead of continuing",
                        task.id, continue_profile, info.name)
            continue_session, review_feedback = None, None

        lock = _profile_locks.setdefault(info.name, asyncio.Lock())
        async with lock:
            self.active.set(info.name, {
                "workflow_id": workflow_id,
                "task_id": task.id,
                "agent_id": agent_id or "",
                "task_tools": [t.name for t in tools],
            })
            try:
                docs = await asyncio.to_thread(
                    skill_documents, self.agent, self.registry, None,
                    {t.name for t in [*tools, *approval]}, set(task.required_skills),
                )
                await asyncio.to_thread(self.profiles.write_profile_skills, info.name, docs)
                return await self._run(task, persona, tools, info.name, info.api_key, upstream_context, user_query,
                                       on_token, on_event, on_heartbeat, resume_checkpoint, workflow_id, start,
                                       continue_session, review_feedback, approval_tools or [])
            finally:
                self.active.clear(info.name)

    async def _run(
        self,
        task: Task,
        persona: str,
        tools: list[ToolSpec],
        profile: str,
        key: str,
        upstream_context: dict[str, str] | None,
        user_query: str,
        on_token: Callable[[str], None] | None,
        on_event: Callable[[dict[str, Any]], None] | None,
        on_heartbeat: Callable[..., None] | None,
        resume_checkpoint: dict[str, Any] | None,
        workflow_id: str,
        start: float,
        continue_session: str | None = None,
        review_feedback: str | None = None,
        approval_tools: list[ToolSpec] | None = None,
    ) -> TaskResult:
        run_id, last_seq = self._resumable(resume_checkpoint, profile)
        session_id = self._new_session_id(workflow_id, task)
        follow_up: str | None = None
        # A supervisor retry continues the reviewed session, which already holds the task's evidence.
        grounded = bool(continue_session)
        if continue_session:
            session_id = continue_session
            follow_up = self._review_message(review_feedback or "", tools)
        model_errors = 0
        steered = False
        tool_calls: list[str] = []
        while True:
            try:
                if not run_id:
                    run_id = await self.client.create_run(
                        profile, key,
                        follow_up or self._user_content(task, tools, user_query, upstream_context, approval_tools),
                        instructions=persona, session_id=session_id,
                    )
                    logger.info("Task '%s' started Hermes run %s on profile '%s'", task.id, run_id, profile)
                else:
                    logger.info("Task '%s' reattaching to Hermes run %s after seq %d", task.id, run_id, last_seq)
            except HermesAPIError as exc:
                return self._failed(task, start, str(exc))
            except httpx.HTTPError as exc:
                raise TransientLLMError(f"Hermes Agent unreachable at {self.settings.hermes_api_url}: {exc}",
                                        original_error=exc) from exc

            outcome: dict[str, Any] = {}
            try:
                async with asyncio.timeout(self.settings.hermes_run_timeout_seconds):
                    async for event in self.client.events(profile, key, run_id, last_seq):
                        last_seq = int(event.get("seq", last_seq))
                        self._heartbeat(on_heartbeat, task, run_id, profile, last_seq)
                        if await self._handle(event, task, profile, key, run_id, tool_calls, on_token, on_event,
                                              workflow_id):
                            outcome = event
                            break
                    if not outcome:
                        outcome = await self.client.get_run(profile, key, run_id)
            except TimeoutError:
                await self._stop(profile, key, run_id)
                return self._failed(task, start, f"Hermes run {run_id} timed out after "
                                                 f"{self.settings.hermes_run_timeout_seconds}s", tool_calls)
            except asyncio.CancelledError:
                # Workflow cancelled/terminated: otherwise the run keeps going and holds the profile for the next task.
                await asyncio.shield(self._stop(profile, key, run_id))
                raise
            except HermesAPIError as exc:
                if run_id and ("run_not_found" in str(exc).lower() or "not found" in str(exc).lower() or "404" in str(exc)):
                    logger.warning("Hermes run %s not found on gateway; resetting to start fresh run: %s", run_id, exc)
                    run_id, last_seq = None, -1
                    continue
                if run_id:
                    await self._stop(profile, key, run_id)
                return self._failed(task, start, str(exc), tool_calls)
            except httpx.HTTPError as exc:
                if run_id:
                    await self._stop(profile, key, run_id)
                raise TransientLLMError(f"Lost the Hermes run {run_id}: {exc}", original_error=exc) from exc
            except Exception as exc:
                if run_id:
                    await self._stop(profile, key, run_id)
                logger.error("Task '%s' Hermes run %s encountered an unexpected exception: %s", task.id, run_id, exc, exc_info=True)
                return self._failed(task, start, f"Unexpected error during Hermes run {run_id}: {exc}", tool_calls)

            status = str(outcome.get("status") or str(outcome.get("event", "")).removeprefix("run."))
            session_id = str(outcome.get("session_id") or session_id)
            output_text = str(outcome.get("output") or "")
            lowered_out = output_text.lower()
            # Only check for MCP unreachable if no tools were called and task is not grounded.
            # Security logs naturally mention 'connection refused', 'failed connection', etc., so we must
            # match explicitly on MCP infrastructure error phrases.
            is_mcp_unreachable = (
                not (tool_calls or grounded) and (
                    ("mcp" in lowered_out and any(k in lowered_out for k in ("unreach", "cannot connect", "could not connect", "connection error", "mcp server error", "failed to connect")))
                    or "mcp server is down" in lowered_out
                    or "mcp endpoint error" in lowered_out
                )
            )
            if status == "completed":
                if is_mcp_unreachable and model_errors < MODEL_ERROR_RETRIES:
                    model_errors += 1
                    logger.warning("Task '%s' Hermes run %s hit parked/unreachable MCP backend; restarting gateway to revive MCP connection...", task.id, run_id)
                    await self._restart_gateway(profile, force=True)
                    run_id, last_seq = None, -1
                    session_id, follow_up, steered, tool_calls = self._new_session_id(workflow_id, task), None, False, []
                    grounded = False
                    continue

                if tools and not tool_calls and not steered and not grounded:
                    # Same session: Hermes replays its history, so the model sees its own ungrounded answer.
                    logger.info("Task '%s' Hermes run %s answered without tools; steering it to use them",
                                task.id, run_id)
                    follow_up, steered = self._steering_message(tools), True
                    run_id, last_seq = None, -1
                    continue
                break
            reason = str(outcome.get("error") or f"Hermes run ended as '{status or 'unknown'}'")
            lowered_reason = reason.lower()
            is_mcp_err_reason = (
                not (tool_calls or grounded) and (
                    ("mcp" in lowered_reason and any(k in lowered_reason for k in ("unreach", "cannot connect", "could not connect", "connection error", "mcp server error", "failed to connect")))
                    or "mcp connection refused" in lowered_reason
                )
            )
            if (is_mcp_err_reason or is_mcp_unreachable) and model_errors < MODEL_ERROR_RETRIES:
                model_errors += 1
                logger.warning("Task '%s' Hermes run %s hit parked/unreachable MCP backend (%s); restarting gateway...", task.id, run_id, reason)
                await self._restart_gateway(profile, force=True)
                run_id, last_seq = None, -1
                session_id, follow_up, steered, tool_calls = self._new_session_id(workflow_id, task), None, False, []
                grounded = False
                continue
            if model_errors < MODEL_ERROR_RETRIES and MODEL_ERROR.search(reason):
                model_errors += 1
                logger.warning("Task '%s' Hermes run %s hit an inference-server error (retry %d/%d), "
                               "starting a fresh run: %s", task.id, run_id, model_errors, MODEL_ERROR_RETRIES,
                               reason)
                run_id, last_seq = None, -1
                session_id, follow_up, steered, tool_calls = self._new_session_id(workflow_id, task), None, False, []
                grounded = False
                continue
            return self._failed(task, start, f"Hermes run {run_id}: {reason}", tool_calls)

        if tools and not tool_calls and not grounded:
            return self._failed(task, start, (
                f"No evidence collected: Hermes finished without calling any of the {len(tools)} tools "
                "available for this task, even after being asked to. Any findings would be unverified model recall."
            ), tool_calls)

        output = str(outcome.get("output") or "").strip() or f"Task completed: {task.name}."
        if on_event:
            on_event({"type": "final_answer", "task_id": task.id, "answer": output})
        return TaskResult(
            task_id=task.id,
            status=TaskStatus.COMPLETED,
            output=output,
            tool_calls_made=tool_calls,
            execution_time_ms=int((time.monotonic() - start) * 1000),
            hermes_session_id=session_id,
            hermes_profile=profile,
        )

    async def _handle(
        self,
        event: dict[str, Any],
        task: Task,
        profile: str,
        key: str,
        run_id: str,
        tool_calls: list[str],
        on_token: Callable[[str], None] | None,
        on_event: Callable[[dict[str, Any]], None] | None,
        workflow_id: str,
    ) -> bool:
        """Relay one Hermes event; True when it ends the run."""
        name = str(event.get("event") or event.get("type") or "")
        if name != "message.delta":
            logger.info("[Hermes Event] task=%s, profile=%s, event=%s, tool=%s, error=%s, payload=%s",
                        task.id, profile, name, event.get("tool"), event.get("error"),
                        {k: (str(v)[:100] if k != "preview" else f"<{len(str(v))} chars>") for k, v in event.items()})
        if name == "message.delta" and on_token and event.get("delta"):
            on_token(str(event["delta"]))
        elif name == "tool.started":
            tool = display_tool_name(str(event.get("tool", "")))
            if tool and tool not in tool_calls:
                tool_calls.append(tool)
            if on_event:
                on_event({"type": "tool_start", "task_id": task.id,
                          "tool": tool, "args": event.get("preview")})
        elif name in ("tool.completed", "tool.failed"):
            tool = display_tool_name(str(event.get("tool", "")))
            if tool and tool not in tool_calls:
                tool_calls.append(tool)
            failed = name == "tool.failed" or bool(event.get("error"))
            preview_str = str(event.get("preview") or "")
            logger.info("[Hermes Tool Result] tool=%s, failed=%s, preview=%r", tool, failed, preview_str[:500])
            if on_event:
                on_event({"type": "tool_end", "task_id": task.id, "tool": tool,
                          "output": preview_str[:200], "error": failed})
        elif name == "approval.request":
            await self._approval(event, task, profile, key, run_id, workflow_id)
        return name in TERMINAL_EVENTS

    async def _approval(
        self, event: dict[str, Any], task: Task, profile: str, key: str, run_id: str, workflow_id: str
    ) -> None:
        choices = [c for c in event.get("choices") or ["once", "deny"] if c in APPROVAL_LABELS]
        labels = [APPROVAL_LABELS[c] for c in choices]
        detail = event.get("description") or event.get("command") or event.get("tool") or "an action"
        question = f"Hermes Agent asks to approve: {detail}"
        answer = await self.ask(question, labels, workflow_id, task.id, self.settings.hermes_approval_timeout_seconds)
        choice = next((c for c, label in zip(choices, labels) if label == answer), "deny")
        await self.client.respond_approval(profile, key, run_id, choice, event.get("request_id"))
        logger.info("Task '%s' Hermes approval on run %s answered '%s'", task.id, run_id, choice)

    async def _restart_gateway(self, profile: str, force: bool = False) -> None:
        async with _gateway_lock:
            if not force and self._mcp_ready(profile):
                return
            restarted_wall = self.profiles.state.gateway_restarted_at()
            cooldown = 5.0 if force else 60.0
            if (time.time() - restarted_wall < cooldown) or (time.monotonic() - _gateway_restarted_at < cooldown):
                logger.info("Gateway was restarted recently (%0.1fs ago); waiting for profile '%s' instead of restarting again",
                            time.time() - restarted_wall, profile)
                return
            logger.info("Hermes MCP server unreachable or unready on profile '%s' (force=%s); restarting the gateway", profile, force)
            # Marked before the call: the new gateway lists MCP tools during startup, before the CLI returns.
            began = time.time()
            await asyncio.to_thread(self.profiles.restart_gateway)
            _mark_gateway_restarted(began)
            await self._wait_for_api(MCP_READY_TIMEOUT_SECONDS)

    def _mcp_ready(self, profile: str) -> bool:
        wall = max(_gateway_restarted_wall, self.profiles.state.gateway_restarted_at())
        return self.profiles.state.mcp_connected(profile, since=wall)

    def _restart_recent(self) -> bool:
        if time.monotonic() - _gateway_restarted_at < MCP_READY_TIMEOUT_SECONDS:
            return True
        marker = getattr(self.profiles.state, "gateway_restarted_at", None)
        return bool(marker) and time.time() - marker() < MCP_READY_TIMEOUT_SECONDS

    def _ready_bundle(self, tools: list[ToolSpec], approval: list[ToolSpec]) -> str | None:
        """The tool group whose profile this no-agent task runs on; None runs it on aiagent-default."""
        if self.agent or not getattr(self.settings, "hermes_tool_bundles", False):
            return None
        bundle = select_bundle(t.name for t in [*tools, *approval])
        ready = getattr(self.profiles, "bundle_ready", None)
        if bundle is None or ready is None or not ready(bundle):
            logger.info("No ready tool group for tools %s; using the default Hermes profile",
                        sorted(t.name for t in [*tools, *approval]))
            return None
        return bundle

    async def _wait_for_mcp(self, profile: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._mcp_ready(profile):
                return True
            await asyncio.sleep(2)
        return False

    async def _wait_for_api(self, timeout: float) -> None:
        """A restarted gateway lists MCP tools before its API server listens."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.client.healthy():
                return
            await asyncio.sleep(1)

    async def _stop(self, profile: str, key: str, run_id: str) -> None:
        try:
            await self.client.stop_run(profile, key, run_id)
        except Exception as exc:
            logger.warning("Could not stop Hermes run %s: %s", run_id, exc)

    @staticmethod
    def _resumable(checkpoint: dict[str, Any] | None, profile: str) -> tuple[str | None, int]:
        if (
            isinstance(checkpoint, dict)
            and checkpoint.get("engine") == ENGINE
            and checkpoint.get("hermes_profile") == profile
            and checkpoint.get("hermes_run_id")
        ):
            return str(checkpoint["hermes_run_id"]), int(checkpoint.get("last_seq", -1))
        return None, -1

    @staticmethod
    def _heartbeat(on_heartbeat: Callable[..., None] | None, task: Task, run_id: str, profile: str, seq: int) -> None:
        if not on_heartbeat:
            return
        # "messages" keeps the payload recognisable as a checkpoint to execute_task.
        payload = {"engine": ENGINE, "task_id": task.id, "hermes_run_id": run_id, "hermes_profile": profile,
                   "last_seq": seq, "messages": []}
        try:
            on_heartbeat(payload)
        except TypeError:
            on_heartbeat()
        except Exception:
            pass

    @staticmethod
    def _new_session_id(workflow_id: str, task: Task) -> str:
        return f"aiagent-{workflow_id or 'run'}-{task.id}-{uuid.uuid4().hex[:6]}"

    @staticmethod
    def _steering_message(tools: list[ToolSpec]) -> str:
        names = ", ".join(f"{MCP_TOOL_PREFIX}{t.name}" for t in tools)
        return (
            "You answered without calling any tool, so nothing in that answer is backed by evidence. "
            f"Call at least one of these tools now: {names}. Point it at the investigation target or the "
            "data from previous tasks, then give your final answer based on what the tools returned."
        )

    @staticmethod
    def _review_message(feedback: str, tools: list[ToolSpec]) -> str:
        names = ", ".join(f"{MCP_TOOL_PREFIX}{t.name}" for t in tools)
        return (
            f"A reviewer checked your answer and found gaps:\n{feedback.strip() or '(no details given)'}\n\n"
            + (f"Use your tools ({names}) to gather what is missing. " if names else "Address these gaps. ")
            + "Then reply with your COMPLETE final answer for the task: everything from your previous answer plus "
            "the new findings, because this reply replaces it."
        )

    def _user_content(
        self,
        task: Task,
        tools: list[ToolSpec],
        user_query: str,
        upstream_context: dict[str, str] | None,
        approval_tools: list[ToolSpec] | None = None,
    ) -> str:
        parts = []
        if user_query and user_query.strip():
            parts.append(f"# Overall User Request / Target Context:\n{user_query.strip()}")
        parts.append(f"# Task to Execute\n**{task.name}**\n\n{task.description}")
        if task.expected_output and task.expected_output.strip():
            parts.append(f"**Expected Output:**\n{task.expected_output}")
        if task.parameters:
            params = json.dumps(task.parameters, ensure_ascii=False, default=str)
            if len(params) > PARAMETERS_LIMIT:
                params = params[:PARAMETERS_LIMIT] + " [...truncated]"
            parts.append(f"# Task Parameters\n{params}")
        if tools:
            names = ", ".join(f"{MCP_TOOL_PREFIX}{t.name}" for t in tools)
            parts.append(f"# Tools for This Task\n{names}")
        elif not approval_tools:
            parts.append("# Tools for This Task\nNone assigned. Answer from the context you are given.")
        if approval_tools:
            names = ", ".join(f"{MCP_TOOL_PREFIX}{t.name}" for t in approval_tools)
            parts.append(
                "# Tools That Need Operator Approval\n"
                f"{names}\nThis task needs them but this agent is not approved for them. Call one when you need it; "
                "the operator is asked to allow it."
            )
        context = format_upstream_context(upstream_context or {}, self.settings.worker_max_context_chars)
        if context:
            parts.append(context.strip())
        return "\n\n".join(parts)

    @staticmethod
    def _failed(task: Task, start: float, error: str, tool_calls: list[str] | None = None) -> TaskResult:
        logger.error("Task '%s' failed on Hermes Agent: %s", task.id, error)
        return TaskResult(
            task_id=task.id,
            status=TaskStatus.FAILED,
            output="",
            error=error,
            tool_calls_made=tool_calls or [],
            execution_time_ms=int((time.monotonic() - start) * 1000),
        )
