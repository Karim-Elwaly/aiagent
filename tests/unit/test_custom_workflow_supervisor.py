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

        # An unparseable supervisor verdict is NOT an approval. The gate
        # must fail closed and ask for a retry rather than silently passing.
        evaluation = await evaluate_task_output(task_dict, worker_output, user_query, prior_completed)
        assert evaluation["decision"] == "needs_retry"
        assert evaluation["confidence"] == 0.0
        assert evaluation["feedback"]


@pytest.mark.asyncio
async def test_workflow_templates_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/workflows/templates")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        template_ids = [t["id"] for t in data]
        assert "soc-10-phase-investigation" in template_ids
        assert "code-vulnerability-audit" in template_ids
        soc_tpl = next(t for t in data if t["id"] == "soc-10-phase-investigation")
        assert len(soc_tpl["tasks"]) == 10
        assert soc_tpl["tasks"][0]["id"] == "t1"
        # Containment is the only high-risk phase and gates on human approval.
        assert soc_tpl["tasks"][9]["risk_level"] == "high"
        assert [t["risk_level"] for t in soc_tpl["tasks"]].count("high") == 1


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


@pytest.mark.asyncio
async def test_evaluate_task_output_circuit_breaker_abort():
    task_dict = {
        "id": "t1",
        "name": "Target Discovery & Evidence Enumeration",
        "description": "Inspect log directory",
        "required_skills": ["file_tree", "filesystem_inspection"],
        "expected_output": "List of discovered files",
    }
    worker_output = "Directory enumeration complete: 0 files enumerated. Target path does not exist on disk."
    user_query = "Forensic audit on D:\\missing\\logs"
    prior_completed = {}

    with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm:
        mock_llm = mock_get_llm.return_value
        mock_llm.chat = AsyncMock(return_value=json.dumps({
            "decision": "pass",
            "confidence": 0.9,
            "feedback": "",
        }))

        evaluation = await evaluate_task_output(task_dict, worker_output, user_query, prior_completed)
        assert evaluation["decision"] == "abort"
        assert "Target log directory yielded 0 files" in evaluation["feedback"]

