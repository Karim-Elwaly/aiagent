"""
Integration and simulation tests for UAOSWorkflow and DAG routing.
"""

import pytest

from src.orchestrator.workflow import UAOSWorkflow


def test_get_ready_tasks_initial():
    wf = UAOSWorkflow()
    dag_dict = {
        "goal": "Test goal",
        "reasoning": "Test",
        "tasks": [
            {
                "id": "t1",
                "name": "Task 1",
                "description": "First",
                "required_skills": ["web_search"],
                "dependencies": [],
            },
            {
                "id": "t2",
                "name": "Task 2",
                "description": "Second",
                "required_skills": ["file_read"],
                "dependencies": ["t1"],
            },
            {
                "id": "t3",
                "name": "Task 3",
                "description": "Parallel to t1",
                "required_skills": ["code_execution"],
                "dependencies": [],
            },
        ],
    }

    # Initially, t1 and t3 have no dependencies
    ready = wf._get_ready_tasks(dag_dict, completed={}, failed={})
    ready_ids = [t["id"] for t in ready]
    assert set(ready_ids) == {"t1", "t3"}

    # After t1 completes, t2 becomes ready (assuming t3 is done or in progress)
    ready = wf._get_ready_tasks(dag_dict, completed={"t1": "done"}, failed={})
    ready_ids = [t["id"] for t in ready]
    assert "t2" in ready_ids
    assert "t3" in ready_ids
    assert "t1" not in ready_ids


def test_get_ready_tasks_blocked_by_failure():
    wf = UAOSWorkflow()
    dag_dict = {
        "goal": "Test goal",
        "reasoning": "Test",
        "tasks": [
            {
                "id": "t1",
                "name": "Task 1",
                "description": "First",
                "dependencies": [],
            },
            {
                "id": "t2",
                "name": "Task 2",
                "description": "Depends on t1",
                "dependencies": ["t1"],
            },
        ],
    }

    # If t1 fails, t2 should NOT become ready because dependencies must be completed
    ready = wf._get_ready_tasks(dag_dict, completed={}, failed={"t1": "Error occurred"})
    assert len(ready) == 0


@pytest.mark.asyncio
async def test_approval_signal_handling():
    wf = UAOSWorkflow()
    assert wf._approval_result is None

    # Simulate sending approval signal
    await wf.approve_task(True)
    assert wf._approval_result is True

    # Check status query
    wf._pending_task_name = "Delete Database"
    wf._approval_result = None
    status = wf.get_status()
    assert status["awaiting_approval"] is True
    assert status["pending_task"] == "Delete Database"

    await wf.approve_task(False)
    assert wf._approval_result is False
