"""
Cron Scheduler for UAOS Recurring Workflows.

Manages persistent cron schedules in data/schedules.json and dispatches
recurring problem solving workflows automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine
from uuid import uuid4

from src.core.config import ROOT_DIR
from src.core.scheduler_models import ScheduledJob, ScheduleCreateRequest, ScheduleUpdateRequest

logger = logging.getLogger(__name__)

SCHEDULES_FILE = ROOT_DIR / "data" / "schedules.json"


def _field_matches(pattern: str, val: int) -> bool:
    """Check if an integer value satisfies a single cron field pattern."""
    pattern = pattern.strip()
    if pattern == "*":
        return True
    if pattern.startswith("*/"):
        try:
            step = int(pattern[2:])
            return step > 0 and (val % step == 0)
        except ValueError:
            return False
    if "," in pattern:
        return any(_field_matches(part, val) for part in pattern.split(","))
    if "-" in pattern:
        try:
            start, end = map(int, pattern.split("-", 1))
            return start <= val <= end
        except ValueError:
            return False
    try:
        return int(pattern) == val
    except ValueError:
        return False


def is_cron_due(cron_expr: str, dt: datetime) -> bool:
    """Evaluate if a 5-part cron expression is due at datetime dt."""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False

    min_p, hour_p, dom_p, mon_p, dow_p = parts
    dow_val = dt.isoweekday() % 7  # 0=Sunday, 1=Monday ... 6=Saturday

    return (
        _field_matches(min_p, dt.minute)
        and _field_matches(hour_p, dt.hour)
        and _field_matches(dom_p, dt.day)
        and _field_matches(mon_p, dt.month)
        and _field_matches(dow_p, dow_val)
    )


class CronScheduler:
    """Manages scheduled recurring problem workflows in UAOS."""

    def __init__(self, dispatch_fn: Callable[[str, str | None], Coroutine[Any, Any, str]] | None = None) -> None:
        self.dispatch_fn = dispatch_fn
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_checked_minute = -1
        self._load()

    def _load(self) -> None:
        """Load jobs from persistent storage."""
        if SCHEDULES_FILE.exists():
            try:
                with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    job = ScheduledJob.model_validate(item)
                    self._jobs[job.id] = job
                logger.info("Loaded %d scheduled jobs from %s", len(self._jobs), SCHEDULES_FILE)
            except Exception as e:
                logger.warning("Failed to load schedules from %s: %s", SCHEDULES_FILE, e)

    def _save(self) -> None:
        """Persist jobs to disk."""
        SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
                json.dump([j.model_dump() for j in self._jobs.values()], f, indent=2)
        except Exception as e:
            logger.error("Failed to save schedules to %s: %s", SCHEDULES_FILE, e)

    def list_jobs(self) -> list[ScheduledJob]:
        """Return all registered scheduled jobs."""
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> ScheduledJob | None:
        """Get job by ID."""
        return self._jobs.get(job_id)

    def add_job(self, req: ScheduleCreateRequest) -> ScheduledJob:
        """Create and persist a new scheduled job."""
        job_id = f"sched-{uuid4().hex[:8]}"
        job = ScheduledJob(
            id=job_id,
            name=req.name,
            cron_expression=req.cron_expression,
            query=req.query,
            agent_id=req.agent_id,
            enabled=req.enabled,
        )
        self._jobs[job.id] = job
        self._save()
        logger.info("Created scheduled job '%s' (%s, cron: %s)", job.name, job.id, job.cron_expression)
        return job

    def update_job(self, job_id: str, req: ScheduleUpdateRequest) -> ScheduledJob | None:
        """Update an existing scheduled job."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        if req.name is not None:
            job.name = req.name
        if req.cron_expression is not None:
            job.cron_expression = req.cron_expression
        if req.query is not None:
            job.query = req.query
        if req.agent_id is not None:
            job.agent_id = req.agent_id
        if req.enabled is not None:
            job.enabled = req.enabled

        self._save()
        logger.info("Updated scheduled job '%s'", job.id)
        return job

    def delete_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            logger.info("Deleted scheduled job '%s'", job_id)
            return True
        return False

    async def start(self) -> None:
        """Start the background cron evaluation loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("CronScheduler background service started")

    async def stop(self) -> None:
        """Stop the background cron evaluation loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CronScheduler background service stopped")

    async def _loop(self) -> None:
        """Periodic loop that checks for due jobs once every 20 seconds."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                current_min = now.minute

                # Avoid running multiple times in the same minute
                if current_min != self._last_checked_minute:
                    self._last_checked_minute = current_min
                    await self._check_and_dispatch(now)

            except Exception as e:
                logger.error("Error in CronScheduler loop: %s", e)

            await asyncio.sleep(20.0)

    async def _check_and_dispatch(self, now: datetime) -> None:
        """Check all enabled jobs and trigger those due."""
        for job in list(self._jobs.values()):
            if not job.enabled:
                continue

            if is_cron_due(job.cron_expression, now):
                logger.info("Cron job '%s' (%s) is due. Dispatching...", job.name, job.id)
                job.last_run = now.isoformat()
                job.run_count += 1
                job.last_status = "running"
                self._save()

                if self.dispatch_fn:
                    asyncio.create_task(self._execute_job(job))

    async def _execute_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job asynchronously."""
        try:
            wf_id = await self.dispatch_fn(job.query, job.agent_id)
            job.last_status = f"dispatched ({wf_id})"
            logger.info("Scheduled job '%s' successfully dispatched: %s", job.name, wf_id)
        except Exception as e:
            job.last_status = f"failed: {e}"
            logger.error("Scheduled job '%s' execution failed: %s", job.name, e)
        finally:
            self._save()
