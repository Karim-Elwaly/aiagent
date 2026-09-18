"""
Clarification Protocol & Hub for Human-in-the-Loop Operator Dialogue.

Allows autonomous agents to pause execution when encountering ambiguous
instructions, emit a structured question with choices to the operator, and
resume immediately once answered, using zero CPU while waiting.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from src.orchestrator.event_bus import get_event_bus

logger = logging.getLogger(__name__)

# Context variables to track execution context in async tasks/tools
current_workflow_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_workflow_id", default=""
)
current_task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_task_id", default=""
)


class ClarificationRequest(BaseModel):
    """Model representing an active operator clarification request."""

    id: str = Field(default_factory=lambda: f"clr-{uuid.uuid4().hex[:8]}")
    workflow_id: str
    task_id: str
    question: str
    choices: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    timeout_seconds: int = 600
    status: str = "pending"  # "pending", "resolved", "timed_out", "cancelled"
    answer: str | None = None


class ClarificationHub:
    """Central registry and coordinator for interactive operator clarifications.

    Coordinates between agent worker tools, the event bus (SSE), and
    incoming operator responses from the Web UI or API.
    """

    _instance: ClarificationHub | None = None

    def __new__(cls) -> ClarificationHub:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pending = {}
            cls._instance._futures = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    def __init__(self) -> None:
        # Initialized once in __new__
        pass

    async def request_clarification(
        self,
        question: str,
        choices: list[str] | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        timeout_seconds: int = 600,
    ) -> str:
        """Pause agent execution and request human operator clarification.

        Emits a 'clarification_required' event, enters an efficient wait
        with periodic heartbeats for Temporal, and returns the operator's answer.
        """
        wf_id = workflow_id or current_workflow_id.get() or "default"
        t_id = task_id or current_task_id.get() or "unknown_task"
        cleaned_choices = [str(c).strip() for c in (choices or []) if str(c).strip()]

        req = ClarificationRequest(
            workflow_id=wf_id,
            task_id=t_id,
            question=question,
            choices=cleaned_choices,
            timeout_seconds=timeout_seconds,
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()

        self._pending[req.id] = req
        self._futures[req.id] = future

        logger.info(
            "Agent requested operator clarification [id=%s, wf=%s, task=%s]: %s (choices: %s)",
            req.id,
            wf_id,
            t_id,
            question,
            cleaned_choices,
        )

        # Broadcast event to Web UI via EventBus
        bus = get_event_bus()
        bus.publish(
            wf_id,
            {
                "type": "clarification_required",
                "clarification_id": req.id,
                "workflow_id": wf_id,
                "task_id": t_id,
                "question": question,
                "choices": cleaned_choices,
                "timeout_seconds": timeout_seconds,
            },
        )

        # Non-blocking wait loop with Temporal heartbeat support
        deadline = time.monotonic() + timeout_seconds
        heartbeat_interval = 4.0

        try:
            while not future.done():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                wait_step = min(heartbeat_interval, remaining)
                try:
                    await asyncio.wait_for(asyncio.shield(future), timeout=wait_step)
                    break
                except asyncio.TimeoutError:
                    # Send activity heartbeat if running inside a Temporal Activity
                    try:
                        from temporalio import activity

                        if activity.in_activity():
                            activity.heartbeat(
                                {
                                    "status": "awaiting_clarification",
                                    "clarification_id": req.id,
                                    "task_id": t_id,
                                }
                            )
                    except Exception:
                        pass

            if future.done():
                answer = future.result()
                req.status = "resolved"
                req.answer = answer
                logger.info(
                    "Clarification %s resolved with answer: '%s'",
                    req.id,
                    answer,
                )
                return f"Operator clarified: '{answer}'"
            else:
                req.status = "timed_out"
                logger.warning(
                    "Clarification %s timed out after %ds without operator response.",
                    req.id,
                    timeout_seconds,
                )
                default_choice = (
                    cleaned_choices[0]
                    if cleaned_choices
                    else "proceed with standard system defaults"
                )
                return (
                    f"Notice: Operator clarification timed out after {timeout_seconds}s. "
                    f"Proceed autonomously using the safest/recommended default: '{default_choice}'."
                )

        finally:
            self._pending.pop(req.id, None)
            self._futures.pop(req.id, None)

    def resolve_clarification(
        self,
        workflow_id: str,
        answer: str,
        clarification_id: str | None = None,
    ) -> bool:
        """Resolve a pending clarification with the operator's response."""
        target_id = clarification_id
        if not target_id:
            # Find first pending request matching this workflow
            for cid, req in self._pending.items():
                if req.workflow_id == workflow_id and req.status == "pending":
                    target_id = cid
                    break

        if not target_id or target_id not in self._futures:
            logger.warning(
                "No pending clarification found to resolve for wf=%s (target_id=%s)",
                workflow_id,
                target_id,
            )
            return False

        fut = self._futures[target_id]
        if not fut.done():
            fut.set_result(answer)

        # Broadcast resolved event to Web UI
        bus = get_event_bus()
        bus.publish(
            workflow_id,
            {
                "type": "clarification_resolved",
                "clarification_id": target_id,
                "workflow_id": workflow_id,
                "answer": answer,
            },
        )
        return True

    def get_pending(self, workflow_id: str) -> ClarificationRequest | None:
        """Get the active pending clarification request for a workflow, if any."""
        for req in self._pending.values():
            if req.workflow_id == workflow_id and req.status == "pending":
                return req
        return None

    def get_all_pending(self) -> list[ClarificationRequest]:
        """Return all active pending requests across workflows."""
        return [r for r in self._pending.values() if r.status == "pending"]

    def reset(self) -> None:
        """Reset all pending requests (primarily for test teardown)."""
        for fut in self._futures.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        self._futures.clear()


def get_clarification_hub() -> ClarificationHub:
    """Return singleton ClarificationHub instance."""
    return ClarificationHub()
