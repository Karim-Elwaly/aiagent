"""
Unit tests for order-flip replay (Phase 1) and the hybrid supervisor readout
path (Phase 4).

Order-flip rate answers: does the verdict change when the same three options are
listed in a different sequence? If it does, the model is responding to position
rather than to evidence.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.brain.prompts import (
    SUPERVISOR_DECISION_OPTIONS,
    SUPERVISOR_EVALUATION_PROMPT,
    format_decision_options,
)
from src.core import decision_replay


# ── Option rendering ─────────────────────────────────────────────


def test_default_option_order_is_canonical():
    rendered = format_decision_options()
    assert rendered.index('"pass"') < rendered.index('"needs_retry"')
    assert rendered.index('"needs_retry"') < rendered.index('"abort"')


def test_options_can_be_permuted():
    rendered = format_decision_options(["abort", "needs_retry", "pass"])
    assert rendered.index('"abort"') < rendered.index('"pass"')


def test_omitted_options_are_appended_not_hidden():
    """A caller must never be able to hide a valid answer from the model."""
    rendered = format_decision_options(["abort"])
    for name in SUPERVISOR_DECISION_OPTIONS:
        assert f'"{name}"' in rendered


def test_unknown_option_names_are_ignored():
    rendered = format_decision_options(["not_a_decision", "abort"])
    assert "not_a_decision" not in rendered
    for name in SUPERVISOR_DECISION_OPTIONS:
        assert f'"{name}"' in rendered


def test_prompt_still_formats_with_options_injected():
    prompt = SUPERVISOR_EVALUATION_PROMPT.format(
        user_query="q",
        task_name="t",
        task_description="d",
        expected_output="e",
        prior_context="None",
        worker_output="o",
        decision_options=format_decision_options(),
    )
    assert '"pass"' in prompt
    assert '"abort"' in prompt
    # The fabricated-confidence anchor removed in Phase 0 must stay gone
    assert "0.95+" not in prompt


# ── Permutations ─────────────────────────────────────────────────


def test_production_order_is_always_replayed_first():
    """The canonical order must be one of the compared runs, not a baseline
    assumed from elsewhere."""
    orders = decision_replay.option_orders()
    assert orders[0] == list(SUPERVISOR_DECISION_OPTIONS)


def test_permutation_count_is_bounded():
    assert len(decision_replay.option_orders(2)) == 2
    assert len(decision_replay.option_orders()) == 6  # 3! orders


# ── Replay ───────────────────────────────────────────────────────


def _record(worker_output="out"):
    return {
        "fingerprint": "abc123",
        "inputs": {
            "user_query": "Investigate",
            "task_name": "Triage",
            "task_description": "Check the alert",
            "expected_output": "A verdict",
            "worker_output": worker_output,
            "prior_task_ids": [],
        },
        "observed": {"decision": "pass"},
    }


@pytest.mark.asyncio
async def test_stable_answer_is_not_a_flip():
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value='{"decision": "pass", "confidence": 0.8}')

    result = await decision_replay.replay_record(llm, _record(), permutations=3)

    assert result["flipped"] is False
    assert result["distinct_decisions"] == ["pass"]


@pytest.mark.asyncio
async def test_changed_answer_is_a_flip():
    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=[
        '{"decision": "pass"}',
        '{"decision": "needs_retry"}',
        '{"decision": "pass"}',
    ])

    result = await decision_replay.replay_record(llm, _record(), permutations=3)

    assert result["flipped"] is True
    assert result["distinct_decisions"] == ["needs_retry", "pass"]


@pytest.mark.asyncio
async def test_single_usable_verdict_is_undecidable_not_stable():
    """Counting a lone verdict as 'stable' would improve the score every time
    the model failed, which is exactly backwards."""
    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=[
        '{"decision": "pass"}',
        "not json at all",
        RuntimeError("connection reset"),
    ])

    result = await decision_replay.replay_record(llm, _record(), permutations=3)

    assert result["flipped"] is None


@pytest.mark.asyncio
async def test_replay_records_error_kinds_separately():
    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=[
        "unparseable",
        RuntimeError("down"),
        '{"decision": "abort"}',
    ])

    result = await decision_replay.replay_record(llm, _record(), permutations=3)
    errors = [r["error"] for r in result["runs"]]

    assert any(e and e.startswith("parse_error") for e in errors)
    assert any(e and e.startswith("llm_error") for e in errors)


@pytest.mark.asyncio
async def test_replay_of_empty_corpus_does_not_call_the_model():
    with patch.object(decision_replay.decision_capture, "load_records", return_value=[]):
        result = await decision_replay.measure_flip_rate()

    assert result["n"] == 0
    assert result["flip_rate"] is None


def test_report_on_empty_corpus_is_actionable():
    report = decision_replay.format_report(
        {"n": 0, "flip_rate": None, "records": [], "undecidable": 0}
    )
    assert "decision_capture_enabled" in report


# ── Hybrid supervisor readout (Phase 4) ──────────────────────────


@pytest.mark.asyncio
async def test_supervisor_ignores_readout_when_not_promoted():
    """Default configuration must keep the generated verdict authoritative."""
    from src.core.decider import Decision
    from src.orchestrator.activities import evaluate_task_output

    strong = Decision(
        decision="abort", distribution={"abort": 0.99}, level="L2", backend="fake"
    )

    with patch("src.orchestrator.activities._get_planner_llm") as mock_llm, \
         patch("src.core.decision_shadow.read_decision", AsyncMock(return_value=strong)):
        mock_llm.return_value.chat = AsyncMock(
            return_value='{"decision": "pass", "confidence": 0.7}'
        )
        result = await evaluate_task_output(
            {"id": "t1", "name": "T", "description": "d"}, "output", "q", {}
        )

    # The readout said abort; without promotion the generated verdict stands.
    assert result["decision"] == "pass"


@pytest.mark.asyncio
async def test_promoted_confident_pass_skips_generation():
    """A confident pass needs no feedback prose, so nothing is generated."""
    from src.core.decider import Decision
    from src.orchestrator.activities import evaluate_task_output

    readout = Decision(
        decision="pass", distribution={"pass": 0.97, "needs_retry": 0.03}, level="L2"
    )

    chat = AsyncMock(return_value='{"decision": "needs_retry"}')
    with patch("src.orchestrator.activities._get_planner_llm") as mock_llm, \
         patch("src.core.decision_shadow.read_decision", AsyncMock(return_value=readout)), \
         patch("src.core.decision_shadow.evaluate_gate", return_value=(True, "ok")):
        mock_llm.return_value.chat = chat
        result = await evaluate_task_output(
            {"id": "t1", "name": "T", "description": "d"}, "output", "q", {}
        )

    assert result["decision"] == "pass"
    assert result["confidence"] == pytest.approx(0.97)
    assert result["degraded"] is False
    chat.assert_not_called()


@pytest.mark.asyncio
async def test_promoted_non_pass_still_generates_feedback():
    """The retry path needs prose a typed choice cannot produce."""
    from src.core.decider import Decision
    from src.orchestrator.activities import evaluate_task_output

    readout = Decision(
        decision="needs_retry",
        distribution={"needs_retry": 0.95, "pass": 0.05},
        level="L2",
    )

    chat = AsyncMock(
        return_value='{"decision": "pass", "confidence": 0.6, "feedback": "Run the tool."}'
    )
    with patch("src.orchestrator.activities._get_planner_llm") as mock_llm, \
         patch("src.core.decision_shadow.read_decision", AsyncMock(return_value=readout)), \
         patch("src.core.decision_shadow.evaluate_gate", return_value=(True, "ok")):
        mock_llm.return_value.chat = chat
        result = await evaluate_task_output(
            {"id": "t1", "name": "T", "description": "d"}, "output", "q", {}
        )

    # Readout decides; generation supplied only the feedback text.
    assert result["decision"] == "needs_retry"
    assert result["confidence"] == pytest.approx(0.95)
    assert result["feedback"] == "Run the tool."
    chat.assert_called_once()
