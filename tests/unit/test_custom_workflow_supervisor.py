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


class _FakeStore:
    def __init__(self, count: int):
        self._count = count

    def count(self) -> int:
        return self._count


class TestVerdictParsing:
    """Local models wrap verdict JSON in reasoning; a parsing artifact must
    not consume the single supervisor retry."""

    VERDICT = {"decision": "pass", "confidence": 0.9, "feedback": "ok", "missing_info": []}

    @pytest.mark.parametrize(
        "wrapper",
        [
            # bare JSON
            "{json}",
            # fenced
            "```json\n{json}\n```",
            # reasoning prose before a fence
            "Let me evaluate the output carefully.\n\n```json\n{json}\n```",
            # <think> block containing braces, then bare JSON
            "<think>The output {{looks}} complete and cites ids.</think>\n{json}",
            # two fences, verdict in the second
            "```\nnot the verdict\n```\nHere is my verdict:\n```json\n{json}\n```",
            # prose with stray braces before the verdict object
            "Considering {{severity}} and coverage...\n{json}\nDone.",
        ],
    )
    @pytest.mark.asyncio
    async def test_wrapped_verdicts_parse(self, wrapper):
        resp = wrapper.format(json=json.dumps(self.VERDICT))
        task_dict = {"id": "t3", "name": "Triage", "description": "d", "expected_output": "e"}

        with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm:
            mock_get_llm.return_value.chat = AsyncMock(return_value=resp)

            evaluation = await evaluate_task_output(task_dict, "Findings [EV-000001].", "q", {})

        assert evaluation["decision"] == "pass", f"failed for wrapper: {wrapper!r}"
        assert evaluation["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_genuinely_unparseable_still_fails_closed(self):
        task_dict = {"id": "t3", "name": "Triage", "description": "d", "expected_output": "e"}

        with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm:
            mock_get_llm.return_value.chat = AsyncMock(return_value="I approve this output.")

            evaluation = await evaluate_task_output(task_dict, "Findings.", "q", {})

        assert evaluation["decision"] == "needs_retry"
        assert evaluation["confidence"] == 0.0


def _ingestion_task(**overrides):
    task = {
        "id": "t1",
        "name": "Evidence Ingestion & Indexing",
        "description": "Ingest all log files into the evidence store",
        "required_skills": ["evidence_gathering", "log_ingestion"],
        "expected_output": "Ingestion counts with citation id ranges",
        "_workflow_id": "gate-test",
    }
    task.update(overrides)
    return task


def _mock_llm_verdict(decision: str = "pass"):
    return json.dumps({
        "decision": decision,
        "confidence": 0.9,
        "feedback": "",
        "missing_info": [],
    })


class TestDeterministicIngestionGate:
    """The evidence store, not output prose, decides whether ingestion happened."""

    @pytest.mark.asyncio
    async def test_empty_store_overrides_llm_pass(self):
        """A confident narrative cannot pass an ingestion task that stored nothing."""
        with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm, \
             patch("src.orchestrator.activities.get_store", return_value=_FakeStore(0)):
            mock_get_llm.return_value.chat = AsyncMock(return_value=_mock_llm_verdict("pass"))

            evaluation = await evaluate_task_output(
                _ingestion_task(),
                "Ingestion complete. All logs processed successfully.",
                "Investigate incident",
                {},
            )

        assert evaluation["decision"] == "needs_retry"
        assert "0 events" in evaluation["feedback"]
        assert "ingest_logs" in evaluation["feedback"]

    @pytest.mark.asyncio
    async def test_empty_store_after_retry_aborts(self):
        """A second failure to ingest is fatal — downstream analysis would be ungrounded."""
        with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm, \
             patch("src.orchestrator.activities.get_store", return_value=_FakeStore(0)):
            mock_get_llm.return_value.chat = AsyncMock(return_value=_mock_llm_verdict("pass"))

            evaluation = await evaluate_task_output(
                _ingestion_task(_supervisor_retried=1),
                "Ingestion complete.",
                "Investigate incident",
                {},
            )

        assert evaluation["decision"] == "abort"

    @pytest.mark.asyncio
    async def test_populated_store_passes_without_legacy_markers(self):
        """Regression: the old substring markers did not match the current
        ingest_logs phrasing, so a factually successful ingestion could be
        misjudged. With events in the store, phrasing must not matter."""
        output = (
            "# Log Ingestion Complete\n\n"
            "Ingested **32** new events from **2** file(s) into the evidence store."
        )
        with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm, \
             patch("src.orchestrator.activities.get_store", return_value=_FakeStore(32)):
            mock_get_llm.return_value.chat = AsyncMock(return_value=_mock_llm_verdict("pass"))

            evaluation = await evaluate_task_output(
                _ingestion_task(), output, "Investigate incident", {}
            )

        assert evaluation["decision"] == "pass"

    @pytest.mark.asyncio
    async def test_populated_store_downgrades_wrong_abort(self):
        """Evidence on disk contradicts an abort verdict — the run must survive."""
        with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm, \
             patch("src.orchestrator.activities.get_store", return_value=_FakeStore(10)):
            mock_get_llm.return_value.chat = AsyncMock(return_value=_mock_llm_verdict("abort"))

            evaluation = await evaluate_task_output(
                _ingestion_task(), "Some output.", "Investigate incident", {}
            )

        assert evaluation["decision"] == "needs_retry"

    @pytest.mark.asyncio
    async def test_unreadable_store_does_not_gate(self):
        """A store read failure is unknown, not evidence of failure — fall back
        to the LLM's verdict rather than punishing the worker."""
        with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm, \
             patch("src.orchestrator.activities.get_store", side_effect=OSError("disk")):
            mock_get_llm.return_value.chat = AsyncMock(return_value=_mock_llm_verdict("pass"))

            evaluation = await evaluate_task_output(
                _ingestion_task(), "Ingested logs.", "Investigate incident", {}
            )

        assert evaluation["decision"] == "pass"

