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

    # ── Worker Configuration ─────────────────────────────
    worker_max_iterations: int = 8  # ReAct loop iteration limit
    worker_max_output_chars: int = 30000  # cap tool output per call (increased to allow full log dumps)
    worker_max_context_chars: int = 30000  # cap upstream context in persona

    # ── Planner Configuration ────────────────────────────
    planner_max_retries: int = 3  # retries on JSON parse failure
    planner_max_tasks: int = 12  # maximum tasks in a single DAG

    # ── Detection Analytics Thresholds ───────────────────
    # These are tunable parameters with documented rationale, deliberately not
    # magic numbers embedded in the analytics functions. They describe generic
    # behavioural properties and must never be tuned to make a specific
    # dataset score better.

    # Beaconing: automated callbacks repeat on a near-fixed cycle. Human and
    # application traffic has far higher relative variance in its intervals.
    beacon_min_events: int = 4  # too few samples cannot establish a cycle
    beacon_max_jitter_ratio: float = 0.15  # stddev/mean below this reads as machine-timed
    beacon_max_interval_seconds: int = 3600  # ignore cycles slower than hourly

    # Authentication sequences.
    auth_burst_window_seconds: int = 600  # window for grouping related attempts
    auth_spray_min_accounts: int = 3  # one source failing against N accounts
    auth_bruteforce_min_failures: int = 5  # repeated failures against one account
    auth_fatigue_min_denials: int = 3  # rejected prompts before an approval
    auth_fatigue_max_interval_seconds: int = 120  # rapid re-prompting, not user retries
    auth_typo_max_failures: int = 2  # a genuine typo is one or two attempts...
    auth_typo_success_window_seconds: int = 120  # ...immediately self-corrected

    # Impossible travel. Commercial aviation cruises near 900 km/h; the
    # threshold sits above it so legitimate air travel is not flagged.
    velocity_impossible_kmh: float = 1000.0
    velocity_min_distance_km: float = 100.0  # ignore jitter within a metro area
    velocity_same_metro_km: float = 150.0  # carrier/NAT pools span a region

    # Data transfer outliers, expressed in standard deviations above the mean
    # for the same source, so each environment sets its own baseline.
    transfer_outlier_sigma: float = 3.0
    transfer_min_bytes: int = 10_000_000  # ignore small transfers regardless of sigma

    # DNS pattern analytics. Tunneling encodes payloads inside query labels,
    # which drives label length and character entropy far beyond human-chosen
    # names; DGAs generate many high-entropy names that mostly fail to resolve.
    # All thresholds describe generic statistical properties of the encoding,
    # never any particular domain.
    dns_min_queries_per_domain: int = 4  # fewer samples cannot establish a pattern
    dns_tunnel_min_unique_subdomains: int = 4  # payload chunking yields unique labels
    dns_tunnel_min_label_length: float = 20.0  # human labels are short; encodings are not
    dns_tunnel_min_entropy: float = 3.0  # bits/char; english words sit near 2
    dns_hex_label_ratio: float = 0.5  # majority hex-only labels = byte encoding
    dns_dga_min_domains: int = 4  # a DGA burns through many domains
    dns_dga_min_nxdomain_ratio: float = 0.5  # most DGA candidates never resolve
    dns_dga_min_entropy: float = 2.8  # bits/char of the registered label

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

