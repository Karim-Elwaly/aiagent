"""
Dense Embedding Client & Vector Utilities (Phase 3b)

Provides embedding generation via /v1/embeddings endpoint (LM Studio, Ollama, OpenAI)
and Reciprocal Rank Fusion (RRF) for hybrid BM25 + dense search.
"""

from __future__ import annotations

import logging
import math
from typing import Any
import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


class EmbeddingClient:
    """Client for generating dense embeddings via OpenAI-compatible endpoints."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or getattr(settings, "embedding_model", "text-embedding-nomic-embed-text-v1.5")

    async def get_embedding(self, text: str) -> list[float] | None:
        """Generate float vector embedding for input text string."""
        if not text or not text.strip():
            return None

        url = f"{self.base_url}/embeddings"
        payload = {
            "input": text.strip()[:2000],
            "model": self.model,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    data_items = data.get("data", [])
                    if data_items and "embedding" in data_items[0]:
                        return [float(x) for x in data_items[0]["embedding"]]
                logger.debug("Embedding endpoint returned status %s", resp.status_code)
                return None
        except Exception as e:
            logger.debug("Failed to obtain embedding from %s: %s", url, e)
            return None


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    key_field: str = "key",
    k: int = 60,
) -> list[dict[str, Any]]:
    """Merge multiple ranked result lists using Reciprocal Rank Fusion (RRF).

    Score(d) = sum(1 / (k + rank_i(d)))
    """
    scores: dict[str, float] = {}
    item_lookup: dict[str, dict[str, Any]] = {}

    for rlist in ranked_lists:
        for rank, item in enumerate(rlist):
            item_id = str(item.get(key_field, ""))
            if not item_id:
                continue
            item_lookup[item_id] = item
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank + 1))

    sorted_ids = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)
    return [item_lookup[i] for i in sorted_ids]
