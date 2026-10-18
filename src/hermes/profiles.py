"""
Hermes profiles for aiagent agents: one ``aiagent-<agent>`` profile per agent (``aiagent-default`` without one).

Each profile is cloned from the user's default Hermes profile (model and provider), gets its own API key and an
``AIAGENT_MCP_TOKEN`` in its ``.env``, an ``aiagent`` MCP server pointing back at aiagent, only the Hermes
built-in toolsets aiagent allows for API runs, and the agent's aiagent skills (``skills.external_dirs``).
Hermes's tool search is off: it would hide aiagent's tools behind a search step, and aiagent already limits
which tools each agent sees. aiagent stores token hashes only, never the tokens.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.core.config import ROOT_DIR
from src.hermes.bundles import bundle_profile, bundle_tools
from src.hermes.skills import write_skills
from src.hermes.toolsets import BUILTIN_TOOLSETS

logger = logging.getLogger(__name__)

PROFILE_PREFIX = "aiagent-"
DEFAULT_PROFILE = "aiagent-default"
DYNAMIC_PROFILE_PREFIX = "aiagent-dyn-"
# Runs aiagent's planner, supervisor and report model calls when the Hermes engine is on; has no aiagent tools.
ORCHESTRATOR_PROFILE = "aiagent-orchestrator"
ORCHESTRATOR_SOUL = (
    "You are a precise reasoning model inside an orchestration system. You have no tools. Follow the instructions you "
    "are given exactly and reply only in the format they ask for.\n"
)
MCP_SERVER_NAME = "aiagent"
TOKEN_ENV = "AIAGENT_MCP_TOKEN"
STATE_DIR = ROOT_DIR / "data" / "hermes"
# Always on for aiagent profiles: without it Hermes cannot list or read the skills aiagent installs.
REQUIRED_TOOLSETS = ("skills",)

_state_lock = threading.Lock()


class HermesError(RuntimeError):
    """Hermes Agent could not be reached or configured."""


@dataclass
class ProfileInfo:
    name: str
    api_key: str
    changed: bool  # the aiagent MCP connection was (re)configured: wait for Hermes to list the tools again
    restarted_at: float = 0.0  # time.time() just before ensure() restarted the gateway


def hermes_home(settings: Any) -> Path:
    if getattr(settings, "hermes_home", ""):
        return Path(settings.hermes_home)
    local = os.environ.get("LOCALAPPDATA")
    if local and (Path(local) / "hermes").is_dir():
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def hermes_bin(settings: Any) -> str:
    if getattr(settings, "hermes_bin", ""):
        return settings.hermes_bin
    for candidate in ("hermes.exe", "hermes"):
        path = hermes_home(settings) / "bin" / candidate
        if path.exists():
            return str(path)
    return "hermes"


def profile_name(agent_id: str | None) -> str:
    if not agent_id:
        return DEFAULT_PROFILE
    slug = re.sub(r"[^a-z0-9]+", "-", agent_id.lower()).strip("-")[:48] or "agent"
    return PROFILE_PREFIX + slug


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def read_env_value(path: Path, key: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def append_env_value(path: Path, key: str, value: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    sep = "" if not existing or existing.endswith("\n") else "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{sep}{key}={value}\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class ProfileState:
    """``data/hermes/profiles.json``: what aiagent last applied to each profile, keyed by profile name."""

    def __init__(self, path: Path | None = None):
        self.path = path or STATE_DIR / "profiles.json"

    def load(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def update(self, name: str, entry: dict[str, Any]) -> None:
        with _state_lock:
            data = self.load()
            data[name] = {**data.get(name, {}), **entry}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def get(self, name: str) -> dict[str, Any]:
        return self.load().get(name, {})

    def remove(self, name: str) -> None:
        with _state_lock:
            data = self.load()
            if name in data:
                del data[name]
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)

    def touch_profile(self, name: str) -> None:
        self.update(name, {"last_used_at": time.time()})

    def list_dynamic_profiles(self) -> list[tuple[str, dict[str, Any]]]:
        """Returns list of (profile_name, entry) for all dynamic bespoke profiles."""
        data = self.load()
        return [
            (name, entry)
            for name, entry in data.items()
            if entry.get("is_dynamic") or name.startswith(DYNAMIC_PROFILE_PREFIX)
        ]

    def by_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        digest = token_hash(token)
        for name, entry in self.load().items():
            if secrets.compare_digest(entry.get("token_sha256", ""), digest):
                return {"profile": name, **entry}
        return None

    @property
    def _endpoint_path(self) -> Path:
        return self.path.with_name("mcp_endpoint.json")

    def mark_endpoint_started(self) -> None:
        self._endpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._endpoint_path.write_text(json.dumps({"started_at": time.time()}), encoding="utf-8")

    def endpoint_started_at(self) -> float:
        try:
            return float(json.loads(self._endpoint_path.read_text(encoding="utf-8")).get("started_at", 0))
        except (OSError, ValueError, AttributeError):
            return 0.0

    def mcp_connected(self, name: str, since: float = 0.0) -> bool:
        """Hermes has listed aiagent's tools since the profile was last (re)configured and the endpoint started."""
        entry = self.get(name)
        since = max(float(entry.get("configured_at", 0)), self.endpoint_started_at(), self.gateway_restarted_at(), since)
        return float(entry.get("mcp_listed_at", 0)) >= since

    @property
    def _restart_path(self) -> Path:
        return self.path.with_name("gateway_restart.json")

    def mark_gateway_restarted(self, at: float | None = None) -> None:
        self._restart_path.parent.mkdir(parents=True, exist_ok=True)
        self._restart_path.write_text(json.dumps({"at": at or time.time()}), encoding="utf-8")

    def gateway_restarted_at(self) -> float:
        try:
            return float(json.loads(self._restart_path.read_text(encoding="utf-8")).get("at", 0))
        except (OSError, ValueError, AttributeError):
            return 0.0


_SOUL_PLACEHOLDERS = {
    "{task_name}": "the task you are given",
    "{task_description}": "the task you are given",
    "{expected_output}": "the output the task asks for",
    "{tools}": "the tools available to you",
}
_DESCRIPTION_LIMIT = 500


def render_soul(agent: Any) -> str:
    """The agent's persona as a standing SOUL.md: per-task placeholders have no value outside a run."""
    text = (getattr(agent, "system_prompt_template", "") or "").strip()
    if not text:
        text = f"You are {agent.name}. {agent.description}".strip()
    for placeholder, replacement in _SOUL_PLACEHOLDERS.items():
        text = text.replace(placeholder, replacement)
    return text + "\n"


def render_description(agent: Any) -> str:
    return f"{agent.name}: {agent.description}".strip()[:_DESCRIPTION_LIMIT]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def purge_cloned_skills(profile_dir: Path, allowed_skills: set[str] | None = None) -> None:
    """Removes generic Hermes built-in skills and any unapproved skills from profile."""
    skills_dir = profile_dir / "skills"
    if not skills_dir.is_dir():
        return
    for item in list(skills_dir.iterdir()):
        try:
            if allowed_skills is not None:
                if item.name not in allowed_skills:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    elif item.is_file():
                        item.unlink(missing_ok=True)
            else:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    item.unlink(missing_ok=True)
        except OSError:
            pass


Runner = Callable[[list[str]], str]


class HermesProfiles:
    """Creates and configures aiagent's Hermes profiles through the ``hermes`` CLI."""

    def __init__(self, settings: Any, runner: Runner | None = None, state: ProfileState | None = None,
                 skills_root: Path | None = None):
        self.settings = settings
        self.home = hermes_home(settings)
        self.state = state or ProfileState()
        self.skills_root = skills_root or self.state.path.parent / "skills"
        self._run = runner or self._cli
        try:
            self.purge_all_duplicate_skills()
            self.sync_all_existing_dynamic_profiles()
        except Exception:
            pass

    def _cli(self, args: list[str]) -> str:
        cmd = [hermes_bin(self.settings), *args]
        env = dict(os.environ, HERMES_HOME=str(self.home))
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, timeout=180, env=env, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HermesError(f"hermes {' '.join(args)} could not run: {exc}") from exc
        if proc.returncode != 0:
            reason = (proc.stderr.strip() or proc.stdout.strip() or "no output")[-500:]
            raise HermesError(f"hermes {' '.join(args)} failed ({proc.returncode}): {reason}")
        return proc.stdout

    def wanted_toolsets(self, name: str, agent_toolsets: list[str]) -> list[str]:
        extra = self.state.get(name).get("extra_toolsets", []) if name == DEFAULT_PROFILE else agent_toolsets
        # Dynamic bespoke profiles run task-specific MCP tools and should not include the built-in 'skills' toolset
        # unless explicitly requested, preventing models from looping on skill_view instead of executing MCP tools.
        if name.startswith(DYNAMIC_PROFILE_PREFIX):
            wanted = set(agent_toolsets or [])
        else:
            wanted = set(self.settings.hermes_default_toolsets) | set(REQUIRED_TOOLSETS) | set(extra or [])
        return sorted(t for t in wanted if t in BUILTIN_TOOLSETS)

    def profile_config(self, name: str, tools: list[str] | None = None) -> dict[str, str]:
        config = {
            "tools.tool_search.enabled": "off",
            "skills.external_dirs": json.dumps([(self.skills_root / name).resolve().as_posix()]),
            # Force JSON tool-calling so local models (e.g. gpt-oss-20b) that do not support
            # Hermes's peg-native protocol can still call tools via the OpenAI-compatible format.
            "tool_format": "json",
        }
        if tools is not None:
            # Hermes registers only these tools of the aiagent server for this profile.
            config[f"mcp_servers.{MCP_SERVER_NAME}.tools.include"] = json.dumps(sorted(tools))
        return config

    def ensure(
        self, agent_id: str | None, agent_toolsets: list[str] | None = None,
        skill_docs: dict[str, str] | None = None, agent: Any = None, bundle: str | None = None,
        dynamic_tools: list[str] | None = None, profile_name_override: str | None = None,
    ) -> ProfileInfo:
        """Create or update the profile so it matches what aiagent allows. Idempotent.

        ``bundle`` selects a tool-group profile (tasks without an agent) instead of the agent's own profile.
        ``dynamic_tools`` & ``profile_name_override`` configure bespoke dynamic task profiles.
        """
        is_dynamic = bool(profile_name_override and profile_name_override.startswith(DYNAMIC_PROFILE_PREFIX))
        if profile_name_override:
            name = profile_name_override
            tools = sorted(dynamic_tools) if dynamic_tools is not None else []
        elif bundle:
            name = bundle_profile(bundle)
            tools = bundle_tools(bundle)
        else:
            name = profile_name(agent_id)
            tools = None
        pdir = self.home / "profiles" / name
        changed = False
        restarted_at = 0.0
        if pdir.is_dir() and not self.profile_has_model(name):
            logger.info("Profile '%s' on disk is missing model configuration; deleting to re-clone from default", name)
            self.delete_profile(name)
            changed = True

        profile_exists = pdir.is_dir() and (pdir / "config.yaml").is_file()
        if not profile_exists:
            description = (
                f"aiagent dynamic bespoke profile '{name}'" if is_dynamic else
                render_description(agent) if agent else
                f"aiagent tool group '{bundle}'" if bundle else
                f"aiagent agent '{agent_id}'" if agent_id else "aiagent tasks run without a selected agent"
            )
            if pdir.is_dir():
                (pdir / "config.yaml").unlink(missing_ok=True)
                shutil.rmtree(pdir, ignore_errors=True)
            try:
                self._run(["profile", "create", name, "--clone-from", "default", "--no-alias", "--description", description])
                changed = True
                logger.info("Created Hermes profile '%s'", name)
            except HermesError as exc:
                pdir.mkdir(parents=True, exist_ok=True)
                if not (pdir / "config.yaml").is_file():
                    logger.warning("Hermes profile create failed (%s); bootstrapping profile '%s' directly", exc, name)
                    self.sync_model_from_default(name)
                changed = True

        if is_dynamic or name == ORCHESTRATOR_PROFILE or bundle:
            if name == ORCHESTRATOR_PROFILE:
                purge_cloned_skills(pdir, allowed_skills=set())
            elif is_dynamic or bundle:
                self.sync_exact_task_skills(name, tools=tools)
            if self.sync_model_from_default(name):
                changed = True

        env = pdir / ".env"
        api_key = read_env_value(env, "API_SERVER_KEY")
        if not api_key:
            api_key = secrets.token_urlsafe(32)
            append_env_value(env, "API_SERVER_KEY", api_key)
            changed = True
        token = read_env_value(env, TOKEN_ENV)
        if not token:
            token = secrets.token_urlsafe(32)
            append_env_value(env, TOKEN_ENV, token)
            changed = True

        applied = self.state.get(name)
        identity: dict[str, str] = {}
        if agent:
            # Re-applied only when the agent changed, so a hand edit in Hermes survives until then.
            description = render_description(agent)
            identity["description_sha256"] = _digest(description)
            if applied.get("description_sha256") != identity["description_sha256"] and not created:
                self._run(["profile", "describe", name, "--text", description])
            soul = render_soul(agent)
            identity["soul_sha256"] = _digest(soul)
            if applied.get("soul_sha256") != identity["soul_sha256"]:
                (pdir / "SOUL.md").write_text(soul, encoding="utf-8")

        wanted = self.wanted_toolsets(name, agent_toolsets or [])
        if applied.get("toolsets") != wanted:
            self.apply_toolsets(name, wanted)
        disabled = self.wanted_disabled_skills(name, agent)
        if applied.get("disabled_skills", []) != disabled:
            self.apply_disabled_skills(name, disabled)

        if skill_docs is not None:
            if write_skills(self.skills_root / name, skill_docs):
                logger.info("Synced %d aiagent skills to Hermes profile '%s'", len(skill_docs), name)
            p_skills = pdir / "skills"
            if p_skills.is_dir():
                for item in list(p_skills.iterdir()):
                    if item.name.startswith("aiagent-"):
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        elif item.is_file():
                            item.unlink(missing_ok=True)
        (self.skills_root / name).mkdir(parents=True, exist_ok=True)
        config = self.profile_config(name, tools)
        applied_config = applied.get("config", {})
        config_to_set: dict[str, Any] = {}
        for key, value in config.items():
            prev_val = applied_config.get(key)
            if key.endswith(".tools.include") and prev_val is not None:
                try:
                    if set(json.loads(prev_val)) == set(json.loads(value)):
                        continue
                except Exception:
                    pass
            if prev_val != value:
                config_to_set[key] = value
                if key.endswith(".tools.include") and applied.get("mcp_url"):
                    changed = True  # Hermes lists the tools again only after a gateway restart

        mcp_url = self.settings.hermes_mcp_url
        target_timeout = int(getattr(self.settings, "hermes_run_timeout_seconds", 600))
        if applied.get("mcp_url") != mcp_url or applied.get("mcp_timeout") != target_timeout:
            config_to_set[f"mcp_servers.{MCP_SERVER_NAME}.url"] = mcp_url
            config_to_set[f"mcp_servers.{MCP_SERVER_NAME}.headers.Authorization"] = "Bearer ${" + TOKEN_ENV + "}"
            config_to_set[f"mcp_servers.{MCP_SERVER_NAME}.timeout"] = target_timeout
            changed = True
            if applied.get("mcp_url") and applied.get("mcp_url") != mcp_url:
                # The running gateway keeps the old URL for new runs until it restarts (no MCP reload command).
                logger.info("aiagent's MCP URL moved %s -> %s", applied["mcp_url"], mcp_url)
                restarted_at = time.time()
                self.restart_gateway()

        if config_to_set:
            self.write_profile_config(name, config_to_set)

        now = time.time()
        self.state.update(name, {
            "agent_id": agent_id or "",
            "token_sha256": token_hash(token),
            "toolsets": wanted,
            "mcp_url": mcp_url,
            "mcp_timeout": target_timeout,
            "config": config,
            **({"bundle": tools} if tools is not None else {}),
            **({"is_dynamic": True, "created_at": applied.get("created_at", now), "last_used_at": now} if is_dynamic else {}),
            **identity,
            **({"configured_at": restarted_at or now} if changed else {}),
        })
        return ProfileInfo(name=name, api_key=api_key, changed=changed, restarted_at=restarted_at)

    def delete_profile(self, name: str) -> bool:
        """Delete a dynamic profile from disk and state. Refuses to delete permanent profiles."""
        if name in (DEFAULT_PROFILE, ORCHESTRATOR_PROFILE) or not name.startswith(DYNAMIC_PROFILE_PREFIX):
            logger.warning("Refusing to delete permanent profile %r", name)
            return False
        pdir = self.home / "profiles" / name
        sdir = self.skills_root / name
        try:
            try:
                self._run(["profile", "delete", name, "--yes"])
            except Exception:
                pass
            if pdir.is_dir():
                (pdir / "config.yaml").unlink(missing_ok=True)
                shutil.rmtree(pdir, ignore_errors=True)
            if sdir.is_dir():
                shutil.rmtree(sdir, ignore_errors=True)
            self.state.remove(name)
            logger.info("Evicted dynamic profile %r", name)
            return True
        except Exception as exc:
            logger.warning("Failed to evict dynamic profile %r: %s", name, exc)
            return False

    def evict_lru_dynamic_profiles(
        self, needed_slots: int, max_dynamic: int, active_profiles: set[str] | None = None
    ) -> list[str]:
        """Evict least-recently used dynamic profiles if dynamic count + needed_slots > max_dynamic."""
        active = active_profiles or set()
        p_root = self.home / "profiles"
        disk_profiles: dict[str, dict[str, Any]] = {}
        if p_root.is_dir():
            for p in p_root.iterdir():
                if p.is_dir() and p.name.startswith(DYNAMIC_PROFILE_PREFIX):
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    disk_profiles[p.name] = {
                        "is_dynamic": True,
                        "created_at": mtime,
                        "last_used_at": mtime,
                    }

        state_profiles = dict(self.state.list_dynamic_profiles())
        all_dynamic = {**disk_profiles, **state_profiles}
        excess = (len(all_dynamic) + needed_slots) - max_dynamic
        if excess <= 0:
            return []

        candidates = [
            (name, entry) for name, entry in all_dynamic.items()
            if name not in active and name.startswith(DYNAMIC_PROFILE_PREFIX)
        ]
        candidates.sort(
            key=lambda pair: float(pair[1].get("last_used_at") or pair[1].get("created_at") or 0.0)
        )

        evicted = []
        for name, _ in candidates[:excess]:
            if self.delete_profile(name):
                evicted.append(name)
        return evicted

    def purge_orphan_profiles(self) -> list[str]:
        """Remove obsolete test profiles that bloat multiplexing and slow down gateway restart."""
        known_orphans = {
            "case-orchestrator",
            "evidence-collector-agent",
            "evidence-gatherer",
            "firewall-rule-generator",
            "firewall-rule-generator-agent",
            "firewall-rule-proposer",
            "impact-analyzer",
            "impact-analyzer-agent",
            "indicator-analyzer",
            "log-reader",
            "log-triage-agent",
            "log-triager",
            "report-generator",
            "threat-indicator-extractor",
            "timeline-compressor-agent",
            "timeline-constructor",
        }
        p_root = self.home / "profiles"
        purged = []
        if not p_root.is_dir():
            return purged

        for pdir in list(p_root.iterdir()):
            if not pdir.is_dir():
                continue
            name = pdir.name
            if name in known_orphans:
                try:
                    try:
                        self._run(["profile", "delete", name, "--yes"])
                    except Exception:
                        pass
                    (pdir / "config.yaml").unlink(missing_ok=True)
                    shutil.rmtree(pdir, ignore_errors=True)
                    self.state.remove(name)
                    purged.append(name)
                    logger.info("Purged orphan profile '%s'", name)
                except Exception as exc:
                    logger.warning("Could not purge orphan profile '%s': %s", name, exc)
        return purged

    def ensure_orchestrator(self) -> ProfileInfo:
        """The profile that answers aiagent's planner, supervisor and report calls: no aiagent tools, no skills."""
        name = ORCHESTRATOR_PROFILE
        pdir = self.home / "profiles" / name
        created = not pdir.is_dir()
        if created:
            self._run(["profile", "create", name, "--clone-from", "default", "--no-alias", "--description",
                       "aiagent planner, supervisor and report model calls"])
            logger.info("Created Hermes profile '%s'", name)
        purge_cloned_skills(pdir, allowed_skills=set())
        if self.sync_model_from_default(name):
            created = True
        env = pdir / ".env"
        api_key = read_env_value(env, "API_SERVER_KEY")
        if not api_key:
            api_key = secrets.token_urlsafe(32)
            append_env_value(env, "API_SERVER_KEY", api_key)
            created = True
        applied = self.state.get(name)
        soul_hash = _digest(ORCHESTRATOR_SOUL)
        if applied.get("soul_sha256") != soul_hash:
            (pdir / "SOUL.md").write_text(ORCHESTRATOR_SOUL, encoding="utf-8")
        if applied.get("toolsets") is None:
            try:
                self.apply_toolsets(name, [])
            except HermesError:
                self.apply_toolsets(name, list(REQUIRED_TOOLSETS))  # Hermes refused an empty toolset list
        self.state.update(name, {
            "role": "orchestrator",
            "soul_sha256": soul_hash,
            **({"configured_at": time.time()} if created else {}),
        })
        return ProfileInfo(name=name, api_key=api_key, changed=created)

    def get_skills_library_dir(self) -> Path | None:
        """Locates the master library of Hermes skills (e.g. 65 skills in aiagent-default or default)."""
        candidates = [
            self.home / "profiles" / DEFAULT_PROFILE / "skills",
            self.home / "profiles" / "default" / "skills",
            self.home / "skills",
            ROOT_DIR / "data" / "hermes_skills",
        ]
        for c in candidates:
            if c.is_dir() and any(c.iterdir()):
                return c
        return None

    def list_available_library_skills(self) -> dict[str, dict[str, Any]]:
        """Maps skill_name -> metadata dict with path, description, tags, and text content."""
        skills_meta: dict[str, dict[str, Any]] = {}

        def _index_dir(dir_path: Path) -> None:
            if not dir_path.is_dir():
                return
            for item in dir_path.iterdir():
                if item.name.startswith(".") or item.name.startswith("aiagent-"):
                    continue
                # If directory does not contain SKILL.md, check if it's a category folder with nested skills
                candidates = [item]
                if item.is_dir() and not (item / "SKILL.md").is_file():
                    sub_dirs = [sub for sub in item.iterdir() if sub.is_dir() and (sub / "SKILL.md").is_file()]
                    if sub_dirs:
                        candidates = sub_dirs
                    else:
                        continue

                for cand in candidates:
                    sname = cand.stem if cand.is_file() else cand.name
                    if sname.startswith(".") or sname.startswith("aiagent-"):
                        continue
                    content = ""
                    desc = ""
                    tags: list[str] = []
                    if cand.is_dir():
                        sfile = cand / "SKILL.md"
                        if sfile.is_file():
                            try:
                                content = sfile.read_text(encoding="utf-8", errors="replace")
                            except Exception:
                                pass
                    elif cand.is_file() and cand.suffix == ".md" and cand.name != "DESCRIPTION.md":
                        try:
                            content = cand.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            pass
                    if content:
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                try:
                                    import yaml
                                    meta = yaml.safe_load(parts[1])
                                    if isinstance(meta, dict):
                                        desc = str(meta.get("description", ""))
                                        m_meta = meta.get("metadata", {})
                                        if isinstance(m_meta, dict):
                                            for key in ("skills", "category", "tags"):
                                                val = m_meta.get(key)
                                                if isinstance(val, list):
                                                    tags.extend(val)
                                                elif isinstance(val, str):
                                                    tags.append(val)
                                            h_meta = m_meta.get("hermes", {})
                                            if isinstance(h_meta, dict):
                                                h_tags = h_meta.get("tags")
                                                if isinstance(h_tags, list):
                                                    tags.extend(h_tags)
                                except Exception:
                                    pass
                        if not desc:
                            first_line = content.split("\n", 1)[0].strip("# -")
                            desc = first_line[:200]
                    skills_meta[sname] = {
                        "path": cand,
                        "description": desc,
                        "tags": [t.lower() for t in tags if isinstance(t, str)],
                        "content": content[:2000].lower(),
                    }

        lib_dir = self.get_skills_library_dir()
        if lib_dir:
            _index_dir(lib_dir)

        # Augment with data/hermes_skills
        _index_dir(ROOT_DIR / "data" / "hermes_skills")
        return skills_meta

    def match_skills_for_task(
        self,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        task_name: str | None = None,
        task_desc: str | None = None,
    ) -> set[str]:
        """Matches the exact Hermes skills an agent needs to achieve the given task.
        
        Guarantees that each dynamic agent acquires between 0 and 65 skills (never all 65,
        and avoids polluting prompts with irrelevant skills).
        """
        tools_list = list(tools or [])
        skills_list = list(skills or [])
        if not tools_list and not skills_list:
            return set()

        available = self.list_available_library_skills()
        if not available:
            return set()

        # Domain mapping for standard tools to confirmed valid skills
        tool_domain_map: dict[str, list[str]] = {
            "gather_log_evidence": ["oss_forensics", "oss-forensics"],
            "lookup_threat_indicators": ["oss_forensics", "oss-forensics"],
            "analyze_incident_impact": ["oss_forensics", "oss-forensics", "docker_ops"],
            "compress_security_timeline": ["oss_forensics", "oss-forensics"],
            "propose_containment_response": ["oss_forensics", "oss-forensics", "docker_ops"],
            "triage_security_alert": ["oss_forensics", "oss-forensics"],
            "read_file": ["simplify_code", "file_ops"],
            "write_file": ["simplify_code", "file_ops"],
            "list_directory": ["file_ops", "simplify_code", "computer_use"],
            "get_disk_usage": ["computer_use", "system_diagnostics"],
            "delete_file": ["file_ops", "computer_use"],
            "execute_command": ["computer_use", "docker_ops"],
            "execute_python": ["computer_use", "instructor_mlops"],
            "python_session": ["computer_use", "instructor_mlops"],
            "get_system_info": ["computer_use", "docker_ops"],
            "web_search": ["arxiv_research", "web_search"],
            "web_extract": ["arxiv_research", "web_search"],
            "gitnexus_explorer": ["gitnexus_explorer", "github_workflow", "simplify_code"],
        }

        # Normalize explicit inquiry tokens (use full phrase to avoid substring word collisions)
        tokens: set[str] = set()
        for t in tools_list:
            clean_t = t.lower().replace("-", "_")
            tokens.add(clean_t)
        for s in skills_list:
            clean_s = s.lower().replace("-", "_")
            tokens.add(clean_s)

        full_context = f"{task_name or ''} {task_desc or ''}".lower()
        has_security = any(k in full_context for k in ("threat", "rootkit", "malware", "compromise", "attacker", "exfiltration", "reverse shell", "audit", "rbac", "security", "forensic"))
        has_k8s = any(k in full_context for k in ("k8s", "kubernetes", "pod", "container", "cluster", "node", "docker"))
        has_fs = any(k in full_context for k in ("list", "file", "tree", "directory", "enumerate", "read", "parse", "log", "read_file", "list_dir"))
        has_net = any(k in full_context for k in ("firewall", "iptables", "netsh", "containment", "traffic", "network", "c2", "beacon"))
        has_code = any(k in full_context for k in ("refactor", "codebase", "pull request", "syntax error"))
        has_git = any(k in full_context for k in ("git", "github", "commit", "repo", "branch"))
        has_db = any(k in full_context for k in ("database", "sql query", "postgres", "mysql", "slow query"))

        # Blacklist of consumer/specialist skills that should NEVER be injected into security/system operations
        unrelated_blacklist = {
            "drug_discovery", "fitness_nutrition", "apple_notes", "apple_reminders",
            "ascii_art", "home_assistant", "stripe_payments", "airtable_crm", "discord_notifier",
            "1password", "sherlock", "bitwarden", "lastpass",
        }

        scores: dict[str, int] = {}
        for sname, smeta in available.items():
            sname_clean = sname.lower().replace("-", "_")
            if sname_clean in unrelated_blacklist and sname_clean not in tokens:
                continue

            score = 0

            # 1. Direct exact skill name match
            if sname_clean in tokens or sname.lower() in [s.lower() for s in skills_list]:
                score += 15

            # 2. Tag matches (exact tag match with requested tokens)
            skill_tags = set(smeta.get("tags", []))
            if skill_tags & tokens:
                score += 8

            # 3. Tool domain mapping matches
            for tool_name in tools_list:
                mapped_skills = tool_domain_map.get(tool_name, [])
                for ms in mapped_skills:
                    if ms == sname_clean or ms in skill_tags:
                        score += 6

            # 4. Granular context matches
            if has_k8s and sname_clean in ("docker_ops", "container_management", "devops_troubleshooting"):
                score += 10
            if has_security and sname_clean in ("oss_forensics", "oss-forensics"):
                score += 10
            if has_fs and sname_clean in ("simplify_code", "computer_use", "file_ops"):
                score += 8
            if has_net and sname_clean in ("docker_ops", "computer_use"):
                score += 6
            if has_code and sname_clean in ("simplify_code", "computer_use"):
                score += 7
            if has_git and sname_clean in ("github_workflow", "gitnexus_explorer"):
                score += 8
            if has_db and sname_clean in ("database_optimizer", "sql"):
                score += 8

            # Description keyword overlap (only for significant domain words)
            desc = smeta.get("description", "").lower()
            for tok in tokens:
                if len(tok) >= 5 and tok in desc and tok not in ("tools", "using", "check", "system", "command", "order"):
                    score += 2

            if score > 0:
                scores[sname] = score

        # Rank candidates and deduplicate by normalized name (e.g. oss_forensics vs oss-forensics)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        seen_normalized: set[str] = set()
        matched: set[str] = set()
        for name, sc in ranked:
            if sc < 6:
                continue
            norm = name.lower().replace("-", "_")
            if norm in seen_normalized:
                continue
            seen_normalized.add(norm)
            matched.add(name)
            if len(matched) >= 4:
                break

        # Fallback only to top mapped tool skill if none matched
        if not matched and ranked and ranked[0][1] >= 5:
            matched = {ranked[0][0]}

        return matched

    def sync_exact_task_skills(
        self,
        name: str,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        task_name: str | None = None,
        task_desc: str | None = None,
    ) -> set[str]:
        """Ensures the profile on disk acquires the exact skills it needs (between 0 and 65).
        
        Writes matched skill folders to both ``self.profile_dir(name) / 'skills'``
        and ``self.skills_root / name``, and removes any unneeded skills.
        """
        if name == ORCHESTRATOR_PROFILE:
            purge_cloned_skills(self.profile_dir(name), allowed_skills=set())
            return set()
        if name == DEFAULT_PROFILE:
            return set()

        matched = self.match_skills_for_task(
            tools=tools, skills=skills, task_name=task_name, task_desc=task_desc
        )
        lib = self.list_available_library_skills()

        # 1. Update native profile skills dir (pdir / "skills")
        p_skills = self.profile_dir(name) / "skills"
        p_skills.mkdir(parents=True, exist_ok=True)

        for item in list(p_skills.iterdir()):
            if item.name not in matched:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    item.unlink(missing_ok=True)

        for sname in matched:
            target = p_skills / sname
            if target.is_dir() and (target / "SKILL.md").is_file():
                continue
            meta = lib.get(sname)
            if not meta:
                continue
            src = meta["path"]
            if src.is_dir():
                shutil.copytree(src, target, dirs_exist_ok=True)
            elif src.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target / "SKILL.md")

        # 2. Update external skills root (self.skills_root / name)
        ext_skills = self.skills_root / name
        ext_skills.mkdir(parents=True, exist_ok=True)
        for item in list(ext_skills.iterdir()):
            if item.name not in matched:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    item.unlink(missing_ok=True)
        for sname in matched:
            target = ext_skills / sname
            if target.is_dir() and (target / "SKILL.md").is_file():
                continue
            meta = lib.get(sname)
            if not meta:
                continue
            src = meta["path"]
            if src.is_dir():
                shutil.copytree(src, target, dirs_exist_ok=True)
            elif src.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target / "SKILL.md")

        self.state.update(name, {
            "task_skills": sorted(matched),
            "skills_count": len(matched),
        })
        logger.info("Profile '%s' acquired %d exact skills: %s", name, len(matched), sorted(matched))
        return matched

    def sync_all_existing_dynamic_profiles(self) -> int:
        """Syncs exact task skills for all dynamic profiles currently on disk/state."""
        p_root = self.home / "profiles"
        if not p_root.is_dir():
            return 0
        updated = 0
        for p in list(p_root.iterdir()):
            if p.is_dir() and p.name.startswith(DYNAMIC_PROFILE_PREFIX):
                entry = self.state.get(p.name)
                tools = entry.get("bundle", [])
                skills = entry.get("task_skills")
                self.sync_exact_task_skills(p.name, tools=tools, skills=skills)
                updated += 1
        return updated

    def purge_all_dynamic_cloned_skills(self) -> None:
        """Prunes generic unneeded Hermes built-in skills from all dynamic profiles,
        retaining only the exact task-matched skills (between 0 and 65)."""
        p_root = self.home / "profiles"
        if not p_root.is_dir():
            return
        targets = [ORCHESTRATOR_PROFILE] + [
            p.name for p in p_root.iterdir()
            if p.is_dir() and (p.name.startswith(DYNAMIC_PROFILE_PREFIX) or p.name.startswith("aiagent-bundle-"))
        ]
        for name in targets:
            pdir = p_root / name
            if name == ORCHESTRATOR_PROFILE:
                purge_cloned_skills(pdir, allowed_skills=set())
            else:
                entry = self.state.get(name)
                tools = entry.get("bundle", [])
                task_skills = entry.get("task_skills")
                self.sync_exact_task_skills(name, tools=tools, skills=task_skills)

    def _find_reference_model_config(self) -> tuple[dict[str, Any], dict[str, str]]:
        """Finds a valid (config_dict, env_dict) holding model/provider settings to propagate to profiles."""
        import yaml

        candidate_dirs = [
            self.home,
            self.home / "profiles" / DEFAULT_PROFILE,
            self.home / "profiles" / "default",
        ]
        p_root = self.home / "profiles"
        if p_root.is_dir():
            for p in p_root.iterdir():
                if p.is_dir() and p not in candidate_dirs:
                    candidate_dirs.append(p)

        ref_config: dict[str, Any] = {}
        ref_env: dict[str, str] = {}

        for cdir in candidate_dirs:
            cyaml = cdir / "config.yaml"
            if cyaml.is_file() and not ref_config:
                try:
                    loaded = yaml.safe_load(cyaml.read_text(encoding="utf-8")) or {}
                    if loaded.get("model") or loaded.get("provider") or loaded.get("custom_providers"):
                        ref_config = loaded
                except Exception:
                    pass

            cenv = cdir / ".env"
            if cenv.is_file():
                try:
                    for line in cenv.read_text(encoding="utf-8").splitlines():
                        line_s = line.strip()
                        if line_s and not line_s.startswith("#") and "=" in line_s:
                            k, v = line_s.split("=", 1)
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            if k not in ("API_SERVER_KEY", "API_SERVER_PORT", "API_SERVER_HOST", TOKEN_ENV) and k not in ref_env:
                                ref_env[k] = v
                except Exception:
                    pass

            if ref_config and any(k in ref_env for k in ("OPENAI_API_BASE", "OPENAI_BASE_URL", "HERMES_MODEL")):
                break

        return ref_config, ref_env

    def profile_has_model(self, name: str) -> bool:
        """True if the profile has a model or provider defined in its config.yaml or .env."""
        pdir = self.home / "profiles" / name
        if not pdir.is_dir():
            return False
        ref_config, ref_env = self._find_reference_model_config()
        if not ref_config and not ref_env:
            # No reference model configured in the environment (e.g. mock unit tests)
            return True
        yaml_path = pdir / "config.yaml"
        if yaml_path.is_file():
            try:
                import yaml
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                if data.get("model") or data.get("provider"):
                    return True
            except Exception:
                pass
        env_path = pdir / ".env"
        if env_path.is_file():
            try:
                text = env_path.read_text(encoding="utf-8")
                if "HERMES_MODEL" in text or "OPENAI_API_BASE" in text or "OPENROUTER_API_KEY" in text:
                    return True
            except Exception:
                pass
        return False

    def sync_model_from_default(self, name: str) -> bool:
        """Propagate model, provider, custom_providers, and provider env credentials into profile."""
        pdir = self.home / "profiles" / name
        if not pdir.is_dir():
            return False

        ref_config, ref_env = self._find_reference_model_config()
        if not ref_config and not ref_env:
            return False

        import yaml
        updated = False
        target_yaml = pdir / "config.yaml"
        target_data: dict[str, Any] = {}
        if target_yaml.is_file():
            try:
                target_data = yaml.safe_load(target_yaml.read_text(encoding="utf-8")) or {}
            except Exception:
                target_data = {}

        for k in ("model", "provider", "custom_providers", "fallback_models", "model_options", "llm"):
            if k in ref_config and (k not in target_data or not target_data[k]):
                target_data[k] = ref_config[k]
                updated = True

        # Always enforce JSON tool-calling format for aiagent-managed profiles so that
        # local models that don't support peg-native can still invoke tools correctly.
        if target_data.get("tool_format") != "json":
            target_data["tool_format"] = "json"
            updated = True

        if updated:
            try:
                target_yaml.write_text(
                    yaml.safe_dump(target_data, sort_keys=False, default_flow_style=False),
                    encoding="utf-8",
                )
                logger.info("Synchronized model/provider configuration into profile '%s'", name)
            except Exception as e:
                logger.warning("Failed writing synced config to profile '%s': %s", name, e)

        target_env = pdir / ".env"
        target_lines = target_env.read_text(encoding="utf-8").splitlines() if target_env.is_file() else []
        target_keys = {l.split("=", 1)[0].strip() for l in target_lines if "=" in l}

        to_append = []
        for k, v in ref_env.items():
            if k not in target_keys:
                to_append.append(f"{k}={v}")

        if to_append:
            try:
                sep = "\n" if target_lines and target_lines[-1].strip() else ""
                with open(target_env, "a", encoding="utf-8") as f:
                    f.write(sep + "\n".join(to_append) + "\n")
                logger.info("Synchronized %d environment variables into profile '%s'", len(to_append), name)
                updated = True
            except Exception as e:
                logger.warning("Failed appending env to profile '%s': %s", name, e)

        return updated

    def repair_all_dynamic_profiles(self) -> int:
        """Inspect all dynamic bespoke profiles on disk. Evict broken model-less profiles so they are cleanly re-cloned."""
        p_root = self.home / "profiles"
        if not p_root.is_dir():
            return 0
        repaired = 0
        for p in list(p_root.iterdir()):
            if p.is_dir() and p.name.startswith(DYNAMIC_PROFILE_PREFIX):
                if not self.profile_has_model(p.name):
                    logger.info("Evicting model-less dynamic profile '%s' so it will be freshly cloned from default", p.name)
                    self.delete_profile(p.name)
                    repaired += 1
                else:
                    self.sync_model_from_default(p.name)
        return repaired

    def purge_all_duplicate_skills(self) -> int:
        """Purge any aiagent-* skills found in any profile's local skills/ dir to prevent duplicate skill errors."""
        p_root = self.home / "profiles"
        if not p_root.is_dir():
            return 0
        cleaned = 0
        for p in list(p_root.iterdir()):
            if p.is_dir():
                s_dir = p / "skills"
                if s_dir.is_dir():
                    for item in list(s_dir.iterdir()):
                        if item.name.startswith("aiagent-"):
                            if item.is_dir():
                                shutil.rmtree(item, ignore_errors=True)
                            elif item.is_file():
                                item.unlink(missing_ok=True)
                            cleaned += 1
        if cleaned:
            logger.info("Purged %d duplicate aiagent-* skills from local profile directories", cleaned)
        return cleaned

    def write_profile_config(self, name: str, entries: dict[str, Any]) -> None:
        """Update profile config keys directly in config.yaml for speed, falling back to CLI."""
        pdir = self.home / "profiles" / name
        yaml_path = pdir / "config.yaml"
        updated_directly = False
        if pdir.is_dir():
            try:
                import yaml

                data: dict[str, Any] = {}
                if yaml_path.is_file():
                    try:
                        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                    except Exception:
                        data = {}
                for key, value in entries.items():
                    parts = key.split(".")
                    curr = data
                    for p in parts[:-1]:
                        if not isinstance(curr.get(p), dict):
                            curr[p] = {}
                        curr = curr[p]
                    val: Any = value
                    if isinstance(value, str):
                        s = value.strip()
                        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
                            try:
                                val = json.loads(s)
                            except Exception:
                                pass
                        elif s.lower() in ("true", "yes", "on"):
                            val = True
                        elif s.lower() in ("false", "no", "off"):
                            val = False
                        elif s.isdigit():
                            val = int(s)
                        else:
                            try:
                                val = float(s)
                            except ValueError:
                                pass
                    curr[parts[-1]] = val

                # Ensure any mcp_servers timeout is always numeric (int/float), never a string
                mcp_servers = data.get("mcp_servers", {})
                if isinstance(mcp_servers, dict):
                    for sname, sdata in mcp_servers.items():
                        if isinstance(sdata, dict) and "timeout" in sdata:
                            t_val = sdata["timeout"]
                            if isinstance(t_val, str):
                                try:
                                    sdata["timeout"] = int(t_val)
                                except ValueError:
                                    try:
                                        sdata["timeout"] = float(t_val)
                                    except ValueError:
                                        sdata["timeout"] = int(getattr(self.settings, "hermes_run_timeout_seconds", 600))

                yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False), encoding="utf-8")
                updated_directly = True
            except Exception as exc:
                logger.debug("Direct YAML update for profile '%s' failed (%s); falling back to CLI", name, exc)

        # In mock runner tests or when direct write was not possible, invoke CLI
        if not updated_directly or self._run != self._cli:
            for key, value in entries.items():
                self._run(["-p", name, "config", "set", key, value])

    def write_profile_skills(self, name: str, docs: dict[str, str]) -> None:
        if write_skills(self.skills_root / name, docs):
            logger.info("Synced %d aiagent skills to Hermes profile '%s'", len(docs), name)
        p_skills = self.profile_dir(name) / "skills"
        if p_skills.is_dir():
            for item in list(p_skills.iterdir()):
                if item.name.startswith("aiagent-"):
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    elif item.is_file():
                        item.unlink(missing_ok=True)

    def bundle_ready(self, bundle: str) -> bool:
        """The group's profile exists with the group's tool filter, and Hermes has connected its tools."""
        name = bundle_profile(bundle)
        if not (self.home / "profiles" / name).is_dir():
            return False
        return self.state.get(name).get("bundle") == bundle_tools(bundle) and self.state.mcp_connected(name)

    def sync_all_profiles_mcp_url(self) -> int:
        """Ensure every profile on disk and in state points to the current hermes_mcp_url with numeric timeout."""
        target_url = self.settings.hermes_mcp_url
        target_timeout = int(getattr(self.settings, "hermes_run_timeout_seconds", 600))
        updated = 0
        p_root = self.home / "profiles"
        if p_root.is_dir():
            for pdir in p_root.iterdir():
                if not pdir.is_dir():
                    continue
                cyaml = pdir / "config.yaml"
                if not cyaml.is_file():
                    continue
                try:
                    import yaml
                    data = yaml.safe_load(cyaml.read_text(encoding="utf-8")) or {}
                    mcp_servers = data.get("mcp_servers", {})
                    aiagent_mcp = mcp_servers.get(MCP_SERVER_NAME)
                    if isinstance(aiagent_mcp, dict):
                        curr_url = aiagent_mcp.get("url")
                        curr_timeout = aiagent_mcp.get("timeout")
                        modified = False
                        if curr_url and curr_url != target_url:
                            aiagent_mcp["url"] = target_url
                            modified = True
                            logger.info("Fixed stale MCP URL in %s: %s -> %s", pdir.name, curr_url, target_url)
                        if curr_timeout is not None and not isinstance(curr_timeout, (int, float)):
                            try:
                                aiagent_mcp["timeout"] = int(curr_timeout)
                            except (ValueError, TypeError):
                                aiagent_mcp["timeout"] = target_timeout
                            modified = True
                            logger.info("Fixed string timeout in %s: %r -> %d", pdir.name, curr_timeout, aiagent_mcp["timeout"])
                        if modified:
                            cyaml.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False), encoding="utf-8")
                            updated += 1
                except Exception as exc:
                    logger.debug("Could not inspect/update MCP config in %s: %s", pdir.name, exc)

        for name, entry in list(self.state.load().items()):
            if entry.get("mcp_url") and entry.get("mcp_url") != target_url:
                self.state.update(name, {"mcp_url": target_url, "mcp_timeout": target_timeout})
                updated += 1

        return updated

    def restart_gateway(self) -> None:
        """The only way to revive a parked MCP server or drop a cached URL in a running gateway."""
        # Marked before the call: the new gateway lists MCP tools during startup, before the CLI returns.
        self.state.mark_gateway_restarted()
        try:
            self._run(["gateway", "restart"])
            logger.info("Restarted the Hermes gateway")
        except HermesError as exc:
            logger.warning("Could not restart the Hermes gateway: %s", exc)

    def profile_dir(self, name: str) -> Path:
        return self.home / "profiles" / name

    def apply_toolsets(self, name: str, wanted: list[str]) -> None:
        off = [t for t in BUILTIN_TOOLSETS if t not in wanted]
        try:
            self._run(["-p", name, "tools", "disable", "--platform", "api_server", *off])
        except HermesError as exc:
            logger.warning("Could not disable toolsets for profile '%s' via CLI: %s", name, exc)
        if wanted:
            try:
                self._run(["-p", name, "tools", "enable", "--platform", "api_server", *wanted])
            except HermesError as exc:
                logger.warning("Could not enable toolsets for profile '%s' via CLI: %s", name, exc)
        self.state.update(name, {"toolsets": wanted})

    def wanted_disabled_skills(self, name: str, agent: Any = None) -> list[str]:
        if agent is not None:
            return sorted(set(getattr(agent, "hermes_disabled_skills", None) or []))
        return sorted(set(self.state.get(name).get("default_disabled_skills", [])))

    def apply_disabled_skills(self, name: str, disabled: list[str]) -> None:
        """Hermes skills the profile's API runs must not load (``skills.platform_disabled.api_server``)."""
        try:
            self._run(["-p", name, "config", "set", "skills.platform_disabled.api_server", json.dumps(disabled)])
        except HermesError as exc:
            logger.warning("Could not set platform_disabled skills for profile '%s' via CLI: %s", name, exc)
        self.state.update(name, {"disabled_skills": disabled})

    def set_default_toolsets(self, toolsets: list[str]) -> None:
        self.state.update(DEFAULT_PROFILE, {"extra_toolsets": sorted(set(toolsets))})

    def set_default_disabled_skills(self, names: list[str]) -> None:
        self.state.update(DEFAULT_PROFILE, {"default_disabled_skills": sorted(set(names))})

    def add_default_toolset(self, toolset: str) -> None:
        extra = set(self.state.get(DEFAULT_PROFILE).get("extra_toolsets", []))
        extra.add(toolset)
        self.state.update(DEFAULT_PROFILE, {"extra_toolsets": sorted(extra)})
