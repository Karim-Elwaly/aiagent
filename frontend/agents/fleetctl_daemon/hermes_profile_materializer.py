import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("fleetctl.materializer")

FLEET_DYNAMIC_PREFIX = "fleet-dyn-"


def get_hermes_home(custom_home: str = "") -> Path:
    """Resolve Hermes home directory according to platform defaults."""
    if custom_home:
        return Path(custom_home)
    env_home = os.environ.get("FLEET_STUDIO_HERMES_HOME") or os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home)
    local = os.environ.get("LOCALAPPDATA")
    if local and (Path(local) / "hermes").is_dir():
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def sanitize_profile_name(agent_id: str, name: str = "") -> str:
    """Create a deterministic, safe Hermes profile name."""
    clean_name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()[:20] if name else ""
    clean_id = re.sub(r"[^a-zA-Z0-9]+", "-", agent_id).strip("-").lower()[:12]
    if clean_name:
        return f"{FLEET_DYNAMIC_PREFIX}{clean_name}-{clean_id}"
    return f"{FLEET_DYNAMIC_PREFIX}{clean_id}"


class HermesProfileMaterializer:
    """Materializes declared Fleet Studio agent proposals into real, executable Hermes profiles on host disk."""

    def __init__(self, custom_home: str = "", max_profiles: int = 25):
        self.home = get_hermes_home(custom_home)
        self.profiles_dir = self.home / "profiles"
        self.state_file = self.home / "fleet_profiles.json"
        self.max_profiles = max_profiles
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            try:
                self.state_file.write_text(json.dumps({}, indent=2), encoding="utf-8")
            except OSError:
                pass

    def _read_state(self) -> dict[str, dict[str, Any]]:
        try:
            if self.state_file.exists():
                return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read fleet_profiles.json: %s", exc)
        return {}

    def _write_state(self, state: dict[str, dict[str, Any]]) -> None:
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not write fleet_profiles.json: %s", exc)

    def _sync_from_default_profile(self, target_dir: Path) -> None:
        """Copy baseline config and model defaults from default Hermes profile if present."""
        default_dir = self.profiles_dir / "default"
        if not default_dir.is_dir():
            return
        # Copy env if target has none
        default_env = default_dir / ".env"
        target_env = target_dir / ".env"
        if default_env.is_file() and not target_env.exists():
            try:
                shutil.copy2(default_env, target_env)
            except OSError:
                pass

    def ensure_agent_profile(
        self,
        agent_id: str,
        name: str,
        role: str,
        scope: str,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        assigned_llm: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Materialize or update an agent's disk profile on the host Hermes system."""
        profile_name = sanitize_profile_name(agent_id, name)
        pdir = self.profiles_dir / profile_name
        is_new = not pdir.is_dir()
        pdir.mkdir(parents=True, exist_ok=True)

        self._sync_from_default_profile(pdir)

        # 1. Write or update .env with API_SERVER_KEY
        env_file = pdir / ".env"
        api_key = ""
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("API_SERVER_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass
        if not api_key:
            api_key = secrets.token_urlsafe(32)
            try:
                with open(env_file, "a", encoding="utf-8") as f:
                    f.write(f"\nAPI_SERVER_KEY={api_key}\n")
            except OSError as exc:
                logger.warning("Could not append API_SERVER_KEY for %s: %s", profile_name, exc)

        # 2. Write SOUL.md persona file
        bound_tools = tools or []
        tools_str = ", ".join(bound_tools) if bound_tools else "Deterministic Reasoning & Analysis"
        soul_content = f"""# Role: {name}
## Identifier
`{profile_name}` (Agent ID: `{agent_id}`)

## Operational Scope
{role}
{scope}

## Operational Boundaries
- You are an Autonomous Execution Unit (AEU) bound strictly to tools: [{tools_str}].
- Do NOT invent tools or external network connections outside this verified boundary.
- Any destructive or mutating state change requires operator sign-off in the Decision Room.
"""
        soul_file = pdir / "SOUL.md"
        try:
            soul_file.write_text(soul_content, encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to write SOUL.md for %s: %s", profile_name, exc)

        # 3. Write config.yaml with model and scoped tools.include
        llm = assigned_llm or {}
        family = llm.get("family", "local")
        version = llm.get("version", "default")

        yaml_lines = [
            f"# Fleet Studio Generated Profile: {profile_name}",
            "model:",
            f"  provider: \"{family}\"",
            f"  name: \"{version}\"",
            "tool_format: \"json\"",
            "tools:",
        ]
        if bound_tools:
            yaml_lines.append("  include:")
            for t in bound_tools:
                yaml_lines.append(f"    - \"{t}\"")
        else:
            yaml_lines.append("  tool_search:")
            yaml_lines.append("    enabled: false")

        config_file = pdir / "config.yaml"
        try:
            config_file.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to write config.yaml for %s: %s", profile_name, exc)

        # 4. Update tracking state
        now = time.time()
        state = self._read_state()
        state[profile_name] = {
            "agent_id": agent_id,
            "name": name,
            "profile_name": profile_name,
            "path": str(pdir),
            "created_at": state.get(profile_name, {}).get("created_at", now),
            "last_used_at": now,
            "is_dynamic": True,
            "bound_tools_count": len(bound_tools),
        }
        self._write_state(state)

        logger.info(
            "%s profile '%s' at %s (tools: %d)",
            "Materialized new" if is_new else "Updated",
            profile_name,
            pdir,
            len(bound_tools),
        )

        return {
            "profile_name": profile_name,
            "agent_id": agent_id,
            "path": str(pdir),
            "api_key_configured": bool(api_key),
            "bound_tools": bound_tools,
        }

    def evict_lru_dynamic_profiles(self, keep_profile_names: set[str] | None = None) -> list[str]:
        """Evict least recently used dynamic fleet profiles when total dynamic profiles exceed max_profiles."""
        keep = keep_profile_names or set()
        state = self._read_state()

        # Find dynamic profiles on disk
        candidates: list[tuple[str, float]] = []
        for pdir in self.profiles_dir.iterdir():
            if pdir.is_dir() and pdir.name.startswith(FLEET_DYNAMIC_PREFIX):
                if pdir.name in keep:
                    continue
                last_used = state.get(pdir.name, {}).get("last_used_at", 0.0)
                if not last_used:
                    try:
                        last_used = pdir.stat().st_mtime
                    except OSError:
                        last_used = 0.0
                candidates.append((pdir.name, last_used))

        total_dynamic = len(candidates) + len(keep)
        excess = total_dynamic - self.max_profiles
        if excess <= 0:
            return []

        # Sort oldest first
        candidates.sort(key=lambda pair: pair[1])
        evicted = []

        for name, _ in candidates[:excess]:
            pdir = self.profiles_dir / name
            try:
                shutil.rmtree(pdir, ignore_errors=True)
                state.pop(name, None)
                evicted.append(name)
                logger.info("LRU evicted dynamic profile '%s'", name)
            except Exception as exc:
                logger.warning("Could not evict profile '%s': %s", name, exc)

        self._write_state(state)
        return evicted

    def materialize_blueprint(self, blueprint: dict[str, Any]) -> dict[str, Any]:
        """Materialize all declared agents from a compiled blueprint."""
        agents = blueprint.get("agents") or []
        if not agents:
            return {"materialized": 0, "profiles": [], "evicted": []}

        active_profile_names: set[str] = set()
        results: list[dict[str, Any]] = []

        for raw_agent in agents:
            agent_id = raw_agent.get("agent_id") or raw_agent.get("id") or ""
            name = raw_agent.get("name") or "Specialist"
            role = raw_agent.get("role") or ""
            scope = raw_agent.get("scope") or ""
            tools = raw_agent.get("bound_tools") or raw_agent.get("tools") or []
            skills = raw_agent.get("bound_skills") or raw_agent.get("skills") or []
            assigned_llm = raw_agent.get("assigned_llm") or {}

            res = self.ensure_agent_profile(
                agent_id=agent_id,
                name=name,
                role=role,
                scope=scope,
                tools=tools,
                skills=skills,
                assigned_llm=assigned_llm,
            )
            active_profile_names.add(res["profile_name"])
            results.append(res)

        # Evict old dynamic profiles if over capacity
        evicted = self.evict_lru_dynamic_profiles(keep_profile_names=active_profile_names)

        return {
            "materialized": len(results),
            "profiles": results,
            "evicted": evicted,
            "hermes_home": str(self.home),
        }
