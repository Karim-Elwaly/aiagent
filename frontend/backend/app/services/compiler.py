from app.schemas.domain import (
    Blueprint,
    FleetProposal,
    HermesEstateInventory,
    PlanAction,
    PlannedChange,
    ReconciliationPlan,
    RiskLevel,
)


def parse_proposal(proposal: FleetProposal, inventory: HermesEstateInventory) -> FleetProposal:
    skills = {skill.skill_id for skill in inventory.installed_skills}
    skills_by_id = {skill.skill_id: skill for skill in inventory.installed_skills}
    tools = {tool.tool_id: tool for tool in inventory.registered_tools}
    models = {(model.family, model.version) for model in inventory.available_models}
    errors = []
    ordered_steps_by_agent = {}
    for agent in proposal.agents:
        invalid_skills = set(agent.bound_skills) - skills
        invalid_tools = set(agent.bound_tools) - tools.keys()
        if invalid_skills:
            errors.append(f"{agent.name} binds unknown skills: {', '.join(sorted(invalid_skills))}")
        if invalid_tools:
            errors.append(f"{agent.name} binds unknown tools: {', '.join(sorted(invalid_tools))}")
        for skill_id in set(agent.bound_skills) & skills:
            missing_required_tools = set(skills_by_id[skill_id].required_tools) - set(agent.bound_tools)
            if missing_required_tools:
                errors.append(
                    f"{agent.name} is missing required tools for {skill_id}: "
                    f"{', '.join(sorted(missing_required_tools))}"
                )
        if (agent.assigned_llm.family, agent.assigned_llm.version) not in models:
            errors.append(f"{agent.name} uses a model absent from the live estate.")
        allowed = set(agent.bound_skills) | set(agent.bound_tools)
        try:
            ordered_steps_by_agent[agent.agent_id] = order_workflow_steps(agent.workflow_steps)
        except ValueError as error:
            errors.append(f"{agent.name} workflow DAG is invalid: {error}")
        for step in agent.workflow_steps:
            if step.capability_id not in allowed and not step.capability_id.startswith("stage:"):
                errors.append(f"{agent.name} workflow step references unbound capability {step.capability_id}.")
    if errors:
        raise ValueError(" ".join(errors))
    return proposal.model_copy(
        update={
            "agents": [
                agent.model_copy(update={"workflow_steps": ordered_steps_by_agent[agent.agent_id]})
                for agent in proposal.agents
            ]
        }
    )


def order_workflow_steps(steps):
    by_id = {step.step_id: step for step in steps}
    if len(by_id) != len(steps):
        raise ValueError("step IDs must be unique")
    unknown_dependencies = {
        dependency
        for step in steps
        for dependency in step.depends_on
        if dependency not in by_id
    }
    if unknown_dependencies:
        raise ValueError(f"unknown dependencies: {', '.join(sorted(unknown_dependencies))}")
    original_order = {step.step_id: index for index, step in enumerate(steps)}
    pending = {step_id: set(step.depends_on) for step_id, step in by_id.items()}
    ordered = []
    while pending:
        ready = sorted(
            (step_id for step_id, dependencies in pending.items() if not dependencies),
            key=original_order.__getitem__,
        )
        if not ready:
            raise ValueError("dependencies contain a cycle")
        for step_id in ready:
            ordered.append(by_id[step_id])
            pending.pop(step_id)
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return ordered


def to_blueprint(proposal: FleetProposal, inventory: HermesEstateInventory) -> Blueprint:
    proposal = parse_proposal(proposal, inventory)
    tools = {tool.tool_id: tool for tool in inventory.registered_tools}
    used_tools = {tool_id for agent in proposal.agents for tool_id in agent.bound_tools}
    policy = tuple(
        {
            "capability_id": tool_id,
            "risk_level": tools[tool_id].risk_level,
            "requires_approval": tools[tool_id].requires_hitl_approval
            or tools[tool_id].risk_level is not RiskLevel.READ_ONLY,
        }
        for tool_id in sorted(used_tools)
    )
    return Blueprint(
        mission_id=proposal.mission_id,
        state=(
            "READY"
            if inventory.connected
            and inventory.provider_configured is not False
            and not any(agent.capability_gaps for agent in proposal.agents)
            else "DRAFT"
        ),
        agents=tuple(proposal.agents),
        policy=policy,
    )


def compute_plan(blueprint: Blueprint, live_agents: dict[str, dict] | None = None) -> ReconciliationPlan:
    live_agents = live_agents or {}
    desired = blueprint.managed_fields()
    changes = []
    for agent_id, agent in desired.items():
        current = live_agents.get(agent_id)
        if current is None:
            changes.append(PlannedChange(action=PlanAction.CREATE, target=agent_id, reason="Agent is absent from Hermes."))
        elif current.get("managed_state") == "REMOVED":
            changes.append(PlannedChange(action=PlanAction.CREATE, target=agent_id, reason="Agent was previously removed."))
        elif current.get("specification", current) != agent:
            changes.append(PlannedChange(action=PlanAction.UPDATE, target=agent_id, reason="Managed fields differ from the blueprint."))
        if any(rule.capability_id in agent["bound_tools"] and rule.requires_approval for rule in blueprint.policy):
            changes.append(
                PlannedChange(
                    action=PlanAction.APPROVAL_REQUIRED,
                    target=agent_id,
                    reason="One or more bound tools require human approval before execution.",
                )
            )
    for agent_id, current in live_agents.items():
        if current.get("managed_by") == "fleet-studio" and current.get("managed_state") != "REMOVED" and agent_id not in desired:
            changes.append(PlannedChange(action=PlanAction.REMOVE, target=agent_id, reason="Agent is no longer declared."))
    return ReconciliationPlan(blueprint_id=blueprint.blueprint_id, changes=changes)