"""
Creates the Hermes profiles aiagent needs ahead of time: one per tool group (tasks without an agent) and the
orchestrator (planner, supervisor and report calls).

Hermes connects a profile to aiagent's tools, and starts serving its API key, only when its gateway starts, so a
profile created in the middle of a workflow would cost that workflow a gateway restart. They are created in the
background when aiagent starts (or the engine is switched to Hermes) and the gateway is restarted once, when idle.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from src.hermes.active_runs import ActiveRuns
from src.hermes.bundles import BUNDLES
from src.hermes.client import profile_prefix
from src.hermes.profiles import ORCHESTRATOR_PROFILE, HermesError, HermesProfiles

logger = logging.getLogger(__name__)

IDLE_WAIT_SECONDS = 900
# A workflow is between two Hermes runs for a few seconds (supervisor check, next task); wait this long after the last.
QUIET_SECONDS = 60


def hermes_in_use(settings: Any) -> bool:
    """The global engine, or any saved agent's engine, is Hermes."""
    if str(getattr(settings, "worker_engine", "") or "").strip().lower() == "hermes":
        return True
    try:
        from src.core.agent_store import AgentStore

        return any((a.worker_engine or "").strip().lower() == "hermes" for a in AgentStore().list_all())
    except Exception as exc:
        logger.debug("Could not list agents to check for the Hermes engine: %s", exc)
        return False


def orchestrator_loaded(settings: Any, api_key: str) -> bool:
    """The gateway serves the orchestrator profile's API key. True when it cannot be told (gateway unreachable)."""
    import httpx

    url = f"{settings.hermes_api_url.rstrip('/')}{profile_prefix(ORCHESTRATOR_PROFILE)}/v1/models"
    try:
        return httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=5.0).status_code < 400
    except httpx.HTTPError:
        return True


def provision_profiles(
    settings: Any,
    profiles: HermesProfiles | None = None,
    active: ActiveRuns | None = None,
    sleep: Callable[[float], None] = time.sleep,
    idle_wait_seconds: float = IDLE_WAIT_SECONDS,
    quiet_seconds: float = QUIET_SECONDS,
) -> bool:
    """Create the missing profiles; True when the gateway was restarted to pick them up."""
    if not hermes_in_use(settings):
        return False
    profiles = profiles or HermesProfiles(settings)
    active = active or ActiveRuns()
    changed = False
    try:
        if getattr(settings, "hermes_tool_bundles", False):
            for bundle in BUNDLES:
                info = profiles.ensure(None, [], None, bundle=bundle)
                # Never listed by Hermes: the gateway started before this profile existed.
                changed |= info.changed or not profiles.state.get(info.name).get("mcp_listed_at")
        if getattr(settings, "hermes_orchestration", False):
            info = profiles.ensure_orchestrator()
            changed |= info.changed or not orchestrator_loaded(settings, info.api_key)
    except HermesError as exc:
        logger.warning("Could not prepare the Hermes profiles: %s", exc)
        return False
    if not changed:
        return False

    waited = 0.0
    while active.any_active(quiet_seconds) and waited < idle_wait_seconds:
        sleep(5)
        waited += 5
    if active.any_active(quiet_seconds):
        logger.warning("Hermes runs stayed busy for %ds; the new profiles load on the next gateway restart",
                       idle_wait_seconds)
        return False
    logger.info("Restarting the Hermes gateway to load the new aiagent profiles")
    profiles.restart_gateway()
    return True
