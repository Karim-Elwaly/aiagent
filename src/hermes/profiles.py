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
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.core.config import ROOT_DIR
from src.hermes.skills import write_skills
from src.hermes.toolsets import BUILTIN_TOOLSETS

logger = logging.getLogger(__name__)

PROFILE_PREFIX = "aiagent-"
DEFAULT_PROFILE = "aiagent-default"
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

    def by_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        digest = token_hash(token)
        for name, entry in self.load().items():
            if secrets.compare_digest(entry.get("token_sha256", ""), digest):
                return {"profile": name, **entry}
        return None

    def mcp_connected(self, name: str) -> bool:
        """Hermes has listed aiagent's tools since the profile was last (re)configured."""
        entry = self.get(name)
        return float(entry.get("mcp_listed_at", 0)) >= float(entry.get("configured_at", 0))


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
        wanted = set(self.settings.hermes_default_toolsets) | set(REQUIRED_TOOLSETS) | set(extra or [])
        return sorted(t for t in wanted if t in BUILTIN_TOOLSETS)

    def profile_config(self, name: str) -> dict[str, str]:
        return {
            "tools.tool_search.enabled": "off",
            "skills.external_dirs": json.dumps([(self.skills_root / name).resolve().as_posix()]),
        }

    def ensure(
        self, agent_id: str | None, agent_toolsets: list[str] | None = None,
        skill_docs: dict[str, str] | None = None, agent: Any = None,
    ) -> ProfileInfo:
        """Create or update the agent's profile so it matches what aiagent allows. Idempotent."""
        name = profile_name(agent_id)
        pdir = self.home / "profiles" / name
        changed = False
        created = not pdir.is_dir()
        if created:
            description = (render_description(agent) if agent else
                           f"aiagent agent '{agent_id}'" if agent_id else "aiagent tasks run without a selected agent")
            self._run(["profile", "create", name, "--clone-from", "default", "--no-alias", "--description", description])
            changed = True
            logger.info("Created Hermes profile '%s'", name)

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
            off = [t for t in BUILTIN_TOOLSETS if t not in wanted]
            self._run(["-p", name, "tools", "disable", "--platform", "api_server", *off])
            self._run(["-p", name, "tools", "enable", "--platform", "api_server", *wanted])

        if skill_docs is not None and write_skills(self.skills_root / name, skill_docs):
            logger.info("Synced %d aiagent skills to Hermes profile '%s'", len(skill_docs), name)
        (self.skills_root / name).mkdir(parents=True, exist_ok=True)
        config = self.profile_config(name)
        applied_config = applied.get("config", {})
        for key, value in config.items():
            if applied_config.get(key) != value:
                self._run(["-p", name, "config", "set", key, value])

        mcp_url = self.settings.hermes_mcp_url
        if applied.get("mcp_url") != mcp_url:
            self._run(["-p", name, "config", "set", f"mcp_servers.{MCP_SERVER_NAME}.url", mcp_url])
            self._run([
                "-p", name, "config", "set", f"mcp_servers.{MCP_SERVER_NAME}.headers.Authorization",
                "Bearer ${" + TOKEN_ENV + "}",
            ])
            self._run(["-p", name, "config", "set", f"mcp_servers.{MCP_SERVER_NAME}.timeout",
                       str(self.settings.hermes_run_timeout_seconds)])
            changed = True

        self.state.update(name, {
            "agent_id": agent_id or "",
            "token_sha256": token_hash(token),
            "toolsets": wanted,
            "mcp_url": mcp_url,
            "config": config,
            **identity,
            **({"configured_at": time.time()} if changed else {}),
        })
        return ProfileInfo(name=name, api_key=api_key, changed=changed)

    def add_default_toolset(self, toolset: str) -> None:
        extra = set(self.state.get(DEFAULT_PROFILE).get("extra_toolsets", []))
        extra.add(toolset)
        self.state.update(DEFAULT_PROFILE, {"extra_toolsets": sorted(extra)})
