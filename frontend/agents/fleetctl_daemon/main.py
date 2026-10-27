import asyncio
import json
import logging
import os
import socket
from uuid import uuid4

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.schemas.domain import FleetAgentProposal, TriggerKind
from app.services.scheduler_monitor import schedule_agent_workflow

try:
    from hermes_profile_materializer import HermesProfileMaterializer
except ImportError:
    from agents.fleetctl_daemon.hermes_profile_materializer import HermesProfileMaterializer

logger = logging.getLogger("fleetctl.daemon")


API_URL = os.environ.get("FLEET_STUDIO_API_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.environ.get("FLEET_STUDIO_DAEMON_TOKEN", "")
WORKER_ID = os.environ.get("FLEET_STUDIO_DAEMON_ID", f"{socket.gethostname()}-{uuid4().hex[:8]}")


async def _cycle(client: httpx.AsyncClient, agent_id: str, trigger_context: dict | None = None) -> None:
    response = await client.post(
        f"/api/v1/daemon/workflow-cycles/{agent_id}",
        json={"event_id": "scheduled", "payload": trigger_context or {}},
        timeout=650,
    )
    response.raise_for_status()


def _cycle_callback(client: httpx.AsyncClient):
    async def scheduled_cycle(agent_id: str) -> None:
        await _cycle(client, agent_id)

    return scheduled_cycle


async def _replace_schedules(client: httpx.AsyncClient, scheduler: AsyncIOScheduler) -> set[str]:
    response = await client.get("/api/v1/daemon/agents")
    response.raise_for_status()
    active_ids = set()
    signatures: dict[str, str] = getattr(scheduler, "_fleet_signatures", {})
    cycle_callback = _cycle_callback(client)
    for raw_agent in response.json().get("agents", []):
        agent = FleetAgentProposal.model_validate(raw_agent)
        if agent.trigger_policy in {TriggerKind.CRON, TriggerKind.CONTINUOUS_POLL}:
            active_ids.add(agent.agent_id)
            signature = json.dumps(agent.model_dump(mode="json"), sort_keys=True)
            if signatures.get(agent.agent_id) != signature:
                schedule_agent_workflow(scheduler, agent, cycle_callback)
                signatures[agent.agent_id] = signature
    for job in scheduler.get_jobs():
        if job.id not in active_ids:
            scheduler.remove_job(job.id)
            signatures.pop(job.id, None)
    scheduler._fleet_signatures = signatures
    return active_ids


async def _apply_job(client: httpx.AsyncClient, job: dict, scheduler: AsyncIOScheduler) -> None:
    job_id = job["job_id"]
    job_type = job.get("job_type")
    status = "SUCCEEDED"
    last_error = None
    try:
        if job_type == "RECONCILE_BLUEPRINT":
            blueprint = job.get("payload", {}).get("blueprint", {})
            if not blueprint.get("agents"):
                raise ValueError("Reconciliation job has an empty agent roster.")
            materializer = HermesProfileMaterializer()
            mat_result = materializer.materialize_blueprint(blueprint)
            logger.info("Materialized blueprint into Hermes host profiles: %s", mat_result)
        elif job_type == "RUN_AGENT_CYCLE":
            payload = job.get("payload", {})
            await _cycle(client, payload["agent_id"], payload.get("trigger_context"))
        else:
            raise ValueError(f"Unsupported daemon job type: {job_type}")
    except Exception as error:
        status = "FAILED"
        last_error = str(error)[:4000]
    heartbeat = await client.post(
        f"/api/v1/daemon/jobs/{job_id}/heartbeat",
        json={"status": status, "last_error": last_error},
        headers={"X-Fleet-Daemon-Id": WORKER_ID},
    )
    heartbeat.raise_for_status()
    if status == "SUCCEEDED" and job_type == "RECONCILE_BLUEPRINT":
        await _replace_schedules(client, scheduler)


async def run() -> None:
    if not TOKEN:
        raise RuntimeError("FLEET_STUDIO_DAEMON_TOKEN is required")
    headers = {"X-Fleet-Daemon-Token": TOKEN, "X-Fleet-Daemon-Id": WORKER_ID}
    timeout = httpx.Timeout(connect=10, read=35, write=10, pool=10)
    scheduler = AsyncIOScheduler()
    scheduler.start()
    try:
        async with httpx.AsyncClient(base_url=API_URL, headers=headers, timeout=timeout) as client:
            await _replace_schedules(client, scheduler)
            last_sync = asyncio.get_running_loop().time()
            while True:
                if asyncio.get_running_loop().time() - last_sync >= 30:
                    await _replace_schedules(client, scheduler)
                    last_sync = asyncio.get_running_loop().time()
                response = await client.get("/api/v1/daemon/jobs", params={"wait": 15})
                response.raise_for_status()
                for job in response.json().get("jobs", []):
                    await _apply_job(client, job, scheduler)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(run())