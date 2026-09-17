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
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "uaos-workers"

    # ── Worker Configuration ─────────────────────────────
    worker_max_iterations: int = 8  # ReAct loop iteration limit
    worker_max_output_chars: int = 2000  # cap tool output per call
    worker_max_context_chars: int = 3000  # cap upstream context in persona

    # ── Planner Configuration ────────────────────────────
    planner_max_retries: int = 3  # retries on JSON parse failure
    planner_max_tasks: int = 12  # maximum tasks in a single DAG

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
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(_settings, k) and v is not None:
                    setattr(_settings, k, v)
        except Exception as e:
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

