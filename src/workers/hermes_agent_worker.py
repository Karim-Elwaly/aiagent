"""
UAOS Hermes Agent Worker

Runs a task inside Hermes Agent instead of aiagent's own ReAct loop: the persona becomes the run's instructions,
the task becomes its input, and Hermes calls the model and the tools (aiagent's over MCP, plus the Hermes built-ins
the agent is allowed). Hermes's tool and approval events are relayed to aiagent's event bus.
"""

from __future__ import annotations

import asyncio
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
from src.hermes.client import TERMINAL_EVENTS, HermesAPIError, HermesClient
from src.hermes.profiles import MCP_SERVER_NAME, HermesError, HermesProfiles
from src.hermes.skills import skill_documents
from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

ENGINE = "hermes"
# Hermes 0.21.5 registers MCP tools as mcp__<server>__<tool>.
MCP_TOOL_PREFIX = f"mcp__{MCP_SERVER_NAME}__"
MCP_READY_TIMEOUT_SECONDS = 180
APPROVAL_LABELS = {
    "once": "Allow once",
    "session": "Allow for this run",
    "always": "Always allow",
    "deny": "Deny",
}
_profile_locks: dict[str, asyncio.Lock] = {}


def display_tool_name(name: str) -> str:
    return name[len(MCP_TOOL_PREFIX):] if name.startswith(MCP_TOOL_PREFIX) else name


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
    ) -> TaskResult:
        start = time.monotonic()
        agent_id = self.agent.id if self.agent else None
        toolsets = list(self.agent.hermes_toolsets) if self.agent else []

        def prepare() -> Any:
            return self.profiles.ensure(agent_id, toolsets, skill_documents(self.agent, self.registry),
                                        agent=self.agent)

        try:
            info = await asyncio.to_thread(prepare)
        except HermesError as exc:
            return self._failed(task, start, f"Could not prepare the Hermes profile: {exc}")

        if info.changed and not await self._wait_for_mcp(info.name):
            return self._failed(task, start, (
                f"Hermes has not connected aiagent's tools on profile '{info.name}' within "
                f"{MCP_READY_TIMEOUT_SECONDS}s of configuring it. Check that the Hermes gateway is running "
                f"(hermes gateway restart) and can reach {self.settings.hermes_mcp_url}."
            ))

        lock = _profile_locks.setdefault(info.name, asyncio.Lock())
        async with lock:
            self.active.set(info.name, {
                "workflow_id": workflow_id,
                "task_id": task.id,
                "agent_id": agent_id or "",
                "task_tools": [t.name for t in tools],
            })
            try:
                return await self._run(task, persona, tools, info.name, info.api_key, upstream_context, user_query,
                                       on_token, on_event, on_heartbeat, resume_checkpoint, workflow_id, start)
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
    ) -> TaskResult:
        run_id, last_seq = self._resumable(resume_checkpoint, profile)
        try:
            if not run_id:
                run_id = await self.client.create_run(
                    profile, key, self._user_content(task, user_query, upstream_context), instructions=persona,
                    session_id=f"aiagent-{workflow_id or 'run'}-{task.id}-{uuid.uuid4().hex[:6]}",
                )
                logger.info("Task '%s' started Hermes run %s on profile '%s'", task.id, run_id, profile)
            else:
                logger.info("Task '%s' reattaching to Hermes run %s after seq %d", task.id, run_id, last_seq)
        except HermesAPIError as exc:
            return self._failed(task, start, str(exc))
        except httpx.HTTPError as exc:
            raise TransientLLMError(f"Hermes Agent unreachable at {self.settings.hermes_api_url}: {exc}",
                                    original_error=exc) from exc

        tool_calls: list[str] = []
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
        except HermesAPIError as exc:
            return self._failed(task, start, str(exc), tool_calls)
        except httpx.HTTPError as exc:
            raise TransientLLMError(f"Lost the Hermes run {run_id}: {exc}", original_error=exc) from exc

        status = str(outcome.get("status") or str(outcome.get("event", "")).removeprefix("run."))
        if status != "completed":
            reason = outcome.get("error") or f"Hermes run ended as '{status or 'unknown'}'"
            return self._failed(task, start, f"Hermes run {run_id}: {reason}", tool_calls)
        if tools and not tool_calls:
            return self._failed(task, start, (
                f"No evidence collected: Hermes finished without calling any of the {len(tools)} tools "
                "available for this task. Any findings would be unverified model recall."
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
        name = event.get("event", "")
        if name == "message.delta" and on_token and event.get("delta"):
            on_token(str(event["delta"]))
        elif name == "tool.started":
            if on_event:
                on_event({"type": "tool_start", "task_id": task.id,
                          "tool": display_tool_name(str(event.get("tool", ""))), "args": event.get("preview")})
        elif name in ("tool.completed", "tool.failed"):
            tool = display_tool_name(str(event.get("tool", "")))
            failed = name == "tool.failed" or bool(event.get("error"))
            if not failed:
                tool_calls.append(tool)
            if on_event:
                on_event({"type": "tool_end", "task_id": task.id, "tool": tool,
                          "output": str(event.get("preview") or "")[:200], "error": failed})
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

    async def _wait_for_mcp(self, profile: str) -> bool:
        """A (re)configured profile picks up its MCP server on Hermes's next config scan, usually within a minute."""
        deadline = time.monotonic() + MCP_READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.profiles.state.mcp_connected(profile):
                return True
            await asyncio.sleep(2)
        return False

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
    def _user_content(task: Task, user_query: str, upstream_context: dict[str, str] | None) -> str:
        parts = []
        if user_query and user_query.strip():
            parts.append(f"# Overall User Request / Target Context:\n{user_query.strip()}")
        parts.append(f"# Task to Execute\n**{task.name}**\n\n{task.description}")
        if task.expected_output and task.expected_output.strip():
            parts.append(f"**Expected Output:**\n{task.expected_output}")
        if upstream_context:
            blocks = [f"### Output from Prior Task `{uid}`:\n{out}" for uid, out in upstream_context.items()]
            parts.append("# Context and Data from Previous Tasks:\n" + "\n\n".join(blocks))
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
