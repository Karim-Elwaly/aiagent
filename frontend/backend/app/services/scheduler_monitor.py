from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.schemas.domain import FleetAgentProposal, TriggerKind


def schedule_agent_workflow(
    scheduler: AsyncIOScheduler,
    agent: FleetAgentProposal,
    cycle: Callable[[str], Awaitable[None]],
) -> None:
    if agent.trigger_policy is TriggerKind.CRON:
        trigger = CronTrigger.from_crontab(agent.schedule)
        scheduler.add_job(cycle, trigger, args=[agent.agent_id], id=agent.agent_id, replace_existing=True)
    elif agent.trigger_policy is TriggerKind.CONTINUOUS_POLL:
        scheduler.add_job(
            cycle,
            "interval",
            seconds=30,
            args=[agent.agent_id],
            id=agent.agent_id,
            replace_existing=True,
        )
