"""
Unit tests for typed decision readout, the promotion gate, and shadow mode
(Phases 2-5).

The central guarantee under test: none of this affects a running workflow until
it is explicitly promoted, and even then only within limits it must satisfy on
every call. A readout that is weak, uncertain, or unavailable must fall through
to the existing generated-and-parsed path rather than decide anything.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core import decision_shadow
from src.core.decider import (
    AnyJevBackend,
    Decision,
    DecisionUnavailable,
    build_backend,
)


@pytest.fixture(autouse=True)
def _reset_backend():
    decision_shadow.reset_backend_cache()
    yield
    decision_shadow.reset_backend_cache()


def _settings(**overrides):
    base = {
        "decision_backend": "none",
        "decision_backend_url": "",
        "decision_backend_model": "",
        "decision_level": "L0",
        "decision_shadow_enabled": False,
        "decision_act_on_readout": False,
        "decision_required_level": "L1",
        "decision_auto_accept_threshold": 0.9,
        "llm_base_url": "http://localhost:1234/v1",
        "llm_model": "test-model",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ── Decision value object ────────────────────────────────────────


def test_confidence_is_the_winning_probability():
    d = Decision(decision="pass", distribution={"pass": 0.81, "needs_retry": 0.12, "abort": 0.07})
    assert d.confidence == 0.81


def test_margin_separates_a_clear_win_from_a_near_tie():
    """High confidence and a narrow margin can coexist; both must be visible."""
    clear = Decision(decision="pass", distribution={"pass": 0.9, "needs_retry": 0.05, "abort": 0.05})
    tied = Decision(decision="pass", distribution={"pass": 0.45, "needs_retry": 0.44, "abort": 0.11})
    assert clear.margin == pytest.approx(0.85)
    assert tied.margin == pytest.approx(0.01)


def test_level_ordering_is_enforced():
    raw = Decision(decision="pass", level="raw")
    l0 = Decision(decision="pass", level="L0")
    l2 = Decision(decision="pass", level="L2")

    assert raw.meets("raw") and not raw.meets("L0")
    assert l0.meets("L0") and not l0.meets("L1")
    assert l2.meets("L1") and l2.meets("L2")
    # No requirement means anything is acceptable
    assert raw.meets(None)


def test_unknown_level_never_satisfies_a_requirement():
    assert not Decision(decision="pass", level="bogus").meets("L0")


# ── Promotion gate ───────────────────────────────────────────────


def test_gate_blocks_when_not_promoted(monkeypatch):
    monkeypatch.setattr(decision_shadow, "get_settings", lambda: _settings())
    readout = Decision(decision="pass", distribution={"pass": 0.99}, level="L2")

    allowed, reason = decision_shadow.evaluate_gate(readout)

    assert allowed is False
    assert reason == "not_promoted"


def test_gate_blocks_a_readout_weaker_than_required(monkeypatch):
    """A raw readout is position-biased and uncalibrated: never sufficient."""
    monkeypatch.setattr(
        decision_shadow, "get_settings",
        lambda: _settings(decision_act_on_readout=True, decision_required_level="L1"),
    )
    readout = Decision(decision="pass", distribution={"pass": 0.99}, level="raw")

    allowed, reason = decision_shadow.evaluate_gate(readout)

    assert allowed is False
    assert "level_too_weak" in reason


def test_gate_blocks_below_threshold(monkeypatch):
    monkeypatch.setattr(
        decision_shadow, "get_settings",
        lambda: _settings(decision_act_on_readout=True, decision_auto_accept_threshold=0.9),
    )
    readout = Decision(
        decision="pass", distribution={"pass": 0.6, "needs_retry": 0.4}, level="L2"
    )

    allowed, reason = decision_shadow.evaluate_gate(readout)

    assert allowed is False
    assert "below_threshold" in reason


def test_gate_allows_a_strong_confident_readout(monkeypatch):
    monkeypatch.setattr(
        decision_shadow, "get_settings",
        lambda: _settings(decision_act_on_readout=True),
    )
    readout = Decision(
        decision="pass", distribution={"pass": 0.97, "needs_retry": 0.03}, level="L2"
    )

    allowed, reason = decision_shadow.evaluate_gate(readout)

    assert allowed is True
    assert reason == "ok"


def test_gate_blocks_a_missing_readout(monkeypatch):
    monkeypatch.setattr(
        decision_shadow, "get_settings",
        lambda: _settings(decision_act_on_readout=True),
    )
    allowed, reason = decision_shadow.evaluate_gate(None)
    assert allowed is False
    assert reason == "no_readout"


# ── Backend construction ─────────────────────────────────────────


def test_no_backend_by_default():
    """Shipped configuration keeps every decision generated-and-parsed."""
    assert build_backend(_settings()) is None


def test_anyjev_is_dormant():
    """Selecting AnyJev is not enough to activate it.

    The integration is held behind an explicit flag because the deployment
    prerequisites (token-score endpoint, a usable head) are not in place. A
    stray config change must not be able to switch it on.
    """
    from src.core import decider

    assert decider.ANYJEV_DORMANT is True
    assert build_backend(_settings(decision_backend="anyjev")) is None


def test_anyjev_builds_once_undormanted(monkeypatch):
    """Clearing the flag is the only thing standing between config and backend."""
    from src.core import decider

    monkeypatch.setattr(decider, "ANYJEV_DORMANT", False)
    backend = build_backend(_settings(decision_backend="anyjev"))

    assert isinstance(backend, AnyJevBackend)
    # Falls back to the main LLM settings when no override is given
    assert backend.base_url == "http://localhost:1234/v1"
    assert backend.model == "test-model"


def test_unknown_backend_degrades_instead_of_raising():
    assert build_backend(_settings(decision_backend="not-a-real-backend")) is None


def test_anyjev_backend_rejects_an_unknown_level():
    with pytest.raises(ValueError):
        AnyJevBackend(base_url="http://x", model="m", level="L9")


@pytest.mark.asyncio
async def test_anyjev_reports_a_clear_error_when_not_installed():
    """A missing optional dependency must say so, not fail obscurely."""
    backend = AnyJevBackend(base_url="http://localhost:8000", model="m")

    with pytest.raises(DecisionUnavailable) as exc:
        await backend.decide("q?", ["a", "b"], "context")

    assert "not installed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_anyjev_rejects_too_many_options():
    """The letter readout cannot address more than 26 answers."""
    backend = AnyJevBackend(base_url="http://localhost:8000", model="m")

    with pytest.raises(DecisionUnavailable) as exc:
        await backend.decide("q?", [f"opt{i}" for i in range(30)], "ctx")

    assert "26" in str(exc.value)


@pytest.mark.asyncio
async def test_anyjev_rejects_a_single_option():
    backend = AnyJevBackend(base_url="http://localhost:8000", model="m")
    with pytest.raises(DecisionUnavailable):
        await backend.decide("q?", ["only"], "ctx")


# ── Availability / no-op behaviour ───────────────────────────────


@pytest.mark.asyncio
async def test_read_decision_returns_none_without_a_backend(monkeypatch):
    monkeypatch.setattr(decision_shadow, "get_settings", lambda: _settings())
    assert await decision_shadow.read_decision("q?", ["a", "b"], "ctx") is None


@pytest.mark.asyncio
async def test_backend_failure_never_propagates(monkeypatch):
    """A broken decision backend must not fail a running investigation."""
    class Exploding:
        name = "boom"

        async def decide(self, *_a, **_k):
            raise RuntimeError("backend on fire")

    monkeypatch.setattr(decision_shadow, "_get_backend", lambda: Exploding())
    assert await decision_shadow.read_decision("q?", ["a", "b"], "ctx") is None


@pytest.mark.asyncio
async def test_shadow_is_a_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(decision_shadow, "get_settings", lambda: _settings())
    backend = AsyncMock()
    monkeypatch.setattr(decision_shadow, "_get_backend", lambda: backend)

    result = await decision_shadow.shadow_supervisor_decision(
        task_dict={"id": "t1", "name": "T"},
        worker_output="out",
        user_query="q",
        generated_decision="pass",
        generated_confidence=0.7,
    )

    assert result is None
    backend.decide.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_records_disagreement_without_acting(monkeypatch):
    monkeypatch.setattr(
        decision_shadow, "get_settings",
        lambda: _settings(decision_shadow_enabled=True),
    )

    class Fake:
        name = "fake"

        async def decide(self, *_a, **_k):
            return Decision(
                decision="needs_retry",
                distribution={"needs_retry": 0.7, "pass": 0.2, "abort": 0.1},
                level="L0",
                backend="fake",
            )

    monkeypatch.setattr(decision_shadow, "_get_backend", lambda: Fake())

    comparison = await decision_shadow.shadow_supervisor_decision(
        task_dict={"id": "t1", "name": "Triage"},
        worker_output="out",
        user_query="q",
        generated_decision="pass",
        generated_confidence=0.95,
    )

    assert comparison["agrees"] is False
    assert comparison["generated"]["decision"] == "pass"
    assert comparison["readout"]["decision"] == "needs_retry"
    # Shadow mode observes only — the caller keeps its own verdict.
    assert "acted" not in comparison


@pytest.mark.asyncio
async def test_shadow_risk_flags_crossing_the_approval_gate(monkeypatch):
    """A medium->high disagreement matters more than low->medium."""
    monkeypatch.setattr(
        decision_shadow, "get_settings",
        lambda: _settings(decision_shadow_enabled=True),
    )

    class Fake:
        name = "fake"

        async def decide(self, *_a, **_k):
            return Decision(
                decision="high",
                distribution={"high": 0.8, "medium": 0.15, "low": 0.03, "critical": 0.02},
                level="L0",
            )

    monkeypatch.setattr(decision_shadow, "_get_backend", lambda: Fake())

    comparison = await decision_shadow.shadow_risk_level(
        user_query="Contain the host",
        task={"id": "t1", "name": "Isolate", "risk_level": "medium"},
    )

    assert comparison["agrees"] is False
    assert comparison["crosses_approval_gate"] is True


@pytest.mark.asyncio
async def test_shadow_risk_ignores_disagreement_that_stays_below_the_gate(monkeypatch):
    monkeypatch.setattr(
        decision_shadow, "get_settings",
        lambda: _settings(decision_shadow_enabled=True),
    )

    class Fake:
        name = "fake"

        async def decide(self, *_a, **_k):
            return Decision(decision="medium", distribution={"medium": 0.7, "low": 0.3}, level="L0")

    monkeypatch.setattr(decision_shadow, "_get_backend", lambda: Fake())

    comparison = await decision_shadow.shadow_risk_level(
        user_query="List files",
        task={"id": "t1", "name": "Scan", "risk_level": "low"},
    )

    assert comparison["agrees"] is False
    assert comparison["crosses_approval_gate"] is False


# ── Shadow summary ───────────────────────────────────────────────


def test_summarize_shadow_reports_disagreement_directions():
    records = [
        {"kind": "supervisor_verdict", "agrees": True,
         "generated": {"decision": "pass"}, "readout": {"decision": "pass"}},
        {"kind": "supervisor_verdict", "agrees": False,
         "generated": {"decision": "pass"}, "readout": {"decision": "needs_retry"}},
        {"kind": "supervisor_verdict", "agrees": False,
         "generated": {"decision": "pass"}, "readout": {"decision": "needs_retry"}},
    ]

    summary = decision_shadow.summarize_shadow(records)

    assert summary["n"] == 3
    assert summary["agreement"] == pytest.approx(1 / 3)
    bucket = summary["by_kind"]["supervisor_verdict"]
    # Direction matters: generated-pass becoming readout-retry is the case
    # where today's silent approvals would be caught.
    assert bucket["disagreements"]["pass->needs_retry"] == 2


def test_summarize_shadow_empty():
    assert decision_shadow.summarize_shadow([])["agreement"] is None
