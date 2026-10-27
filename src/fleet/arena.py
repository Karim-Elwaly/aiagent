"""
Fleet Arena — Reusable Named Agent Profiles for the Autonomous Fleet

Manages the full Fleet Arena lifecycle:
    1. Plan:     Decompose mission → TaskDAG → FleetArenaManifest (draft)
    2. Provision: Create missing named Hermes profiles
    3. Attach:    Bind files to specific tasks/phases
    4. Start:     Launch execution via Temporal workflow

Fleet profiles use the prefix ``fleet-`` and are persistent, reusable
across different missions (exempt from LRU eviction).
"""

from __future__ import annotations

import copy
import logging
import re
import time
from typing import Any
from uuid import uuid4

from src.core.models import (
    FleetArenaManifest,
    FleetArenaUnit,
    TaskDAG,
)
from src.fleet.arena_store import FleetArenaStore
from src.hermes.profiles import (
    FLEET_PROFILE_PREFIX,
    fleet_profile_name,
    is_fleet_profile_name,
)
from src.registry.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def _infer_arena_slug(mission_prompt: str) -> str:
    """Auto-infer a short slug from the mission prompt for profile naming."""
    # Take the first few meaningful words
    stop_words = {
        "the", "a", "an", "for", "and", "or", "to", "in", "on", "of",
        "with", "from", "by", "at", "is", "are", "was", "were", "be",
        "this", "that", "it", "i", "we", "you", "my", "our", "me",
        "do", "does", "did", "will", "would", "could", "should",
        "can", "may", "might", "shall", "about", "into", "all",
    }
    words = re.findall(r"[a-zA-Z0-9]+", mission_prompt.lower())
    meaningful = [w for w in words if w not in stop_words and len(w) > 2][:3]
    slug = "-".join(meaningful) if meaningful else "mission"
    return slug[:24]


def _infer_arena_name(mission_prompt: str) -> str:
    """Auto-infer a human-readable arena name from the mission prompt."""
    clean = mission_prompt.strip()
    if len(clean) > 60:
        clean = clean[:57] + "..."
    return f"{clean} Arena"


def _infer_operational_stage(idx: int, total: int, task_name: str) -> str:
    """Infer the operational stage from task position and name keywords."""
    name_lower = task_name.lower()
    if idx == 0 or any(k in name_lower for k in [
        "ingest", "extract", "recon", "collect", "parse", "fetch", "scan"
    ]):
        return "RECON_INGESTION"
    if idx == total - 1 or any(k in name_lower for k in [
        "synthesize", "report", "dossier", "summary", "deliverable"
    ]):
        return "DELIVERABLE_SYNTHESIS"
    if any(k in name_lower for k in [
        "verify", "validate", "check", "audit", "compliance", "correlate"
    ]):
        return "CROSS_VERIFICATION"
    if any(k in name_lower for k in [
        "remediat", "block", "isolate", "patch", "execute", "action", "deploy"
    ]):
        return "EXECUTION_ACTION"
    return "DEEP_ANALYSIS"


class FleetArenaComposer:
    """Plans, provisions, and manages Fleet Arena lifecycles with reusable named profiles."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        store: FleetArenaStore | None = None,
        settings: Any = None,
    ):
        self.registry = registry
        self.store = store or FleetArenaStore()
        self.settings = settings

    # ── Phase 1: Plan ──────────────────────────────────────────────

    async def plan_arena(
        self,
        mission_prompt: str,
        agent_id: str = "",
        arena_slug: str | None = None,
        arena_name: str | None = None,
        strategy_profile: str = "STANDARD",
    ) -> FleetArenaManifest:
        """Plan a Fleet Arena: decompose mission → TaskDAG → named units.

        Does NOT provision profiles or start execution. Returns a draft
        manifest for user review.
        """
        from src.brain.meta_planner import MetaPlanner
        from src.core.llm_client import LocalLLMClient
        from src.core.config import get_settings

        settings = get_settings()

        # Build planner
        available_skills = self.registry.list_skills() if self.registry else []
        agents_roster: list[dict] = []
        try:
            from src.core.agent_store import AgentStore
            agents = AgentStore().list_all()
            agents_roster = [
                {"id": a.id, "name": a.name, "description": a.description, "skills": list(a.curated_skills)}
                for a in agents
            ]
        except Exception:
            pass

        llm = LocalLLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=max(settings.llm_max_tokens, settings.planner_max_tokens),
            timeout=settings.llm_timeout_seconds,
        )

        planner = MetaPlanner(
            llm=llm,
            available_skills=available_skills,
            max_retries=settings.planner_max_retries,
            agents=agents_roster,
            default_agent_id=agent_id,
        )

        dag = await planner.plan(mission_prompt)
        dag_dict = dag.to_serializable()

        # Derive arena identifiers
        slug = arena_slug or _infer_arena_slug(mission_prompt)
        name = arena_name or _infer_arena_name(mission_prompt)
        arena_id = f"arena-{slug}-{uuid4().hex[:6]}"

        # Check which fleet profiles already exist on disk
        existing_profiles = self._list_existing_fleet_profiles()

        # Build fleet arena units
        units: list[FleetArenaUnit] = []
        profiles_to_create: list[str] = []
        profiles_existing: list[str] = []

        total_tasks = len(dag.tasks)
        for idx, task in enumerate(dag.tasks):
            # Generate the deterministic profile name
            pname = fleet_profile_name(slug, task.name)

            # Resolve exact tools for this task
            scoped_tools: list[str] = []
            if self.registry and task.required_skills:
                resolved = self.registry.resolve(task.required_skills)
                scoped_tools = sorted(t.name for t in resolved)

            # Derive operational stage
            op_stage = _infer_operational_stage(idx, total_tasks, task.name)

            # Codename from task name
            codename = re.sub(r"[^A-Za-z0-9]+", "-", task.name).strip("-").upper()[:24]

            # Check existence
            exists = pname in existing_profiles
            if exists:
                profiles_existing.append(pname)
            else:
                profiles_to_create.append(pname)

            # Input/output contracts
            input_contract = (
                f"Requires verified outputs from upstream dependency nodes: "
                f"[{', '.join(task.dependencies) if task.dependencies else 'None - Initial Branch Node'}]"
            )
            output_contract = (
                task.expected_output
                or f"Verified execution payload fulfilling task '{task.name}'"
            )

            unit = FleetArenaUnit(
                profile_name=pname,
                unit_codename=codename,
                task_id=task.id,
                task_name=task.name,
                operational_stage=op_stage,
                scoped_tools=scoped_tools,
                required_skills=list(task.required_skills),
                description=task.description,
                input_contract=input_contract,
                output_contract=output_contract,
                profile_exists=exists,
            )
            units.append(unit)

            # Stamp the profile name onto the DAG task for downstream use
            for t in dag_dict.get("tasks", []):
                if t.get("id") == task.id:
                    t["hermes_profile"] = pname
                    t["_hermes_profile"] = pname

        manifest = FleetArenaManifest(
            arena_id=arena_id,
            arena_name=name,
            arena_slug=slug,
            mission_prompt=mission_prompt,
            strategy_profile=strategy_profile,
            units=units,
            dag=dag_dict,
            status="draft",
            created_at=time.time(),
            profiles_to_create=sorted(set(profiles_to_create)),
            profiles_existing=sorted(set(profiles_existing)),
            agent_id=agent_id or None,
        )

        # Persist the draft manifest
        self.store.save(manifest)

        logger.info(
            "Planned Fleet Arena '%s' (%s) with %d units — %d profiles to create, %d existing",
            arena_id, name, len(units),
            len(manifest.profiles_to_create), len(manifest.profiles_existing),
        )
        return manifest

    # ── Phase 2: Provision Named Profiles ──────────────────────────

    def provision_arena(self, arena_id: str) -> FleetArenaManifest:
        """Create missing Hermes profiles for all fleet units and restart gateway once.

        Transitions the arena from 'draft' to 'provisioned'.
        """
        manifest = self.store.load(arena_id)
        if manifest is None:
            raise ValueError(f"Fleet Arena '{arena_id}' not found")
        # Allow provisioning for all statuses so re-runs and updates don't crash
        valid_statuses = ("draft", "provisioned", "ready", "running", "completed", "files_attached")
        if manifest.status not in valid_statuses:
            logger.info("Arena status '%s' will be re-provisioned", manifest.status)

        from src.core.config import get_settings
        from src.hermes.profiles import HermesProfiles

        settings = get_settings()
        profiles = HermesProfiles(settings)
        gateway_needs_restart = False

        for unit in manifest.units:
            pname = unit.profile_name
            try:
                info = profiles.ensure_fleet_unit(
                    profile_name=pname,
                    unit_name=unit.task_name,
                    role=unit.operational_stage,
                    scope=unit.description,
                    skills=list(unit.required_skills or []),
                    tools=list(unit.scoped_tools or []),
                    arena_name=manifest.arena_name,
                    input_contract=unit.input_contract,
                    output_contract=unit.output_contract,
                    registry=self.registry,
                )
                unit.profile_exists = True
                if info.changed:
                    gateway_needs_restart = True
                logger.info(
                    "Provisioned fleet specialist profile '%s' (role: %s, %d skills: %s, %d tools: %s, changed=%s)",
                    pname, unit.operational_stage, len(unit.required_skills), unit.required_skills,
                    len(unit.scoped_tools), unit.scoped_tools, info.changed,
                )
            except Exception as exc:
                logger.warning("Failed to configure fleet profile '%s': %s", pname, exc)
                unit.profile_exists = False

        # Sync MCP URLs for all fleet profiles
        if profiles.sync_all_profiles_mcp_url():
            gateway_needs_restart = True

        # Single gateway restart only if brand new profiles were actually created
        if gateway_needs_restart and bool(manifest.profiles_to_create):
            import time as _time
            from src.hermes.active_runs import ActiveRuns

            active = ActiveRuns()
            # Also check if any direct workflows are currently running in FastAPI app
            is_workflow_running = False
            try:
                from src.api.main import app as fastapi_app
                direct_wf = getattr(fastapi_app.state, "direct_workflows", {})
                for wf_id, wf_st in direct_wf.items():
                    if isinstance(wf_st, dict) and wf_st.get("status") == "running":
                        is_workflow_running = True
                        break
            except Exception:
                pass

            if is_workflow_running or active.any_active(quiet_seconds=0):
                logger.warning(
                    "Another Hermes or direct workflow run is active; skipping gateway restart. "
                    "Fleet profiles will load on the next restart."
                )
            else:
                logger.info("Restarting Hermes gateway to mount %d new fleet profiles", len(manifest.profiles_to_create))
                profiles.restart_gateway()

                # Wait for gateway health
                import httpx
                deadline = _time.monotonic() + float(getattr(settings, "hermes_gateway_restart_timeout_seconds", 35))
                while _time.monotonic() < deadline:
                    try:
                        if httpx.get(f"{settings.hermes_api_url.rstrip('/')}/health", timeout=2.0).status_code == 200:
                            break
                    except Exception:
                        pass
                    _time.sleep(0.5)

        # Update manifest
        manifest.profiles_to_create = [
            u.profile_name for u in manifest.units if not u.profile_exists
        ]
        manifest.profiles_existing = [
            u.profile_name for u in manifest.units if u.profile_exists
        ]
        manifest.status = "provisioned"
        self.store.save(manifest)

        logger.info(
            "Fleet Arena '%s' provisioned — %d profiles ready, %d failed",
            arena_id, len(manifest.profiles_existing), len(manifest.profiles_to_create),
        )
        return manifest

    # ── Phase 3: Attach Files ──────────────────────────────────────

    def attach_files(
        self, arena_id: str, attachments: dict[str, list[dict[str, Any]]]
    ) -> FleetArenaManifest:
        """Attach files to specific tasks in the arena.

        Args:
            arena_id: The arena to attach files to.
            attachments: Mapping of task_id → list of file metadata dicts.
                Each dict should have at minimum: {filename, file_path}
                and optionally: {extracted_text, file_type, size_bytes}
        """
        manifest = self.store.load(arena_id)
        if manifest is None:
            raise ValueError(f"Fleet Arena '{arena_id}' not found")
        if manifest.status not in ("provisioned", "files_attached", "draft"):
            raise ValueError(
                f"Cannot attach files in status '{manifest.status}'"
            )

        for unit in manifest.units:
            if unit.task_id in attachments:
                unit.attached_files.extend(attachments[unit.task_id])
                # Enrich the corresponding DAG task description
                for task in manifest.dag.get("tasks", []):
                    if task.get("id") == unit.task_id:
                        lines = [task.get("description", "")]
                        lines.append("\n\n---\n# Attached Files:")
                        for att in attachments[unit.task_id]:
                            fname = att.get("filename", "unknown")
                            fpath = att.get("file_path", "")
                            text = att.get("extracted_text", "")
                            lines.append(f"### `{fname}`")
                            if fpath:
                                lines.append(f"- **Path**: `{fpath}`")
                            if text:
                                lines.append(f"- **Content**:\n```\n{text.strip()}\n```")
                        task["description"] = "\n".join(lines)

        has_any_files = any(u.attached_files for u in manifest.units)
        if has_any_files and manifest.status == "provisioned":
            manifest.status = "files_attached"
        self.store.save(manifest)

        logger.info(
            "Attached files to Fleet Arena '%s' — %d tasks received files",
            arena_id, len(attachments),
        )
        return manifest

    # ── Phase 4: Start Execution ───────────────────────────────────

    def get_enriched_dag(self, arena_id: str) -> dict[str, Any]:
        """Return the DAG enriched with file attachments and profile assignments.

        Called just before launching the Temporal workflow.
        """
        manifest = self.store.load(arena_id)
        if manifest is None:
            raise ValueError(f"Fleet Arena '{arena_id}' not found")
        return manifest.dag

    def clone_arena(
        self,
        arena_id: str,
        new_name: str | None = None,
        new_prompt: str | None = None,
    ) -> FleetArenaManifest:
        """Clone an existing Fleet Arena into a fresh ready-to-run instance.

        Preserves all named Hermes profile bindings, tool assignments, and unit
        specifications, but clears prior execution state and attached files so
        the operator can attach new files and launch a new mission immediately.

        Because the named profiles already exist in Hermes, the cloned arena
        starts with status 'provisioned' (zero gateway restarts required).
        """
        manifest = self.store.load(arena_id)
        if manifest is None:
            raise ValueError(f"Fleet Arena '{arena_id}' not found")

        from uuid import uuid4
        import time

        new_arena_id = f"arena-{manifest.arena_slug}-{uuid4().hex[:6]}"
        existing_profiles = self._list_existing_fleet_profiles()

        new_units = []
        for u in manifest.units:
            clean_desc = re.split(r"\n+--- (?:ATTACHED FILE|# Attached Files)", u.description)[0].rstrip()
            unit_copy = FleetArenaUnit(
                profile_name=u.profile_name,
                unit_codename=u.unit_codename,
                task_id=u.task_id,
                task_name=u.task_name,
                operational_stage=u.operational_stage,
                scoped_tools=list(u.scoped_tools),
                required_skills=list(u.required_skills),
                description=clean_desc,
                input_contract=u.input_contract,
                output_contract=u.output_contract,
                profile_exists=(u.profile_name in existing_profiles),
                attached_files=[],
            )
            new_units.append(unit_copy)

        new_dag = copy.deepcopy(manifest.dag)
        new_tasks = []
        for t in new_dag.get("tasks", []):
            t_copy = dict(t)
            t_copy["description"] = re.split(r"\n+--- (?:ATTACHED FILE|# Attached Files)", t_copy.get("description", ""))[0].rstrip()
            t_copy.pop("tool_calls_made", None)
            new_tasks.append(t_copy)
        new_dag["tasks"] = new_tasks

        all_exist = all(u.profile_exists for u in new_units)
        cloned_manifest = FleetArenaManifest(
            arena_id=new_arena_id,
            arena_name=new_name or f"{manifest.arena_name} (Reused)",
            arena_slug=manifest.arena_slug,
            mission_prompt=new_prompt or manifest.mission_prompt,
            strategy_profile=manifest.strategy_profile,
            units=new_units,
            dag=new_dag,
            status="provisioned" if all_exist else "draft",
            created_at=time.time(),
            profiles_to_create=[u.profile_name for u in new_units if not u.profile_exists],
            profiles_existing=[u.profile_name for u in new_units if u.profile_exists],
            agent_id=manifest.agent_id,
        )

        self.store.save(cloned_manifest)
        logger.info(
            "Cloned Fleet Arena '%s' -> '%s' (status=%s, %d/%d profiles existing in Hermes)",
            arena_id, new_arena_id, cloned_manifest.status,
            len(cloned_manifest.profiles_existing), len(new_units),
        )
        return cloned_manifest

    # ── Utility ────────────────────────────────────────────────────

    def _list_existing_fleet_profiles(self) -> set[str]:
        """Scan Hermes profiles directory for existing fleet-* profiles."""
        try:
            from src.core.config import get_settings
            from src.hermes.profiles import hermes_home

            settings = self.settings or get_settings()
            p_root = hermes_home(settings) / "profiles"
            if not p_root.is_dir():
                return set()
            return {
                p.name for p in p_root.iterdir()
                if p.is_dir() and is_fleet_profile_name(p.name) and (p / "config.yaml").is_file()
            }
        except Exception:
            return set()

    def list_fleet_profiles(self) -> list[dict[str, Any]]:
        """List all reusable fleet profiles with their metadata."""
        try:
            from src.core.config import get_settings
            from src.hermes.profiles import HermesProfiles, ProfileState

            settings = get_settings()
            state = ProfileState()
            p_root = HermesProfiles(settings).home / "profiles"

            results = []
            if not p_root.is_dir():
                return results

            for pdir in sorted(p_root.iterdir()):
                if not pdir.is_dir() or not is_fleet_profile_name(pdir.name):
                    continue
                entry = state.get(pdir.name)
                results.append({
                    "profile_name": pdir.name,
                    "tools": entry.get("bundle", []),
                    "created_at": entry.get("created_at", 0.0),
                    "last_used_at": entry.get("last_used_at", 0.0),
                    "has_config": (pdir / "config.yaml").is_file(),
                })
            return results
        except Exception as exc:
            logger.warning("Could not list fleet profiles: %s", exc)
            return []

    def delete_fleet_profile(self, profile_name: str) -> bool:
        """Delete a single fleet profile from Hermes."""
        if not is_fleet_profile_name(profile_name):
            raise ValueError(f"'{profile_name}' is not a fleet profile (must start with '{FLEET_PROFILE_PREFIX}')")
        try:
            from src.core.config import get_settings
            from src.hermes.profiles import HermesProfiles

            settings = get_settings()
            profiles = HermesProfiles(settings)
            return profiles.delete_profile(profile_name)
        except Exception as exc:
            logger.warning("Could not delete fleet profile '%s': %s", profile_name, exc)
            return False
