"""
Scheduled Job Models for UAOS.

Defines schemas for recurring background workflows (Cron Automation).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ScheduledJob(BaseModel):
    """Configuration and state for a recurring scheduled workflow."""

    id: str = Field(description="Unique identifier for schedule, e.g. 'sched-audit-01'")
    name: str = Field(description="Human-readable schedule name")
    cron_expression: str = Field(description="Standard 5-part cron expression (e.g. '0 8 * * *')")
    query: str = Field(description="The problem query to execute automatically")
    agent_id: str | None = Field(default=None, description="Optional Agent Profile ID to use")
    enabled: bool = Field(default=True, description="Whether this schedule is active")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 creation timestamp",
    )
    last_run: str | None = Field(default=None, description="ISO timestamp of last execution")
    next_run: str | None = Field(default=None, description="ISO timestamp of next expected run")
    run_count: int = Field(default=0, description="Total number of times executed")
    last_status: str = Field(default="idle", description="Status of last execution (e.g. completed, running, failed)")


class ScheduleCreateRequest(BaseModel):
    """Request payload to create a new scheduled job."""

    name: str
    cron_expression: str = "0 8 * * *"
    query: str
    agent_id: str | None = None
    enabled: bool = True


class ScheduleUpdateRequest(BaseModel):
    """Request payload to update an existing scheduled job."""

    name: str | None = None
    cron_expression: str | None = None
    query: str | None = None
    agent_id: str | None = None
    enabled: bool | None = None
