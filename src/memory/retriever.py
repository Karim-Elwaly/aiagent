"""
UAOS Long-Term Memory Retriever (Gap 3)

Retrieves top-k relevant facts, past episodes, and operational lessons
and formats them into a bounded, grounded context block for:
  1. MetaPlanner task decomposition prompt.
  2. UniversalWorker system prompt.

Rules:
- Volatile facts are explicitly flagged so the model knows it MUST verify
  them with tools and never rely on them as current truth.
- Respects context token budgets (default ~800 tokens / 3200 chars).
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.text_utils import smart_truncate
from src.memory.store import MemoryStore, get_memory_store

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_BUDGET_CHARS = 3200  # ~800 tokens


class MemoryRetriever:
    """Retrieves and formats long-term memory for agent prompt injection."""

    def __init__(self, store: MemoryStore | None = None, budget_chars: int = DEFAULT_MEMORY_BUDGET_CHARS):
        self.store = store or get_memory_store()
        self.budget_chars = budget_chars

    def build_context(self, query: str, budget_chars: int | None = None) -> str:
        """Query memory store and format a grounded context block.

        Returns an empty string if no relevant memory was found.
        """
        if not query or not query.strip():
            return ""

        effective_budget = budget_chars or self.budget_chars
        facts = self.store.search_facts(query, limit=5)
        episodes = self.store.search_episodes(query, limit=2)

        if not facts and not episodes:
            return ""

        sections = []

        # 1. Facts Section
        if facts:
            fact_lines = []
            has_volatile = False
            for f in facts:
                is_vol = bool(f.get("volatile", False))
                tag = "[VOLATILE] " if is_vol else ""
                if is_vol:
                    has_volatile = True
                fact_lines.append(f"- {tag}**{f['key']}**: {f['value']}")

            vol_warning = (
                "\n> [!WARNING]\n"
                "> Facts marked [VOLATILE] (e.g. system state, current disk/IP) reflect "
                "prior runs. They inform the plan but MUST be verified using tools."
                if has_volatile
                else ""
            )

            sections.append(
                "## Known Facts & Environment Memory:\n"
                + "\n".join(fact_lines)
                + vol_warning
            )

        # 2. Similar Past Episodes
        if episodes:
            ep_lines = []
            for ep in episodes:
                ep_lines.append(
                    f"- Query: \"{ep['query'][:60]}\" → Outcome: {ep['outcome']} (ID: {ep['run_id']})"
                )
            sections.append(
                "## Similar Prior Workflow Runs:\n" + "\n".join(ep_lines)
            )

        content = "\n\n".join(sections)
        return smart_truncate(content, max_chars=effective_budget)


# Global singleton instance
_MEMORY_RETRIEVER: MemoryRetriever | None = None


def get_memory_retriever() -> MemoryRetriever:
    global _MEMORY_RETRIEVER
    if _MEMORY_RETRIEVER is None:
        _MEMORY_RETRIEVER = MemoryRetriever()
    return _MEMORY_RETRIEVER
