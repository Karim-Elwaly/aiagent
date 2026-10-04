"""
Unit tests for new API endpoints:
- Long-Term Memory API (/api/memory, /api/memory/episodes)
- Distilled Skills Lifecycle API (/api/skills/distilled/*)
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.memory.store import Episode, Fact
from src.skills.manager import SkillCandidate


@pytest.fixture
def client():
    # Use TestClient with lifespan disabled to avoid connecting to Temporal/LLM during simple route unit testing
    return TestClient(app, raise_server_exceptions=False)


def test_api_memory_lifecycle(tmp_path):
    """Verify /api/memory GET, POST, DELETE, and /api/memory/episodes."""
    from src.memory.store import MemoryStore

    test_db = tmp_path / "test_api_memory.db"
    store = MemoryStore(db_path=test_db)

    with patch("src.memory.store.get_memory_store", return_value=store):
        client = TestClient(app, raise_server_exceptions=False)

        # 1. Post a new fact
        res = client.post(
            "/api/memory",
            json={"key": "api_port", "value": "8000", "scope": "project", "volatile": False},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "saved"

        # 2. Get all facts
        get_res = client.get("/api/memory")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["count"] == 1
        assert data["facts"][0]["key"] == "api_port"

        # 3. Search facts with query
        search_res = client.get("/api/memory?q=api_port")
        assert search_res.status_code == 200
        assert len(search_res.json()["facts"]) >= 1

        # 4. Search episodes
        store.record_episode(
            Episode(
                run_id="run-api-1",
                query="Query for test episode",
                goal="Goal for test episode",
                dag_json="{}",
            )
        )
        ep_res = client.get("/api/memory/episodes?q=test")
        assert ep_res.status_code == 200
        assert ep_res.json()["count"] >= 1
        assert ep_res.json()["episodes"][0]["run_id"] == "run-api-1"

        # 5. Delete fact
        del_res = client.delete("/api/memory/api_port")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Confirm deleted
        get_after = client.get("/api/memory")
        assert get_after.json()["count"] == 0


def test_api_distilled_skills_lifecycle(tmp_path):
    """Verify /api/skills/distilled/pending, approved, approve, reject endpoints."""
    from src.skills.manager import SkillManager

    manager = SkillManager(base_dir=tmp_path / "skills")

    cand = SkillCandidate(
        id="skill_api_distilled",
        name="api_distilled",
        goal="Test API distillation workflow",
        description="A distilled skill for testing",
        code="async def run(): return 'done'",
        parameters={},
        skills_provided=["api_distilled"],
        status="pending_approval",
    )
    manager.save_candidate(cand)

    with patch("src.skills.manager.get_skill_manager", return_value=manager):
        client = TestClient(app, raise_server_exceptions=False)

        # 1. List pending
        pending_res = client.get("/api/skills/distilled/pending")
        assert pending_res.status_code == 200
        pending_data = pending_res.json()
        assert len(pending_data) == 1
        assert pending_data[0]["name"] == "api_distilled"

        # 2. Approve
        approve_res = client.post("/api/skills/distilled/api_distilled/approve")
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "approved"

        # 3. List approved
        approved_res = client.get("/api/skills/distilled/approved")
        assert approved_res.status_code == 200
        approved_data = approved_res.json()
        assert len(approved_data) == 1
        assert approved_data[0]["name"] == "api_distilled"

        # 4. Pending should now be empty
        pending_after = client.get("/api/skills/distilled/pending")
        assert len(pending_after.json()) == 0
