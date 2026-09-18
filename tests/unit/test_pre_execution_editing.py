"""
Unit tests for Pre-Execution DAG Parameter & Configuration Editing.

Verifies:
1. Custom DAG payload serialization with edited parameters, risk levels, and injected operator guidance
2. Task model properly validates pre-execution parameter overrides
3. Custom DAG execution properly passes parameter overrides and guidance to worker activities
4. Risk level elevation (e.g. low -> high) before execution properly triggers approval gate handling
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app, run_direct_workflow
from src.core.models import RiskLevel, Task, TaskDAG


@pytest.fixture
def clean_app_state():
    app.state.direct_workflows = {}
    yield app.state.direct_workflows
    app.state.direct_workflows = {}


def test_task_model_with_customized_parameters_and_guidance():
    """Verify Task model accepts custom parameters and operator guidance."""
    task_dict = {
        "id": "t1",
        "name": "Customized Log Triage",
        "description": "Parse security logs\n\n[OPERATOR GUIDANCE]: Focus only on IP 192.168.1.50",
        "required_skills": ["file_reading", "log_forensics"],
        "dependencies": [],
        "risk_level": "high",
        "parameters": {
            "timeout_seconds": 45,
            "max_log_lines": 500,
            "target_ip": "192.168.1.50",
            "operator_guidance": "Focus only on IP 192.168.1.50",
        },
    }

    task = Task.model_validate(task_dict)
    assert task.id == "t1"
    assert task.risk_level == RiskLevel.HIGH
    assert task.parameters["max_log_lines"] == 500
    assert task.parameters["target_ip"] == "192.168.1.50"
    assert "[OPERATOR GUIDANCE]" in task.description


@pytest.mark.asyncio
async def test_solve_endpoint_with_customized_pre_execution_dag():
    """Verify POST /solve accepts pre-execution customized DAG with parameters and executes cleanly."""
    custom_dag = {
        "goal": "Customized Investigation",
        "reasoning": "Operator adjusted parameters ahead of execution",
        "tasks": [
            {
                "id": "t1",
                "name": "Targeted Discovery",
                "description": "Enumerate files\n\n[OPERATOR GUIDANCE]: Only inspect .json files",
                "required_skills": ["file_reading"],
                "dependencies": [],
                "risk_level": "low",
                "parameters": {"file_extension": ".json", "max_items": 15},
            },
        ],
    }

    mock_exec = AsyncMock(return_value={
        "status": "completed",
        "output": "Found 3 .json files",
        "execution_time_ms": 40,
        "tool_calls_made": ["read_file"],
    })
    mock_assemble = AsyncMock(return_value="All 3 .json files verified.")
    mock_eval = AsyncMock(return_value={"decision": "pass", "confidence": 0.98})

    with patch("src.api.main.execute_task", mock_exec), \
         patch("src.api.main.assemble_response", mock_assemble), \
         patch("src.api.main.evaluate_task_output", mock_eval):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/solve",
                json={
                    "query": "Investigate json logs",
                    "custom_dag": custom_dag,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks_completed"] == 1
        assert data["response"] == "All 3 .json files verified."

        # Verify that execute_task received the custom parameters and guidance in task_dict
        executed_task_dict = mock_exec.call_args[0][0]
        assert executed_task_dict["parameters"]["file_extension"] == ".json"
        assert executed_task_dict["parameters"]["max_items"] == 15
        assert "[OPERATOR GUIDANCE]: Only inspect .json files" in executed_task_dict["description"]


@pytest.mark.asyncio
async def test_pre_execution_risk_elevation_triggers_approval_gate(clean_app_state):
    """Verify that editing risk level to 'high' before execution enforces approval gate."""
    # Task originally low risk, elevated to high risk by operator
    custom_dag = {
        "goal": "Elevated Risk Action",
        "reasoning": "Operator elevated risk level",
        "tasks": [
            {
                "id": "t1",
                "name": "Modify Configuration",
                "description": "Apply configuration changes",
                "required_skills": ["code_patching"],
                "dependencies": [],
                "risk_level": "high",  # Elevated risk
                "parameters": {"backup_first": True},
            },
        ],
    }

    workflow_id = "test-wf-risk-elevation"
    wf_task = asyncio.create_task(
        run_direct_workflow(
            workflow_id=workflow_id,
            user_query="Modify configuration",
            custom_dag=custom_dag,
        )
    )

    # Wait for workflow to hit approval gate
    for _ in range(50):
        await asyncio.sleep(0.02)
        state = app.state.direct_workflows.get(workflow_id, {})
        if state.get("awaiting_approval"):
            break

    state = app.state.direct_workflows.get(workflow_id, {})
    assert state.get("awaiting_approval") is True
    assert state.get("pending_task_id") == "t1"
    assert state.get("pending_task_risk") == "high"
    assert state.get("pending_task_params") == {"backup_first": True}

    # Cleanly resolve approval so background task exits
    approval_event = state.get("approval_event")
    state["approval_response"] = {"approved": True, "guidance": "Backup verified"}
    if approval_event:
        approval_event.set()

    mock_exec = AsyncMock(return_value={
        "status": "completed",
        "output": "Configuration applied cleanly.",
        "execution_time_ms": 30,
    })
    mock_assemble = AsyncMock(return_value="Done")
    mock_eval = AsyncMock(return_value={"decision": "pass", "confidence": 0.99})

    with patch("src.api.main.execute_task", mock_exec), \
         patch("src.api.main.assemble_response", mock_assemble), \
         patch("src.api.main.evaluate_task_output", mock_eval):

        result = await wf_task

    assert result["tasks_completed"] == 1
