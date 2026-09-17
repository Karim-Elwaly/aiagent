"""
Unit tests for Custom Workflow Pipelines and Supervisor ReAct Evaluation.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from src.core.models import SupervisorEvaluation, TaskDAG, Task
from src.orchestrator.activities import evaluate_task_output
from src.api.main import app


def test_supervisor_evaluation_model():
    eval_pass = SupervisorEvaluation(
        decision="pass",
        confidence=0.95,
        feedback="Extracted all indicators correctly and verified log source.",
        missing_info=[],
        retry_prompt=None,
    )
    assert eval_pass.decision == "pass"
    assert eval_pass.confidence == 0.95

    eval_retry = SupervisorEvaluation(
        decision="retry",
        confidence=0.45,
        feedback="Missing source IP address and destination port.",
        missing_info=["src_ip", "dest_port"],
        retry_prompt="Please inspect network headers and extract src_ip and dest_port.",
    )
    assert eval_retry.decision == "retry"
    assert "src_ip" in eval_retry.missing_info


@pytest.mark.asyncio
async def test_evaluate_task_output_activity_pass():
    task_dict = {
        "id": "t1",
        "name": "Incident Triage",
        "description": "Parse alert details and evaluate severity",
        "expected_output": "Detailed triage analysis",
    }
    worker_output = "Triaged successfully. Severity: HIGH. 5 failed login attempts identified."
    user_query = "Investigate security incident"
    prior_completed = {}

    mock_llm_json = json.dumps({
        "decision": "pass",
        "confidence": 0.92,
        "feedback": "Output accurately addresses the triage requirements.",
        "missing_info": [],
        "retry_prompt": None,
    })

    with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm:
        mock_llm = mock_get_llm.return_value
        mock_llm.chat = AsyncMock(return_value=mock_llm_json)

        evaluation = await evaluate_task_output(task_dict, worker_output, user_query, prior_completed)
        assert evaluation["decision"] == "pass"
        assert evaluation["confidence"] == 0.92


@pytest.mark.asyncio
async def test_evaluate_task_output_activity_fallback_on_error():
    task_dict = {
        "id": "t2",
        "name": "Evidence Gathering",
        "description": "Extract IOCs from logs",
    }
    worker_output = "Task completed."
    user_query = "Forensic audit"
    prior_completed = {}

    with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm:
        mock_llm = mock_get_llm.return_value
        mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        # Should fallback gracefully without crashing
        evaluation = await evaluate_task_output(task_dict, worker_output, user_query, prior_completed)
        assert evaluation["decision"] in ["pass", "accurate"]


@pytest.mark.asyncio
async def test_workflow_templates_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/workflows/templates")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        template_ids = [t["id"] for t in data]
        assert "soc-5-phase-investigation" in template_ids
        assert "code-vulnerability-audit" in template_ids
        soc_tpl = next(t for t in data if t["id"] == "soc-5-phase-investigation")
        assert len(soc_tpl["tasks"]) == 5
        assert soc_tpl["tasks"][0]["id"] == "t1"
        assert soc_tpl["tasks"][4]["risk_level"] == "high"


@pytest.mark.asyncio
async def test_custom_dag_validation():
    custom_dag = {
        "goal": "Custom SOC Investigation",
        "reasoning": "User defined 2-phase pipeline",
        "tasks": [
            {
                "id": "t1",
                "name": "Phase 1: Alert Triage",
                "description": "Examine alert",
                "required_skills": ["alert_triage"],
                "dependencies": [],
                "risk_level": "low",
            },
            {
                "id": "t2",
                "name": "Phase 2: Action Proposal",
                "description": "Propose containment",
                "required_skills": ["containment_actions"],
                "dependencies": ["t1"],
                "risk_level": "high",
            },
        ],
    }

    dag = TaskDAG(**custom_dag)
    assert dag.goal == "Custom SOC Investigation"
    assert len(dag.tasks) == 2
    assert dag.tasks[0].id == "t1"
    assert dag.tasks[1].dependencies == ["t1"]
