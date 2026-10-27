from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from opentelemetry import trace

from app.core.config import settings
from app.models import (
    BlueprintRecord,
    AgentWorkflowRecord,
    DaemonJobRecord,
    DecisionRoomRecord,
    EvidenceRecord,
    FleetAgentRecord,
    FleetOutputRecord,
    MissionRecord,
    WorkflowRunRecord,
    WorkflowStepRecord,
)
from app.schemas.domain import AssuranceVerdict, EpistemicBasis, EvidenceCreate
from app.services.assurance import verify_evidence
from app.services.estate_discovery import estate_summary
from app.services.hermes_gateway import HermesGatewayError, connected_hermes

tracer = trace.get_tracer("fleet-studio.workflow")


async def _hermes_rpc(hermes, method: str, params: dict, correlation: dict, timeout: float = 30) -> dict:
    with tracer.start_as_current_span("fleet_studio.hermes.rpc") as span:
        span.set_attributes({**correlation, "rpc.system": "hermes-jsonrpc", "rpc.method": method})
        return await hermes.call(method, params, timeout=timeout)


def _flatten_content(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in value
        )
    return ""


def _redact_transcript(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted email]", text)
    return re.sub(r"\b(?:\+?\d[\d ()-]{7,}\d)\b", "[redacted phone]", text)


def _assistant_text(history: dict) -> str:
    for message in reversed(history.get("messages", [])):
        if message.get("role") == "assistant":
            return _flatten_content(message.get("content"))
    return ""


def _transcript_text(history: dict) -> str:
    lines = []
    for message in history.get("messages", []):
        role = str(message.get("role") or "unknown")
        if role == "user":
            continue
        text = _flatten_content(message.get("content"))
        if not text:
            continue
        tool_name = message.get("tool_name") or message.get("name")
        label = f"tool:{tool_name}" if role == "tool" or tool_name else role
        lines.append(f"[{label}] {_redact_transcript(text)}")
    return "\n".join(lines)[-200_000:]


def _find_output(text: str) -> dict:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}


async def _wait_for_turn(hermes, session_id: str, timeout_seconds: int, correlation: dict) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        snapshot = await _hermes_rpc(
            hermes,
            "session.resume",
            {"session_id": session_id, "lazy": True, "omit_messages": True},
            correlation,
            timeout=30,
        )
        status = str(snapshot.get("status") or "").lower()
        if snapshot.get("running") is False or status in {"idle", "completed", "complete", "stopped"}:
            return
        await asyncio.sleep(2)
    raise TimeoutError("Hermes workflow cycle timed out.")


async def execute_agent_cycle(agent_id: str, session: AsyncSession, trigger_context: dict | None = None) -> dict:
    agent = await session.get(FleetAgentRecord, agent_id)
    if agent is None or agent.managed_state != "APPLIED" or agent.applied_specification is None:
        raise ValueError("Agent has no applied Fleet Studio policy.")
    if not settings.hermes_hooks_enabled:
        raise RuntimeError("Hermes runtime hook is not enabled; workflow execution is disabled.")
    inventory = await estate_summary()
    if not inventory.connected or not inventory.provider_configured:
        raise RuntimeError("Hermes inference provider is not configured; workflow execution is disabled.")
    spec = agent.applied_specification
    if spec.get("capability_gaps"):
        raise RuntimeError("Agent has unresolved capability gaps.")
    steps = spec.get("workflow_steps") or []
    if not steps:
        raise RuntimeError("Agent has no workflow steps.")
    blueprint = await session.get(BlueprintRecord, agent.blueprint_id)
    if blueprint is None:
        raise RuntimeError("Agent blueprint is unavailable.")
    mission = await session.get(MissionRecord, blueprint.mission_id)
    if mission is None:
        raise RuntimeError("Agent mission is unavailable.")

    trigger_context = trigger_context or {}
    resume_cycle_id = trigger_context.get("resume_workflow_cycle_id")
    resume_step_id = trigger_context.get("resume_step_id")
    start_index = 0
    if resume_cycle_id:
        run = await session.get(WorkflowRunRecord, resume_cycle_id)
        if run is None or run.agent_id != agent_id or run.status != "RUNNING":
            raise ValueError("Approved workflow continuation is no longer active.")
        cycle_id = run.workflow_cycle_id
        trigger_context = run.trigger_context or {}
        start_index = next(
            (index for index, item in enumerate(steps) if item.get("step_id") == resume_step_id),
            -1,
        )
        if start_index < 0:
            raise ValueError("Approved workflow step is not part of the applied specification.")
        evidence_ids = list(
            await session.scalars(
                select(EvidenceRecord.evidence_id).where(EvidenceRecord.workflow_cycle_id == cycle_id)
            )
        )
    else:
        cycle_id = str(uuid4())
        run = WorkflowRunRecord(
            workflow_cycle_id=cycle_id,
            agent_id=agent_id,
            status="STARTING",
            usage_usd=0,
            trigger_context=trigger_context,
        )
        session.add(run)
        await session.commit()

    correlation = {
        "fleet_id": mission.mission_id,
        "agent_id": agent_id,
        "workflow_cycle_id": cycle_id,
    }
    requires_gate = (
        steps[0].get("requires_step_challenge")
        or "decision room" in str((mission.clarification_answers or {}).get("compliance-gate", "")).lower()
        or "bid-review" in str((mission.clarification_answers or {}).get("compliance-gate", "")).lower()
        or "gate" in str((mission.clarification_answers or {}).get("compliance-gate", "")).lower()
    )
    if not resume_cycle_id and requires_gate:
        first_step = steps[0]
        step_run = WorkflowStepRecord(
            step_run_id=str(uuid4()),
            workflow_cycle_id=cycle_id,
            step_id=str(first_step.get("step_id") or uuid4()),
            capability_id=first_step["capability_id"],
            status="WAITING_REVIEW",
        )
        session.add(step_run)
        doc_name = trigger_context.get("input_document") or "RFP.docx"
        session.add(
            DecisionRoomRecord(
                room_id=str(uuid4()),
                mission_id=mission.mission_id,
                fleet_id=mission.mission_id,
                agent_id=agent_id,
                title=f"Bid-Review Gate: {agent.name}",
                status="PENDING",
                epistemic_basis=EpistemicBasis.JUDGMENT.value,
                assurance_verdict=AssuranceVerdict.NOT_VERIFIABLE.value,
                content={
                    "summary": f"Document '{doc_name}' staged. Mandatory compliance & bid-review gate awaiting two-person integrity approval before downstream proposal synthesis.",
                    "agent_name": agent.name,
                    "workflow_cycle_id": cycle_id,
                    "step_id": step_run.step_id,
                    "document": doc_name,
                    "parameters_redacted": True,
                },
            )
        )
        run.status = "WAITING_REVIEW"
        await session.commit()
        return {"workflow_cycle_id": cycle_id, "status": run.status, "evidence_ids": []}

    evidence_ids = evidence_ids if resume_cycle_id else []
    try:
        async with connected_hermes() as hermes:
            llm = spec.get("assigned_llm") or {}
            if resume_cycle_id and run.hermes_stored_session_id:
                resumed = await _hermes_rpc(
                    hermes,
                    "session.resume",
                    {"session_id": run.hermes_stored_session_id, "lazy": False},
                    correlation,
                    timeout=60,
                )
                session_id = resumed.get("session_id")
                stored_session_id = resumed.get("stored_session_id") or run.hermes_stored_session_id
            else:
                created = await _hermes_rpc(
                    hermes,
                    "session.create",
                    {
                        "title": f"Fleet Studio: {agent.name} · {cycle_id[:8]}",
                        "source": "fleet-studio",
                        "model": llm.get("version"),
                        "provider": llm.get("family"),
                        "close_on_disconnect": False,
                    },
                    correlation,
                )
                session_id = created.get("session_id")
                stored_session_id = created.get("stored_session_id")
            if not session_id:
                raise HermesGatewayError("Hermes did not return a runtime session id.")
            run.hermes_session_id = session_id
            run.hermes_stored_session_id = stored_session_id
            correlation["hermes.session_id"] = session_id
            run.status = "RUNNING"
            await session.commit()

            for step_spec in steps[start_index:]:
                step_id = str(step_spec.get("step_id") or uuid4())
                step_run = await session.scalar(
                    select(WorkflowStepRecord).where(
                        WorkflowStepRecord.workflow_cycle_id == cycle_id,
                        WorkflowStepRecord.step_id == step_id,
                    )
                )
                if step_run is None:
                    step_run = WorkflowStepRecord(
                        step_run_id=str(uuid4()),
                        workflow_cycle_id=cycle_id,
                        step_id=step_id,
                        capability_id=step_spec["capability_id"],
                        status="RUNNING",
                    )
                    session.add(step_run)
                else:
                    step_run.status = "RUNNING"
                    step_run.completed_at = None
                await session.commit()
                step_correlation = {**correlation, "step_id": step_id}
                if step_spec.get("requires_step_challenge"):
                    challenge_room = DecisionRoomRecord(
                        room_id=str(uuid4()),
                        mission_id=mission.mission_id,
                        fleet_id=mission.mission_id,
                        agent_id=agent_id,
                        title=f"Step challenge: {step_spec.get('name', step_id)}",
                        status="PENDING",
                        epistemic_basis=EpistemicBasis.JUDGMENT.value,
                        assurance_verdict=AssuranceVerdict.NOT_VERIFIABLE.value,
                        content={
                            "summary": "A configured runtime step is paused for human challenge.",
                            "agent_name": agent.name,
                            "workflow_cycle_id": cycle_id,
                            "step_id": step_id,
                            "parameters_redacted": True,
                        },
                    )
                    session.add(challenge_room)
                    step_run.status = "WAITING_REVIEW"
                    run.status = "WAITING_REVIEW"
                    await session.commit()
                    return {"workflow_cycle_id": cycle_id, "status": run.status, "evidence_ids": evidence_ids}
                prompt = (
                    "You are a narrowly scoped specialist in a governed Hermes fleet.\n"
                    f"Mission: {mission.goal}\n"
                    f"Your role: {spec.get('role')}\n"
                    f"Your allowed scope: {spec.get('scope')}\n"
                    f"Current workflow step: {step_spec.get('name')}\n"
                    f"Trigger event context: {json.dumps(trigger_context, ensure_ascii=True)}\n"
                    f"Step parameters: {json.dumps(step_spec.get('parameters') or {}, ensure_ascii=True)}\n\n"
                    "Do not make or imply a human judgment. If a human decision is needed, state that it is needed. "
                    "Use only the configured Hermes skill/tool capabilities; runtime policy enforces the allowlist. "
                    "Return one JSON object with a findings array. Each finding must contain claim, epistemic_basis "
                    "(SOURCE, ANALYTICAL, INTERPRETATION, or ASSUMPTION), and an optional supporting_quote copied "
                    "from your transcript. Never return JUDGMENT as an agent-authored basis."
                )
                await _hermes_rpc(hermes, "prompt.submit", {"session_id": session_id, "text": prompt}, step_correlation)
                await _wait_for_turn(hermes, session_id, settings.hermes_cycle_timeout_seconds, step_correlation)
                history = await _hermes_rpc(hermes, "session.history", {"session_id": session_id}, step_correlation)
                transcript = _transcript_text(history)
                output = _find_output(_assistant_text(history))
                findings = output.get("findings") if isinstance(output.get("findings"), list) else []
                judgment = next(
                    (
                        finding
                        for finding in findings
                        if isinstance(finding, dict)
                        and str(finding.get("epistemic_basis", "")).upper() == EpistemicBasis.JUDGMENT.value
                    ),
                    None,
                )
                if judgment or output.get("decision_required"):
                    summary = str((judgment or {}).get("claim") or output.get("decision_context") or "Human decision required.")
                    session.add(
                        DecisionRoomRecord(
                            room_id=str(uuid4()),
                            mission_id=mission.mission_id,
                            fleet_id=mission.mission_id,
                            agent_id=agent_id,
                            title=f"Human decision required: {agent.name}",
                            status="PENDING",
                            epistemic_basis=EpistemicBasis.JUDGMENT.value,
                            assurance_verdict=AssuranceVerdict.NOT_VERIFIABLE.value,
                            content={"summary": _redact_transcript(summary), "agent_name": agent.name, "workflow_cycle_id": cycle_id},
                        )
                    )
                    step_run.status = "WAITING_REVIEW"
                    run.status = "WAITING_REVIEW"
                    await session.commit()
                    return {"workflow_cycle_id": cycle_id, "status": run.status, "evidence_ids": evidence_ids}

                for finding in findings:
                    if not isinstance(finding, dict):
                        continue
                    basis_text = str(finding.get("epistemic_basis", "ANALYTICAL")).upper()
                    try:
                        basis = EpistemicBasis(basis_text)
                    except ValueError:
                        basis = EpistemicBasis.ANALYTICAL
                    if basis is EpistemicBasis.JUDGMENT:
                        continue
                    with tracer.start_as_current_span("fleet_studio.evidence.verify") as evidence_span:
                        evidence_span.set_attributes(step_correlation)
                        evidence = EvidenceCreate(
                        fleet_id=mission.mission_id,
                        agent_id=agent_id,
                        workflow_cycle_id=cycle_id,
                        step_id=step_id,
                        claim=_redact_transcript(str(finding.get("claim", "")))[:4000],
                        epistemic_basis=basis,
                        transcript=transcript,
                        supporting_quote=_redact_transcript(str(finding.get("supporting_quote", ""))) or None,
                        trace_available=False,
                        )
                        assurance = verify_evidence(evidence)
                    session.add(
                        EvidenceRecord(
                            evidence_id=evidence.evidence_id,
                            fleet_id=mission.mission_id,
                            workflow_cycle_id=cycle_id,
                            agent_id=agent_id,
                            step_id=step_id,
                            epistemic_basis=basis.value,
                            content={"claim": evidence.claim, "transcript": transcript, "supporting_quote": evidence.supporting_quote, "otel_trace_id": assurance.trace_id},
                            assurance_verdict=assurance.verdict.value,
                        )
                    )
                    evidence_ids.append(evidence.evidence_id)
                output_text = _assistant_text(history) or transcript
                step_name = step_spec.get("name") or "Specialist Output"
                session.add(
                    FleetOutputRecord(
                        output_id=str(uuid4()),
                        mission_id=mission.mission_id,
                        workflow_cycle_id=cycle_id,
                        agent_id=agent_id,
                        name=f"{step_name}: {agent.name}",
                        kind="markdown" if "```" in output_text or "#" in output_text else "document",
                        classification="confidential",
                        produced_by=agent.name,
                        case_name=mission.name,
                        text=output_text,
                        size_bytes=len(output_text.encode("utf-8")),
                        source={
                            "kind": "agent",
                            "workflow_cycle_id": cycle_id,
                            "step_id": step_id,
                            "step_name": step_name,
                            "agent_id": agent_id,
                            "agent_role": spec.get("role"),
                            "tool_calls_count": len([m for m in history.get("messages", []) if m.get("role") == "tool" or m.get("tool_calls")]),
                        },
                    )
                )
                step_run.status = "SUCCEEDED"
                step_run.completed_at = datetime.now(timezone.utc)
                await session.commit()
            session.add(
                FleetOutputRecord(
                    output_id=str(uuid4()),
                    mission_id=mission.mission_id,
                    workflow_cycle_id=cycle_id,
                    agent_id=agent_id,
                    name=f"Synthesis Deliverable: {mission.name}",
                    kind="document",
                    classification="confidential",
                    produced_by=f"Fleet: {agent.name}",
                    case_name=mission.name,
                    text=output_text if 'output_text' in locals() else transcript,
                    size_bytes=len((output_text if 'output_text' in locals() else transcript).encode("utf-8")),
                    source={
                        "kind": "mission_run",
                        "workflow_cycle_id": cycle_id,
                        "mission_id": mission.mission_id,
                        "status": "SUCCEEDED",
                        "evidence_count": len(evidence_ids),
                    },
                )
            )
            run.status = "SUCCEEDED"
            run.completed_at = datetime.now(timezone.utc)
            await session.commit()
            workflows = await session.scalars(
                select(AgentWorkflowRecord).where(AgentWorkflowRecord.trigger_policy == "EVENT_DRIVEN")
            )
            for workflow in workflows:
                upstream_ids = set((workflow.workflow_specification or {}).get("upstream_agent_ids", []))
                if agent_id not in upstream_ids:
                    continue
                downstream = await session.get(FleetAgentRecord, workflow.agent_id)
                if downstream is None or downstream.managed_state != "APPLIED":
                    continue
                event_key = f"handoff:{cycle_id}:{downstream.agent_id}"
                existing_job = await session.scalar(
                    select(DaemonJobRecord).where(DaemonJobRecord.idempotency_key == event_key)
                )
                if existing_job is None:
                    session.add(
                        DaemonJobRecord(
                            job_id=str(uuid4()),
                            job_type="RUN_AGENT_CYCLE",
                            idempotency_key=event_key,
                            status="QUEUED",
                            payload={
                                "agent_id": downstream.agent_id,
                                "trigger_context": {
                                    "event_id": event_key,
                                    "source_agent_id": agent_id,
                                    "source_workflow_cycle_id": cycle_id,
                                    "evidence_ids": evidence_ids,
                                },
                            },
                        )
                    )
            await session.commit()
            await _hermes_rpc(hermes, "session.close", {"session_id": session_id}, correlation, timeout=15)
    except Exception as error:
        run.status = "FAILED"
        run.completed_at = datetime.now(timezone.utc)
        await session.commit()
        raise RuntimeError(str(error)) from error
    return {"workflow_cycle_id": cycle_id, "status": run.status, "evidence_ids": evidence_ids}