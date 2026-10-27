from app.schemas.domain import (
    ClarifyingQuestion,
    FleetProposal,
    HermesEstateInventory,
    Mission,
)
from app.services.clarification_generator import generate_clarifying_questions
from app.services.fleet_composer import MissionFleetArchitect


async def clarifying_questions(
    mission: Mission,
    inventory: HermesEstateInventory | None = None,
) -> list[ClarifyingQuestion]:
    """Generate high-leverage clarifying questions for the mission."""
    return await generate_clarifying_questions(mission, inventory)


async def propose_fleet(mission: Mission, inventory: HermesEstateInventory) -> FleetProposal:
    """Compose a dynamic task-stage fleet tailored to the mission outcome and estate using LLM reasoning."""
    architect = MissionFleetArchitect(inventory=inventory)
    return await architect.compose_fleet_with_llm(mission, inventory)


def propose_fleet_sync(mission: Mission, inventory: HermesEstateInventory) -> FleetProposal:
    """Fast synchronous domain heuristics fleet composer."""
    architect = MissionFleetArchitect(inventory=inventory)
    return architect.compose_fleet(mission, inventory)