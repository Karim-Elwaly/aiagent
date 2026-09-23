"""
UAOS Temporal Worker Runner

Starts a Temporal worker that polls for and executes UAOS activities.
This is the entry point for the worker process (run separately from the API).

Usage:
    python -m src.orchestrator.worker_runner
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from temporalio.client import Client
from temporalio.worker import Worker

from src.core.config import get_settings
from src.orchestrator.activities import (
    assemble_response,
    escalate_approval,
    evaluate_task_output,
    execute_task,
    notify_approval_required,
    plan_tasks,
    replan_tasks,
)
from src.orchestrator.workflow import UAOSWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Temporal worker."""
    settings = get_settings()

    logger.info(
        "Connecting to Temporal at %s (namespace: %s)",
        settings.temporal_host,
        settings.temporal_namespace,
    )

    while True:
        try:
            client = await Client.connect(
                settings.temporal_host,
                namespace=settings.temporal_namespace,
            )
            break
        except Exception as e:
            logger.info(
                "Temporal server not reached on %s (%s). Retrying in 10s... (Standalone engine is handling tasks in the meantime)",
                settings.temporal_host,
                e,
            )
            await asyncio.sleep(10.0)

    logger.info(
        "Starting worker on task queue: %s", settings.temporal_task_queue
    )

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[UAOSWorkflow],
        activities=[
            plan_tasks,
            execute_task,
            replan_tasks,
            assemble_response,
            escalate_approval,
            notify_approval_required,
            evaluate_task_output,
        ],
        # On SIGTERM/SIGINT (container stop, redeploy), let in-flight activities
        # finish a final heartbeat/checkpoint before the process exits so Temporal
        # can resume them cleanly on the next worker rather than waiting for the
        # heartbeat timeout to lapse.
        graceful_shutdown_timeout=timedelta(seconds=30),
    )

    logger.info("UAOS Worker is running. Press Ctrl+C to stop.")

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
