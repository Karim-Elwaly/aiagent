from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskLevel(StrEnum):
    READ_ONLY = "READ_ONLY"
    STATE_MUTATING = "STATE_MUTATING"
    EXTERNAL_EGRESS = "EXTERNAL_EGRESS"


class TriggerKind(StrEnum):
    CRON = "CRON"
    CONTINUOUS_POLL = "CONTINUOUS_POLL"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    WEBHOOK = "WEBHOOK"


class EpistemicBasis(StrEnum):
    SOURCE = "SOURCE"
    ANALYTICAL = "ANALYTICAL"
    INTERPRETATION = "INTERPRETATION"
    ASSUMPTION = "ASSUMPTION"
    JUDGMENT = "JUDGMENT"


class AssuranceVerdict(StrEnum):
    EVIDENCE_FOUND = "EVIDENCE_FOUND"
    NO_EVIDENCE = "NO_EVIDENCE"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class PlanAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class UserRole(StrEnum):
    PLATFORM_ENGINEER = "PlatformEngineer"
    FLEET_ARCHITECT = "FleetArchitect"
    OPERATOR = "Operator"
    COMPLIANCE_OFFICER = "ComplianceOfficer"
    APPROVER = "Approver"


class ModelRef(BaseModel):
    family: str
    version: str


class InstalledSkill(BaseModel):
    skill_id: str
    version: str
    description: str
    input_schema: dict = Field(default_factory=dict)
    required_tools: list[str] = Field(default_factory=list)
    host_node_ids: list[str] = Field(default_factory=list)


class RegisteredTool(BaseModel):
    tool_id: str
    mcp_server: str | None = None
    parameter_schema: dict = Field(default_factory=dict)
    risk_level: RiskLevel
    requires_hitl_approval: bool = False
    risk_classification_source: str | None = None
    risk_assessed: bool = True
    description: str = ""


class AvailableModel(ModelRef):
    cloud: bool = False
    data_residencies: list[str] = Field(default_factory=list)
    reasoning_tier: int | None = Field(default=None, ge=1, le=5)
    estimated_daily_cost_usd: float | None = Field(default=None, ge=0)
    residency_verified: bool = False
    cost_basis: str | None = None


class HermesEstateInventory(BaseModel):
    connected: bool = False
    runtime_hooks_enabled: bool = False
    connection_error: str | None = None
    hermes_version: str | None = None
    profile: str | None = None
    inference_provider: str | None = None
    provider_configured: bool | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    installed_skills: list[InstalledSkill] = Field(default_factory=list)
    registered_tools: list[RegisteredTool] = Field(default_factory=list)
    available_models: list[AvailableModel] = Field(default_factory=list)


class MissionConstraints(BaseModel):
    data_residency: str = "local"
    cloud_access_allowed: bool = False
    daily_budget_usd: float = Field(default=25, ge=0)
    task_complexity: int = Field(default=3, ge=1, le=5)
    execution_frequency: str = "daily"
    external_action_approval: bool = True


class MissionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    goal: str = Field(min_length=10, max_length=5000)
    constraints: MissionConstraints = Field(default_factory=MissionConstraints)
    competitive_benchmarking: bool = False
    clarification_answers: dict[str, str] = Field(default_factory=dict)


class Mission(MissionCreate):
    mission_id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["INTAKE", "DESIGNING", "READY"] = "INTAKE"


class ClarifyingAnswers(BaseModel):
    answers: dict[str, str]


class ClarifyingQuestion(BaseModel):
    question_id: str
    prompt: str
    category: str
    options: list[str] = Field(default_factory=list)
    rationale: str | None = None
    allow_custom: bool = True
    default_answer: str | None = None


class WorkflowStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    capability_id: str
    parameters: dict = Field(default_factory=dict)
    retries: int = Field(default=1, ge=0, le=10)
    depends_on: list[str] = Field(default_factory=list)
    requires_step_challenge: bool = False


class CapabilityGapWarning(BaseModel):
    capability_id: str
    reason: str
    resolution: str = "Resolve during the architecture challenge gate."


class FleetAgentProposal(BaseModel):
    agent_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    role: str
    scope: str
    bound_skills: list[str] = Field(default_factory=list)
    bound_tools: list[str] = Field(default_factory=list)
    capability_gaps: list[CapabilityGapWarning] = Field(default_factory=list)
    trigger_policy: TriggerKind = TriggerKind.CRON
    schedule: str = "0 8 * * *"
    upstream_agent_ids: list[str] = Field(default_factory=list)
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    assigned_llm: ModelRef


class FleetProposal(BaseModel):
    model_config = ConfigDict(title="fleetcontrol.proposal/v1")

    schema_version: Literal["fleetcontrol.proposal/v1"] = "fleetcontrol.proposal/v1"
    mission_id: str
    agents: list[FleetAgentProposal] = Field(min_length=1)
    challenge_gate_required: bool = True


class PolicyRule(BaseModel):
    capability_id: str
    risk_level: RiskLevel
    requires_approval: bool


class Blueprint(BaseModel):
    model_config = ConfigDict(frozen=True)

    blueprint_id: str = Field(default_factory=lambda: str(uuid4()))
    mission_id: str
    version: int = 1
    state: Literal["DRAFT", "READY"] = "DRAFT"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agents: tuple[FleetAgentProposal, ...]
    policy: tuple[PolicyRule, ...]

    def managed_fields(self) -> dict[str, dict]:
        return {agent.agent_id: agent.model_dump(mode="json") for agent in self.agents}


class PlannedChange(BaseModel):
    action: PlanAction
    target: str
    reason: str


class ReconciliationPlan(BaseModel):
    blueprint_id: str
    changes: list[PlannedChange]


class EvidenceCreate(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    fleet_id: str
    agent_id: str
    workflow_cycle_id: str
    step_id: str
    claim: str
    epistemic_basis: EpistemicBasis
    transcript: str = ""
    supporting_quote: str | None = None
    trace_available: bool = False
    policy_blocked: bool = False

    @model_validator(mode="after")
    def prohibit_agent_judgment(self) -> EvidenceCreate:
        if self.epistemic_basis is EpistemicBasis.JUDGMENT:
            raise ValueError("Agents cannot emit JUDGMENT; escalate to a human Decision Room.")
        return self


class AssuranceResult(BaseModel):
    evidence_id: str
    verdict: AssuranceVerdict
    rationale: str
    trace_id: str | None = None


class DecisionRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str = ""


class ChallengeGateCreate(BaseModel):
    stage: str = Field(min_length=2, max_length=48)
    challenge_snapshot: dict


class ChallengeGateDecision(BaseModel):
    decision: Literal["APPROVE", "RETURN"]
    feedback: str = Field(default="", max_length=4000)


class ReconciliationApprovalRequest(BaseModel):
    confirm_changes: bool = False
    confirm_removals: bool = False
    confirm_external_actions: bool = False


class DaemonHeartbeatRequest(BaseModel):
    status: Literal["RUNNING", "SUCCEEDED", "FAILED"] = "RUNNING"
    last_error: str | None = Field(default=None, max_length=4000)


class WorkflowTriggerRequest(BaseModel):
    event_id: str = Field(default="scheduled", min_length=1, max_length=200)
    source_agent_id: str | None = Field(default=None, max_length=120)
    payload: dict = Field(default_factory=dict)
    resume_workflow_cycle_id: str | None = Field(default=None, max_length=120)
    resume_step_id: str | None = Field(default=None, max_length=120)


class ToolHookEvent(BaseModel):
    hook_event_name: Literal["pre_tool_call", "post_tool_call"]
    session_id: str = Field(min_length=1, max_length=120)
    tool_name: str = Field(min_length=1, max_length=240)


class EmailDispatchRequest(BaseModel):
    room_id: str
    recipient: str
    subject: str = Field(min_length=3, max_length=180)


class FormSchemaRequest(BaseModel):
    title: str = "Governance decision"
    properties: dict[str, dict]
    required: list[str] = Field(default_factory=list)


class FormSubmissionRequest(BaseModel):
    values: dict


class TelemetrySummary(BaseModel):
    active_fleets: int
    active_agents: int
    workflow_cycles_24h: int
    workflow_cycles_7d: int = 0
    pending_challenge_gates: int
    policy_blocks_24h: int
    avg_cycle_duration_seconds: float
    avg_step_execution_latency_seconds: float = 0
    avg_challenge_turnaround_seconds: float = 0
    avg_reconciliation_seconds: float = 0
    daily_budget_burn_usd: float
    assurance_verdicts: dict[AssuranceVerdict, int]
    hourly_cycles: list[dict] = Field(default_factory=list)
    model_distribution: dict[str, int] = Field(default_factory=dict)
    skill_tool_utilization: dict[str, int] = Field(default_factory=dict)