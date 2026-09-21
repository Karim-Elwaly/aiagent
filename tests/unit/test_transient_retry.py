"""
Unit tests for durable retry of transient worker failures:

1. execute_task raises a retryable ApplicationError (TransientWorkerError)
   when the worker reports an LLM timeout / connection failure, so
   Temporal's RetryPolicy actually fires instead of receiving a
   "successful" activity result carrying status='failed'.
2. Genuine (non-transient) task failures are still returned normally.
3. The direct-mode helper _execute_task_with_retries retries transient
   failures with backoff and returns a failed dict on exhaustion, so one
   flaky phase does not kill the whole run.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from src.core.models import TaskResult, TaskStatus
from src.orchestrator.activities import execute_task


def _task_dict(task_id: str = "t7") -> dict:
    return {
        "id": task_id,
        "name": "Heavy analysis phase",
        "description": "Analyse all the things",
        "required_skills": ["general_reasoning"],
        "dependencies": [],
        "risk_level": "low",
    }


def _worker_returning(result: TaskResult) -> MagicMock:
    worker_cls = MagicMock()
    worker_cls.return_value.execute = AsyncMock(return_value=result)
    return worker_cls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_msg",
    [
        "LLM call timed out after 300s",
        "LLM call failed: Connection refused",
        "connection reset by peer",
    ],
)
async def test_execute_task_raises_on_transient_failure(error_msg):
    result = TaskResult(
        task_id="t7", status=TaskStatus.FAILED, output="", error=error_msg
    )
    with patch(
        "src.orchestrator.activities.UniversalWorkerAgent",
        _worker_returning(result),
    ), patch("src.orchestrator.activities._get_worker_llm", return_value=None):
        with pytest.raises(ApplicationError) as exc_info:
            await execute_task(_task_dict(), {}, "")

    assert exc_info.value.type == "TransientWorkerError"
    assert not exc_info.value.non_retryable
    assert error_msg in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_task_returns_non_transient_failure():
    """A genuine task failure (not infra) must NOT raise — no point retrying."""
    result = TaskResult(
        task_id="t7",
        status=TaskStatus.FAILED,
        output="",
        error="Tool 'query_evidence' rejected the parameters",
    )
    with patch(
        "src.orchestrator.activities.UniversalWorkerAgent",
        _worker_returning(result),
    ), patch("src.orchestrator.activities._get_worker_llm", return_value=None):
        out = await execute_task(_task_dict(), {}, "")

    assert out["status"] == "failed"
    assert "rejected" in out["error"]


@pytest.mark.asyncio
async def test_execute_task_returns_completed_normally():
    result = TaskResult(
        task_id="t7", status=TaskStatus.COMPLETED, output="findings here"
    )
    with patch(
        "src.orchestrator.activities.UniversalWorkerAgent",
        _worker_returning(result),
    ), patch("src.orchestrator.activities._get_worker_llm", return_value=None):
        out = await execute_task(_task_dict(), {}, "")

    assert out["status"] == "completed"
    assert out["output"] == "findings here"


@pytest.mark.asyncio
async def test_direct_retry_recovers_after_transient_failure():
    from src.api.main import _execute_task_with_retries

    transient = ApplicationError(
        "Transient worker failure on task 't7': LLM call timed out after 300s",
        type="TransientWorkerError",
        non_retryable=False,
    )
    mock_exec = AsyncMock(
        side_effect=[transient, {"status": "completed", "output": "ok"}]
    )
    with patch("src.api.main.execute_task", mock_exec), patch(
        "src.api.main.asyncio.sleep", new=AsyncMock()
    ):
        out = await _execute_task_with_retries(_task_dict(), {}, "")

    assert out["status"] == "completed"
    assert mock_exec.await_count == 2


@pytest.mark.asyncio
async def test_direct_retry_exhaustion_returns_failed_dict():
    from src.api.main import _execute_task_with_retries

    transient = ApplicationError(
        "Transient worker failure on task 't7': LLM call timed out after 300s",
        type="TransientWorkerError",
        non_retryable=False,
    )
    mock_exec = AsyncMock(side_effect=transient)
    task = _task_dict()
    task["max_retries"] = 1  # 2 attempts total
    with patch("src.api.main.execute_task", mock_exec), patch(
        "src.api.main.asyncio.sleep", new=AsyncMock()
    ):
        out = await _execute_task_with_retries(task, {}, "")

    assert out["status"] == "failed"
    assert "after 2 attempts" in out["error"]
    assert "timed out" in out["error"]
    assert mock_exec.await_count == 2


@pytest.mark.asyncio
async def test_direct_retry_passes_through_non_transient_exception():
    """Non-ApplicationError exceptions propagate (outer handler owns them)."""
    from src.api.main import _execute_task_with_retries

    mock_exec = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("src.api.main.execute_task", mock_exec):
        with pytest.raises(RuntimeError):
            await _execute_task_with_retries(_task_dict(), {}, "")

    assert mock_exec.await_count == 1
