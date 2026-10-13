"""
aiagent's own model calls (planner, re-planner, supervisor, final report) answered by Hermes Agent.

A drop-in for ``LocalLLMClient.chat``: the system message becomes the run's instructions and the rest its input, run on
the ``aiagent-orchestrator`` profile (no tools). When Hermes cannot take the call (profile not loaded yet, gateway
down, the model server rejecting the output repeatedly) the call falls back to the direct client, so a Hermes problem
never stops planning.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import httpx

from src.hermes.active_runs import ActiveRuns
from src.hermes.client import (
    MODEL_ERROR,
    MODEL_ERROR_RETRIES,
    TERMINAL_EVENTS,
    HermesAPIError,
    HermesClient,
)
from src.hermes.profiles import ORCHESTRATOR_PROFILE, HermesError, HermesProfiles

logger = logging.getLogger(__name__)

# Hermes runs an agent loop with its own formatting guidance; this keeps it to the caller's format.
HEADER = (
    "This is a text-generation request. No tools are available and none are needed. Reply with exactly the output "
    "the instructions below ask for (JSON, Markdown or text); this overrides any earlier formatting guidance.\n\n"
)


class HermesUnavailable(RuntimeError):
    """Hermes could not answer; the caller falls back to the direct model client."""


def split_messages(messages: list[dict[str, Any]]) -> tuple[str, str]:
    """``(instructions, input)`` from chat messages: system text vs. the conversation."""
    system = "\n\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
    rest = [m for m in messages if m.get("role") != "system"]
    if len(rest) == 1:
        return system, str(rest[0].get("content", ""))
    turns = "\n\n".join(f"### {m.get('role', 'user')}\n{m.get('content', '')}" for m in rest)
    return system, f"{turns}\n\nReply to the last user message."


class HermesLLMClient:
    def __init__(self, settings: Any, fallback: Any, profiles: HermesProfiles | None = None,
                 client: HermesClient | None = None, active: ActiveRuns | None = None):
        self.settings = settings
        self.fallback = fallback
        self.profiles = profiles or HermesProfiles(settings)
        self.client = client or HermesClient(settings.hermes_api_url)
        self.active = active or ActiveRuns()

    async def chat(self, messages: list[dict[str, Any]]) -> str:
        # Marked so a gateway restart (new profiles) waits for this call instead of killing it.
        marker = f"{ORCHESTRATOR_PROFILE}~{uuid.uuid4().hex[:8]}"
        self.active.set(marker, {"orchestration": True})
        try:
            return await self._chat_or_fall_back(messages)
        finally:
            self.active.clear(marker)

    async def _chat_or_fall_back(self, messages: list[dict[str, Any]]) -> str:
        try:
            return await self._chat(messages)
        except HermesUnavailable as exc:
            logger.warning("Hermes could not answer this model call (%s); using the direct model client", exc)
            return await self.fallback.chat(messages)

    async def _chat(self, messages: list[dict[str, Any]]) -> str:
        try:
            info = await asyncio.to_thread(self.profiles.ensure_orchestrator)
        except HermesError as exc:
            raise HermesUnavailable(f"orchestrator profile: {exc}") from exc
        instructions, text = split_messages(messages)
        instructions = HEADER + instructions
        timeout = float(getattr(self.settings, "hermes_orchestration_timeout_seconds", 170))
        reason = ""
        for _ in range(MODEL_ERROR_RETRIES + 1):
            run_id = ""
            try:
                async with asyncio.timeout(timeout):
                    run_id = await self.client.create_run(
                        ORCHESTRATOR_PROFILE, info.api_key, text, instructions=instructions,
                        session_id=f"aiagent-orch-{uuid.uuid4().hex[:10]}",
                    )
                    outcome: dict[str, Any] = {}
                    async for event in self.client.events(ORCHESTRATOR_PROFILE, info.api_key, run_id):
                        if event.get("event") in TERMINAL_EVENTS:
                            outcome = event
                            break
                    if not outcome:
                        outcome = await self.client.get_run(ORCHESTRATOR_PROFILE, info.api_key, run_id)
            except TimeoutError:
                await self._stop(info.api_key, run_id)
                raise
            except asyncio.CancelledError:
                await asyncio.shield(self._stop(info.api_key, run_id))
                raise
            except (HermesAPIError, httpx.HTTPError) as exc:
                raise HermesUnavailable(str(exc)) from exc

            status = str(outcome.get("status") or str(outcome.get("event", "")).removeprefix("run."))
            if status == "completed":
                return str(outcome.get("output") or "").strip()
            reason = str(outcome.get("error") or f"Hermes run ended as '{status or 'unknown'}'")
            if not MODEL_ERROR.search(reason):
                break
        raise HermesUnavailable(reason)

    async def _stop(self, key: str, run_id: str) -> None:
        if not run_id:
            return
        try:
            await self.client.stop_run(ORCHESTRATOR_PROFILE, key, run_id)
        except Exception as exc:
            logger.warning("Could not stop Hermes run %s: %s", run_id, exc)
