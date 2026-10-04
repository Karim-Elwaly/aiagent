"""
UAOS Tool Context

Per-workflow execution context propagated to tools via ``contextvars``.
Tools that need to know *which workflow* or *which task* they are serving
(e.g. stateful Python sessions, memory recall, skill learning) read from
these variables instead of receiving ad-hoc kwargs.

Usage in a tool function::

    from src.core.tool_context import get_tool_context

    async def my_tool(arg: str) -> str:
        ctx = get_tool_context()
        wf_id = ctx.workflow_id   # might be "" outside a workflow
        ctx.emit("tool_telemetry", {"details": "..."})
        ...

The worker sets the context before invoking any task/tool and resets it afterwards.
"""

from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolContext:
    """Immutable snapshot of the execution context visible to tools.

    Fields are intentionally broad so future phases (memory, REPL, browser)
    can access what they need without changing the interface.
    """

    workflow_id: str = ""
    task_id: str = ""
    session_id: str = ""
    agent_id: str = ""
    user_query: str = ""
    # Arbitrary metadata tools may inspect (e.g. ``{"resilience": "standard"}``).
    extras: dict[str, Any] = field(default_factory=dict)

    # ── Convenience helpers ──────────────────────────────────────

    @property
    def has_workflow(self) -> bool:
        return bool(self.workflow_id)

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Publish a telemetry event to the EventBus for this workflow, if active."""
        if not self.workflow_id:
            return
        payload = dict(data or {})
        payload.setdefault("type", event_type)
        payload.setdefault("task_id", self.task_id)
        try:
            from src.orchestrator.event_bus import get_event_bus
            get_event_bus().publish(self.workflow_id, payload)
        except Exception as e:
            logger.debug("Failed to emit event from ToolContext: %s", e)


# ── Context variable ────────────────────────────────────────────

_tool_context_var: contextvars.ContextVar[ToolContext] = contextvars.ContextVar(
    "uaos_tool_context",
    default=ToolContext(),
)


def get_tool_context() -> ToolContext:
    """Return the current ``ToolContext`` (never raises)."""
    return _tool_context_var.get()


def set_tool_context(ctx: ToolContext) -> contextvars.Token[ToolContext]:
    """Set a new ``ToolContext`` and return a reset token.

    The caller should pass the token to :func:`reset_tool_context` when
    the scope ends (e.g. after a tool invocation) to restore the previous
    value.
    """
    return _tool_context_var.set(ctx)


def reset_tool_context(token: contextvars.Token[ToolContext]) -> None:
    """Restore the ``ToolContext`` to the value captured by *token*."""
    try:
        _tool_context_var.reset(token)
    except Exception as e:
        logger.debug("Failed to reset tool context token: %s", e)
