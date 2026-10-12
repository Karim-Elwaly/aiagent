import json
import logging
import os
from pathlib import Path
from typing import Any
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = ROOT_DIR / "runtime_settings.json"
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and runtime_settings.json."""

    # ── LLM Configuration ────────────────────────────────
    # Points to local inference server (Ollama, vLLM, LM Studio)
    llm_base_url: str = "http://10.7.75.103:1234/v1"
    llm_model: str = "qwen/qwen3.8-27b"
    llm_temperature: float = 0.1  # low for reliability
    llm_max_tokens: int = 4096
    llm_timeout_seconds: float = 300.0

    # Optional: separate model for workers (smaller, faster)
    # If not set, uses the same model as the planner
    worker_llm_model: str | None = None

    # ── Temporal Configuration ───────────────────────────
    temporal_host: str = "localhost:7234"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "uaos-workers"
    temporal_max_concurrent_activities: int = 3  # Max parallel tasks in a single ready batch

    # ── Worker Configuration ─────────────────────────────
    worker_max_iterations: int = 8  # ReAct loop iteration limit
    worker_max_output_chars: int = 8000  # cap tool output per call (increased for forensic log dumps)
    worker_max_context_chars: int = 12000  # cap upstream context in persona (increased for multi-phase correlation)
    # "universal" (aiagent's own ReAct loop) or "hermes" (the task runs inside Hermes Agent); agents may override.
    worker_engine: str = "universal"

    # ── Hermes Agent ─────────────────────────────────────
    hermes_api_url: str = "http://127.0.0.1:8642"
    hermes_home: str = ""  # empty: %LOCALAPPDATA%\hermes when it exists, else ~/.hermes
    hermes_bin: str = ""  # empty: the hermes executable under hermes_home, else PATH
    hermes_mcp_url: str = "http://127.0.0.1:8000/mcp/"  # where Hermes reaches aiagent's tools
    hermes_default_toolsets: list[str] = ["web"]  # Hermes built-ins every aiagent profile gets
    hermes_run_timeout_seconds: int = 1800
    hermes_approval_timeout_seconds: int = 600

    # ── Planner Configuration ────────────────────────────
    planner_max_retries: int = 3  # retries on JSON parse failure
    planner_max_tasks: int = 12  # maximum tasks in a single DAG

    # ── Durability / Resilience ──────────────────────────
    # Default outage tolerance when a request doesn't specify one.
    # One of: brief | standard | extended | unlimited (see src/core/resilience.py)
    default_resilience: str = "standard"
    # Hard upper bound on total wall-clock time for a single workflow run,
    # including all retries. Backstop so "unlimited" resilience cannot retry
    # forever against a permanently-dead LLM — Temporal force-closes the run
    # once this deadline passes.
    workflow_execution_timeout_seconds: int = 86400  # 24h

    # ── Decision Capture (offline evaluation) ────────────
    # Records the inputs + outputs of constrained-choice LLM calls (supervisor
    # verdict, task risk level) to data/decision_capture/*.jsonl so a corpus can
    # be built from real traffic and replayed offline. Off by default; captured
    # records include worker output and so may contain sensitive evidence.
    decision_capture_enabled: bool = False
    decision_capture_max_field_chars: int = 8000

    # ── Typed Decision Readout (AnyJev) — DORMANT ────────
    # Reads constrained choices (supervisor verdict, task risk level) out of the
    # model's distribution instead of parsing generated JSON. See
    # src/core/decider.py.
    #
    # The AnyJev backend is currently DORMANT (ANYJEV_DORMANT in decider.py):
    # these settings are wired and tested but cannot activate it on their own.
    # Setting decision_backend="anyjev" logs a warning and changes nothing.
    # The re-enable checklist lives next to the flag in decider.py.
    decision_backend: str = "none"
    decision_backend_url: str = ""    # defaults to llm_base_url
    decision_backend_model: str = ""  # defaults to llm_model
    decision_level: str = "L0"        # raw | L0 | L1 | L2

    # Shadow mode: run the typed readout alongside the generated decision, log
    # both, and act on NEITHER. This is how a candidate is compared against the
    # baseline on real traffic without risking a live run.
    decision_shadow_enabled: bool = False

    # Promotion. Only when True is a typed readout allowed to decide anything.
    # Keep this off until shadow-mode results on your own corpus beat the
    # baseline; a published benchmark on someone else's data is not evidence
    # about your traffic.
    decision_act_on_readout: bool = False
    # Refuse to act on a readout weaker than this. "raw" is uncalibrated and
    # position-biased, so it is never an acceptable floor for acting.
    decision_required_level: str = "L1"
    # Below this probability the decision is treated as undecided and handed to
    # a human rather than acted on automatically.
    decision_auto_accept_threshold: float = 0.9

    # ── API Configuration ────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = {
        "env_file": str(ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the application settings singleton, dynamically synced with runtime_settings.json."""
    global _settings
    if _settings is None:
        _settings = Settings()

    # Dynamic overlay from runtime_settings.json
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(_settings, k) and v is not None:
                    setattr(_settings, k, v)
    except Exception as e:
        # Ignore sandbox restriction if called from within a Temporal workflow
        if "Cannot access" not in str(e):
            logger.warning("Failed to load runtime settings from %s: %s", CONFIG_FILE, e)

    return _settings


def save_runtime_settings(updates: dict[str, Any]) -> Settings:
    """Save runtime overrides to runtime_settings.json and sync _settings and .env."""
    settings = get_settings()
    data = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data.update(updates)

    for k, v in updates.items():
        if hasattr(settings, k):
            setattr(settings, k, v)

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Failed to write runtime settings: %s", e)

    # Also sync into .env file
    try:
        env_lines = []
        if ENV_FILE.exists():
            env_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

        env_dict = {}
        for line in env_lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_dict[key.strip()] = val.strip()

        for k, v in updates.items():
            env_dict[k.upper()] = str(v)
            env_dict[f"UAOS_{k.upper()}"] = str(v)

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("# UAOS Environment Settings (Auto-generated)\n")
            for k, v in env_dict.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        logger.warning("Failed to update .env: %s", e)

    return settings

