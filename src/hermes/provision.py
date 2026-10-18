"""
Creates the Hermes profiles aiagent needs ahead of time: one per tool group (tasks without an agent) and the
orchestrator (planner, supervisor and report calls).

Hermes connects a profile to aiagent's tools, and starts serving its API key, only when its gateway starts, so a
profile created in the middle of a workflow would cost that workflow a gateway restart. They are created in the
background when aiagent starts (or the engine is switched to Hermes) and the gateway is restarted once, when idle.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from src.hermes.active_runs import ActiveRuns
from src.hermes.bundles import BUNDLES
from src.hermes.client import profile_prefix
from src.hermes.profiles import (
    DEFAULT_PROFILE,
    DYNAMIC_PROFILE_PREFIX,
    ORCHESTRATOR_PROFILE,
    HermesError,
    HermesProfiles,
)

logger = logging.getLogger(__name__)

IDLE_WAIT_SECONDS = 10
# A workflow is between two Hermes runs for a few seconds (supervisor check, next task); wait this long after the last.
QUIET_SECONDS = 5


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
                # Never listed by Hermes: the gateway started before this profile existed or was parked.
                changed |= info.changed or not profiles.state.mcp_connected(info.name)
        if getattr(settings, "hermes_orchestration", False):
            info = profiles.ensure_orchestrator()
            changed |= info.changed or not orchestrator_loaded(settings, info.api_key)
        max_dynamic = getattr(settings, "hermes_max_dynamic_profiles", 15)
        evicted = profiles.evict_lru_dynamic_profiles(needed_slots=0, max_dynamic=max_dynamic, active_profiles=active.active_profiles())
        if evicted:
            logger.info("Evicted %d stale dynamic profiles at startup: %s", len(evicted), evicted)
            changed = True
        purged = profiles.purge_orphan_profiles()
        if purged:
            logger.info("Purged %d obsolete test profiles at startup: %s", len(purged), purged)
            changed = True
        repaired = profiles.repair_all_dynamic_profiles()
        if repaired:
            logger.info("Repaired/evicted %d dynamic profiles missing model settings at startup", repaired)
            changed = True
        if profiles.sync_all_profiles_mcp_url():
            changed = True
        if not profiles.state.mcp_connected(DEFAULT_PROFILE):
            logger.info("Hermes MCP server not yet connected for default profile; restarting gateway")
            changed = True
        profiles.purge_all_dynamic_cloned_skills()
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


def compute_toolset_hash(tool_names: list[str]) -> str:
    sorted_names = sorted(tool_names)
    return hashlib.sha256(",".join(sorted_names).encode("utf-8")).hexdigest()[:8]


def provision_dag_profiles(
    dag_dict: dict[str, Any],
    registry: Any,
    settings: Any,
    profiles: HermesProfiles | None = None,
    active: ActiveRuns | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], bool]:
    """Inspects a planned TaskDAG, binds bespoke dynamic profiles with exact tools per task,
    enforces LRU capacity capping, and restarts the gateway once if new profiles were added.

    Returns:
        (updated_dag_dict, gateway_restarted_bool)
    """
    if not getattr(settings, "hermes_dynamic_profiles", True):
        return dag_dict, False

    profiles = profiles or HermesProfiles(settings)
    active = active or ActiveRuns()
    prefix = getattr(settings, "hermes_profile_prefix_dynamic", DYNAMIC_PROFILE_PREFIX)
    max_dynamic = getattr(settings, "hermes_max_dynamic_profiles", 15)

    needed_profiles: dict[str, list[str]] = {}

    for task in dag_dict.get("tasks", []):
        # Tasks with an explicit custom agent retain that agent's own profile
        if task.get("agent_id"):
            continue

        skills = task.get("required_skills", [])
        tools = registry.resolve(skills) if registry else []
        tool_names = sorted(t.name for t in tools)

        if not tool_names:
            task["_hermes_profile"] = ORCHESTRATOR_PROFILE
            task["hermes_profile"] = ORCHESTRATOR_PROFILE
            continue

        thash = compute_toolset_hash(tool_names)
        pname = f"{prefix}{thash}"
        task["_hermes_profile"] = pname
        task["hermes_profile"] = pname
        needed_profiles[pname] = tool_names

    if not needed_profiles:
        return dag_dict, False

    # Purge generic Hermes built-in skills and repair any model-less dynamic profiles first
    profiles.purge_all_dynamic_cloned_skills()
    repaired = profiles.repair_all_dynamic_profiles()
    if repaired:
        logger.info("Repaired/evicted %d dynamic profiles missing model settings", repaired)
    profiles.purge_orphan_profiles()
    profiles.sync_all_profiles_mcp_url()

    missing_profiles = {}
    for pname, tools in needed_profiles.items():
        entry = profiles.state.get(pname)
        pdir = profiles.home / "profiles" / pname
        has_config = (pdir / "config.yaml").is_file()
        has_model = profiles.profile_has_model(pname)
        if not pdir.is_dir() or not has_config or entry.get("bundle") != tools or not profiles.state.mcp_connected(pname) or not has_model:
            missing_profiles[pname] = tools

    if not missing_profiles:
        logger.info("All %d dynamic bespoke task profiles already active and configured; skipping gateway restart", len(needed_profiles))
        return dag_dict, False

    # Evict LRU dynamic profiles if adding missing profiles exceeds capacity
    # Protect both currently running active profiles AND profiles needed by this DAG
    protected = active.active_profiles() | set(needed_profiles.keys())
    evicted = profiles.evict_lru_dynamic_profiles(
        needed_slots=len(missing_profiles),
        max_dynamic=max_dynamic,
        active_profiles=protected,
    )
    if evicted:
        logger.info("Evicted %d LRU dynamic profiles to respect cap of %d: %s", len(evicted), max_dynamic, evicted)

    from src.hermes.skills import skill_documents

    # Provision missing profiles and sync exact task skills for all needed profiles
    for pname, tools in needed_profiles.items():
        try:
            pdir = profiles.home / "profiles" / pname
            needs_ensure = pname in missing_profiles or not pdir.is_dir() or not (pdir / "config.yaml").is_file()
            if needs_ensure:
                profiles.ensure(None, dynamic_tools=tools, profile_name_override=pname)
                logger.info("Provisioned bespoke dynamic profile '%s' with %d tools: %s", pname, len(tools), tools)
            else:
                profiles.sync_model_from_default(pname)
            # Ensure exact task skills are written to skills.external_dirs
            docs = skill_documents(None, registry, focus_tools=set(tools))
            profiles.write_profile_skills(pname, docs)
        except HermesError as exc:
            logger.warning("Could not provision dynamic profile '%s': %s", pname, exc)

    # Immediately purge cloned generic skills from all newly provisioned profiles
    profiles.purge_all_dynamic_cloned_skills()

    # Concurrency check: If another workflow is actively running, skip gateway restart
    if active.any_active(quiet_seconds=0):
        logger.warning(
            "Another Hermes run is active; skipping gateway restart to protect in-flight tasks. "
            "New profiles will load on the next gateway restart."
        )
        return dag_dict, False

    logger.info("Restarting Hermes gateway once post-planning to mount %d new dynamic profiles...", len(missing_profiles))
    profiles.restart_gateway()

    timeout = float(getattr(settings, "hermes_gateway_restart_timeout_seconds", 35))
    deadline = time.monotonic() + timeout
    healthy = False
    while time.monotonic() < deadline:
        try:
            import httpx

            if httpx.get(f"{settings.hermes_api_url.rstrip('/')}/health", timeout=2.0).status_code == 200:
                healthy = True
                break
        except Exception:
            pass
        sleep(0.5)

    if not healthy:
        logger.warning("Hermes gateway did not report healthy within %0.1fs after restart", timeout)
    else:
        logger.info("Hermes gateway restarted and healthy with %d bespoke profiles ready", len(missing_profiles))

    return dag_dict, True
