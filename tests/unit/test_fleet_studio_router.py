"""
Unit tests for Fleet Studio API router (src/api/fleet_studio_router.py).

Validates all 15+ bridge endpoints connecting Fleet Studio's Next.js Control Plane
to AgentHub's FastAPI backend.
"""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.models import FleetArenaManifest, FleetArenaUnit


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_me_endpoint(client):
    """GET /auth/me returns operator identity and roles."""
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "sub" in data
    assert "operator" in data["email"].lower()
    assert "OPERATOR" in data["roles"]


def test_estate_inventory_endpoint(client):
    """GET /api/v1/inventory reflects tools, skills, and Hermes LLM models."""
    resp = client.get("/api/v1/inventory")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert "installed_skills" in data
    assert "registered_tools" in data
    assert "available_models" in data
    assert len(data["available_models"]) >= 1


def test_telemetry_endpoint(client):
    """GET /api/v1/telemetry returns estate cycle metrics and assurance breakdown."""
    resp = client.get("/api/v1/telemetry")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_fleets" in data
    assert "active_agents" in data
    assert "assurance_verdicts" in data
    assert "hourly_cycles" in data
    assert "skill_tool_utilization" in data


def test_missions_list_and_create(client):
    """GET /api/v1/missions and POST /api/v1/missions."""
    mock_manifest = FleetArenaManifest(
        arena_id="arena-mission-rfp",
        arena_name="Enterprise RFP Response",
        arena_slug="enterprise-rfp",
        mission_prompt="Ingest RFP.docx and compose proposal",
        units=[
            FleetArenaUnit(
                profile_name="fleet-rfp-ingest",
                unit_codename="INGEST",
                task_id="t1",
                task_name="Ingest RFP",
                scoped_tools=["execute_python"],
            )
        ],
        dag={"tasks": [{"id": "t1", "name": "Ingest RFP"}]},
        status="provisioned",
        profiles_to_create=[],
        profiles_existing=["fleet-rfp-ingest"],
    )

    with patch("src.fleet.arena_store.FleetArenaStore.list_all", return_value=[mock_manifest]):
        resp = client.get("/api/v1/missions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["mission_id"] == "arena-mission-rfp"
        assert data[0]["name"] == "Enterprise RFP Response"
        assert data[0]["status"] == "READY"

    with patch("src.fleet.arena.FleetArenaComposer.plan_arena", new_callable=AsyncMock) as mock_plan:
        mock_plan.return_value = mock_manifest
        resp = client.post(
            "/api/v1/missions",
            json={
                "name": "New Mission",
                "goal": "Decompose mission into multi-agent fleet",
                "competitive_benchmarking": False,
            },
        )
        assert resp.status_code == 200
        created = resp.json()
        assert created["mission_id"] == "arena-mission-rfp"
        assert created["status"] == "DESIGNING"


def test_clarifications_and_gates(client):
    """Test questions, answers, and stage gate decisions."""
    resp = client.post("/api/v1/missions/arena-mission-rfp/questions")
    assert resp.status_code == 200
    questions = resp.json()
    assert len(questions) >= 1
    assert "question_id" in questions[0]

    resp = client.put(
        "/api/v1/missions/arena-mission-rfp/answers",
        json={"answers": {"q1-environment": "Local Air-Gap"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    resp = client.post(
        "/api/v1/missions/arena-mission-rfp/gates",
        json={"stage": "ROSTER", "challenge_snapshot": {}},
    )
    assert resp.status_code == 200
    gate = resp.json()
    assert "gate_id" in gate

    resp = client.post(
        f"/api/v1/gates/{gate['gate_id']}/decision",
        json={"decision": "APPROVE", "feedback": "Approved"},
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "APPROVE"


def test_proposal_generation(client):
    """Test generating fleet agent proposal from planned arena."""
    mock_manifest = FleetArenaManifest(
        arena_id="arena-proposal-test",
        arena_name="Proposal Fleet",
        mission_prompt="Analyze logs and triage",
        units=[
            FleetArenaUnit(
                profile_name="fleet-log-specialist",
                unit_codename="LOGS",
                task_id="t1",
                task_name="Log Analysis Specialist",
                operational_stage="RECON_INGESTION",
                scoped_tools=["execute_python"],
                required_skills=["data_analysis"],
            )
        ],
        dag={"tasks": []},
        status="draft",
    )
    with patch("src.fleet.arena_store.FleetArenaStore.load", return_value=mock_manifest):
        resp = client.post("/api/v1/missions/arena-proposal-test/proposal")
        assert resp.status_code == 200
        prop = resp.json()
        assert prop["mission_id"] == "arena-proposal-test"
        assert len(prop["agents"]) == 1
        agent = prop["agents"][0]
        assert agent["agent_id"] == "fleet-log-specialist"
        assert agent["bound_skills"] == ["data_analysis"]
        assert agent["bound_tools"] == ["execute_python"]
        assert len(agent["workflow_steps"]) == 1


def test_blueprints_and_reconciliation(client):
    """POST /api/v1/blueprints and POST /api/v1/blueprints/{id}/apply."""
    resp = client.post("/api/v1/blueprints", json={"agents": []})
    assert resp.status_code == 200
    bp = resp.json()
    assert "blueprint_id" in bp
    assert bp["state"] == "READY"

    with patch("src.fleet.arena_store.FleetArenaStore.load") as mock_load, \
         patch("src.fleet.arena_store.FleetArenaStore.save"):
        mock_load.return_value = FleetArenaManifest(
            arena_id=bp["blueprint_id"],
            arena_name="Compiled Fleet",
            mission_prompt="Test",
            units=[],
            dag={"tasks": []},
            status="draft",
        )
        resp = client.post(
            f"/api/v1/blueprints/{bp['blueprint_id']}/apply",
            json={"confirm_changes": True},
        )
        assert resp.status_code == 200
        assert resp.json()["applied"] is True


def test_decision_rooms(client):
    """GET /api/v1/rooms and POST /api/v1/rooms/{id}/decision."""
    resp = client.get("/api/v1/rooms")
    assert resp.status_code == 200
    rooms = resp.json()
    assert len(rooms) >= 1
    room = rooms[0]
    assert "room_id" in room
    assert "verdict" in room
    assert room["status"] == "PENDING"

    resp = client.post(
        f"/api/v1/rooms/{room['room_id']}/decision",
        json={"decision": "APPROVE", "note": "Verified by Operator"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVE"


def test_fleet_roster_agents(client):
    """GET /api/v1/agents returns specialist agents for xyflow DAG."""
    mock_manifest = FleetArenaManifest(
        arena_id="arena-roster-123",
        arena_name="Cyber Incident Response",
        mission_prompt="Triage and contain lateral movement",
        units=[
            FleetArenaUnit(
                profile_name="fleet-triage-lead",
                unit_codename="LEAD",
                task_id="t-triage",
                task_name="Alert Triage Specialist",
                operational_stage="RECON_INGESTION",
                scoped_tools=["soc_triage_alert"],
                required_skills=["alert_triage"],
                profile_exists=True,
            )
        ],
        dag={"tasks": []},
        status="provisioned",
    )

    with patch("src.fleet.arena_store.FleetArenaStore.list_all", return_value=[mock_manifest]):
        resp = client.get("/api/v1/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 1
        a = agents[0]
        assert a["agent_id"] == "fleet-triage-lead"
        assert a["name"] == "Alert Triage Specialist"
        assert a["role"] == "RECON_INGESTION"
        assert a["bound_tools"] == ["soc_triage_alert"]
        assert a["managed_state"] == "APPLIED"


def test_run_fleet_and_stage_document(client):
    """POST /api/v1/missions/{id}/stage-document and POST /api/v1/missions/{id}/run."""
    mock_manifest = FleetArenaManifest(
        arena_id="arena-doc-run",
        arena_name="Proposal Fleet",
        mission_prompt="Generate Proposal",
        units=[
            FleetArenaUnit(
                profile_name="fleet-rfp-lead",
                unit_codename="LEAD",
                task_id="t1",
                task_name="Lead Analyst",
                scoped_tools=[],
            )
        ],
        dag={"tasks": []},
        status="provisioned",
    )

    with patch("src.fleet.arena_store.FleetArenaStore.load", return_value=mock_manifest), \
         patch("src.fleet.arena_store.FleetArenaStore.save"):

        # 1. Stage Document
        resp = client.post(
            "/api/v1/missions/arena-doc-run/stage-document?filename=sample_rfp.txt",
            content=b"Sample RFP requirements content for analysis.",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 200
        staged = resp.json()
        assert staged["status"] == "ok"
        assert "sample_rfp.txt" in staged["document_key"]

        # 2. Run Mission
        resp = client.post(
            "/api/v1/missions/arena-doc-run/run",
            json={"input_document": staged["document_key"]},
        )
        assert resp.status_code == 200
        run_data = resp.json()
        assert run_data["status"] == "dispatched"
        assert run_data["agent_name"] == "Lead Analyst"


def test_delete_mission(client):
    """DELETE /api/v1/missions/{id} removes arena from store."""
    with patch("src.fleet.arena_store.FleetArenaStore.delete", return_value=True):
        resp = client.delete("/api/v1/missions/arena-to-delete")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
