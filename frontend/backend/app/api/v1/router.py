import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from jsonschema import Draft202012Validator
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_daemon_token, require_roles
from app.core.config import settings
from app.core.database import get_session
from app.models import (
    AgentWorkflowRecord,
    BlueprintRecord,
    ChallengeGateRecord,
    DaemonJobRecord,
    DecisionRoomRecord,
    EvidenceRecord,
    FleetAgentRecord,
    FleetOutputRecord,
    MissionRecord,
    PolicyRecord,
    WorkflowStepRecord,
    WorkflowRunRecord,
)
from app.schemas.domain import (
    AssuranceVerdict,
    Blueprint,
    ChallengeGateCreate,
    ChallengeGateDecision,
    ClarifyingAnswers,
    DecisionRequest,
    DaemonHeartbeatRequest,
    EmailDispatchRequest,
    FormSchemaRequest,
    FormSubmissionRequest,
    FleetProposal,
    Mission,
    MissionCreate,
    MissionConstraints,
    ReconciliationApprovalRequest,
    TelemetrySummary,
    ToolHookEvent,
    WorkflowTriggerRequest,
    UserRole,
)
from app.services.architect_pipeline import clarifying_questions, propose_fleet
from app.services.compiler import compute_plan, to_blueprint
from app.services.estate_discovery import estate_summary
from app.services.output_dispatcher import build_form_schema, dispatch_governance_email, dispatch_structured_webhook
from app.services.workflow_runner import execute_agent_cycle

router = APIRouter(prefix="/api/v1")
_REQUIRED_BLUEPRINT_GATES = {"INTAKE", "CLARIFICATION", "ROSTER", "COMPILATION"}


@router.get(
    "/inventory",
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)
async def inventory():
    return await estate_summary()


@router.post(
    "/missions",
    response_model=Mission,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT))],
)
async def create_mission(payload: MissionCreate, session: AsyncSession = Depends(get_session)):
    mission = Mission(
        **payload.model_dump(),
        mission_id=str(uuid4()),
    )
    session.add(
        MissionRecord(
            mission_id=mission.mission_id,
            name=mission.name,
            goal=mission.goal,
            status=mission.status,
            constraints=mission.constraints.model_dump(mode="json"),
            competitive_benchmarking=mission.competitive_benchmarking,
            clarification_answers=mission.clarification_answers,
        )
    )
    await session.commit()
    return mission


@router.get(
    "/missions",
    response_model=list[Mission],
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)
async def list_missions(session: AsyncSession = Depends(get_session)):
    records = await session.scalars(select(MissionRecord).order_by(MissionRecord.created_at.desc()))
    return [
        Mission(
            mission_id=record.mission_id,
            name=record.name,
            goal=record.goal,
            status=record.status,
            constraints=MissionConstraints.model_validate(record.constraints),
            competitive_benchmarking=record.competitive_benchmarking,
            clarification_answers=record.clarification_answers,
        )
        for record in records
    ]


@router.api_route(
    "/missions/{mission_id}/questions",
    methods=["GET", "POST"],
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT))],
)
async def get_questions(mission_id: str, session: AsyncSession = Depends(get_session)):
    record = await session.get(MissionRecord, mission_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission = Mission(
        mission_id=record.mission_id,
        name=record.name,
        goal=record.goal,
        status=record.status,
        constraints=MissionConstraints.model_validate(record.constraints),
        competitive_benchmarking=record.competitive_benchmarking,
        clarification_answers=record.clarification_answers,
    )
    inventory = await estate_summary()
    return await clarifying_questions(mission, inventory)


@router.put(
    "/missions/{mission_id}/answers",
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT))],
)
async def save_clarifying_answers(
    mission_id: str,
    payload: ClarifyingAnswers,
    session: AsyncSession = Depends(get_session),
):
    mission = await session.get(MissionRecord, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission.clarification_answers = payload.answers
    await session.commit()
    return {"mission_id": mission_id, "saved": len(payload.answers)}

import os
import shutil

_UPLOAD_DIR = os.environ.get(
    "FLEET_STUDIO_UPLOAD_DIR",
    "/hermes-uploads" if os.path.exists("/hermes-uploads") else os.path.join(os.environ.get("TEMP", "."), "hermes-uploads"),
)


@router.post(
    "/missions/{mission_id}/stage-document",
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.OPERATOR))],
)
async def stage_document(
    mission_id: str,
    request: Request,
    filename: str = Query(default=""),
    x_filename: str | None = Header(default=None, alias="x-filename"),
):
    """Accept a file upload from the browser and stage it for agent access.

    Writes the file into the shared uploads volume (/hermes-uploads) and returns
    a document_key that the run endpoint passes to the agent as input_document.
    Supports raw body uploads and multipart streams without requiring
    python-multipart at import time.
    """
    import os

    content_type = request.headers.get("content-type", "")
    target_filename = filename or x_filename or "document.docx"

    content = b""
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            file_field = form.get("file")
            if hasattr(file_field, "read"):
                content = await file_field.read()
                if hasattr(file_field, "filename") and file_field.filename:
                    target_filename = file_field.filename
            elif isinstance(file_field, (bytes, str)):
                content = file_field.encode() if isinstance(file_field, str) else file_field
        except Exception:
            content = await request.body()
    else:
        content = await request.body()

    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in target_filename)
    if not safe_name:
        safe_name = "document.docx"

    upload_dir = os.path.join(_UPLOAD_DIR, mission_id)
    os.makedirs(upload_dir, exist_ok=True)
    dest_path = os.path.join(upload_dir, safe_name)

    with open(dest_path, "wb") as fh:
        fh.write(content)

    document_key = f"uploads/{mission_id}/{safe_name}"
    return {"document_key": document_key, "filename": safe_name, "size_bytes": len(content)}



@router.post(
    "/missions/{mission_id}/run",
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.OPERATOR))],
)
async def run_mission(
    mission_id: str,
    payload: dict | None = None,
    session: AsyncSession = Depends(get_session),
):
    import os
    import platform
    import shutil

    mission = await session.get(MissionRecord, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    blueprint_record = await session.scalar(
        select(BlueprintRecord)
        .where(BlueprintRecord.mission_id == mission_id)
        .order_by(BlueprintRecord.version.desc())
    )
    if blueprint_record is None:
        if mission.proposal:
            prop = FleetProposal.model_validate(mission.proposal)
        else:
            prop = await propose_fleet(
                Mission(
                    mission_id=mission.mission_id,
                    name=mission.name,
                    goal=mission.goal,
                    status=mission.status,
                    constraints=MissionConstraints.model_validate(mission.constraints or {}),
                    competitive_benchmarking=mission.competitive_benchmarking,
                    clarification_answers=mission.clarification_answers or {},
                ),
                await estate_summary(),
            )
            mission.proposal = prop.model_dump(mode="json")
        bp = to_blueprint(prop, await estate_summary())
        blueprint_record = BlueprintRecord(
            blueprint_id=bp.blueprint_id,
            mission_id=mission.mission_id,
            version=1,
            specification=bp.model_dump(mode="json"),
        )
        session.add(blueprint_record)
        for agent in bp.agents:
            session.add(
                FleetAgentRecord(
                    agent_id=agent.agent_id,
                    blueprint_id=bp.blueprint_id,
                    name=agent.name,
                    specification=agent.model_dump(mode="json"),
                    applied_specification=agent.model_dump(mode="json"),
                    managed_state="APPLIED",
                )
            )
        mission.status = "READY"
        await session.commit()
    blueprint = Blueprint.model_validate(blueprint_record.specification)
    if not blueprint.agents:
        raise HTTPException(status_code=400, detail="Blueprint has no declared agents")
    first_agent = blueprint.agents[0]

    # ── Resolve the requested input document or target directory ───────────
    raw_doc = (payload or {}).get("input_document") or ""
    target_path = (payload or {}).get("target_path") or ""

    # ── Resolve Hermes home directory (where agents are sandboxed to) ────────
    hermes_home: str = settings.hermes_home or ""
    if not hermes_home:
        if platform.system() == "Windows":
            hermes_home = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")
        else:
            hermes_home = os.path.expanduser("~/.hermes")

    # ── Auto-stage: if target_path or uploaded file or absolute path ─────────
    staged_doc = raw_doc
    if not raw_doc and target_path:
        staged_doc = target_path
    elif raw_doc and raw_doc.startswith("uploads/"):
        rel = raw_doc[len("uploads/"):]
        src = os.path.join(_UPLOAD_DIR, rel)
        if os.path.isfile(src):
            workspace_dir = os.path.join(hermes_home, "workspace")
            os.makedirs(workspace_dir, exist_ok=True)
            filename = os.path.basename(src)
            dest = os.path.join(workspace_dir, filename)
            shutil.copy2(src, dest)
            staged_doc = os.path.join("workspace", filename)
    elif raw_doc and os.path.isabs(raw_doc):
        src = raw_doc
        if os.path.isfile(src):
            workspace_dir = os.path.join(hermes_home, "workspace")
            os.makedirs(workspace_dir, exist_ok=True)
            dest = os.path.join(workspace_dir, os.path.basename(src))
            if not os.path.exists(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
                shutil.copy2(src, dest)
            staged_doc = os.path.join("workspace", os.path.basename(src))
        elif os.path.isdir(src):
            staged_doc = src
    elif not raw_doc and not target_path:
        # Check if clarification answers contain a target log or directory path
        clarif_path = str((mission.clarification_answers or {}).get("source-log-path") or (mission.clarification_answers or {}).get("target_path") or "")
        if clarif_path:
            staged_doc = clarif_path
        else:
            candidate_paths = [
                "/host-downloads/RFP.docx",
                os.path.join(os.path.expanduser("~"), "Downloads", "RFP.docx"),
            ]
            downloads_rfp = next((p for p in candidate_paths if os.path.isfile(p)), None)
            if downloads_rfp:
                workspace_dir = os.path.join(hermes_home, "workspace")
                os.makedirs(workspace_dir, exist_ok=True)
                dest = os.path.join(workspace_dir, "RFP.docx")
                if not os.path.exists(dest) or os.path.getmtime(downloads_rfp) > os.path.getmtime(dest):
                    shutil.copy2(downloads_rfp, dest)
                staged_doc = "workspace/RFP.docx"
            else:
                staged_doc = "workspace"

    trigger_payload = {
        "event_id": f"manual-run-{uuid4().hex[:8]}",
        "source": "fleet-studio-ui",
        "mission_id": mission_id,
        "goal": mission.goal,
        "input_document": staged_doc,
        "target_path": target_path or staged_doc,
    }
    try:
        result = await execute_agent_cycle(first_agent.agent_id, session, trigger_context=trigger_payload)
        return {"status": "SUCCESS", "agent_id": first_agent.agent_id, "agent_name": first_agent.name, "result": result}
    except Exception as error:
        job = DaemonJobRecord(
            job_id=str(uuid4()),
            job_type="RUN_AGENT_CYCLE",
            idempotency_key=f"run:{mission_id}:{uuid4().hex[:8]}",
            status="QUEUED",
            payload={"agent_id": first_agent.agent_id, "trigger_context": trigger_payload},
        )
        session.add(job)
        await session.commit()
        return {"status": "QUEUED", "job_id": job.job_id, "agent_id": first_agent.agent_id, "agent_name": first_agent.name, "detail": str(error)}


@router.delete(
    "/missions/{mission_id}",
    status_code=204,
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT, UserRole.OPERATOR))],
)
async def delete_mission(mission_id: str, session: AsyncSession = Depends(get_session)):
    record = await session.get(MissionRecord, mission_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    # 1. Delete associated challenge gates
    await session.execute(delete(ChallengeGateRecord).where(ChallengeGateRecord.mission_id == mission_id))

    # 2. Delete associated decision rooms
    await session.execute(delete(DecisionRoomRecord).where(DecisionRoomRecord.mission_id == mission_id))

    # 3. Delete blueprints and their nested agent/workflow/run hierarchy
    blueprints = (
        await session.execute(select(BlueprintRecord).where(BlueprintRecord.mission_id == mission_id))
    ).scalars().all()

    for bp in blueprints:
        agents = (
            await session.execute(select(FleetAgentRecord).where(FleetAgentRecord.blueprint_id == bp.blueprint_id))
        ).scalars().all()
        for ag in agents:
            await session.execute(delete(AgentWorkflowRecord).where(AgentWorkflowRecord.agent_id == ag.agent_id))
            runs = (
                await session.execute(select(WorkflowRunRecord).where(WorkflowRunRecord.agent_id == ag.agent_id))
            ).scalars().all()
            for r in runs:
                await session.execute(delete(EvidenceRecord).where(EvidenceRecord.workflow_cycle_id == r.workflow_cycle_id))
                await session.execute(delete(WorkflowStepRecord).where(WorkflowStepRecord.workflow_cycle_id == r.workflow_cycle_id))
            await session.execute(delete(WorkflowRunRecord).where(WorkflowRunRecord.agent_id == ag.agent_id))
            await session.execute(delete(FleetAgentRecord).where(FleetAgentRecord.agent_id == ag.agent_id))

        await session.execute(delete(PolicyRecord).where(PolicyRecord.blueprint_id == bp.blueprint_id))
        await session.execute(delete(BlueprintRecord).where(BlueprintRecord.blueprint_id == bp.blueprint_id))

    await session.delete(record)
    await session.commit()
    return None


@router.post(
    "/missions/{mission_id}/gates",
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT, UserRole.OPERATOR))],
)
async def create_challenge_gate(
    mission_id: str,
    payload: ChallengeGateCreate,
    session: AsyncSession = Depends(get_session),
):
    if await session.get(MissionRecord, mission_id) is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    gate = ChallengeGateRecord(
        gate_id=str(uuid4()),
        mission_id=mission_id,
        stage=payload.stage,
        state="PENDING",
        challenge_snapshot=payload.challenge_snapshot,
    )
    session.add(gate)
    await session.commit()
    return {"gate_id": gate.gate_id, "mission_id": gate.mission_id, "stage": gate.stage, "state": gate.state}


@router.post(
    "/gates/{gate_id}/decision",
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT, UserRole.OPERATOR))],
)
async def decide_challenge_gate(
    gate_id: str,
    payload: ChallengeGateDecision,
    user: dict = Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    gate = await session.get(ChallengeGateRecord, gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail="Challenge gate not found")
    if gate.state != "PENDING":
        raise HTTPException(status_code=409, detail="Challenge gate has already been resolved")
    gate.state = "APPROVED" if payload.decision == "APPROVE" else "RETURNED"
    gate.decision = payload.decision
    gate.feedback = payload.feedback
    gate.actor_id = user.get("name") or user.get("email") or user.get("sub", "unknown")
    gate.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    return {"gate_id": gate_id, "state": gate.state, "actor_id": gate.actor_id}


@router.post(
    "/missions/{mission_id}/proposal",
    response_model=FleetProposal,
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT))],
)
async def create_proposal(mission_id: str, session: AsyncSession = Depends(get_session)):
    record = await session.get(MissionRecord, mission_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission = Mission(
        mission_id=record.mission_id,
        name=record.name,
        goal=record.goal,
        status=record.status,
        constraints=MissionConstraints.model_validate(record.constraints),
        competitive_benchmarking=record.competitive_benchmarking,
        clarification_answers=record.clarification_answers,
    )
    proposal = await propose_fleet(mission, await estate_summary())
    record.proposal = proposal.model_dump(mode="json")
    record.status = "DESIGNING"
    await session.commit()
    return proposal


@router.post(
    "/blueprints",
    response_model=Blueprint,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.FLEET_ARCHITECT))],
)
async def compile_blueprint(proposal: FleetProposal, session: AsyncSession = Depends(get_session)):
    mission = await session.get(MissionRecord, proposal.mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    gates = await session.scalars(
        select(ChallengeGateRecord)
        .where(ChallengeGateRecord.mission_id == proposal.mission_id)
        .order_by(ChallengeGateRecord.created_at.desc())
    )
    latest_by_stage = {}
    for gate in gates:
        latest_by_stage.setdefault(gate.stage, gate)
    missing = _REQUIRED_BLUEPRINT_GATES - latest_by_stage.keys()
    unresolved = [stage for stage in _REQUIRED_BLUEPRINT_GATES if stage in latest_by_stage and latest_by_stage[stage].state != "APPROVED"]
    if missing or unresolved:
        blocked = sorted(missing | set(unresolved))
        raise HTTPException(
            status_code=409,
            detail=f"Blueprint compilation requires approved challenge gates for: {', '.join(blocked)}.",
        )
    try:
        blueprint = to_blueprint(proposal, await estate_summary())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    version = await session.scalar(
        select(func.max(BlueprintRecord.version)).where(BlueprintRecord.mission_id == blueprint.mission_id)
    )
    blueprint = blueprint.model_copy(update={"version": (version or 0) + 1})
    session.add(
        BlueprintRecord(
            blueprint_id=blueprint.blueprint_id,
            mission_id=blueprint.mission_id,
            version=blueprint.version,
            specification=blueprint.model_dump(mode="json"),
        )
    )
    for agent in blueprint.agents:
        record = await session.get(FleetAgentRecord, agent.agent_id)
        agent_spec = agent.model_dump(mode="json")
        if record is None:
            record = FleetAgentRecord(
                agent_id=agent.agent_id,
                blueprint_id=blueprint.blueprint_id,
                name=agent.name,
                specification=agent_spec,
                applied_specification=None,
                managed_state="DECLARED",
            )
            session.add(record)
        else:
            record.blueprint_id = blueprint.blueprint_id
            record.name = agent.name
            record.specification = agent_spec
            if record.managed_state != "APPLIED":
                record.managed_state = "DECLARED"
        workflow = await session.scalar(
            select(AgentWorkflowRecord).where(AgentWorkflowRecord.agent_id == agent.agent_id)
        )
        workflow_spec = {
            "schedule": agent.schedule,
            "upstream_agent_ids": agent.upstream_agent_ids,
            "steps": [step.model_dump(mode="json") for step in agent.workflow_steps],
        }
        if workflow is None:
            session.add(
                AgentWorkflowRecord(
                    workflow_id=str(uuid4()),
                    agent_id=agent.agent_id,
                    trigger_policy=agent.trigger_policy.value,
                    workflow_specification=workflow_spec,
                )
            )
        else:
            workflow.trigger_policy = agent.trigger_policy.value
            workflow.workflow_specification = workflow_spec
    session.add(
        PolicyRecord(
            policy_id=str(uuid4()),
            blueprint_id=blueprint.blueprint_id,
            rules=[rule.model_dump(mode="json") for rule in blueprint.policy],
        )
    )
    mission.status = "READY" if blueprint.state == "READY" else "DESIGNING"
    await session.commit()
    return blueprint


@router.get(
    "/blueprints/{blueprint_id}",
    response_model=Blueprint,
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)
async def get_blueprint(blueprint_id: str, session: AsyncSession = Depends(get_session)):
    record = await session.get(BlueprintRecord, blueprint_id)
    if record is None:
        record = await session.scalar(
            select(BlueprintRecord)
            .where(BlueprintRecord.mission_id == blueprint_id)
            .order_by(BlueprintRecord.version.desc())
        )
    if record is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return Blueprint.model_validate(record.specification)


@router.get("/agents", dependencies=[Depends(require_roles(*tuple(UserRole)))])
async def list_agents(session: AsyncSession = Depends(get_session)):
    subquery = (
        select(
            BlueprintRecord.mission_id,
            func.max(BlueprintRecord.version).label("max_version"),
        )
        .group_by(BlueprintRecord.mission_id)
        .subquery()
    )
    latest_blueprints = (
        select(BlueprintRecord.blueprint_id)
        .join(
            subquery,
            (BlueprintRecord.mission_id == subquery.c.mission_id)
            & (BlueprintRecord.version == subquery.c.max_version),
        )
    )
    results = await session.execute(
        select(FleetAgentRecord, BlueprintRecord.mission_id)
        .join(BlueprintRecord, FleetAgentRecord.blueprint_id == BlueprintRecord.blueprint_id)
        .where(
            FleetAgentRecord.managed_state.in_(["DECLARED", "APPLIED"]),
            BlueprintRecord.blueprint_id.in_(latest_blueprints),
        )
        .order_by(FleetAgentRecord.name)
    )
    return [
        {
            **row.specification,
            "agent_id": row.agent_id,
            "blueprint_id": row.blueprint_id,
            "mission_id": b_mission_id,
            "managed_state": row.managed_state,
            "applied": row.applied_specification is not None,
        }
        for row, b_mission_id in results
    ]


async def _load_plan(blueprint_id: str, session: AsyncSession):
    record = await session.get(BlueprintRecord, blueprint_id)
    if record is None:
        record = await session.scalar(
            select(BlueprintRecord)
            .where(BlueprintRecord.mission_id == blueprint_id)
            .order_by(BlueprintRecord.version.desc())
        )
    if record is None:
        mission = await session.get(MissionRecord, blueprint_id)
        if mission and mission.proposal:
            from app.schemas.domain import FleetProposal
            from app.services.compiler import to_blueprint
            prop = FleetProposal.model_validate(mission.proposal)
            bp = to_blueprint(prop, await estate_summary())
            record = BlueprintRecord(
                blueprint_id=bp.blueprint_id,
                mission_id=mission.mission_id,
                version=1,
                specification=bp.model_dump(mode="json"),
            )
            session.add(record)
            for agent in bp.agents:
                session.add(
                    FleetAgentRecord(
                        agent_id=agent.agent_id,
                        blueprint_id=bp.blueprint_id,
                        name=agent.name,
                        specification=agent.model_dump(mode="json"),
                        applied_specification=None,
                        managed_state="DECLARED",
                    )
                )
            mission.status = "READY"
            await session.commit()
    if record is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    inventory = await estate_summary()
    if not inventory.connected:
        raise HTTPException(
            status_code=503,
            detail="Live planning requires a connected Hermes estate.",
        )
    blueprint = Blueprint.model_validate(record.specification)
    agent_rows = await session.scalars(
        select(FleetAgentRecord)
        .join(BlueprintRecord, FleetAgentRecord.blueprint_id == BlueprintRecord.blueprint_id)
        .where(BlueprintRecord.mission_id == record.mission_id)
    )
    live_agents = {
        agent.agent_id: {
            "managed_by": "fleet-studio",
            "managed_state": agent.managed_state,
            "specification": agent.applied_specification or {},
        }
        for agent in agent_rows
        if agent.managed_state in {"APPLIED", "REMOVED"}
    }
    return compute_plan(blueprint, live_agents)


@router.post(
    "/blueprints/{blueprint_id}/plan",
    dependencies=[Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.OPERATOR))],
)
async def get_plan(blueprint_id: str, session: AsyncSession = Depends(get_session)):
    return await _load_plan(blueprint_id, session)


@router.post("/blueprints/{blueprint_id}/apply")
async def apply_blueprint(
    blueprint_id: str,
    payload: ReconciliationApprovalRequest,
    user: dict = Depends(require_roles(UserRole.PLATFORM_ENGINEER, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    blueprint_record = await session.get(BlueprintRecord, blueprint_id)
    if blueprint_record is None:
        blueprint_record = await session.scalar(
            select(BlueprintRecord)
            .where(BlueprintRecord.mission_id == blueprint_id)
            .order_by(BlueprintRecord.version.desc())
        )
    if blueprint_record is None:
        mission = await session.get(MissionRecord, blueprint_id)
        if mission and mission.proposal:
            from app.schemas.domain import FleetProposal
            from app.services.compiler import to_blueprint
            prop = FleetProposal.model_validate(mission.proposal)
            bp = to_blueprint(prop, await estate_summary())
            blueprint_record = BlueprintRecord(
                blueprint_id=bp.blueprint_id,
                mission_id=mission.mission_id,
                version=1,
                specification=bp.model_dump(mode="json"),
            )
            session.add(blueprint_record)
            for agent in bp.agents:
                session.add(
                    FleetAgentRecord(
                        agent_id=agent.agent_id,
                        blueprint_id=bp.blueprint_id,
                        name=agent.name,
                        specification=agent.model_dump(mode="json"),
                        applied_specification=None,
                        managed_state="DECLARED",
                    )
                )
            mission.status = "READY"
            await session.commit()
    if blueprint_record is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    blueprint = Blueprint.model_validate(blueprint_record.specification)
    if blueprint.state != "READY" and any(agent.capability_gaps for agent in blueprint.agents):
        raise HTTPException(status_code=409, detail="Blueprint has unresolved capability gaps.")
    plan = await _load_plan(blueprint_id, session)

    if plan.changes:
        if not payload.confirm_changes:
            raise HTTPException(status_code=409, detail="Reconciliation requires explicit human confirmation.")
        if any(change.action.value == "REMOVE" for change in plan.changes) and not payload.confirm_removals:
            raise HTTPException(status_code=409, detail="Agent removals require separate confirmation.")
        if any(change.action.value == "APPROVAL_REQUIRED" for change in plan.changes) and not (payload.confirm_external_actions or payload.confirm_changes):
            raise HTTPException(status_code=409, detail="External or mutating actions require approval.")

    mission = await session.get(MissionRecord, blueprint.mission_id)
    if mission:
        mission.status = "READY"
    for agent_spec in blueprint.agents:
        agent_row = await session.get(FleetAgentRecord, agent_spec.agent_id)
        if agent_row is not None:
            agent_row.applied_specification = agent_spec.model_dump(mode="json")
            agent_row.managed_state = "APPLIED"

    now = datetime.now(timezone.utc)
    if plan.changes:
        session.add(
            ChallengeGateRecord(
                gate_id=str(uuid4()),
                mission_id=blueprint.mission_id,
                stage="RECONCILIATION",
                state="APPROVED",
                challenge_snapshot={"blueprint_id": blueprint_record.blueprint_id, "changes": [change.model_dump(mode="json") for change in plan.changes]},
                decision="APPROVE",
                feedback="Reconciliation explicitly approved.",
                actor_id=user.get("name") or user.get("email") or user.get("sub", "unknown"),
                created_at=now,
                resolved_at=now,
            )
        )
        job = DaemonJobRecord(
            job_id=str(uuid4()),
            job_type="RECONCILE_BLUEPRINT",
            status="QUEUED",
            payload={
                "blueprint": blueprint.model_dump(mode="json"),
                "changes": [change.model_dump(mode="json") for change in plan.changes],
            },
        )
        session.add(job)
        await session.commit()
        return {"status": "QUEUED", "job_id": job.job_id, "plan": plan}
    else:
        await session.commit()
        return {"status": "IN_SYNC", "job_id": None, "plan": plan}


@router.get("/rooms", dependencies=[Depends(require_roles(*tuple(UserRole)))])
async def list_rooms(session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(select(DecisionRoomRecord).order_by(DecisionRoomRecord.created_at.desc()))
    return [
        {
            "room_id": row.room_id,
            "title": row.title,
            "agent": row.content.get("agent_name", row.agent_id),
            "fleet_id": row.fleet_id,
            "basis": row.epistemic_basis,
            "verdict": row.assurance_verdict,
            "status": row.status,
            "summary": row.content.get("summary", ""),
            "evidence": row.content,
            "created_at": row.created_at,
            "decided_by": row.decided_by,
            "decision_note": row.decision_note,
        }
        for row in rows
    ]


@router.post(
    "/rooms/{room_id}/decision",
    dependencies=[Depends(require_roles(UserRole.APPROVER, UserRole.COMPLIANCE_OFFICER))],
)
async def decide_room(
    room_id: str,
    payload: DecisionRequest,
    user: dict = Depends(require_roles(UserRole.APPROVER, UserRole.COMPLIANCE_OFFICER)),
    session: AsyncSession = Depends(get_session),
):
    room = await session.scalar(
        select(DecisionRoomRecord).where(DecisionRoomRecord.room_id == room_id).with_for_update()
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Decision Room not found")
    if room.status != "PENDING":
        raise HTTPException(status_code=409, detail="Decision Room has already been resolved.")
    room.status = payload.decision
    room.decided_by = user.get("name") or user.get("email") or user.get("sub", "unknown")
    room.decision_note = payload.note
    room.resolved_at = datetime.now(timezone.utc)
    resume_job_id = None
    workflow_cycle_id = room.content.get("workflow_cycle_id")
    step_id = room.content.get("step_id")
    if workflow_cycle_id and step_id:
        run = await session.get(WorkflowRunRecord, workflow_cycle_id)
        step_run = await session.scalar(
            select(WorkflowStepRecord).where(
                WorkflowStepRecord.workflow_cycle_id == workflow_cycle_id,
                WorkflowStepRecord.step_id == step_id,
            )
        )
        if run is not None and step_run is not None and run.status == "WAITING_REVIEW":
            if payload.decision == "APPROVE":
                run.status = "RUNNING"
                step_run.status = "RUNNING"
                idempotency_key = f"resume:{workflow_cycle_id}:{step_id}"
                resume_job = await session.scalar(
                    select(DaemonJobRecord).where(DaemonJobRecord.idempotency_key == idempotency_key)
                )
                if resume_job is None:
                    resume_job = DaemonJobRecord(
                        job_id=str(uuid4()),
                        job_type="RUN_AGENT_CYCLE",
                        idempotency_key=idempotency_key,
                        status="QUEUED",
                        payload={
                            "agent_id": run.agent_id,
                            "trigger_context": {
                                **(run.trigger_context or {}),
                                "resume_workflow_cycle_id": workflow_cycle_id,
                                "resume_step_id": step_id,
                                "event_id": idempotency_key,
                            },
                        },
                    )
                    session.add(resume_job)
                resume_job_id = resume_job.job_id
            else:
                run.status = "POLICY_BLOCKED"
                run.completed_at = room.resolved_at
                step_run.status = "POLICY_BLOCKED"
                step_run.completed_at = room.resolved_at
    await session.commit()
    return {
        "room_id": room.room_id,
        "status": room.status,
        "decided_by": room.decided_by,
        "resume_job_id": resume_job_id,
    }


@router.get(
    "/telemetry",
    response_model=TelemetrySummary,
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)
async def telemetry(session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    active_fleets = await session.scalar(
        select(func.count()).select_from(MissionRecord).where(MissionRecord.status == "READY")
    )
    active_agents = await session.scalar(
        select(func.count()).select_from(FleetAgentRecord).where(FleetAgentRecord.managed_state == "APPLIED")
    )
    cycles = await session.scalar(
        select(func.count()).select_from(WorkflowRunRecord).where(WorkflowRunRecord.started_at >= day_ago)
    )
    cycles_7d = await session.scalar(
        select(func.count()).select_from(WorkflowRunRecord).where(WorkflowRunRecord.started_at >= week_ago)
    )
    pending_rooms = await session.scalar(
        select(func.count()).select_from(DecisionRoomRecord).where(DecisionRoomRecord.status == "PENDING")
    )
    pending_gates = await session.scalar(
        select(func.count()).select_from(ChallengeGateRecord).where(ChallengeGateRecord.state == "PENDING")
    )
    policy_blocks = await session.scalar(
        select(func.count())
        .select_from(EvidenceRecord)
        .join(WorkflowRunRecord, EvidenceRecord.workflow_cycle_id == WorkflowRunRecord.workflow_cycle_id)
        .where(
            WorkflowRunRecord.started_at >= day_ago,
            EvidenceRecord.assurance_verdict == AssuranceVerdict.POLICY_BLOCKED.value,
        )
    )
    verdict_rows = await session.execute(
        select(EvidenceRecord.assurance_verdict, func.count()).group_by(EvidenceRecord.assurance_verdict)
    )
    verdict_counts = {str(verdict): count for verdict, count in verdict_rows if verdict}
    runs = await session.scalars(
        select(WorkflowRunRecord).where(
            WorkflowRunRecord.started_at >= day_ago,
            WorkflowRunRecord.completed_at.is_not(None),
        )
    )
    durations = [
        (run.completed_at - run.started_at).total_seconds()
        for run in runs
        if run.completed_at and run.started_at
    ]
    step_runs = await session.scalars(
        select(WorkflowStepRecord).where(
            WorkflowStepRecord.started_at >= day_ago,
            WorkflowStepRecord.completed_at.is_not(None),
        )
    )
    step_durations = [
        (step.completed_at - step.started_at).total_seconds()
        for step in step_runs
        if step.completed_at and step.started_at
    ]
    capability_counts: dict[str, int] = {}
    for step in await session.scalars(select(WorkflowStepRecord).where(WorkflowStepRecord.started_at >= day_ago)):
        capability_counts[step.capability_id] = capability_counts.get(step.capability_id, 0) + 1
    resolved_gates = await session.scalars(
        select(ChallengeGateRecord).where(
            ChallengeGateRecord.resolved_at.is_not(None),
            ChallengeGateRecord.created_at >= day_ago,
        )
    )
    challenge_durations = [
        (gate.resolved_at - gate.created_at).total_seconds()
        for gate in resolved_gates
        if gate.resolved_at and gate.created_at
    ]
    completed_jobs = await session.scalars(
        select(DaemonJobRecord).where(
            DaemonJobRecord.job_type == "RECONCILE_BLUEPRINT",
            DaemonJobRecord.status == "SUCCEEDED",
            DaemonJobRecord.completed_at.is_not(None),
            DaemonJobRecord.created_at >= day_ago,
        )
    )
    reconciliation_durations = [
        (job.completed_at - job.created_at).total_seconds()
        for job in completed_jobs
        if job.completed_at and job.created_at
    ]
    applied_agents = await session.scalars(
        select(FleetAgentRecord).where(FleetAgentRecord.managed_state == "APPLIED")
    )
    model_distribution: dict[str, int] = {}
    for agent in applied_agents:
        llm = (agent.applied_specification or {}).get("assigned_llm") or {}
        family, version = llm.get("family"), llm.get("version")
        if family and version:
            label = f"{family} · {version}"
            model_distribution[label] = model_distribution.get(label, 0) + 1
    buckets = {}
    first_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    for offset in range(24):
        hour = first_hour + timedelta(hours=offset)
        label = hour.strftime("%m-%d %H")
        buckets[label] = {"time": hour.strftime("%H"), "cycles": 0, "gates": 0}
    for run in await session.scalars(
        select(WorkflowRunRecord).where(WorkflowRunRecord.started_at >= first_hour)
    ):
        if run.started_at:
            label = run.started_at.strftime("%m-%d %H")
            if label in buckets:
                buckets[label]["cycles"] += 1
    for gate in await session.scalars(
        select(ChallengeGateRecord).where(ChallengeGateRecord.created_at >= first_hour)
    ):
        if gate.created_at:
            label = gate.created_at.strftime("%m-%d %H")
            if label in buckets:
                buckets[label]["gates"] += 1
    budget_burn = await session.scalar(
        select(func.coalesce(func.sum(WorkflowRunRecord.usage_usd), 0)).where(
            WorkflowRunRecord.started_at >= day_ago
        )
    )
    verdicts = {
        verdict: verdict_counts.get(verdict.value, 0)
        for verdict in AssuranceVerdict
    }
    return TelemetrySummary(
        active_fleets=active_fleets or 0,
        active_agents=active_agents or 0,
        workflow_cycles_24h=cycles or 0,
        workflow_cycles_7d=cycles_7d or 0,
        pending_challenge_gates=(pending_rooms or 0) + (pending_gates or 0),
        policy_blocks_24h=policy_blocks or 0,
        avg_cycle_duration_seconds=sum(durations) / len(durations) if durations else 0,
        avg_step_execution_latency_seconds=sum(step_durations) / len(step_durations) if step_durations else 0,
        avg_challenge_turnaround_seconds=sum(challenge_durations) / len(challenge_durations) if challenge_durations else 0,
        avg_reconciliation_seconds=sum(reconciliation_durations) / len(reconciliation_durations) if reconciliation_durations else 0,
        daily_budget_burn_usd=float(budget_burn or 0),
        assurance_verdicts=verdicts,
        hourly_cycles=list(buckets.values()),
        model_distribution=model_distribution,
        skill_tool_utilization=capability_counts,
    )


@router.get("/daemon/jobs", dependencies=[Depends(require_daemon_token)])
async def poll_daemon_jobs(
    wait: int = Query(default=25, ge=0, le=30),
    worker_id: str = Header(alias="X-Fleet-Daemon-Id", min_length=1, max_length=120),
    session: AsyncSession = Depends(get_session),
):
    deadline = asyncio.get_running_loop().time() + wait
    while True:
        stale_before = datetime.now(timezone.utc) - timedelta(seconds=90)
        job = await session.scalar(
            select(DaemonJobRecord)
            .where(
                or_(
                    DaemonJobRecord.status == "QUEUED",
                    and_(
                        DaemonJobRecord.status == "RUNNING",
                        or_(DaemonJobRecord.heartbeat_at.is_(None), DaemonJobRecord.heartbeat_at < stale_before),
                    ),
                )
            )
            .order_by(DaemonJobRecord.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is not None:
            if job.status == "RUNNING":
                job.last_error = "Reclaimed after daemon heartbeat lease expiry."
            job.status = "RUNNING"
            job.claimed_by = worker_id
            job.claimed_at = datetime.now(timezone.utc)
            job.heartbeat_at = job.claimed_at
            await session.commit()
            return {"jobs": [{"job_id": job.job_id, "job_type": job.job_type, "payload": job.payload}]}
        await session.rollback()
        if asyncio.get_running_loop().time() >= deadline:
            return {"jobs": []}
        await asyncio.sleep(min(1, max(0, deadline - asyncio.get_running_loop().time())))


@router.get("/daemon/agents", dependencies=[Depends(require_daemon_token)])
async def list_applied_agents(session: AsyncSession = Depends(get_session)):
    records = await session.scalars(
        select(FleetAgentRecord)
        .where(FleetAgentRecord.managed_state == "APPLIED", FleetAgentRecord.applied_specification.is_not(None))
    )
    return {"agents": [record.applied_specification for record in records]}


@router.post("/daemon/jobs/{job_id}/heartbeat", dependencies=[Depends(require_daemon_token)])
async def daemon_heartbeat(
    job_id: str,
    payload: DaemonHeartbeatRequest,
    worker_id: str = Header(alias="X-Fleet-Daemon-Id", min_length=1, max_length=120),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(DaemonJobRecord, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Daemon job not found")
    if job.claimed_by != worker_id:
        raise HTTPException(status_code=403, detail="Daemon does not own this job")
    job.status = payload.status
    job.heartbeat_at = datetime.now(timezone.utc)
    job.last_error = payload.last_error
    if payload.status in {"SUCCEEDED", "FAILED"}:
        job.completed_at = job.heartbeat_at
    if payload.status == "SUCCEEDED" and job.job_type == "RECONCILE_BLUEPRINT":
        blueprint_payload = job.payload.get("blueprint", {})
        for agent_data in blueprint_payload.get("agents", []):
            agent = await session.get(FleetAgentRecord, agent_data.get("agent_id"))
            if agent is not None:
                agent.applied_specification = agent_data
                agent.managed_state = "APPLIED"
        removed = {
            change.get("target")
            for change in job.payload.get("changes", [])
            if change.get("action") == "REMOVE"
        }
        for agent_id in removed:
            agent = await session.get(FleetAgentRecord, agent_id)
            if agent is not None:
                agent.applied_specification = None
                agent.managed_state = "REMOVED"
    await session.commit()
    return {"job_id": job_id, "accepted": True, "status": job.status}


@router.post("/daemon/tool-policy", dependencies=[Depends(require_daemon_token)])
async def daemon_tool_policy(event: ToolHookEvent, session: AsyncSession = Depends(get_session)):
    run = await session.scalar(
        select(WorkflowRunRecord)
        .where(WorkflowRunRecord.hermes_session_id == event.session_id)
        .order_by(WorkflowRunRecord.started_at.desc())
        .limit(1)
    )
    if run is None:
        return {"decision": "PASS_UNMANAGED"}
    if run.status != "RUNNING":
        return {"decision": "BLOCK", "reason": "Managed workflow cycle is not active."}
    agent = await session.get(FleetAgentRecord, run.agent_id)
    if agent is None or agent.managed_state != "APPLIED" or agent.applied_specification is None:
        raise HTTPException(status_code=403, detail="Managed agent has no applied policy.")

    allowed_tools = set(agent.applied_specification.get("bound_tools", []))
    allowed = event.tool_name in allowed_tools
    policy = await session.scalar(select(PolicyRecord).where(PolicyRecord.blueprint_id == agent.blueprint_id))
    policy_rule = next(
        (rule for rule in (policy.rules if policy else []) if rule.get("capability_id") == event.tool_name),
        None,
    )
    requires_approval = bool(policy_rule and policy_rule.get("requires_approval"))
    blueprint = await session.get(BlueprintRecord, agent.blueprint_id)
    fleet_id = blueprint.mission_id if blueprint else agent.blueprint_id
    step = await session.scalar(
        select(WorkflowStepRecord)
        .where(
            WorkflowStepRecord.workflow_cycle_id == run.workflow_cycle_id,
            WorkflowStepRecord.status == "RUNNING",
        )
        .order_by(WorkflowStepRecord.started_at.desc())
        .limit(1)
    )
    step_id = step.step_id if step else f"tool:{event.tool_name}"
    evidence_id = str(uuid4())
    evidence_content = {
        "event": event.hook_event_name,
        "tool_id": event.tool_name,
        "decision": "BLOCK" if not allowed else "PAUSE_FOR_APPROVAL" if requires_approval else "ALLOW",
        "parameters_redacted": True,
    }

    if event.hook_event_name == "pre_tool_call" and (not allowed or requires_approval):
        if not allowed:
            verdict = AssuranceVerdict.POLICY_BLOCKED.value
            decision_room_id = None
        else:
            verdict = AssuranceVerdict.NOT_VERIFIABLE.value
            decision_room_id = str(uuid4())
            session.add(
                DecisionRoomRecord(
                    room_id=decision_room_id,
                    mission_id=blueprint.mission_id if blueprint else None,
                    fleet_id=fleet_id,
                    agent_id=agent.agent_id,
                    title=f"Approval required: {event.tool_name}",
                    status="PENDING",
                    epistemic_basis="SOURCE",
                    assurance_verdict=verdict,
                    content={
                        "summary": "A runtime tool call is paused for human approval.",
                        "tool_id": event.tool_name,
                        "workflow_cycle_id": run.workflow_cycle_id,
                        "parameters_redacted": True,
                        "agent_name": agent.name,
                    },
                )
            )
        session.add(
            EvidenceRecord(
                evidence_id=evidence_id,
                fleet_id=fleet_id,
                workflow_cycle_id=run.workflow_cycle_id,
                agent_id=agent.agent_id,
                step_id=step_id,
                epistemic_basis="SOURCE",
                content=evidence_content,
                assurance_verdict=verdict,
            )
        )
        await session.commit()
        if decision_room_id:
            return {"decision": "PAUSE_FOR_APPROVAL", "room_id": decision_room_id}
        return {"decision": "BLOCK", "reason": "Tool is outside the compiled agent allowlist."}

    if event.hook_event_name == "pre_tool_call" and allowed:
        return {"decision": "ALLOW"}

    session.add(
        EvidenceRecord(
            evidence_id=evidence_id,
            fleet_id=fleet_id,
            workflow_cycle_id=run.workflow_cycle_id,
            agent_id=agent.agent_id,
            step_id=step_id,
            epistemic_basis="SOURCE",
            content=evidence_content,
            assurance_verdict=None,
        )
    )
    await session.commit()
    return {"decision": "RECORDED"}


@router.get("/daemon/decision-rooms/{room_id}", dependencies=[Depends(require_daemon_token)])
async def poll_runtime_decision_room(room_id: str, session: AsyncSession = Depends(get_session)):
    room = await session.get(DecisionRoomRecord, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Decision Room not found")
    return {"room_id": room_id, "status": room.status, "decision_note": room.decision_note}


@router.post("/daemon/workflow-cycles/{agent_id}", dependencies=[Depends(require_daemon_token)])
async def run_agent_workflow_cycle(
    agent_id: str,
    trigger: WorkflowTriggerRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    try:
        return await execute_agent_cycle(agent_id, session, trigger_context=trigger.model_dump(mode="json") if trigger else {})
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/daemon/agents/{agent_id}/trigger", dependencies=[Depends(require_daemon_token)])
async def trigger_agent_workflow(
    agent_id: str,
    payload: WorkflowTriggerRequest,
    session: AsyncSession = Depends(get_session),
):
    agent = await session.get(FleetAgentRecord, agent_id)
    if agent is None or agent.managed_state != "APPLIED" or agent.applied_specification is None:
        raise HTTPException(status_code=404, detail="Applied agent not found")
    workflow = await session.scalar(
        select(AgentWorkflowRecord).where(AgentWorkflowRecord.agent_id == agent_id)
    )
    trigger_kind = workflow.trigger_policy if workflow else ""
    if trigger_kind not in {"EVENT_DRIVEN", "WEBHOOK"}:
        raise HTTPException(status_code=409, detail="Agent is not configured for event or webhook triggers.")
    expected_upstreams = set((workflow.workflow_specification or {}).get("upstream_agent_ids", [])) if workflow else set()
    if trigger_kind == "EVENT_DRIVEN" and payload.source_agent_id not in expected_upstreams:
        raise HTTPException(status_code=403, detail="Event source is not an approved upstream agent.")
    key = f"trigger:{agent_id}:{payload.event_id}"
    existing = await session.scalar(select(DaemonJobRecord).where(DaemonJobRecord.idempotency_key == key))
    if existing is not None:
        return {"job_id": existing.job_id, "status": existing.status, "duplicate": True}
    job = DaemonJobRecord(
        job_id=str(uuid4()),
        job_type="RUN_AGENT_CYCLE",
        idempotency_key=key,
        status="QUEUED",
        payload={"agent_id": agent_id, "trigger_context": payload.model_dump(mode="json")},
    )
    session.add(job)
    await session.commit()
    return {"job_id": job.job_id, "status": job.status, "duplicate": False}


@router.post("/webhooks/{agent_id}")
async def receive_agent_webhook(
    agent_id: str,
    request: Request,
    signature: str | None = Header(default=None, alias="X-Fleet-Webhook-Signature"),
    session: AsyncSession = Depends(get_session),
):
    if not settings.webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook trigger secret is not configured.")
    if not signature:
        raise HTTPException(status_code=401, detail="Webhook signature is required.")
    try:
        parts = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
        timestamp = int(parts["t"])
        provided = parts["v1"]
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Webhook signature format is invalid.") from None
    if abs(int(time.time()) - timestamp) > 300:
        raise HTTPException(status_code=401, detail="Webhook timestamp is outside the allowed window.")
    raw_body = await request.body()
    expected = hmac.new(
        settings.webhook_secret.encode(),
        str(timestamp).encode() + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Webhook signature is invalid.")
    try:
        payload = WorkflowTriggerRequest.model_validate(json.loads(raw_body))
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Webhook payload is invalid.") from error
    agent = await session.get(FleetAgentRecord, agent_id)
    if agent is None or agent.managed_state != "APPLIED":
        raise HTTPException(status_code=404, detail="Applied agent not found")
    workflow = await session.scalar(select(AgentWorkflowRecord).where(AgentWorkflowRecord.agent_id == agent_id))
    if workflow is None or workflow.trigger_policy != "WEBHOOK":
        raise HTTPException(status_code=409, detail="Agent is not configured for webhook triggers.")
    key = f"webhook:{agent_id}:{payload.event_id}"
    existing = await session.scalar(select(DaemonJobRecord).where(DaemonJobRecord.idempotency_key == key))
    if existing is not None:
        return {"job_id": existing.job_id, "status": existing.status, "duplicate": True}
    job = DaemonJobRecord(
        job_id=str(uuid4()),
        job_type="RUN_AGENT_CYCLE",
        idempotency_key=key,
        status="QUEUED",
        payload={"agent_id": agent_id, "trigger_context": payload.model_dump(mode="json")},
    )
    session.add(job)
    await session.commit()
    return {"job_id": job.job_id, "status": job.status, "duplicate": False}


@router.post(
    "/outputs/form-schema",
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)
async def form_schema(payload: FormSchemaRequest):
    try:
        return build_form_schema(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/rooms/{room_id}/form-schema",
    dependencies=[Depends(require_roles(UserRole.APPROVER, UserRole.COMPLIANCE_OFFICER))],
)
async def room_form_schema(room_id: str, session: AsyncSession = Depends(get_session)):
    room = await session.get(DecisionRoomRecord, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Decision Room not found")
    if room.status != "APPROVE":
        raise HTTPException(status_code=409, detail="Output forms are available only after an approved disposition.")
    schema = room.content.get("form_schema")
    if schema is None:
        schema = build_form_schema(
            FormSchemaRequest(
                title=f"Follow-up for {room.title}",
                properties={
                    "follow_up_action": {"type": "string", "enum": ["NOTIFY", "CREATE_TICKET", "NO_ACTION"]},
                    "note": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "owner": {"type": "string", "maxLength": 240},
                },
                required=["follow_up_action", "note"],
            )
        )
        room.content = {**room.content, "form_schema": schema}
        await session.commit()
    return schema


@router.post(
    "/rooms/{room_id}/form-response",
    dependencies=[Depends(require_roles(UserRole.APPROVER, UserRole.COMPLIANCE_OFFICER))],
)
async def submit_room_form(room_id: str, payload: FormSubmissionRequest, session: AsyncSession = Depends(get_session)):
    room = await session.get(DecisionRoomRecord, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Decision Room not found")
    if room.status != "APPROVE" or not room.decided_by:
        raise HTTPException(status_code=409, detail="Form dispatch requires an approved Decision Room.")
    if room.form_dispatch_status in {"SENDING", "SENT"}:
        raise HTTPException(status_code=409, detail="Form output is already being dispatched or has been sent.")
    schema = room.content.get("form_schema")
    if schema is None:
        raise HTTPException(status_code=409, detail="Fetch the Decision Room form schema before submitting.")
    errors = sorted(Draft202012Validator(schema).iter_errors(payload.values), key=lambda error: list(error.path))
    if errors:
        raise HTTPException(
            status_code=422,
            detail=[{"path": list(error.path), "message": error.message} for error in errors[:20]],
        )
    if room.content.get("form_response_dispatched"):
        raise HTTPException(status_code=409, detail="A form response has already been dispatched for this room.")
    outbound = {
        "room_id": room.room_id,
        "mission_id": room.mission_id,
        "fleet_id": room.fleet_id,
        "agent_id": room.agent_id,
        "decision": room.status,
        "approver": room.decided_by,
        "values": payload.values,
    }
    room.form_dispatch_status = "SENDING"
    await session.commit()
    try:
        await dispatch_structured_webhook(outbound, idempotency_key=f"room-form:{room_id}")
    except RuntimeError as error:
        room.form_dispatch_status = "FAILED"
        await session.commit()
        raise HTTPException(status_code=503, detail=str(error)) from error
    room.form_dispatch_status = "SENT"
    room.content = {**room.content, "form_response_dispatched": True, "form_response": payload.values}
    await session.commit()
    return {"status": "dispatched", "room_id": room_id}


@router.post(
    "/outputs/email",
    dependencies=[Depends(require_roles(UserRole.APPROVER, UserRole.COMPLIANCE_OFFICER))],
)
async def dispatch_email(
    payload: EmailDispatchRequest,
    session: AsyncSession = Depends(get_session),
):
    room = await session.scalar(
        select(DecisionRoomRecord).where(DecisionRoomRecord.room_id == payload.room_id).with_for_update()
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Decision Room not found")
    if room.status != "APPROVE" or not room.decided_by:
        raise HTTPException(status_code=409, detail="Email dispatch requires an approved Decision Room.")
    if room.email_dispatch_status in {"SENDING", "SENT"}:
        raise HTTPException(status_code=409, detail="Governance email is already being sent or has been sent.")
    evidence = await session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.workflow_cycle_id == room.content.get("workflow_cycle_id", ""))
    )
    evidence_references = [record.evidence_id for record in evidence]
    room.email_dispatch_status = "SENDING"
    await session.commit()
    try:
        await dispatch_governance_email(
            payload,
            approver=room.decided_by,
            decision=room.status,
            summary=room.content.get("summary", ""),
            evidence_references=evidence_references,
        )
    except RuntimeError as error:
        room.email_dispatch_status = "FAILED"
        await session.commit()
        raise HTTPException(status_code=503, detail=str(error)) from error
    room.email_dispatch_status = "SENT"
    await session.commit()
    return {"status": "sent", "recipient": payload.recipient, "evidence_redacted": True}


# ----------------------------------------------------------------------------- Fleet outputs (Deliverables & Results)


@router.get("/outputs")
async def list_outputs(
    mission_id: str | None = None,
    kind: str | None = None,
    query: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(FleetOutputRecord).order_by(FleetOutputRecord.created_at.desc())
    if mission_id:
        stmt = stmt.where(FleetOutputRecord.mission_id == mission_id)
    if kind:
        stmt = stmt.where(FleetOutputRecord.kind == kind)
    stmt = stmt.limit(max(1, min(limit, 500)))
    records = list(await session.scalars(stmt))

    result = []
    for r in records:
        if query:
            q = query.lower()
            if q not in r.name.lower() and q not in (r.case_name or "").lower() and q not in (r.produced_by or "").lower():
                continue
        snippet = (r.text or "")[:300] + ("..." if len(r.text or "") > 300 else "")
        result.append({
            "id": r.output_id,
            "output_id": r.output_id,
            "name": r.name,
            "kind": r.kind,
            "classification": r.classification,
            "produced_by": r.produced_by,
            "case_name": r.case_name,
            "case": r.case_name,
            "mission_id": r.mission_id,
            "workflow_cycle_id": r.workflow_cycle_id,
            "agent_id": r.agent_id,
            "size_bytes": r.size_bytes or len(r.text or ""),
            "size": r.size_bytes or len(r.text or ""),
            "text": r.text or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "at": r.created_at.isoformat() if r.created_at else None,
            "snippet": snippet,
            "source": r.source or {},
            "provenance": f"{r.produced_by} produced it for {r.case_name or 'Mission'}",
        })
    return result


@router.get("/outputs/{output_id}")
async def get_output(
    output_id: str,
    session: AsyncSession = Depends(get_session),
):
    record = await session.get(FleetOutputRecord, output_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Fleet output not found.")
    return {
        "id": record.output_id,
        "output_id": record.output_id,
        "name": record.name,
        "kind": record.kind,
        "classification": record.classification,
        "produced_by": record.produced_by,
        "case_name": record.case_name,
        "case": record.case_name,
        "mission_id": record.mission_id,
        "workflow_cycle_id": record.workflow_cycle_id,
        "agent_id": record.agent_id,
        "size_bytes": record.size_bytes or len(record.text or ""),
        "size": record.size_bytes or len(record.text or ""),
        "text": record.text or "",
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "at": record.created_at.isoformat() if record.created_at else None,
        "source": record.source or {},
        "provenance": f"{record.produced_by} produced it for {record.case_name or 'Mission'}",
    }


@router.delete("/outputs/{output_id}")
async def delete_output(
    output_id: str,
    session: AsyncSession = Depends(get_session),
):
    record = await session.get(FleetOutputRecord, output_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Fleet output not found.")
    await session.delete(record)
    await session.commit()
    return {"ok": True, "output_id": output_id}


@router.post("/outputs")
async def create_output(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    output_id = payload.get("output_id") or str(uuid4())
    text = payload.get("text") or ""
    record = FleetOutputRecord(
        output_id=output_id,
        mission_id=payload.get("mission_id"),
        workflow_cycle_id=payload.get("workflow_cycle_id"),
        agent_id=payload.get("agent_id"),
        name=payload.get("name", "Generated Deliverable"),
        kind=payload.get("kind", "markdown"),
        classification=payload.get("classification", "confidential"),
        produced_by=payload.get("produced_by", "Fleet Agent"),
        case_name=payload.get("case_name") or payload.get("case"),
        text=text,
        size_bytes=len(text.encode("utf-8")),
        source=payload.get("source") or {"kind": "manual_entry"},
    )
    session.add(record)
    await session.commit()
    return {"ok": True, "output_id": output_id}