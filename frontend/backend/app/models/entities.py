from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MissionRecord(Base):
    __tablename__ = "missions"

    mission_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="INTAKE")
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    competitive_benchmarking: Mapped[bool] = mapped_column(default=False)
    clarification_answers: Mapped[dict] = mapped_column(JSON, default=dict)
    proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BlueprintRecord(Base):
    __tablename__ = "blueprints"

    blueprint_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.mission_id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    specification: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FleetAgentRecord(Base):
    __tablename__ = "fleet_agents"

    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprints.blueprint_id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    specification: Mapped[dict] = mapped_column(JSON)
    applied_specification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    managed_state: Mapped[str] = mapped_column(String(24), default="DECLARED")


class AgentWorkflowRecord(Base):
    __tablename__ = "agent_workflows"

    workflow_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("fleet_agents.agent_id"), index=True)
    trigger_policy: Mapped[str] = mapped_column(String(24))
    workflow_specification: Mapped[dict] = mapped_column(JSON)


class WorkflowRunRecord(Base):
    __tablename__ = "workflow_runs"

    workflow_cycle_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("fleet_agents.agent_id"), index=True)
    hermes_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    hermes_stored_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    trigger_context: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_usd: Mapped[float] = mapped_column(default=0)


class WorkflowStepRecord(Base):
    __tablename__ = "workflow_steps"

    step_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_cycle_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.workflow_cycle_id"), index=True)
    step_id: Mapped[str] = mapped_column(String(36), index=True)
    capability_id: Mapped[str] = mapped_column(String(240), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_usd: Mapped[float] = mapped_column(default=0)


class PolicyRecord(Base):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    blueprint_id: Mapped[str] = mapped_column(ForeignKey("blueprints.blueprint_id"), index=True)
    rules: Mapped[list] = mapped_column(JSON)


class EvidenceRecord(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fleet_id: Mapped[str] = mapped_column(String(36), index=True)
    workflow_cycle_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.workflow_cycle_id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("fleet_agents.agent_id"), index=True)
    step_id: Mapped[str] = mapped_column(String(36), index=True)
    epistemic_basis: Mapped[str] = mapped_column(String(24))
    content: Mapped[dict] = mapped_column(JSON)
    assurance_verdict: Mapped[str | None] = mapped_column(String(24), nullable=True)


class DecisionRoomRecord(Base):
    __tablename__ = "decision_rooms"

    room_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.mission_id"), nullable=True, index=True)
    fleet_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("fleet_agents.agent_id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    epistemic_basis: Mapped[str] = mapped_column(String(24))
    assurance_verdict: Mapped[str] = mapped_column(String(24))
    email_dispatch_status: Mapped[str] = mapped_column(String(24), default="NOT_SENT")
    form_dispatch_status: Mapped[str] = mapped_column(String(24), default="NOT_SENT")
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[str | None] = mapped_column(String(240), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChallengeGateRecord(Base):
    __tablename__ = "challenge_gates"

    gate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.mission_id"), index=True)
    stage: Mapped[str] = mapped_column(String(48))
    state: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    challenge_snapshot: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DaemonJobRecord(Base):
    __tablename__ = "daemon_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(48), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(240), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    claimed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class FleetOutputRecord(Base):
    __tablename__ = "fleet_outputs"

    output_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.mission_id"), nullable=True, index=True)
    workflow_cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("fleet_agents.agent_id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="markdown", index=True)
    classification: Mapped[str] = mapped_column(String(32), default="confidential")
    produced_by: Mapped[str] = mapped_column(String(120), index=True)
    case_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())