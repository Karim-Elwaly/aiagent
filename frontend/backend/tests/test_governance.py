import pytest
import httpx
import io
import json
import hashlib
import hmac
import time
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.schemas.domain import (
    AssuranceVerdict,
    AvailableModel,
    EvidenceCreate,
    EpistemicBasis,
    FormSchemaRequest,
    HermesEstateInventory,
    InstalledSkill,
    Mission,
    MissionCreate,
    RegisteredTool,
    RiskLevel,
    WorkflowStep,
)
from app.core.database import get_session
from app.core.config import settings
from app.models import AgentWorkflowRecord, Base, BlueprintRecord, DaemonJobRecord, DecisionRoomRecord, FleetAgentRecord, MissionRecord, WorkflowRunRecord, WorkflowStepRecord
from app.services.architect_pipeline import propose_fleet
from app.services.assurance import verify_evidence
from app.services.compiler import order_workflow_steps, parse_proposal, to_blueprint
from app.services.output_dispatcher import build_form_schema
from app.services.workflow_runner import execute_agent_cycle
from app.main import app
import app.api.v1.router as api_router
from agents.fleetcontrol_plugin import hook as fleet_hook


def fake_inventory(connected: bool = True) -> HermesEstateInventory:
    return HermesEstateInventory(
        connected=connected,
        runtime_hooks_enabled=True,
        provider_configured=True,
        installed_skills=[
            InstalledSkill(
                skill_id="document.review",
                version="1.2.0",
                description="Review supplied source documents.",
                required_tools=["vault.read"],
            ),
            InstalledSkill(
                skill_id="policy.summarize",
                version="2.0.1",
                description="Summarize policy with citations.",
                required_tools=["vault.read"],
            ),
            InstalledSkill(
                skill_id="case.triage",
                version="1.0.0",
                description="Classify operational cases and route work into the workflow.",
                required_tools=["case.search"],
            ),
        ],
        registered_tools=[
            RegisteredTool(tool_id="vault.read", risk_level=RiskLevel.READ_ONLY),
            RegisteredTool(tool_id="case.search", risk_level=RiskLevel.READ_ONLY),
            RegisteredTool(
                tool_id="case.create",
                risk_level=RiskLevel.STATE_MUTATING,
                requires_hitl_approval=True,
            ),
        ],
        available_models=[
            AvailableModel(
                family="local",
                version="small-1",
                data_residencies=["local"],
                reasoning_tier=2,
                estimated_daily_cost_usd=1,
            )
        ],
    )


@pytest.fixture
async def api_client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(api_router, "estate_summary", lambda: _inventory_async())
    app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.session_factory = session_factory
        yield client
    app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


async def _inventory_async():
    return fake_inventory()


@pytest.mark.asyncio
async def test_proposal_binds_only_role_required_tools():
    inventory = fake_inventory()
    mission = Mission(**MissionCreate(name="Records review", goal="Review source records and route exceptions.").model_dump())

    proposal = await propose_fleet(mission, inventory)

    assert proposal.agents[0].bound_skills == ["document.review"]
    assert proposal.agents[0].bound_tools == ["vault.read"]
    assert proposal.agents[1].bound_skills == ["policy.summarize"]
    assert proposal.agents[1].bound_tools == ["vault.read"]
    assert proposal.agents[2].bound_skills == ["case.triage"]
    assert proposal.agents[2].bound_tools == ["case.search"]
    assert proposal.agents[2].capability_gaps == []
    assert all(
        set(agent.bound_skills) <= {skill.skill_id for skill in inventory.installed_skills}
        and set(agent.bound_tools) <= {tool.tool_id for tool in inventory.registered_tools}
        for agent in proposal.agents
    )


@pytest.mark.asyncio
async def test_compiler_rejects_capabilities_absent_from_live_estate():
    inventory = fake_inventory()
    mission = Mission(**MissionCreate(name="Records review", goal="Review source records and route exceptions.").model_dump())
    proposal = await propose_fleet(mission, inventory)
    proposal.agents[0].bound_tools.append("shell.execute")

    with pytest.raises(ValueError, match="unknown tools"):
        parse_proposal(proposal, inventory)


@pytest.mark.asyncio
async def test_blueprint_compiles_mutating_tool_approval_policy():
    inventory = fake_inventory()
    mission = Mission(**MissionCreate(name="Records review", goal="Review source records and route exceptions.").model_dump())
    proposal = await propose_fleet(mission, inventory)
    proposal.agents[2].bound_tools.append("case.create")

    blueprint = to_blueprint(proposal, inventory)

    rule = next(rule for rule in blueprint.policy if rule.capability_id == "case.create")
    assert rule.requires_approval is True


def test_agent_judgment_is_rejected_at_schema_boundary():
    with pytest.raises(ValueError, match="cannot emit JUDGMENT"):
        EvidenceCreate(
            fleet_id="fleet-1",
            agent_id="agent-1",
            workflow_cycle_id="cycle-1",
            step_id="step-1",
            claim="Approve this supplier.",
            epistemic_basis=EpistemicBasis.JUDGMENT,
        )


def test_form_schema_rejects_undefined_required_fields():
    with pytest.raises(ValueError, match="Required fields are undefined"):
        build_form_schema(FormSchemaRequest(properties={"decision": {"type": "string"}}, required=["approver"]))


def test_workflow_steps_are_topologically_ordered_and_cycles_rejected():
    dependent = WorkflowStep(step_id="step-2", name="second", capability_id="document.review", depends_on=["step-1"])
    prerequisite = WorkflowStep(step_id="step-1", name="first", capability_id="document.review")
    assert [step.step_id for step in order_workflow_steps([dependent, prerequisite])] == ["step-1", "step-2"]

    cyclic = [
        WorkflowStep(step_id="step-a", name="a", capability_id="document.review", depends_on=["step-b"]),
        WorkflowStep(step_id="step-b", name="b", capability_id="document.review", depends_on=["step-a"]),
    ]
    with pytest.raises(ValueError, match="cycle"):
        order_workflow_steps(cyclic)


def test_runtime_hook_blocks_unbound_tool_without_sending_arguments(monkeypatch, capsys):
    event = {"hook_event_name": "pre_tool_call", "session_id": "hermes-session", "tool_name": "shell.exec", "tool_input": {"command": "secret"}}
    monkeypatch.setattr(fleet_hook.sys, "stdin", io.StringIO(json.dumps(event)))
    calls = []

    def respond(path, payload=None):
        calls.append((path, payload))
        return {"decision": "BLOCK", "reason": "Tool is not in the agent allowlist."}

    monkeypatch.setattr(fleet_hook, "_request", respond)

    assert fleet_hook.main() == 0
    assert json.loads(capsys.readouterr().out)["action"] == "block"
    assert calls == [
        (
            "/api/v1/daemon/tool-policy",
            {"hook_event_name": "pre_tool_call", "session_id": "hermes-session", "tool_name": "shell.exec"},
        )
    ]


def test_runtime_hook_fails_closed_when_policy_api_is_unavailable(monkeypatch):
    event = {"hook_event_name": "pre_tool_call", "session_id": "hermes-session", "tool_name": "vault.read"}
    monkeypatch.setattr(fleet_hook.sys, "stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr(fleet_hook, "_request", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))

    assert fleet_hook.main() == 2


def test_assurance_requires_trace_and_transcript_correlation():
    evidence = EvidenceCreate(
        fleet_id="fleet-1",
        agent_id="agent-1",
        workflow_cycle_id="cycle-1",
        step_id="step-1",
        claim="Supplier record is current.",
        epistemic_basis=EpistemicBasis.ANALYTICAL,
        transcript="Supplier record is current.",
        supporting_quote="Supplier record is current.",
        trace_available=False,
    )

    assert verify_evidence(evidence).verdict is AssuranceVerdict.NOT_VERIFIABLE


@pytest.mark.asyncio
async def test_api_mission_to_blueprint_and_plan(api_client, monkeypatch):
    mission_response = await api_client.post(
        "/api/v1/missions",
        json={
            "name": "Records review",
            "goal": "Review source records and route exceptions.",
            "constraints": {"execution_frequency": "event-driven"},
        },
    )
    assert mission_response.status_code == 201
    mission_id = mission_response.json()["mission_id"]

    list_response = await api_client.get("/api/v1/missions")
    assert list_response.status_code == 200
    assert list_response.json()[0]["mission_id"] == mission_id

    proposal_response = await api_client.post(f"/api/v1/missions/{mission_id}/proposal")
    assert proposal_response.status_code == 200
    assert proposal_response.json()["schema_version"] == "fleetcontrol.proposal/v1"

    blocked_compile = await api_client.post("/api/v1/blueprints", json=proposal_response.json())
    assert blocked_compile.status_code == 409
    for stage in ("INTAKE", "CLARIFICATION", "ROSTER", "COMPILATION"):
        gate_response = await api_client.post(
            f"/api/v1/missions/{mission_id}/gates",
            json={"stage": stage, "challenge_snapshot": {"approved_step": stage}},
        )
        assert gate_response.status_code == 201
        gate_id = gate_response.json()["gate_id"]
        decision_response = await api_client.post(
            f"/api/v1/gates/{gate_id}/decision",
            json={"decision": "APPROVE", "feedback": "Reviewed."},
        )
        assert decision_response.status_code == 200

    blueprint_response = await api_client.post("/api/v1/blueprints", json=proposal_response.json())
    assert blueprint_response.status_code == 201
    assert blueprint_response.json()["state"] == "READY"
    blueprint_id = blueprint_response.json()["blueprint_id"]

    persisted_blueprint = await api_client.get(f"/api/v1/blueprints/{blueprint_id}")
    assert persisted_blueprint.status_code == 200
    assert len(persisted_blueprint.json()["agents"]) == 3

    plan_response = await api_client.post(f"/api/v1/blueprints/{blueprint_id}/plan")
    assert plan_response.status_code == 200
    assert len(plan_response.json()["changes"]) == 3

    blocked_apply = await api_client.post(f"/api/v1/blueprints/{blueprint_id}/apply", json={})
    assert blocked_apply.status_code == 409
    monkeypatch.setattr(settings, "daemon_token", "daemon-test-secret")
    apply_response = await api_client.post(
        f"/api/v1/blueprints/{blueprint_id}/apply",
        json={"confirm_changes": True},
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "QUEUED"
    worker_headers = {
        "X-Fleet-Daemon-Token": "daemon-test-secret",
        "X-Fleet-Daemon-Id": "test-worker",
    }
    claim = await api_client.get("/api/v1/daemon/jobs", params={"wait": 0}, headers=worker_headers)
    assert claim.status_code == 200
    reconcile_job = claim.json()["jobs"][0]
    assert reconcile_job["job_type"] == "RECONCILE_BLUEPRINT"
    completed = await api_client.post(
        f"/api/v1/daemon/jobs/{reconcile_job['job_id']}/heartbeat",
        headers=worker_headers,
        json={"status": "SUCCEEDED"},
    )
    assert completed.status_code == 200

    roster = await api_client.get("/api/v1/agents")
    applied_agents = roster.json()
    assert len(applied_agents) == 3
    assert all(agent["applied"] for agent in applied_agents)
    downstream = next(agent for agent in applied_agents if agent["upstream_agent_ids"])
    source_agent_id = downstream["upstream_agent_ids"][0]
    trigger_payload = {"event_id": "cycle-event-001", "source_agent_id": source_agent_id, "payload": {"cycle_id": "cycle-1"}}
    trigger = await api_client.post(
        f"/api/v1/daemon/agents/{downstream['agent_id']}/trigger",
        headers=worker_headers,
        json=trigger_payload,
    )
    assert trigger.status_code == 200
    duplicate = await api_client.post(
        f"/api/v1/daemon/agents/{downstream['agent_id']}/trigger",
        headers=worker_headers,
        json=trigger_payload,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

@pytest.mark.asyncio
async def test_local_frontend_cors_and_email_approval_gate(api_client):
    preflight = await api_client.options(
            "/api/v1/rooms/room-047/decision",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
    )
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    put_preflight = await api_client.options(
        "/api/v1/missions/test-mission/answers",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "PUT" in put_preflight.headers["access-control-allow-methods"]

    async with api_client.session_factory() as session:
        session.add(MissionRecord(mission_id="mission-room", name="Test", goal="Test governance room", status="READY", constraints={}))
        session.add(BlueprintRecord(blueprint_id="blueprint-room", mission_id="mission-room", version=1, specification={}))
        session.add(FleetAgentRecord(agent_id="agent-room", blueprint_id="blueprint-room", name="Reviewer", specification={}, managed_state="APPLIED"))
        session.add(
            DecisionRoomRecord(
                room_id="room-pending",
                mission_id="mission-room",
                fleet_id="mission-room",
                agent_id="agent-room",
                title="Review required",
                status="PENDING",
                epistemic_basis="ANALYTICAL",
                assurance_verdict="EVIDENCE_FOUND",
                content={"summary": "Reviewed result", "workflow_cycle_id": "cycle-room"},
            )
        )
        await session.commit()

    email = await api_client.post(
        "/api/v1/outputs/email",
        json={
            "room_id": "room-pending",
            "recipient": "review@example.org",
            "subject": "Decision record",
        },
    )
    assert email.status_code == 409

    form_schema = await api_client.get("/api/v1/rooms/room-pending/form-schema")
    assert form_schema.status_code == 409

    approved = await api_client.post(
        "/api/v1/rooms/room-pending/decision",
        json={"decision": "APPROVE", "note": "Reviewed."},
    )
    assert approved.status_code == 200
    form_schema = await api_client.get("/api/v1/rooms/room-pending/form-schema")
    assert form_schema.status_code == 200
    invalid_form = await api_client.post(
        "/api/v1/rooms/room-pending/form-response",
        json={"values": {"follow_up_action": "DELETE_EVERYTHING", "note": "bad enum"}},
    )
    assert invalid_form.status_code == 422

    email = await api_client.post(
        "/api/v1/outputs/email",
        json={"room_id": "room-pending", "recipient": "review@example.org", "subject": "Decision record"},
    )
    assert email.status_code == 503

    daemon = await api_client.get("/api/v1/daemon/jobs")
    assert daemon.status_code == 503
    assert "not configured" in daemon.json()["detail"]


@pytest.mark.asyncio
async def test_production_read_routes_require_oidc_role(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/inventory")).status_code == 401
        assert (await client.get("/api/v1/telemetry")).status_code == 401
        assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_tool_hook_leaves_unmanaged_hermes_sessions_untouched(api_client, monkeypatch):
    monkeypatch.setattr(settings, "daemon_token", "daemon-test-secret")
    response = await api_client.post(
        "/api/v1/daemon/tool-policy",
        headers={"X-Fleet-Daemon-Token": "daemon-test-secret"},
        json={"hook_event_name": "pre_tool_call", "session_id": "interactive-session", "tool_name": "browser_exec"},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "PASS_UNMANAGED"


@pytest.mark.asyncio
async def test_webhook_trigger_requires_signature_and_deduplicates_event(api_client, monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", "test-webhook-secret")
    async with api_client.session_factory() as session:
        session.add(MissionRecord(mission_id="mission-hook", name="Test", goal="Test webhook trigger", status="READY", constraints={}))
        session.add(BlueprintRecord(blueprint_id="blueprint-hook", mission_id="mission-hook", version=1, specification={}))
        session.add(FleetAgentRecord(agent_id="agent-hook", blueprint_id="blueprint-hook", name="Webhook agent", specification={}, applied_specification={}, managed_state="APPLIED"))
        session.add(AgentWorkflowRecord(workflow_id="workflow-hook", agent_id="agent-hook", trigger_policy="WEBHOOK", workflow_specification={}))
        await session.commit()

    body = json.dumps({"event_id": "event-123", "payload": {"source": "test"}}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    digest = hmac.new(b"test-webhook-secret", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    headers = {"X-Fleet-Webhook-Signature": f"t={timestamp},v1={digest}", "Content-Type": "application/json"}
    first = await api_client.post("/api/v1/webhooks/agent-hook", content=body, headers=headers)
    duplicate = await api_client.post("/api/v1/webhooks/agent-hook", content=body, headers=headers)

    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True


@pytest.mark.asyncio
async def test_runtime_step_approval_queues_exact_cycle_resume(api_client):
    async with api_client.session_factory() as session:
        session.add(MissionRecord(mission_id="mission-step", name="Test", goal="Test runtime challenge", status="READY", constraints={}))
        session.add(BlueprintRecord(blueprint_id="blueprint-step", mission_id="mission-step", version=1, specification={}))
        session.add(FleetAgentRecord(agent_id="agent-step", blueprint_id="blueprint-step", name="Step agent", specification={}, applied_specification={}, managed_state="APPLIED"))
        session.add(WorkflowRunRecord(workflow_cycle_id="cycle-step", agent_id="agent-step", hermes_session_id="runtime", hermes_stored_session_id="stored", status="WAITING_REVIEW", trigger_context={}))
        session.add(WorkflowStepRecord(step_run_id="step-run", workflow_cycle_id="cycle-step", step_id="step-one", capability_id="vault.read", status="WAITING_REVIEW"))
        session.add(DecisionRoomRecord(room_id="room-step", mission_id="mission-step", fleet_id="mission-step", agent_id="agent-step", title="Step approval", status="PENDING", epistemic_basis="JUDGMENT", assurance_verdict="NOT_VERIFIABLE", content={"workflow_cycle_id": "cycle-step", "step_id": "step-one"}))
        await session.commit()

    decision = await api_client.post("/api/v1/rooms/room-step/decision", json={"decision": "APPROVE", "note": "Approved."})
    assert decision.status_code == 200
    assert decision.json()["resume_job_id"]
    async with api_client.session_factory() as session:
        run = await session.get(WorkflowRunRecord, "cycle-step")
        step = await session.get(WorkflowStepRecord, "step-run")
        job = await session.scalar(select(DaemonJobRecord).where(DaemonJobRecord.idempotency_key == "resume:cycle-step:step-one"))
        assert run.status == "RUNNING"
        assert step.status == "RUNNING"
        assert job.payload["trigger_context"]["resume_workflow_cycle_id"] == "cycle-step"


@pytest.mark.asyncio
async def test_runtime_step_challenge_pauses_before_hermes_execution(api_client, monkeypatch):
    monkeypatch.setattr(settings, "hermes_hooks_enabled", True)
    monkeypatch.setattr(api_router, "estate_summary", lambda: _inventory_async())
    import app.services.workflow_runner as workflow_runner

    monkeypatch.setattr(workflow_runner, "estate_summary", lambda: _inventory_async())
    async with api_client.session_factory() as session:
        session.add(MissionRecord(mission_id="mission-gate", name="Gate test", goal="Test runtime step gate", status="READY", constraints={}))
        session.add(BlueprintRecord(blueprint_id="blueprint-gate", mission_id="mission-gate", version=1, specification={}))
        session.add(
            FleetAgentRecord(
                agent_id="agent-gate",
                blueprint_id="blueprint-gate",
                name="Gate agent",
                specification={},
                applied_specification={
                    "agent_id": "agent-gate",
                    "name": "Gate agent",
                    "role": "REVIEWER",
                    "scope": "Review source documents.",
                    "capability_gaps": [],
                    "workflow_steps": [{"step_id": "gated-step", "name": "Review", "capability_id": "document.review", "requires_step_challenge": True}],
                    "assigned_llm": {"family": "local", "version": "small-1"},
                },
                managed_state="APPLIED",
            )
        )
        await session.commit()
        result = await execute_agent_cycle("agent-gate", session)
        assert result["status"] == "WAITING_REVIEW"
        run = await session.get(WorkflowRunRecord, result["workflow_cycle_id"])
        room = await session.scalar(select(DecisionRoomRecord).where(DecisionRoomRecord.content["workflow_cycle_id"].as_string() == result["workflow_cycle_id"]))
        assert run.status == "WAITING_REVIEW"
        assert room is not None and room.status == "PENDING"