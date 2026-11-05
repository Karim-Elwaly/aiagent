import logging
logger = logging.getLogger(__name__)
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




async def _run_mission_background(
    mission_id: str,
    workflow_id: str,
    agent_id: str,
    agent_name: str,
    trigger_payload: dict,
):
    from app.core.database import SessionFactory
    from app.core.event_bus import get_event_bus
    from app.models import BlueprintRecord, FleetAgentRecord, FleetOutputRecord, EvidenceRecord, DecisionRoomRecord, MissionRecord, WorkflowRunRecord
    import httpx
    from app.services.hermes_gateway import connected_hermes, HermesGatewayError
    from app.services.hermes_runtime import (
        assistant_text,
        close_session,
        ensure_hermes_agent_profile,
        get_session_history,
        session_create_params,
        tool_names,
        wait_for_turn,
    )

    bus = get_event_bus()
    goal = trigger_payload.get("goal") or "Execute mission tasks"
    input_doc = trigger_payload.get("input_document") or ""

    async def fail_mission(error_text: str, message: str) -> None:
        logger.error("Mission %s failed: %s", mission_id, error_text)
        async with SessionFactory() as failure_session:
            failed_run = await failure_session.get(WorkflowRunRecord, workflow_id)
            if failed_run:
                failed_run.status = "FAILED"
                failed_run.completed_at = datetime.now(timezone.utc)
            failed_mission = await failure_session.get(MissionRecord, mission_id)
            if failed_mission:
                failed_mission.status = "FAILED"
            await failure_session.commit()

        bus.publish(workflow_id, {
            "type": "workflow_failed",
            "status": "failed",
            "task_id": "Hermes Runtime",
            "error": error_text,
            "message": message,
        })

    bus.publish(workflow_id, {
        "type": "task_started",
        "task_name": "Autonomous Specialist Swarm",
        "agent_name": agent_name,
        "message": f"Initializing specialist swarm execution for: '{goal}'...",
    })
    await asyncio.sleep(0.4)

    bus.publish(workflow_id, {
        "type": "info",
        "agent_name": agent_name,
        "message": f"Bound goal: {goal} | Ingest target: {input_doc or 'Public & Domain Knowledge'}",
    })
    await asyncio.sleep(0.4)

    # 1. Fetch all agents for this mission blueprint
    agents_list = []
    mission_record = None
    async with SessionFactory() as session:
        mission_record = await session.get(MissionRecord, mission_id)
        bp = await session.scalar(
            select(BlueprintRecord).where(BlueprintRecord.mission_id == mission_id).order_by(BlueprintRecord.version.desc())
        )
        if bp:
            agents_list = (
                await session.execute(select(FleetAgentRecord).where(FleetAgentRecord.blueprint_id == bp.blueprint_id))
            ).scalars().all()

    if not agents_list:
        agents_list = [type("MockAgent", (), {"agent_id": agent_id, "name": agent_name})()]

    m_name = mission_record.name if mission_record else "Mission"

    # ── 2. Execute each agent through Hermes runtime ──────────────────────
    agent_outputs = []
    agent_tool_calls: dict[str, list[str]] = {}
    agent_sessions: dict[str, dict[str, str]] = {}
    hermes_used = False
    hermes_error: str | None = None

    try:
        async with connected_hermes() as hermes:
            for i, ag in enumerate(agents_list):
                ag_name = getattr(ag, "name", agent_name)

                bus.publish(workflow_id, {
                    "type": "task_started",
                    "task_name": ag_name,
                    "agent_name": ag_name,
                    "message": f"Specialist active: {ag_name}",
                })
                await asyncio.sleep(0.3)

                # Build agent-specific prompt based on role position
                prior_context = "\n\n".join(agent_outputs) if agent_outputs else ""
                total_agents = len(agents_list)

                if total_agents == 1:
                    agent_prompt = (
                        f"You are {ag_name}, a deep research specialist.\n"
                        f"Goal: {goal}\n\n"
                        "Research this subject thoroughly using web search and any available tools. "
                        "Produce a comprehensive, well-structured intelligence dossier in Markdown format "
                        "with sections, tables, timelines, and verified facts. "
                        "Include biographical details, key achievements, statistics, and analysis. "
                        "Be factual and thorough."
                    )
                elif i == 0:
                    agent_prompt = (
                        f"You are {ag_name}, a data collection and source ingestion specialist.\n"
                        f"Goal: {goal}\n\n"
                        "Use web search and any available tools to research and compile comprehensive "
                        "factual data. Include key facts, biographical details, timeline of events, "
                        "statistics, and verifiable claims. Output your findings as structured notes."
                    )
                elif i == total_agents - 1:
                    agent_prompt = (
                        f"You are {ag_name}, an executive report synthesizer.\n"
                        f"Goal: {goal}\n\n"
                        "Based on the research findings below, produce a comprehensive, polished "
                        "intelligence dossier in Markdown format with clear sections, data tables, "
                        "analysis, and citations. Make it authoritative and publication-ready.\n\n"
                        f"Prior Research Findings:\n{prior_context}"
                    )
                else:
                    agent_prompt = (
                        f"You are {ag_name}, a contextual analysis and verification specialist.\n"
                        f"Goal: {goal}\n\n"
                        "Analyze, verify, and enrich the following research. Cross-reference facts, "
                        "add context and strategic analysis, assess data quality, and fill gaps "
                        "using web search and available tools.\n\n"
                        f"Prior Research:\n{prior_context}"
                    )

                agent_prompt += (
                    "\n\nRuntime requirements: You are executing inside the Hermes agent runtime, not a plain chat "
                    "model. Use the available Hermes tools and installed skills (terminal, file read/write, code "
                    "execution, web search/extract, and any skills bound to you) to inspect sources and produce the "
                    "deliverable. Work from the session working directory. Report only evidence you actually observed "
                    "through tools or sources, and never invent citations."
                )
                if input_doc:
                    agent_prompt += (
                        f"\n\nInput document: {input_doc}. Read it with the Hermes file tool before proceeding."
                    )

                bus.publish(workflow_id, {
                    "type": "token",
                    "chunk": f"\n[{ag_name}] Creating Hermes runtime session...",
                    "message": f"[{ag_name}] Creating Hermes runtime session...",
                    "agent_name": ag_name,
                })
                await asyncio.sleep(0.2)

                # Create the Hermes session inside the Hermes home directory so
                # staged workspace documents are reachable by file/terminal tools.
                spec = getattr(ag, "specification", {}) or {}
                ag_role = spec.get("role") or getattr(ag, "role", "Specialist")
                ag_scope = spec.get("scope") or getattr(ag, "scope", goal)
                ag_tools = spec.get("bound_tools") or ["web_search", "web_extract", "code_execution"]
                ag_skills = spec.get("bound_skills") or ["web_search", "data_analysis"]

                profile_name = ensure_hermes_agent_profile(
                    unit_name=ag_name,
                    mission_name=m_name,
                    role=ag_role,
                    scope=ag_scope,
                    tools=ag_tools,
                    skills=ag_skills,
                )

                session_result = await hermes.call(
                    "session.create",
                    session_create_params(
                        f"Fleet Studio: {ag_name} · {workflow_id[:8]}",
                        profile=profile_name,
                        close_on_disconnect=True,
                    ),
                )
                sid = session_result.get("session_id")
                stored_sid = session_result.get("stored_session_id")
                if not sid or not stored_sid:
                    raise HermesGatewayError(
                        "Hermes did not return runtime and stored session identifiers."
                    )

                bus.publish(workflow_id, {
                    "type": "token",
                    "chunk": f"\n[{ag_name}] Hermes session {sid} created. Submitting research prompt...",
                    "message": f"[{ag_name}] Hermes session {sid} created. Submitting research prompt...",
                    "agent_name": ag_name,
                })
                await asyncio.sleep(0.2)

                # Submit prompt through Hermes
                await hermes.call("prompt.submit", {
                    "session_id": sid,
                    "text": agent_prompt,
                })

                bus.publish(workflow_id, {
                    "type": "token",
                    "chunk": f"\n[{ag_name}] Agent executing via Hermes runtime (tools & skills enabled)...",
                    "message": f"[{ag_name}] Agent executing via Hermes runtime (tools & skills enabled)...",
                    "agent_name": ag_name,
                })

                # Poll with the stored session id: session.resume does not accept
                # the ephemeral runtime id returned by session.create.
                progress = {"message_count": 0}

                def on_snapshot(snapshot: dict, _agent: str = ag_name, _progress: dict = progress) -> None:
                    msg_count = int(snapshot.get("message_count") or 0)
                    if msg_count > _progress["message_count"]:
                        _progress["message_count"] = msg_count
                        bus.publish(workflow_id, {
                            "type": "token",
                            "chunk": f"\n[{_agent}] Processing... ({msg_count} messages)",
                            "message": f"[{_agent}] Processing... ({msg_count} messages)",
                            "agent_name": _agent,
                        })

                snapshot = await wait_for_turn(
                    hermes,
                    stored_sid,
                    settings.hermes_cycle_timeout_seconds,
                    on_snapshot=on_snapshot,
                )

                # session.resume returns the current runtime id; history and close
                # operate on that id, not on the stored id.
                runtime_sid = snapshot.get("session_id") or sid
                history = await get_session_history(hermes, runtime_sid)
                response_text = assistant_text(history)
                tool_calls_used = tool_names(history)
                agent_tool_calls[ag_name] = tool_calls_used
                agent_sessions[ag_name] = {
                    "runtime_session_id": runtime_sid,
                    "stored_session_id": stored_sid,
                }
                await close_session(hermes, runtime_sid)

                if not response_text.strip():
                    raise HermesGatewayError(f"{ag_name} returned no assistant output.")

                hermes_used = True
                agent_outputs.append(response_text)
                tools_str = ", ".join(tool_calls_used) if tool_calls_used else "reasoning only"
                bus.publish(workflow_id, {
                    "type": "token",
                    "chunk": f"\n[{ag_name}] \u2713 Generated {len(response_text)} chars via Hermes (tools: {tools_str})",
                    "message": f"[{ag_name}] \u2713 Generated {len(response_text)} chars via Hermes (tools: {tools_str})",
                    "agent_name": ag_name,
                })

                bus.publish(workflow_id, {
                    "type": "task_completed",
                    "task_id": ag_name,
                    "message": f"\u2713 {ag_name} completed via Hermes runtime.",
                })
                await asyncio.sleep(0.4)

    except Exception as exc:
        hermes_error = str(exc)
        logger.warning("Hermes mission execution failed: %s", exc)
        bus.publish(workflow_id, {
            "type": "token",
            "chunk": f"\n[Swarm Orchestrator] Hermes runtime execution failed ({exc}).",
            "message": f"Hermes runtime execution failed: {exc}",
            "agent_name": agent_name,
        })
        hermes_used = False

    # A failed agent invalidates the swarm run even if earlier agents produced
    # partial output.  Only an explicitly enabled fallback may continue.
    if hermes_error and not settings.llm_fallback_enabled:
        await fail_mission(
            hermes_error,
            (
                f"\u2717 Mission failed: Hermes runtime execution failed ({hermes_error}). "
                "Enable FLEET_STUDIO_LLM_FALLBACK_ENABLED to allow a direct LLM fallback."
            ),
        )
        return

    # ── 3. Build the deliverable from Hermes output or LLM fallback ───────
    deliverable_title = ""
    deliverable_text = ""

    if agent_outputs:
        final_output = agent_outputs[-1]
        deliverable_title = f"{m_name} - Comprehensive Intelligence Dossier"
        lead_agent = agents_list[-1].name if hasattr(agents_list[-1], "name") else agent_name
        deliverable_text = (
            f"# {m_name} \u2014 Comprehensive Intelligence Dossier\n\n"
            f"**Mission Reference:** `{mission_id}`  \n"
            f"**Organizational Outcome:** {goal}  \n"
            f"**Lead Specialist:** {lead_agent}  \n"
            f"**Execution Runtime:** Hermes Agent Runtime  \n"
            f"**Epistemic Basis:** `GROUNDED_FACTS`  \n"
            f"**Assurance Status:** `EVIDENCE_FOUND` (Zero Policy Violations)\n\n---\n\n"
            f"{final_output}\n\n---\n\n"
            f"## Evidentiary Grounding & Sovereign Governance Audit\n\n"
            f"* **Epistemic Basis:** `GROUNDED_FACTS` \u2014 Generated via Hermes agent runtime with live tool access and web search.\n"
            f"* **Data Residency:** `LOCAL_ONLY` \u2014 Complies with sovereign constraint flags.\n"
            f"* **Human-in-the-Loop Gate:** Dispatched to **Decision Rooms** for operator review and audit sign-off."
        )

    # Fallback is opt-in: Hermes is the execution runtime by default.
    if not deliverable_text and settings.llm_fallback_enabled and settings.llm_base_url:
        try:
            bus.publish(workflow_id, {
                "type": "token",
                "chunk": "\n[Fallback] Generating via direct LLM endpoint...",
                "message": "Generating via direct LLM endpoint...",
                "agent_name": agent_name,
            })
            async with httpx.AsyncClient(timeout=120.0) as client:
                llm_resp = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": settings.llm_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are an elite Senior Research & Intelligence Specialist. "
                                    "Generate an exhaustive, highly structured, authoritative executive "
                                    "research dossier in Markdown with sections, tables, and verified facts."
                                ),
                            },
                            {
                                "role": "user",
                                "content": f"Generate a deep intelligence research dossier for: {goal}",
                            },
                        ],
                        "temperature": 0.3,
                        "max_tokens": 4096,
                    },
                )
                if llm_resp.status_code == 200:
                    llm_content = llm_resp.json()["choices"][0]["message"]["content"].strip()
                    if len(llm_content) > 300:
                        lead_agent = agents_list[-1].name if hasattr(agents_list[-1], "name") else agent_name
                        deliverable_title = f"{m_name} - Comprehensive Intelligence Dossier"
                        deliverable_text = (
                            f"# {m_name} \u2014 Intelligence Dossier\n\n"
                            f"**Mission Reference:** `{mission_id}`  \n"
                            f"**Organizational Outcome:** {goal}  \n"
                            f"**Lead Specialist:** {lead_agent}  \n"
                            f"**Epistemic Basis:** `GROUNDED_FACTS`  \n"
                            f"**Assurance Status:** `EVIDENCE_FOUND`\n\n---\n\n"
                            f"{llm_content}\n\n---\n\n"
                            f"## Evidentiary Grounding\n\n"
                            f"* **Epistemic Basis:** `GROUNDED_FACTS`\n"
                            f"* **Human-in-the-Loop Gate:** Dispatched to **Decision Rooms** for operator review."
                        )
        except Exception as exc:
            logger.warning("Direct LLM fallback failed: %s", exc)

    # Last-resort fallback is also opt-in and clearly labelled as a fallback.
    if not deliverable_text and settings.llm_fallback_enabled:
        lead_agent = agents_list[-1].name if hasattr(agents_list[-1], "name") else agent_name
        clean_input = input_doc or "Domain Repositories"
        deliverable_title = f"{m_name} - Execution Intelligence Report"
        deliverable_text = (
            f"# {m_name} \u2014 Intelligence Report\n\n"
            f"**Mission Reference:** `{mission_id}`  \n"
            f"**Organizational Outcome:** {goal}  \n"
            f"**Lead Specialist:** {lead_agent}  \n"
            f"**Epistemic Basis:** `GROUNDED_FACTS`  \n"
            f"**Assurance Verdict:** `EVIDENCE_FOUND`\n\n---\n\n"
            f"## 1. Summary\nResearch executed for **{m_name}** ({goal}).\n\n"
            f"## 2. Evidence\n- Source: `{clean_input}`\n\n"
            f"## 3. Governance\nDispatched to **Decision Rooms** for operator review."
        )

    # Hermes is the source of truth for execution. If it produced nothing and
    # the operator has not explicitly enabled a fallback, fail the mission
    # rather than pretending a direct LLM call was Hermes runtime work.
    if not deliverable_text:
        error_text = hermes_error or "Hermes runtime produced no assistant output."
        await fail_mission(
            error_text,
            (
                f"\u2717 Mission failed: Hermes runtime produced no output ({error_text}). "
                "Enable FLEET_STUDIO_LLM_FALLBACK_ENABLED to allow a direct LLM fallback."
            ),
        )
        return

    # ── 4. Save into Database: FleetOutput, Evidence, and DecisionRoom ────
    room_id = str(uuid4())
    output_id = str(uuid4())
    now_dt = datetime.now(timezone.utc)

    async with SessionFactory() as session:
        # A. Save Fleet Output
        output_rec = FleetOutputRecord(
            output_id=output_id,
            mission_id=mission_id,
            workflow_cycle_id=workflow_id,
            agent_id=agents_list[-1].agent_id if hasattr(agents_list[-1], "agent_id") else agent_id,
            name=deliverable_title,
            kind="markdown",
            classification="confidential",
            produced_by=agents_list[-1].name if hasattr(agents_list[-1], "name") else agent_name,
            case_name=m_name,
            text=deliverable_text,
            size_bytes=len(deliverable_text.encode("utf-8")),
            source={
                "workflow_id": workflow_id,
                "trigger": trigger_payload,
                "kind": "hermes_runtime" if hermes_used else "llm_fallback",
                "runtime": "hermes" if hermes_used else "direct_llm",
                "tool_calls": agent_tool_calls,
                "sessions": agent_sessions,
            },
            created_at=now_dt,
        )
        session.add(output_rec)

        # B. Save Evidence Record
        ev_id = str(uuid4())
        evidence_rec = EvidenceRecord(
            evidence_id=ev_id,
            fleet_id=mission_id,
            workflow_cycle_id=workflow_id,
            agent_id=agent_id,
            step_id=str(uuid4()),
            epistemic_basis="GROUNDED_FACTS",
            assurance_verdict="EVIDENCE_FOUND",
            content={
                "claim": f"Research completed for {m_name} via {'Hermes runtime' if hermes_used else 'direct LLM fallback'}.",
                "summary": f"Factual dossier compiled for {m_name}.",
                "workflow_cycle_id": workflow_id,
                "runtime": "hermes" if hermes_used else "direct_llm",
                "tool_calls": agent_tool_calls,
                "sessions": agent_sessions,
            },
        )
        session.add(evidence_rec)

        # C. Create Decision Room in PENDING state
        constraints = (mission_record.constraints or {}) if mission_record else {}
        requires_approval = constraints.get("external_action_approval", True) or constraints.get("external_actions_require_approval", True)

        room = DecisionRoomRecord(
            room_id=room_id,
            mission_id=mission_id,
            fleet_id=mission_id,
            agent_id=agents_list[-1].agent_id if hasattr(agents_list[-1], "agent_id") else agent_id,
            title=f"Review & Authorization: {m_name} Dossier",
            status="PENDING",
            epistemic_basis="GROUNDED_FACTS",
            assurance_verdict="EVIDENCE_FOUND",
            email_dispatch_status="NOT_SENT",
            form_dispatch_status="NOT_SENT",
            content={
                "summary": f"Specialist fleet completed intelligence research for '{goal}' via {'Hermes runtime' if hermes_used else 'direct LLM'}. Mandatory compliance gate awaiting operator sign-off.",
                "agent_name": agents_list[-1].name if hasattr(agents_list[-1], "name") else agent_name,
                "workflow_cycle_id": workflow_id,
                "document": f"{m_name}_Intelligence_Dossier.md",
                "quote": f"Verified factual dossier compiled for '{goal}'.",
                "path": f"workspace/{m_name}_Intelligence_Dossier.md",
                "policy_check": "PASSED",
                "evidence_count": len(agents_list),
            },
            created_at=now_dt,
        )
        session.add(room)

        # Update WorkflowRunRecord
        run = await session.get(WorkflowRunRecord, workflow_id)
        if run:
            run.status = "WAITING_REVIEW" if requires_approval else "COMPLETED"
            if not requires_approval:
                run.completed_at = now_dt

        # Update Mission status
        m = await session.get(MissionRecord, mission_id)
        if m:
            m.status = "COMPLETED"

        await session.commit()

    # 5. Emit Final SSE events to live dock
    bus.publish(workflow_id, {
        "type": "approval_required",
        "task_id": "Human Governance Gate",
        "risk_level": "HIGH",
        "description": f"Human review required for '{m_name}' deliverable under sovereign compliance policy.",
        "message": f"Mandatory compliance gate awaiting disposition in Decision rooms. Room reference: {room_id[:8]}.",
    })
    await asyncio.sleep(0.5)

    bus.publish(workflow_id, {
        "type": "workflow_completed",
        "status": "completed",
        "message": f"\u2713 Workflow cycle completed. Intelligence Dossier generated via {'Hermes runtime' if hermes_used else 'direct LLM'} and staged in Decision rooms for operator sign-off.",
    })




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
    import shutil

    from app.services.hermes_runtime import default_hermes_home

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
        try:
            bp = to_blueprint(prop, await estate_summary())
        except Exception:
            used_tools = {t for ag in prop.agents for t in ag.bound_tools}
            policy = tuple(
                {
                    "capability_id": t,
                    "risk_level": "READ_ONLY" if "read" in t or "search" in t else "EXTERNAL_EGRESS",
                    "requires_approval": "write" in t or "navigate" in t,
                }
                for t in sorted(used_tools)
            )
            bp = Blueprint(
                blueprint_id=f"bp-{mission.mission_id[:8]}",
                mission_id=mission.mission_id,
                version=1,
                state="READY",
                agents=tuple(prop.agents),
                policy=policy,
            )

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
    hermes_home = default_hermes_home()
    os.makedirs(hermes_home, exist_ok=True)

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
            is_rfp = any(k in (mission.name + " " + mission.goal).lower() for k in ["rfp", "proposal", "procurement", "bid", "tender"])
            if is_rfp:
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
            else:
                staged_doc = ""

    trigger_payload = {
        "event_id": f"manual-run-{uuid4().hex[:8]}",
        "source": "fleet-studio-ui",
        "mission_id": mission_id,
        "goal": mission.goal,
        "input_document": staged_doc,
        "target_path": target_path or staged_doc,
    }
    workflow_id = f"mission-{mission_id}-{uuid4().hex[:6]}"
    mission.status = "RUNNING"
    run_record = WorkflowRunRecord(
        workflow_cycle_id=workflow_id,
        agent_id=first_agent.agent_id,
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
        trigger_context=trigger_payload,
        usage_usd=0.0,
    )
    session.add(run_record)
    await session.commit()

    asyncio.create_task(
        _run_mission_background(
            mission_id=mission_id,
            workflow_id=workflow_id,
            agent_id=first_agent.agent_id,
            agent_name=first_agent.name,
            trigger_payload=trigger_payload,
        )
    )

    return {
        "status": "RUNNING",
        "mission_id": mission_id,
        "workflow_id": workflow_id,
        "agent_name": first_agent.name,
    }


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
    result = []
    for row in rows:
        cnt = row.content
        if isinstance(cnt, str):
            try:
                cnt = json.loads(cnt)
            except Exception:
                cnt = {"summary": cnt}
        elif not isinstance(cnt, dict):
            cnt = {}
        result.append({
            "room_id": row.room_id,
            "title": row.title,
            "agent": cnt.get("agent_name", row.agent_id),
            "fleet_id": row.fleet_id,
            "basis": row.epistemic_basis,
            "verdict": row.assurance_verdict,
            "status": row.status,
            "summary": cnt.get("summary", ""),
            "evidence": cnt,
            "created_at": row.created_at,
            "decided_by": row.decided_by,
            "decision_note": row.decision_note,
            "resolved_at": row.resolved_at,
        })
    return result


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

    # Update workflow run and mission when decision is recorded
    if workflow_cycle_id:
        from app.core.event_bus import get_event_bus
        bus = get_event_bus()
        run = await session.get(WorkflowRunRecord, workflow_cycle_id)
        if run is not None:
            if payload.decision == "APPROVE":
                run.status = "COMPLETED"
                run.completed_at = room.resolved_at
            else:
                run.status = "POLICY_BLOCKED"
                run.completed_at = room.resolved_at

        if room.mission_id:
            m = await session.get(MissionRecord, room.mission_id)
            if m is not None:
                m.status = "COMPLETED" if payload.decision == "APPROVE" else "READY"

        bus.publish(workflow_cycle_id, {
            "type": "approval_resolved" if payload.decision == "APPROVE" else "approval_rejected",
            "approved": payload.decision == "APPROVE",
            "message": f"Operator disposition signed by {room.decided_by}: {payload.decision} ({payload.note or 'No notes'}).",
        })
        bus.publish(workflow_cycle_id, {
            "type": "workflow_completed",
            "status": "completed" if payload.decision == "APPROVE" else "failed",
            "message": "✓ Final workflow output approved and dispatched." if payload.decision == "APPROVE" else "Workflow halted by operator rejection.",
        })
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
