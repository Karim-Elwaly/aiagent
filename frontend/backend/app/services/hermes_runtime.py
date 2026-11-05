"""Shared helpers for driving the Hermes agent runtime from Fleet Studio.

Hermes distinguishes between the ephemeral runtime ``session_id`` and the
persisted ``stored_session_id``.  ``session.resume`` only accepts the stored
identifier, while ``session.history`` and ``session.close`` expect the runtime
identifier returned by ``session.resume``.  Getting that pair wrong makes a
healthy runtime look like it is not running, which is why all Fleet Studio
call sites go through this module.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import settings

_IDLE_STATUSES = {"idle", "completed", "complete", "stopped"}
_UNUSABLE_PROVIDERS = {"", "local", "default", "unknown"}
_UNUSABLE_MODELS = {"", "default", "unknown"}


def default_hermes_home() -> str:
    """Return the Hermes home directory used as the agent working directory."""
    configured = (settings.hermes_home or "").strip()
    if configured:
        return os.path.expanduser(configured)
    if platform.system() == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return os.path.join(local_appdata, "hermes")
    return os.path.expanduser("~/.hermes")


def ensure_hermes_home() -> str:
    """Return the Hermes home directory, creating it when needed."""
    path = default_hermes_home()
    os.makedirs(path, exist_ok=True)
    return path


def workspace_path() -> str:
    """Return the Hermes workspace directory where staged documents live."""
    return os.path.join(default_hermes_home(), "workspace")


def flatten_content(value: Any) -> str:
    """Flatten Hermes message content into plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "")
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(value)


def assistant_text(history: dict) -> str:
    """Return the most recent non-empty assistant message from a history payload."""
    for message in reversed(history.get("messages", []) or []):
        if message.get("role") != "assistant":
            continue
        text = flatten_content(message.get("content") or message.get("text"))
        if text.strip():
            return text
    return ""


def tool_names(history: dict) -> list[str]:
    """Collect the distinct tool names recorded in a Hermes history payload."""
    names: list[str] = []

    def add(name: Any) -> None:
        if isinstance(name, str) and name and name not in names:
            names.append(name)

    for message in history.get("messages", []) or []:
        if message.get("role") == "tool":
            add(message.get("tool_name") or message.get("name"))
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            add(function.get("name") or call.get("name"))

    return names


def model_overrides(assigned_llm: dict | None = None) -> dict:
    """Build optional Hermes ``model``/``provider`` session parameters.

    Explicit Fleet Studio settings win.  A blueprint's assigned LLM is used only
    when it names a real Hermes provider/model instead of the heuristic
    ``local/default`` placeholder.
    """
    provider = (settings.hermes_provider or "").strip()
    model = (settings.hermes_model or "").strip()

    assigned_llm = assigned_llm or {}
    if not provider:
        candidate = str(assigned_llm.get("family") or "").strip()
        if candidate.lower() not in _UNUSABLE_PROVIDERS:
            provider = candidate
    if not model:
        candidate = str(assigned_llm.get("version") or "").strip()
        if candidate.lower() not in _UNUSABLE_MODELS:
            model = candidate

    overrides = {}
    if provider:
        overrides["provider"] = provider
    if model:
        overrides["model"] = model
    return overrides


def session_create_params(
    title: str,
    *,
    source: str = "fleet-studio",
    close_on_disconnect: bool = False,
    assigned_llm: dict | None = None,
    profile: str | None = None,
) -> dict:
    """Build ``session.create`` parameters that run inside the Hermes workspace."""
    params = {
        "title": title,
        "source": source,
        "cwd": ensure_hermes_home(),
        "close_on_disconnect": close_on_disconnect,
        **model_overrides(assigned_llm),
    }
    if profile:
        params["profile"] = profile
    return params


def turn_complete(snapshot: dict) -> bool:
    """Return whether a ``session.resume`` snapshot represents a finished turn."""
    status = str(snapshot.get("status") or "").lower()
    return snapshot.get("running") is False or status in _IDLE_STATUSES


async def resume_session(
    hermes,
    stored_session_id: str,
    *,
    lazy: bool = True,
    omit_messages: bool = True,
    timeout: float = 30,
) -> dict:
    """Resume a Hermes session using its persisted/stored identifier."""
    return await hermes.call(
        "session.resume",
        {
            "session_id": stored_session_id,
            "lazy": lazy,
            "omit_messages": omit_messages,
        },
        timeout=timeout,
    )


async def wait_for_turn(
    hermes,
    stored_session_id: str,
    timeout_seconds: float,
    *,
    poll_interval: float = 2.0,
    call_timeout: float = 30,
    on_snapshot: Callable[[dict], None] | None = None,
) -> dict:
    """Poll a Hermes turn until it is idle, returning the final snapshot.

    ``session.resume`` must be called with the stored session identifier.  The
    returned snapshot contains the runtime ``session_id`` needed for
    ``session.history`` / ``session.close``.
    """
    deadline = time.monotonic() + timeout_seconds
    last_snapshot: dict = {}
    started = False
    idle_since: float | None = None
    # Do not mistake the pre-submit idle snapshot for a finished turn.  A turn
    # is accepted as complete immediately once Hermes has reported "working";
    # otherwise it must stay idle for a short grace period.
    idle_grace = min(10.0, max(2.0, poll_interval * 2))
    while time.monotonic() < deadline:
        snapshot = await resume_session(
            hermes,
            stored_session_id,
            lazy=True,
            omit_messages=True,
            timeout=call_timeout,
        )
        last_snapshot = snapshot
        if on_snapshot is not None:
            on_snapshot(snapshot)
        if turn_complete(snapshot):
            if started:
                return snapshot
            if idle_since is None:
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= idle_grace:
                return snapshot
        else:
            started = True
            idle_since = None
        await asyncio.sleep(poll_interval)
    runtime_hint = last_snapshot.get("session_id") or stored_session_id
    raise TimeoutError(
        f"Hermes turn for session {runtime_hint} timed out after {timeout_seconds:g}s."
    )


async def get_session_history(hermes, runtime_session_id: str, *, timeout: float = 60) -> dict:
    """Fetch the transcript for a Hermes runtime session identifier."""
    return await hermes.call(
        "session.history",
        {"session_id": runtime_session_id},
        timeout=timeout,
    )


async def close_session(hermes, runtime_session_id: str, *, timeout: float = 15) -> None:
    """Close a Hermes runtime session, ignoring shutdown races."""
    try:
        await hermes.call("session.close", {"session_id": runtime_session_id}, timeout=timeout)
    except Exception:
        pass


async def current_provider(hermes) -> dict | None:
    """Return the inference provider Hermes is actually configured to use."""
    options = await hermes.call("model.options")
    providers = [row for row in options.get("providers") or [] if isinstance(row, dict)]
    for provider in providers:
        if provider.get("is_current"):
            return provider
    if len(providers) == 1:
        return providers[0]
    return None


async def provider_ready(hermes) -> bool:
    """Return whether the current Hermes provider has usable models.

    ``setup.status.provider_configured`` reports false for custom OpenAI
    compatible providers such as the local ``gpu`` provider, so readiness is
    derived from ``model.options`` instead.
    """
    try:
        provider = await current_provider(hermes)
    except Exception:
        return False
    if not provider:
        return False
    if not provider.get("models"):
        return False
    return provider.get("authenticated") is not False


def sanitize_profile_slug(text: str, max_len: int = 15) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return cleaned[:max_len]


def ensure_hermes_agent_profile(
    unit_name: str,
    mission_name: str,
    role: str = "Specialist",
    scope: str = "",
    tools: list[str] | None = None,
    skills: list[str] | None = None,
) -> str:
    """Materialize a dedicated agent profile on disk in $HERMES_HOME/profiles/<name>.
    This makes the profile visible in the Hermes Dashboard (/profiles) with its
    description, tools, skills, and persona (SOUL.md).
    """
    import shutil
    home = Path(ensure_hermes_home())
    profiles_dir = home / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    m_slug = sanitize_profile_slug(mission_name, 12)
    ag_slug = sanitize_profile_slug(unit_name, 15)
    profile_name = f"fleet-{m_slug}-{ag_slug}"
    pdir = profiles_dir / profile_name
    pdir.mkdir(parents=True, exist_ok=True)

    # 1. profile.yaml (Hermes Dashboard card metadata)
    desc = f"{unit_name} ({role}): {scope or mission_name}"[:280]
    (pdir / "profile.yaml").write_text(f"description: {repr(desc)}\ndescription_auto: false\n", encoding="utf-8")

    # 2. SOUL.md (Persona & Instructions)
    tools_str = ", ".join(tools) if tools else "web_search, web_extract, code_execution, terminal, file"
    skills_str = ", ".join(skills) if skills else "web_search, text_extraction, data_analysis"
    soul_content = f"""# Specialist Agent: {unit_name}

**Operational Role**: {role}
**Mission / Fleet Arena**: {mission_name}
**Fleet Profile**: `{profile_name}`

## Operational Scope & Boundaries
{scope or f"Autonomous specialist agent dedicated to {mission_name}."}

## Capability & Tool Bindings
- **Bound Skills**: {skills_str}
- **Authorized Toolset**: {tools_str}
- **Handoff Upstream**: Direct entry or trigger event

## Execution Directive
You are a dedicated specialist agent operating within an autonomous, multi-agent enterprise fleet.
Follow your operational boundaries strictly. Do NOT exceed your assigned scope or attempt tasks outside your role.
Use only your authorized tools and bound skills. Always deliver structured, epistemically grounded outputs with forensic citations.
"""
    (pdir / "SOUL.md").write_text(soul_content, encoding="utf-8")

    # 3. config.yaml
    default_config = home / "config.yaml"
    if not (pdir / "config.yaml").exists():
        if default_config.exists():
            shutil.copy2(default_config, pdir / "config.yaml")
        else:
            default_yaml = """model:
  api_mode: chat_completions
  base_url: http://10.7.75.103:1234/v1
  default: openai/gpt-oss-20b
  provider: gpu
providers:
  gpu:
    base_url: http://10.7.75.103:1234/v1
    discover_models: true
    model: openai/gpt-oss-20b
tool_format: json
"""
            (pdir / "config.yaml").write_text(default_yaml, encoding="utf-8")

    # 4. .env
    default_env = home / ".env"
    if not (pdir / ".env").exists() and default_env.exists():
        try:
            shutil.copy2(default_env, pdir / ".env")
        except Exception:
            pass

    return profile_name

