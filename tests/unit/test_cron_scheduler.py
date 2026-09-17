"""
Unit tests for CronScheduler and cron expression parser.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.core.scheduler_models import ScheduleCreateRequest, ScheduleUpdateRequest
from src.orchestrator.cron_scheduler import CronScheduler, is_cron_due


def test_is_cron_due():
    # dt: 2026-09-17 14:30:00 UTC (Thursday)
    dt = datetime(2026, 9, 17, 14, 30, 0, tzinfo=timezone.utc)
    # Thursday is weekday 4 in isoweekday()

    assert is_cron_due("* * * * *", dt) is True
    assert is_cron_due("30 14 * * *", dt) is True
    assert is_cron_due("*/15 * * * *", dt) is True
    assert is_cron_due("*/10 * * * *", dt) is True
    assert is_cron_due("0 14 * * *", dt) is False
    assert is_cron_due("30 15 * * *", dt) is False
    assert is_cron_due("30 14 17 9 *", dt) is True
    assert is_cron_due("invalid expression", dt) is False


def test_scheduler_crud(tmp_path: Path, monkeypatch):
    import src.orchestrator.cron_scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "SCHEDULES_FILE", tmp_path / "schedules.json")

    scheduler = CronScheduler()
    assert len(scheduler.list_jobs()) == 0

    # 1. Add job
    req = ScheduleCreateRequest(
        name="Daily SOC Audit",
        cron_expression="0 8 * * *",
        query="Audit security logs for failed authentications",
        agent_id="security-analyst",
    )
    job = scheduler.add_job(req)
    assert job.name == "Daily SOC Audit"
    assert job.cron_expression == "0 8 * * *"
    assert len(scheduler.list_jobs()) == 1

    # 2. Update job
    updated = scheduler.update_job(job.id, ScheduleUpdateRequest(cron_expression="*/30 * * * *"))
    assert updated is not None
    assert updated.cron_expression == "*/30 * * * *"

    # 3. Reload from file
    scheduler2 = CronScheduler()
    assert len(scheduler2.list_jobs()) == 1
    assert scheduler2.get_job(job.id).cron_expression == "*/30 * * * *"

    # 4. Delete job
    deleted = scheduler.delete_job(job.id)
    assert deleted is True
    assert len(scheduler.list_jobs()) == 0
