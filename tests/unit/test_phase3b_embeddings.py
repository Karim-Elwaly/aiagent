"""
Unit tests for Phase 3b: Dense vector embeddings and Reciprocal Rank Fusion (RRF).
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.memory.embeddings import (
    EmbeddingClient,
    cosine_similarity,
    reciprocal_rank_fusion,
)


def test_cosine_similarity():
    """Verify vector cosine similarity calculations."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert pytest.approx(cosine_similarity(v1, v2), 0.001) == 1.0

    v_orth = [0.0, 1.0, 0.0]
    assert pytest.approx(cosine_similarity(v1, v_orth), 0.001) == 0.0

    v_opp = [-1.0, 0.0, 0.0]
    assert pytest.approx(cosine_similarity(v1, v_opp), 0.001) == -1.0

    # Empty vectors
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_reciprocal_rank_fusion():
    """Verify RRF merges two ranked lists by reciprocal rank score."""
    list_bm25 = [
        {"key": "fact_a", "val": "first"},
        {"key": "fact_b", "val": "second"},
        {"key": "fact_c", "val": "third"},
    ]
    list_vector = [
        {"key": "fact_b", "val": "second"},
        {"key": "fact_d", "val": "fourth"},
        {"key": "fact_a", "val": "first"},
    ]

    fused = reciprocal_rank_fusion([list_bm25, list_vector], key_field="key", k=60)
    # fact_b appears at rank 2 in list_bm25 and rank 1 in list_vector, so it should rank #1
    assert fused[0]["key"] == "fact_b"
    assert fused[1]["key"] == "fact_a"
    keys = [item["key"] for item in fused]
    assert "fact_c" in keys
    assert "fact_d" in keys


@pytest.mark.asyncio
async def test_embedding_client():
    """Verify EmbeddingClient queries OpenAI-compatible /v1/embeddings endpoint."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"embedding": [0.12, 0.34, 0.56, 0.78]}]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    client = EmbeddingClient(base_url="http://mock-llm:1234/v1", model="test-embed")

    with patch("httpx.AsyncClient", return_value=mock_client):
        emb = await client.get_embedding("Test prompt text")
        assert emb is not None
        assert len(emb) == 4
        assert pytest.approx(emb[0], 0.01) == 0.12
        mock_client.post.assert_called_once()
