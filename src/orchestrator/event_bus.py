"""UAOS Event Bus.

Asynchronous in-memory pub/sub broadcaster bridging Temporal worker activities
and web clients (SSE / WebSockets). Supports rolling history replay so clients
connecting mid-workflow immediately receive past tokens and state transitions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

MAX_HISTORY_PER_WORKFLOW = 500


class EventBus:
    """Publish/Subscribe event broadcaster with bounded replay history."""

    def __init__(self, max_history: int = MAX_HISTORY_PER_WORKFLOW) -> None:
        self.max_history = max_history
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    def publish(self, workflow_id: str, event: dict[str, Any]) -> None:
        """Publish an event to all subscribers of a workflow.

        Non-blocking and synchronous so activities can call it without awaiting.
        """
        if "timestamp" not in event:
            event["timestamp"] = time.time()

        # 1. Append to circular history buffer
        if workflow_id not in self._history:
            self._history[workflow_id] = deque(maxlen=self.max_history)
        self._history[workflow_id].append(event)

        # 2. Dispatch to active subscriber queues
        queues = self._subscribers.get(workflow_id, set())
        for q in list(queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Subscriber queue full for workflow '%s', dropping event",
                    workflow_id,
                )

    async def subscribe(self, workflow_id: str) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to events for a workflow.

        Replays historical events first, then streams live events as they occur.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

        # Register queue
        async with self._lock:
            if workflow_id not in self._subscribers:
                self._subscribers[workflow_id] = set()
            self._subscribers[workflow_id].add(queue)

            # Snapshot history while holding lock
            historical_events = list(self._history.get(workflow_id, []))

        # Replay history
        for ev in historical_events:
            yield ev

        # Stream live events
        try:
            while True:
                ev = await queue.get()
                yield ev
                # If terminal event, finish stream
                if ev.get("type") in ("workflow_completed", "workflow_failed"):
                    break
        finally:
            async with self._lock:
                if workflow_id in self._subscribers:
                    self._subscribers[workflow_id].discard(queue)
                    if not self._subscribers[workflow_id]:
                        del self._subscribers[workflow_id]

    def get_history(self, workflow_id: str) -> list[dict[str, Any]]:
        """Return all buffered events for a workflow."""
        return list(self._history.get(workflow_id, []))

    def clear(self, workflow_id: str) -> None:
        """Clear history and subscriber state for a workflow."""
        self._history.pop(workflow_id, None)
        self._subscribers.pop(workflow_id, None)


# Global singleton instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return global EventBus singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
