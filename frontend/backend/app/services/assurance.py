from opentelemetry import trace

from app.schemas.domain import AssuranceResult, AssuranceVerdict, EvidenceCreate

tracer = trace.get_tracer("fleet-studio.assurance")


def verify_evidence(evidence: EvidenceCreate) -> AssuranceResult:
    with tracer.start_as_current_span("fleet_studio.assurance.verify") as span:
        span.set_attributes(
            {
                "fleet_id": evidence.fleet_id,
                "agent_id": evidence.agent_id,
                "workflow_cycle_id": evidence.workflow_cycle_id,
                "step_id": evidence.step_id,
                "evidence_id": evidence.evidence_id,
            }
        )
        if evidence.policy_blocked:
            verdict = AssuranceVerdict.POLICY_BLOCKED
            rationale = "Execution was blocked by compiled policy."
        elif not evidence.trace_available or not evidence.transcript:
            verdict = AssuranceVerdict.NOT_VERIFIABLE
            rationale = "A correlated trace and Hermes transcript are both required for verification."
        elif evidence.supporting_quote and evidence.supporting_quote in evidence.transcript:
            verdict = AssuranceVerdict.EVIDENCE_FOUND
            rationale = "The supplied supporting quote appears in the correlated transcript."
        else:
            verdict = AssuranceVerdict.NO_EVIDENCE
            rationale = "No supporting quote was found in the correlated transcript."
        span.set_attribute("assurance.verdict", verdict.value)
        trace_id = f"{span.get_span_context().trace_id:032x}" if span.get_span_context().is_valid else None
    return AssuranceResult(evidence_id=evidence.evidence_id, verdict=verdict, rationale=rationale, trace_id=trace_id)