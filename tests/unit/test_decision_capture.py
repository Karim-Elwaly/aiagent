"""
Unit tests for offline decision capture (Phase 1 evaluation harness).

Verifies:
1. Capture is a no-op when disabled (the default) — no files, no cost
2. Supervisor decisions are recorded with replayable inputs and the raw response
3. Oversized fields are clipped, not dropped, so records stay replayable
4. Capture failures never propagate into the running workflow
5. Corpus summary reports label progress and the observed decision mix
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.core import decision_capture


@pytest.fixture
def capture_dir(tmp_path, monkeypatch):
    """Point capture at a temp dir and enable it."""
    monkeypatch.setattr(decision_capture, "CAPTURE_DIR", tmp_path / "decision_capture")
    monkeypatch.setattr(decision_capture, "is_enabled", lambda: True)
    return tmp_path / "decision_capture"


@pytest.fixture
def capture_dir_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(decision_capture, "CAPTURE_DIR", tmp_path / "decision_capture")
    monkeypatch.setattr(decision_capture, "is_enabled", lambda: False)
    return tmp_path / "decision_capture"


def _supervisor_args(**overrides):
    args = {
        "task_dict": {
            "id": "t1",
            "name": "Log Triage",
            "description": "Parse the auth log",
            "expected_output": "List of failed logins",
            "required_skills": ["log_forensics"],
        },
        "worker_output": "Found 12 failed logins from 10.0.0.5",
        "user_query": "Investigate the auth failures",
        "prior_completed": {"t0": "earlier output"},
        "raw_response": '{"decision": "pass", "confidence": 0.7}',
        "decision": "pass",
        "confidence": 0.7,
        "degraded": False,
        "workflow_id": "uaos-test123",
    }
    args.update(overrides)
    return args


def test_capture_disabled_writes_nothing(capture_dir_disabled):
    """Default-off must cost nothing and leave no trace."""
    decision_capture.capture_supervisor_decision(**_supervisor_args())
    assert not capture_dir_disabled.exists()


def test_capture_supervisor_records_replayable_inputs(capture_dir):
    decision_capture.capture_supervisor_decision(**_supervisor_args())

    records = decision_capture.load_records(decision_capture.KIND_SUPERVISOR)
    assert len(records) == 1
    rec = records[0]

    # Inputs needed to replay the decision against another implementation
    assert rec["inputs"]["user_query"] == "Investigate the auth failures"
    assert rec["inputs"]["task_description"] == "Parse the auth log"
    assert rec["inputs"]["worker_output"] == "Found 12 failed logins from 10.0.0.5"
    assert rec["inputs"]["prior_task_ids"] == ["t0"]
    assert rec["options"] == ["pass", "needs_retry", "abort"]

    # What the system actually did, including the unparsed response
    assert rec["observed"]["decision"] == "pass"
    assert rec["observed"]["confidence"] == 0.7
    assert rec["observed"]["degraded"] is False
    assert "confidence" in rec["observed"]["raw_response"]

    # Awaiting a human label — the whole point of the corpus
    assert rec["label"] is None
    assert rec["fingerprint"]


def test_capture_records_degraded_verdicts(capture_dir):
    """Unreviewed outputs must be captured too — they are the failure signal."""
    decision_capture.capture_supervisor_decision(**_supervisor_args(
        decision="unreviewed",
        confidence=None,
        degraded=True,
        raw_response="I think it looks fine, honestly.",
    ))

    rec = decision_capture.load_records(decision_capture.KIND_SUPERVISOR)[0]
    assert rec["observed"]["decision"] == "unreviewed"
    assert rec["observed"]["confidence"] is None
    assert rec["observed"]["degraded"] is True
    # The unparseable text is retained so a parser fix can be tested against it
    assert rec["observed"]["raw_response"] == "I think it looks fine, honestly."


def test_oversized_fields_are_clipped_not_dropped(capture_dir, monkeypatch):
    monkeypatch.setattr(decision_capture, "_max_chars", lambda: 100)
    huge = "A" * 5000

    decision_capture.capture_supervisor_decision(**_supervisor_args(worker_output=huge))

    rec = decision_capture.load_records(decision_capture.KIND_SUPERVISOR)[0]
    stored = rec["inputs"]["worker_output"]
    assert stored.startswith("A" * 100)
    assert len(stored) < 5000
    assert "capture-truncated" in stored
    # Original size preserved so truncation is detectable during analysis
    assert rec["inputs"]["worker_output_full_chars"] == 5000


def test_capture_failure_never_raises(capture_dir, monkeypatch):
    """A broken capture path must not take down a running investigation."""
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(decision_capture, "_append", boom)
    # Must not raise
    decision_capture.capture_supervisor_decision(**_supervisor_args())


def test_capture_risk_level(capture_dir):
    decision_capture.capture_risk_level_decision(
        user_query="Contain the compromised host",
        task={
            "id": "t3",
            "name": "Isolate Endpoint",
            "description": "Network-isolate the host",
            "required_skills": ["incident_response"],
            "risk_level": "high",
        },
    )

    rec = decision_capture.load_records(decision_capture.KIND_RISK_LEVEL)[0]
    assert rec["observed"]["decision"] == "high"
    assert rec["options"] == ["low", "medium", "high", "critical"]
    # The planner never reports a confidence for risk level
    assert rec["observed"]["confidence"] is None
    assert rec["label"] is None


def test_summarize_reports_label_progress_and_decision_mix(capture_dir):
    for decision in ("pass", "pass", "needs_retry", "unreviewed"):
        decision_capture.capture_supervisor_decision(**_supervisor_args(
            decision=decision,
            degraded=(decision == "unreviewed"),
            worker_output=f"output for {decision}",
        ))

    summary = decision_capture.summarize(decision_capture.KIND_SUPERVISOR)
    assert summary["total"] == 4
    assert summary["labelled"] == 0
    assert summary["unlabelled"] == 4
    assert summary["observed_decisions"]["pass"] == 2
    assert summary["observed_decisions"]["needs_retry"] == 1
    assert summary["degraded"] == 1


def test_load_records_skips_malformed_lines(capture_dir):
    decision_capture.capture_supervisor_decision(**_supervisor_args())
    path = next(capture_dir.glob("supervisor_verdict-*.jsonl"))
    with open(path, "a", encoding="utf-8") as f:
        f.write("{ this is not json\n")

    # A corpus half-written by an interrupted run must still load
    records = decision_capture.load_records(decision_capture.KIND_SUPERVISOR)
    assert len(records) == 1


@pytest.mark.asyncio
async def test_evaluate_task_output_captures_decision(capture_dir):
    """The supervisor activity feeds the corpus without changing its verdict."""
    from src.orchestrator.activities import evaluate_task_output

    task_dict = {"id": "t1", "name": "Triage", "description": "Check alerts"}
    mock_json = json.dumps({"decision": "needs_retry", "confidence": 0.4, "feedback": "Run the tool."})

    with patch("src.orchestrator.activities._get_planner_llm") as mock_get_llm:
        mock_get_llm.return_value.chat = AsyncMock(return_value=mock_json)
        evaluation = await evaluate_task_output(task_dict, "some output", "Investigate", {})

    assert evaluation["decision"] == "needs_retry"

    records = decision_capture.load_records(decision_capture.KIND_SUPERVISOR)
    assert len(records) == 1
    assert records[0]["observed"]["decision"] == "needs_retry"
    assert records[0]["observed"]["confidence"] == 0.4
