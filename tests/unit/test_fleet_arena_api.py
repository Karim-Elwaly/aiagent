"""
Integration unit tests for Fleet Arena API endpoints in src/api/main.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.models import FleetArenaManifest, FleetArenaUnit


@pytest.fixture
def client():
    return TestClient(app)


def test_fleet_arena_plan_endpoint(client):
    """Test POST /api/fleet/arena/plan returns a valid draft manifest."""
    with patch("src.fleet.arena.FleetArenaComposer.plan_arena") as mock_plan:
        mock_manifest = FleetArenaManifest(
            arena_id="arena-soc-triage-123456",
            arena_name="SOC Triage Arena",
            arena_slug="soc-triage",
            mission_prompt="Triage incident #4521",
            units=[
                FleetArenaUnit(
                    profile_name="fleet-soc-triage-log-extractor",
                    unit_codename="LOG-EXTRACTOR",
                    task_id="t1",
                    task_name="Extract Logs",
                    scoped_tools=["search_tool"],
                )
            ],
            dag={"tasks": [{"id": "t1", "name": "Extract Logs"}]},
            status="draft",
            profiles_to_create=["fleet-soc-triage-log-extractor"],
            profiles_existing=[],
        )
        mock_plan.return_value = mock_manifest

        resp = client.post(
            "/api/fleet/arena/plan",
            json={"mission_prompt": "Triage incident #4521"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["arena_id"] == "arena-soc-triage-123456"
        assert data["status"] == "draft"
        assert len(data["units"]) == 1
        assert data["units"][0]["profile_name"] == "fleet-soc-triage-log-extractor"


def test_fleet_arena_crud_endpoints(client):
    """Test GET /api/fleet/arenas and GET /api/fleet/arena/{id}."""
    with patch("src.fleet.arena_store.FleetArenaStore.list_all") as mock_list, \
         patch("src.fleet.arena_store.FleetArenaStore.load") as mock_load:

        mock_manifest = FleetArenaManifest(
            arena_id="arena-test-999",
            arena_name="Test Arena",
            arena_slug="test",
            mission_prompt="Audit logs",
            units=[],
            status="provisioned",
        )
        mock_list.return_value = [mock_manifest]
        mock_load.return_value = mock_manifest

        # List
        resp = client.get("/api/fleet/arenas")
        assert resp.status_code == 200
        arenas = resp.json()
        assert len(arenas) == 1
        assert arenas[0]["arena_id"] == "arena-test-999"

        # Get by ID
        resp2 = client.get("/api/fleet/arena/arena-test-999")
        assert resp2.status_code == 200
        assert resp2.json()["arena_id"] == "arena-test-999"


def test_fleet_arena_attach_endpoint(client):
    """Test POST /api/fleet/arena/{id}/attach."""
    with patch("src.fleet.arena.FleetArenaComposer.attach_files") as mock_attach:
        mock_manifest = FleetArenaManifest(
            arena_id="arena-test-999",
            arena_name="Test Arena",
            arena_slug="test",
            mission_prompt="Audit logs",
            units=[
                FleetArenaUnit(
                    profile_name="fleet-test-parser",
                    task_id="t1",
                    task_name="Parse",
                    attached_files=[{"filename": "test.log", "file_path": "/tmp/test.log"}],
                )
            ],
            status="files_attached",
        )
        mock_attach.return_value = mock_manifest

        payload = {
            "attachments": {
                "t1": [{"filename": "test.log", "file_path": "/tmp/test.log"}]
            }
        }
        resp = client.post("/api/fleet/arena/arena-test-999/attach", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "files_attached"


def test_fleet_profiles_endpoints(client):
    """Test GET /api/fleet/profiles and DELETE /api/fleet/profiles/{name}."""
    with patch("src.fleet.arena.FleetArenaComposer.list_fleet_profiles") as mock_list, \
         patch("src.fleet.arena.FleetArenaComposer.delete_fleet_profile") as mock_del:

        mock_list.return_value = [
            {"profile_name": "fleet-soc-collector", "tools": ["search"], "created_at": 100.0}
        ]
        mock_del.return_value = True

        # List
        resp = client.get("/api/fleet/profiles")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["profiles"][0]["profile_name"] == "fleet-soc-collector"

        # Delete
        resp2 = client.delete("/api/fleet/profiles/fleet-soc-collector")
        assert resp2.status_code == 200
        assert resp2.json()["deleted"] is True


def test_fleet_arena_start_endpoint_direct(client):
    """Test POST /api/fleet/arena/{id}/start launches direct standalone execution."""
    with patch("src.fleet.arena_store.FleetArenaStore.load") as mock_load, \
         patch("src.fleet.arena_store.FleetArenaStore.save") as mock_save, \
         patch("src.fleet.arena.FleetArenaComposer.get_enriched_dag") as mock_dag, \
         patch("src.api.main.run_direct_workflow") as mock_run_direct:

        mock_manifest = FleetArenaManifest(
            arena_id="arena-test-123",
            arena_name="Test Arena",
            arena_slug="test",
            mission_prompt="Test mission",
            units=[
                FleetArenaUnit(
                    profile_name="fleet-test-unit",
                    task_id="t1",
                    task_name="Unit 1",
                )
            ],
            status="files_attached",
        )
        mock_load.return_value = mock_manifest
        mock_dag.return_value = {"tasks": [{"id": "t1"}]}

        with patch.object(app.state, "temporal", None):
            resp = client.post("/api/fleet/arena/arena-test-123/start")
            assert resp.status_code == 200
            data = resp.json()
            assert data["arena_id"] == "arena-test-123"
            assert data["status"] == "running"
            assert data["workflow_id"].startswith("fleet-arena-test-123-")
            assert data["units_count"] == 1

