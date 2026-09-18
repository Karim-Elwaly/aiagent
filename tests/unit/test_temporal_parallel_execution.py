"""
Unit tests for Parallel Activity Execution in UAOSWorkflow (Temporal).

Tests:
1. Diamond DAG parallel execution (T1 -> {T2, T3} in parallel -> T4)
2. Concurrency limiting (batches respect temporal_max_concurrent_activities)
3. Mixed-risk isolation (low-risk task executes immediately while high-risk waits for approval)
4. Error isolation (failure in one branch does not block independent branch)
5. Supervisor circuit breaker abort (halts downstream execution)
"""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.workflow import UAOSWorkflow


@pytest.mark.asyncio
async def test_diamond_dag_parallel_execution():
    """Verify that independent tasks T2 and T3 execute concurrently in UAOSWorkflow."""
    wf = UAOSWorkflow()

    # Diamond DAG: T1 -> (T2, T3) -> T4
    custom_dag = {
        "tasks": [
            {"id": "t1", "name": "Task 1", "dependencies": [], "risk_level": "low"},
            {"id": "t2", "name": "Task 2", "dependencies": ["t1"], "risk_level": "low"},
            {"id": "t3", "name": "Task 3", "dependencies": ["t1"], "risk_level": "low"},
            {"id": "t4", "name": "Task 4", "dependencies": ["t2", "t3"], "risk_level": "low"},
        ]
    }

    t2_t3_concurrency = {"max_concurrent": 0, "active": 0}
    execution_order = []

    async def mock_execute_activity(activity_fn, *args, **kwargs):
        fn_name = getattr(activity_fn, "__name__", str(activity_fn))
        activity_args = kwargs.get("args", [])

        if fn_name == "execute_task":
            task_dict = activity_args[0]
            tid = task_dict["id"]
            execution_order.append(f"start_{tid}")

            t2_t3_concurrency["active"] += 1
            if t2_t3_concurrency["active"] > t2_t3_concurrency["max_concurrent"]:
                t2_t3_concurrency["max_concurrent"] = t2_t3_concurrency["active"]

            # Small async yield to allow concurrent tasks in asyncio.gather to interleave
            await asyncio.sleep(0.05)

            t2_t3_concurrency["active"] -= 1
            execution_order.append(f"end_{tid}")
            return {
                "status": "completed",
                "output": f"Output from {tid}",
                "execution_time_ms": 50,
                "tool_calls_made": [],
            }

        elif fn_name == "evaluate_task_output":
            return {
                "decision": "pass",
                "confidence": 0.95,
                "feedback": "All good",
                "missing_info": [],
            }

        elif fn_name == "assemble_response":
            return "Synthesized final response from all 4 tasks."

        return {}

    with patch("temporalio.workflow.execute_activity", side_effect=mock_execute_activity), \
         patch("temporalio.workflow.logger", MagicMock()):

        result = await wf.run(user_query="Run diamond workflow", custom_dag=custom_dag)

    assert result["tasks_completed"] == 4
    assert result["tasks_failed"] == 0
    assert result["response"] == "Synthesized final response from all 4 tasks."

    # Verify T2 and T3 ran concurrently (active count reached 2)
    assert t2_t3_concurrency["max_concurrent"] == 2
    # Verify T1 completed before T2/T3, and T4 completed after both T2 and T3
    assert execution_order[0] == "start_t1"
    assert execution_order[1] == "end_t1"
    assert "start_t2" in execution_order[2:4]
    assert "start_t3" in execution_order[2:4]
    assert execution_order[-2] == "start_t4"
    assert execution_order[-1] == "end_t4"


@pytest.mark.asyncio
async def test_concurrency_limiting():
    """Verify that ready tasks are batched according to temporal_max_concurrent_activities."""
    wf = UAOSWorkflow()

    # 4 independent tasks with no dependencies
    custom_dag = {
        "tasks": [
            {"id": "t1", "name": "Task 1", "dependencies": [], "risk_level": "low"},
            {"id": "t2", "name": "Task 2", "dependencies": [], "risk_level": "low"},
            {"id": "t3", "name": "Task 3", "dependencies": [], "risk_level": "low"},
            {"id": "t4", "name": "Task 4", "dependencies": [], "risk_level": "low"},
        ]
    }

    concurrent_tracker = {"max": 0, "current": 0}

    async def mock_execute_activity(activity_fn, *args, **kwargs):
        fn_name = getattr(activity_fn, "__name__", str(activity_fn))
        activity_args = kwargs.get("args", [])

        if fn_name == "execute_task":
            tid = activity_args[0]["id"]
            concurrent_tracker["current"] += 1
            if concurrent_tracker["current"] > concurrent_tracker["max"]:
                concurrent_tracker["max"] = concurrent_tracker["current"]

            await asyncio.sleep(0.04)
            concurrent_tracker["current"] -= 1
            return {"status": "completed", "output": f"Done {tid}"}

        elif fn_name == "evaluate_task_output":
            return {"decision": "pass"}

        elif fn_name == "assemble_response":
            return "All tasks done"

        return {}

    # Mock settings with temporal_max_concurrent_activities = 2
    mock_settings = MagicMock()
    mock_settings.temporal_max_concurrent_activities = 2

    with patch("temporalio.workflow.execute_activity", side_effect=mock_execute_activity), \
         patch("src.orchestrator.workflow.get_settings", return_value=mock_settings), \
         patch("temporalio.workflow.logger", MagicMock()):

        result = await wf.run(user_query="Test concurrency limit", custom_dag=custom_dag)

    assert result["tasks_completed"] == 4
    # Max concurrency observed must not exceed the configured limit of 2
    assert concurrent_tracker["max"] <= 2


@pytest.mark.asyncio
async def test_mixed_risk_parallel_isolation():
    """Verify that a low-risk task executes immediately while a high-risk sibling waits for approval."""
    wf = UAOSWorkflow()

    # T1 (low risk) and T2 (high risk) are both ready initially
    custom_dag = {
        "tasks": [
            {"id": "t1", "name": "Low Risk Task", "dependencies": [], "risk_level": "low"},
            {"id": "t2", "name": "High Risk Task", "dependencies": [], "risk_level": "high"},
        ]
    }

    events = []

    async def mock_execute_activity(activity_fn, *args, **kwargs):
        fn_name = getattr(activity_fn, "__name__", str(activity_fn))
        activity_args = kwargs.get("args", [])

        if fn_name == "notify_approval_required":
            events.append("notified_t2")
            return True
        elif fn_name == "execute_task":
            tid = activity_args[0]["id"]
            events.append(f"executed_{tid}")
            return {"status": "completed", "output": f"Result {tid}"}
        elif fn_name == "evaluate_task_output":
            return {"decision": "pass"}
        elif fn_name == "assemble_response":
            return "Mixed risk pipeline done"
        return {}

    async def mock_wait_condition(fn, *args, **kwargs):
        # Simulate operator delaying approval until T1 is finished
        while not fn():
            await asyncio.sleep(0.01)

    async def simulate_human_approval():
        # Wait until T1 is executed and T2 is awaiting approval
        while "executed_t1" not in events or "t2" not in wf._pending_tasks:
            await asyncio.sleep(0.01)
        # Operator approves T2
        await wf.approve_task({"task_id": "t2", "approved": True, "guidance": "Proceed with care"})

    with patch("temporalio.workflow.execute_activity", side_effect=mock_execute_activity), \
         patch("temporalio.workflow.wait_condition", side_effect=mock_wait_condition), \
         patch("temporalio.workflow.logger", MagicMock()):

        workflow_task = asyncio.create_task(
            wf.run(user_query="Test mixed risk", custom_dag=custom_dag)
        )
        approval_task = asyncio.create_task(simulate_human_approval())

        result = await workflow_task
        await approval_task

    assert result["tasks_completed"] == 2
    assert "executed_t1" in events
    assert "executed_t2" in events
    # T1 must have executed BEFORE T2 was approved and executed
    assert events.index("executed_t1") < events.index("executed_t2")


@pytest.mark.asyncio
async def test_error_isolation_in_parallel_batch():
    """Verify that failure of T1 does not block independent sibling T2 from succeeding."""
    wf = UAOSWorkflow()

    # T1 and T2 run in parallel; T3 depends on T1 (will be cascaded/skipped); T4 depends on T2
    custom_dag = {
        "tasks": [
            {"id": "t1", "name": "Failing Task", "dependencies": [], "risk_level": "low"},
            {"id": "t2", "name": "Succeeding Task", "dependencies": [], "risk_level": "low"},
            {"id": "t3", "name": "Downstream of T1", "dependencies": ["t1"], "risk_level": "low"},
            {"id": "t4", "name": "Downstream of T2", "dependencies": ["t2"], "risk_level": "low"},
        ]
    }

    async def mock_execute_activity(activity_fn, *args, **kwargs):
        fn_name = getattr(activity_fn, "__name__", str(activity_fn))
        activity_args = kwargs.get("args", [])

        if fn_name == "execute_task":
            tid = activity_args[0]["id"]
            if tid == "t1":
                return {"status": "failed", "error": "Disk write failed"}
            return {"status": "completed", "output": f"Success {tid}"}
        elif fn_name == "evaluate_task_output":
            return {"decision": "pass"}
        elif fn_name == "assemble_response":
            return "Partial response with T2 and T4 outputs"
        return {}

    with patch("temporalio.workflow.execute_activity", side_effect=mock_execute_activity), \
         patch("temporalio.workflow.logger", MagicMock()):

        result = await wf.run(user_query="Test error isolation", custom_dag=custom_dag)

    # T2 and T4 succeed; T1 fails and T3 is cascaded/skipped
    assert result["tasks_completed"] == 2
    assert wf._task_statuses["t1"] == "failed"
    assert wf._task_statuses["t2"] == "completed"
    assert wf._task_statuses["t3"] == "skipped"
    assert wf._task_statuses["t4"] == "completed"


@pytest.mark.asyncio
async def test_circuit_breaker_abort_in_parallel_batch():
    """Verify that if supervisor evaluation triggers an abort, downstream tasks are halted."""
    wf = UAOSWorkflow()

    custom_dag = {
        "tasks": [
            {"id": "t1", "name": "Discovery", "dependencies": [], "risk_level": "low"},
            {"id": "t2", "name": "Analysis", "dependencies": ["t1"], "risk_level": "low"},
        ]
    }

    async def mock_execute_activity(activity_fn, *args, **kwargs):
        fn_name = getattr(activity_fn, "__name__", str(activity_fn))
        activity_args = kwargs.get("args", [])

        if fn_name == "execute_task":
            return {"status": "completed", "output": "Directory empty: 0 files enumerated"}
        elif fn_name == "evaluate_task_output":
            return {
                "decision": "abort",
                "confidence": 0.99,
                "feedback": "Target yielded 0 files. Halting pipeline.",
            }
        return {}

    with patch("temporalio.workflow.execute_activity", side_effect=mock_execute_activity), \
         patch("temporalio.workflow.logger", MagicMock()):

        result = await wf.run(user_query="Test circuit breaker", custom_dag=custom_dag)

    assert result["tasks_completed"] == 0
    assert wf._task_statuses["t1"] == "aborted"
    assert wf._task_statuses["t2"] == "aborted"
    assert "Errors" in result["response"]
