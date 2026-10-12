"""
Worker engine selection: per-agent override, then the global setting, then "universal".
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.agent_models import AgentProfile
from src.core.llm_client import LocalLLMClient
from src.registry.tool_registry import ToolRegistry
from src.workers.hermes_agent_worker import HermesAgentWorker
from src.workers.universal_worker import UniversalWorkerAgent

logger = logging.getLogger(__name__)

WORKER_ENGINES = ("universal", "hermes")
DEFAULT_ENGINE = "universal"


def resolve_engine(profile: Any, settings: Any) -> str:
    """The engine a task runs on; unknown values fall back to universal with a warning."""
    for source, value in (
        ("agent", getattr(profile, "worker_engine", None) if profile else None),
        ("settings", getattr(settings, "worker_engine", None)),
    ):
        if not value:
            continue
        engine = str(value).strip().lower()
        if engine in WORKER_ENGINES:
            return engine
        logger.warning("Unknown worker_engine %r from %s; using %s", value, source, DEFAULT_ENGINE)
        return DEFAULT_ENGINE
    return DEFAULT_ENGINE


def create_worker(
    engine: str, llm: LocalLLMClient, settings: Any, agent: AgentProfile | None = None,
    registry: ToolRegistry | None = None,
) -> UniversalWorkerAgent | HermesAgentWorker:
    if engine == "hermes":
        return HermesAgentWorker(settings=settings, agent=agent, registry=registry)
    return UniversalWorkerAgent(
        llm=llm,
        max_iterations=settings.worker_max_iterations,
        max_output_chars=settings.worker_max_output_chars,
    )
