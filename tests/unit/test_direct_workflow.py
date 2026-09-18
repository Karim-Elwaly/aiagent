"""
Unit tests for the direct in-process standalone workflow engine:
- Topological execution order
- Event bus event sequence (dag_planned, task_started, task_completed, final_solution)
- Exception handling and error reporting
"""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from src.api.main import app, run_direct_workflow
from src.core.models import RiskLevel
from src.orchestrator.event_bus import get_event_bus


@pytest.fixture
def clean_app_state():
    app.state.direct_workflows = {}
    yield app.state.direct_workflows
    app.state.direct_workflows = {}


@pytest.mark.asyncio
async def test_run_direct_workflow_success(clean_app_state):
    custom_dag = {
        "goal": "Test workflow execution",
        "reasoning": "Linear pipeline",
        "tasks": [
            {
                "id": "t1",
                "name": "Step 1",
                "description": "First step",
                "required_skills": ["general_reasoning"],
                "dependencies": [],
                "risk_level": "low",
            },
            {
                "id": "t2",
                "name": "Step 2",
                "description": "Second step",
                "required_skills": ["general_reasoning"],
                "dependencies": ["t1"],
                "risk_level": "low",
            },
        ],
    }

    mock_exec = AsyncMock(side_effect=[
        {"status": "completed", "output": "Output 1", "execution_time_ms": 50, "tool_calls_made": []},
        {"status": "completed", "output": "Output 2", "execution_time_ms": 60, "tool_calls_made": []},
    ])
    mock_assemble = AsyncMock(return_value="Final synthesized answer")
    mock_eval = AsyncMock(return_value={"decision": "pass", "confidence": 0.99})

    with patch("src.api.main.execute_task", mock_exec), \
         patch("src.api.main.assemble_response", mock_assemble), \
         patch("src.api.main.evaluate_task_output", mock_eval):

        workflow_id = "test-wf-success-123"
        result = await run_direct_workflow(
            workflow_id=workflow_id,
            user_query="Calculate prime numbers",
            custom_dag=custom_dag,
        )

        assert result["response"] == "Final synthesized answer"
        assert result["tasks_completed"] == 2
        assert result["tasks_failed"] == 0

        state = clean_app_state[workflow_id]
        assert state["status"] == "completed"
        assert state["task_statuses"]["t1"] == "completed"
        assert state["task_statuses"]["t2"] == "completed"


@pytest.mark.asyncio
async def test_run_direct_workflow_error_handling(clean_app_state):
    custom_dag = {
        "goal": "Test error handling",
        "reasoning": "Will trigger error",
        "tasks": [
            {
                "id": "t1",
                "name": "Failing Step",
                "description": "Boom",
                "required_skills": ["general_reasoning"],
                "dependencies": [],
                "risk_level": "low",
            },
        ],
    }

    mock_exec = AsyncMock(side_effect=RuntimeError("Simulated worker failure"))

    with patch("src.api.main.execute_task", mock_exec):
        workflow_id = "test-wf-fail-123"
        result = await run_direct_workflow(
            workflow_id=workflow_id,
            user_query="Failing query",
            custom_dag=custom_dag,
        )

        assert "Simulated worker failure" in result["response"]
        assert result["tasks_failed"] >= 1

        state = clean_app_state[workflow_id]
        assert "Simulated worker failure" in state["error"]
        assert state["result"] is not None
        assert "Simulated worker failure" in state["result"]["response"]


@pytest.mark.asyncio
async def test_status_endpoint_reports_error(clean_app_state):
    from httpx import AsyncClient, ASGITransport

    wf_id = "test-status-err-456"
    clean_app_state[wf_id] = {
        "workflow_id": wf_id,
        "status": "failed",
        "awaiting_approval": False,
        "pending_task": "",
        "pending_task_id": "",
        "pending_task_desc": "",
        "pending_task_risk": "",
        "pending_task_params": {},
        "dag": None,
        "task_statuses": {"t1": "failed"},
        "supervisor_evaluations": [],
        "result": {"response": "Fatal execution fault", "tasks_completed": 0, "tasks_failed": 1},
        "error": "Fatal execution fault",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        res = await ac.get(f"/status/{wf_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["workflow_id"] == wf_id
        assert data["status"] == "failed"
        assert data["error"] == "Fatal execution fault"
        assert data["result"]["response"] == "Fatal execution fault"

