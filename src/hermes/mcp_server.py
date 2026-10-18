"""
aiagent's tools for Hermes Agent, over MCP (streamable HTTP, mounted at ``/mcp``).

Each Hermes profile authenticates with its own ``AIAGENT_MCP_TOKEN``; the token says which profile (and so which
agent) is calling, and :class:`ActiveRuns` says which aiagent task that profile is running. A call to a tool the
agent has not been approved for pauses until the operator answers: add it to the agent, allow it for this run, or
deny it. ``request_tool`` lets Hermes ask for aiagent tools it was not shown and for Hermes built-in toolsets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from src.core.agent_models import AgentProfile
from src.core.agent_store import AgentStore
from src.core.models import RiskLevel
from src.core.text_utils import smart_truncate
from src.hermes.active_runs import ActiveRuns
from src.hermes.profiles import DEFAULT_PROFILE, HermesProfiles, ProfileState
from src.hermes.skills import flat_parameters
from src.hermes.toolsets import BUILTIN_TOOLSETS
from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

REQUEST_TOOL = "request_tool"
HERMES_TOOLSET_PREFIX = "hermes:"
ADD_TO_AGENT = "Add to this agent"
ALLOW_FOR_RUN = "Allow for this run"
DENY = "Deny"
ENABLE_FOR_DEFAULT = "Enable for tasks without an agent"
# Skill-adapter echo tools and simulated hermes_* tools: Hermes has real equivalents of these.
HIDDEN_SOURCES = frozenset({"skill", "hermes"})
_TYPE_ALIASES = {"int": "integer", "float": "number", "str": "string", "bool": "boolean", "list": "array", "dict": "object"}

Ask = Callable[[str, list[str], str, str, int], Awaitable[str | None]]


class ToolDenied(RuntimeError):
    pass


def tool_input_schema(spec: ToolSpec) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, raw in flat_parameters(spec).items():
        prop = dict(raw) if isinstance(raw, dict) else {}
        if prop.pop("required", False):
            required.append(name)
        ptype = _TYPE_ALIASES.get(str(prop.get("type", "")), prop.get("type"))
        if ptype in (None, "", "any"):
            prop.pop("type", None)
        else:
            prop["type"] = ptype
        if prop.get("type") == "array" and "items" not in prop:
            prop["items"] = {}
        properties[name] = prop
    return {"type": "object", "properties": properties, "required": required}


async def _default_ask(question: str, choices: list[str], workflow_id: str, task_id: str, timeout: int) -> str | None:
    from src.core.clarification import get_clarification_hub

    return await get_clarification_hub().ask_choice(question, choices, workflow_id, task_id, timeout)


class ToolGate:
    """Who may run which aiagent tool for which Hermes profile; asks the operator when unsure."""

    def __init__(
        self,
        registry: ToolRegistry,
        settings: Any,
        state: ProfileState | None = None,
        active: ActiveRuns | None = None,
        store: AgentStore | None = None,
        ask: Ask | None = None,
        profiles: HermesProfiles | None = None,
    ):
        self.registry = registry
        self.settings = settings
        self.state = state or ProfileState()
        self.active = active or ActiveRuns()
        self.store = store or AgentStore()
        self.ask = ask or _default_ask
        self._profiles = profiles
        self.grants: dict[str, set[str]] = {}

    @property
    def profiles(self) -> HermesProfiles:
        if self._profiles is None:
            self._profiles = HermesProfiles(self.settings, state=self.state)
        return self._profiles

    def entry_for_token(self, token: str) -> dict[str, Any] | None:
        return self.state.by_token(token)

    def _agent(self, entry: dict[str, Any]) -> AgentProfile | None:
        agent_id = entry.get("agent_id")
        return self.store.load(agent_id) if agent_id else None

    def _candidates(self) -> list[ToolSpec]:
        return [t for t in self.registry.get_all_tools() if t.source_type not in HIDDEN_SOURCES]

    def exposed_tools(self, entry: dict[str, Any]) -> list[ToolSpec]:
        """The tools Hermes is shown for this profile: a tool group's tools, the agent's curated tools, or every tool."""
        agent = self._agent(entry)
        candidates = self._candidates()
        if entry.get("bundle") is not None:
            names = set(entry["bundle"])
            return [t for t in candidates if t.name in names]
        if agent and agent.curated_skills:
            skills = set(agent.curated_skills)
            return [t for t in candidates if skills & set(t.skills_provided)]
        return candidates

    def allowed(self, entry: dict[str, Any], active: dict[str, Any]) -> set[str]:
        agent = self._agent(entry)
        if agent:
            base = {t.name for t in self.exposed_tools(entry)}
        else:
            base = set(active.get("task_tools") or [])
            if entry.get("bundle") is not None:
                # The group was picked for this task: its low-risk tools need no approval.
                base |= {t.name for t in self.exposed_tools(entry) if t.risk_level.value == "low"}
        return base | self.grants.get(active.get("workflow_id", ""), set())

    async def call(self, entry: dict[str, Any], name: str, arguments: dict[str, Any]) -> str:
        name = name.removeprefix("mcp__aiagent__").removeprefix("mcp__")
        reason = ""
        if name == REQUEST_TOOL:
            target = str(arguments.get("tool_name") or "").strip()
            reason = str(arguments.get("reason") or "")
            if target.startswith(HERMES_TOOLSET_PREFIX):
                return await self._request_toolset(entry, target[len(HERMES_TOOLSET_PREFIX):], reason)
            raw_args = arguments.get("arguments") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except ValueError:
                    raise ToolDenied("request_tool.arguments must be a JSON object") from None
            name, arguments = target, raw_args if isinstance(raw_args, dict) else {}
            name = name.removeprefix("mcp__aiagent__").removeprefix("mcp__")

        logger.info("[MCP] Tool call received: profile=%s, tool=%s, args=%s", entry.get("profile"), name, arguments)
        active = self.active.get(entry["profile"])
        if not active:
            logger.warning("[MCP] ToolDenied: No active task for profile '%s'", entry.get("profile"))
            raise ToolDenied(f"No aiagent task is running on Hermes profile '{entry['profile']}'.")
        spec = self.registry.get_tool_by_name(name)
        if spec is None or spec.source_type in HIDDEN_SOURCES:
            names = ", ".join(sorted(t.name for t in self._candidates()))
            logger.warning("[MCP] ToolDenied: Unknown tool '%s' for profile '%s'", name, entry.get("profile"))
            raise ToolDenied(f"aiagent has no tool named '{name}'. Its tools: {names}")

        if name not in self.allowed(entry, active) and not await self._approve(entry, active, spec, reason):
            logger.warning("[MCP] ToolDenied: Operator did not approve tool '%s'", name)
            raise ToolDenied(f"The operator did not approve the aiagent tool '{name}' for this task.")

        timeout = getattr(self.settings, "hermes_run_timeout_seconds", 1800)
        try:
            result = await asyncio.wait_for(spec.invoke(**arguments), timeout=timeout)
            logger.info("[MCP] Tool '%s' executed successfully: result=%s", name, str(result)[:150])
            return smart_truncate(str(result), max_chars=getattr(self.settings, "worker_max_output_chars", 8000))
        except Exception as exc:
            logger.error("[MCP] Tool '%s' invoke error: %s", name, exc, exc_info=True)
            return f"Error executing tool '{name}': {exc}"

    async def _approve(self, entry: dict[str, Any], active: dict[str, Any], spec: ToolSpec, reason: str) -> bool:
        agent = self._agent(entry)
        who = f"agent '{agent.name}'" if agent else "this task (no agent selected)"
        question = (
            f"Hermes wants to use the aiagent tool '{spec.name}' ({spec.risk_level.value} risk), "
            f"which {who} is not approved for. {spec.description[:200]}"
            + (f"\nReason given: {reason}" if reason else "")
        )
        choices = [ADD_TO_AGENT, ALLOW_FOR_RUN, DENY] if agent else [ALLOW_FOR_RUN, DENY]
        answer = await self.ask(
            question, choices, active.get("workflow_id", ""), active.get("task_id", ""),
            getattr(self.settings, "hermes_approval_timeout_seconds", 600),
        )
        if answer not in (ADD_TO_AGENT, ALLOW_FOR_RUN):
            logger.info("Operator denied tool '%s' for profile '%s' (%s)", spec.name, entry["profile"], answer)
            return False
        if answer == ADD_TO_AGENT and agent:
            skill = min(spec.skills_provided, key=lambda s: len(self.registry.tools_providing(s)), default=None)
            if skill and skill not in agent.curated_skills:
                agent.curated_skills.append(skill)
                self.store.save(agent)
                logger.info("Added skill '%s' (tool '%s') to agent '%s'", skill, spec.name, agent.id)
        self.grants.setdefault(active.get("workflow_id", ""), set()).add(spec.name)
        return True

    async def _request_toolset(self, entry: dict[str, Any], toolset: str, reason: str) -> str:
        if toolset not in BUILTIN_TOOLSETS:
            raise ToolDenied(f"Unknown Hermes toolset '{toolset}'. Known: {', '.join(BUILTIN_TOOLSETS)}")
        active = self.active.get(entry["profile"]) or {}
        agent = self._agent(entry)
        current = set(agent.hermes_toolsets if agent else self.state.get(DEFAULT_PROFILE).get("extra_toolsets", []))
        if toolset in current or toolset in self.settings.hermes_default_toolsets:
            return f"Hermes toolset '{toolset}' is already approved; it is available from the next run of this profile."
        label = ADD_TO_AGENT if agent else ENABLE_FOR_DEFAULT
        question = (
            f"Hermes wants its built-in toolset '{toolset}' for "
            + (f"agent '{agent.name}'" if agent else "tasks without an agent")
            + ". Hermes fixes its toolsets when a run starts, so this applies from the next run."
            + (f"\nReason given: {reason}" if reason else "")
        )
        answer = await self.ask(
            question, [label, DENY], active.get("workflow_id", ""), active.get("task_id", ""),
            getattr(self.settings, "hermes_approval_timeout_seconds", 600),
        )
        if answer != label:
            raise ToolDenied(f"The operator did not approve the Hermes toolset '{toolset}'.")
        if agent:
            agent.hermes_toolsets = sorted({*agent.hermes_toolsets, toolset})
            self.store.save(agent)
        else:
            self.profiles.add_default_toolset(toolset)
        return (
            f"Approved: Hermes toolset '{toolset}' is enabled from the next run. It is not available in this run; "
            "continue with the tools you have."
        )

    def request_tool_definition(self, entry: dict[str, Any]) -> types.Tool:
        shown = {t.name for t in self.exposed_tools(entry)}
        others = [t for t in self._candidates() if t.name not in shown]
        catalog = "; ".join(f"{t.name}: {t.description.split('.')[0][:80]}" for t in others)[:3000]
        toolsets = ", ".join(HERMES_TOOLSET_PREFIX + t for t in BUILTIN_TOOLSETS)
        return types.Tool(
            name=REQUEST_TOOL,
            description=(
                "Ask the operator for a tool you were not given, then run it. Use an aiagent tool name with its "
                "arguments, or 'hermes:<toolset>' to request a Hermes built-in toolset for later runs. "
                f"Other aiagent tools: {catalog or 'none'}. Hermes toolsets: {toolsets}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "aiagent tool name, or hermes:<toolset>"},
                    "arguments": {"type": "object", "description": "Arguments for the aiagent tool"},
                    "reason": {"type": "string", "description": "Why the task needs it"},
                },
                "required": ["tool_name", "reason"],
            },
        )


def build_server(gate: ToolGate) -> Server:
    server: Server = Server("aiagent")

    def current_entry() -> dict[str, Any]:
        request = server.request_context.request
        entry = request.scope.get("aiagent_profile") if request is not None else None
        if not entry:
            raise ToolDenied("Unauthenticated MCP request.")
        return entry

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        entry = current_entry()
        gate.state.update(entry["profile"], {"mcp_listed_at": time.time()})
        tools = [
            types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=tool_input_schema(t),
                annotations=types.ToolAnnotations(readOnlyHint=t.risk_level == RiskLevel.LOW),
            )
            for t in gate.exposed_tools(entry)
        ]
        tools.append(gate.request_tool_definition(entry))
        return tools

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        try:
            text = await gate.call(current_entry(), name, arguments or {})
            return [types.TextContent(type="text", text=text)]
        except Exception as exc:
            logger.error("[MCP] call_tool error on '%s': %s", name, exc, exc_info=True)
            return [types.TextContent(type="text", text=f"Error executing tool '{name}': {exc}")]

    return server


_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


class MCPEndpoint:
    """ASGI app for ``/mcp``: per-profile bearer auth (loopback callers only by default), then the MCP server."""

    def __init__(self, gate: ToolGate, allow_remote: bool = False):
        self.gate = gate
        self.server = build_server(gate)
        self.allow_remote = allow_remote
        self.manager: StreamableHTTPSessionManager | None = None

    @asynccontextmanager
    async def run(self):
        self.manager = StreamableHTTPSessionManager(app=self.server, stateless=True, json_response=True)
        self.gate.state.mark_endpoint_started()
        async with self.manager.run():
            yield
        self.manager = None

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            return
        client = scope.get("client") or ("", 0)
        if not self.allow_remote and client[0] not in _LOOPBACK:
            await self._reply(send, 403, "aiagent's MCP endpoint accepts loopback callers only")
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        entry = self.gate.entry_for_token(token)
        if not entry:
            await self._reply(send, 401, "unknown or missing AIAGENT_MCP_TOKEN")
            return
        if self.manager is None:
            await self._reply(send, 503, "MCP server not started")
            return
        scope["aiagent_profile"] = entry
        await self.manager.handle_request(scope, receive, send)

    @staticmethod
    async def _reply(send: Callable, status: int, message: str) -> None:
        body = json.dumps({"error": message}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
