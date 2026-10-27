from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum


class InterceptDecision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    PAUSE_FOR_APPROVAL = "PAUSE_FOR_APPROVAL"


@dataclass(frozen=True)
class CapabilityPolicy:
    allowed_capabilities: frozenset[str]
    approval_required: frozenset[str]


class FleetControlPlugin:
    """Host adapter for Hermes skill/tool events; wire callbacks to Hermes 0.21 hooks."""

    def __init__(
        self,
        policies: dict[str, CapabilityPolicy],
        emit_evidence: Callable[[dict], Awaitable[None]],
    ) -> None:
        self.policies = policies
        self.emit_evidence = emit_evidence

    async def intercept(self, event: dict) -> InterceptDecision:
        agent_id = event.get("agent_id", "")
        capability_id = event.get("capability_id", "")
        policy = self.policies.get(agent_id)
        if policy is None or capability_id not in policy.allowed_capabilities:
            decision = InterceptDecision.BLOCK
        elif capability_id in policy.approval_required:
            decision = InterceptDecision.PAUSE_FOR_APPROVAL
        else:
            decision = InterceptDecision.ALLOW
        await self.emit_evidence(
            {
                "fleet_id": event.get("fleet_id"),
                "agent_id": agent_id,
                "workflow_cycle_id": event.get("workflow_cycle_id"),
                "step_id": event.get("step_id"),
                "capability_id": capability_id,
                "decision": decision.value,
                "parameters_redacted": True,
            }
        )
        return decision