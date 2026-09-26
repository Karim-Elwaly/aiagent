"""
Shadow evaluation and promotion gate for typed decision readout.

Two jobs, kept together because they are the same question asked at two stages:

  Shadow  — run the typed readout next to the decision the system actually made,
            record both, and act on neither. This is how a candidate earns
            evidence on real traffic without being able to affect a live run.

  Promote — once that evidence exists, allow the readout to decide, but only
            within limits it must satisfy on every single call.

The gate is deliberately conservative. Three independent conditions must hold
before a readout is allowed to decide anything:

  1. ``decision_act_on_readout`` is explicitly enabled.
  2. The readout's level is at least ``decision_required_level``. A "raw"
     readout is position-biased and uncalibrated, so it is never sufficient.
  3. The winning probability clears ``decision_auto_accept_threshold``.

Failing any of them is not an error. It means the decision falls through to the
existing generated-and-parsed path, which is the behaviour that ships today.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core import decision_capture
from src.core.config import get_settings
from src.core.decider import Decision, DecisionUnavailable, build_backend

logger = logging.getLogger(__name__)

# Built once per process; None means decisions stay generated.
_backend: Any = None
_backend_built = False


def _get_backend() -> Any:
    global _backend, _backend_built
    if not _backend_built:
        try:
            _backend = build_backend(get_settings())
        except Exception as e:
            logger.warning("Decision backend unavailable: %s", e)
            _backend = None
        _backend_built = True
    return _backend


def reset_backend_cache() -> None:
    """Drop the cached backend so settings changes take effect. For tests."""
    global _backend, _backend_built
    _backend = None
    _backend_built = False


def is_shadow_enabled() -> bool:
    try:
        return bool(getattr(get_settings(), "decision_shadow_enabled", False))
    except Exception:
        return False


async def read_decision(
    question: str, options: list[str], context: str
) -> Decision | None:
    """Read a typed decision, or None if unavailable.

    Never raises: an unavailable readout must degrade to the existing path
    rather than fail a running investigation.
    """
    backend = _get_backend()
    if backend is None:
        return None
    try:
        return await backend.decide(question, options, context)
    except DecisionUnavailable as e:
        logger.debug("Typed decision unavailable: %s", e)
        return None
    except Exception as e:
        logger.warning("Typed decision backend error: %s", e)
        return None


def evaluate_gate(readout: Decision | None) -> tuple[bool, str]:
    """Whether ``readout`` may be acted on, and why not when it may not."""
    if readout is None:
        return False, "no_readout"

    settings = get_settings()

    if not getattr(settings, "decision_act_on_readout", False):
        return False, "not_promoted"

    required = str(getattr(settings, "decision_required_level", "L1"))
    if not readout.meets(required):
        return False, f"level_too_weak (got {readout.level}, need {required})"

    threshold = float(getattr(settings, "decision_auto_accept_threshold", 0.9))
    confidence = readout.confidence
    if confidence is None:
        return False, "no_confidence"
    if confidence < threshold:
        return False, f"below_threshold ({confidence:.3f} < {threshold:.3f})"

    return True, "ok"


async def shadow_supervisor_decision(
    *,
    task_dict: dict[str, Any],
    worker_output: str,
    user_query: str,
    generated_decision: str,
    generated_confidence: float | None,
    workflow_id: str | None = None,
) -> dict[str, Any] | None:
    """Run the typed readout alongside a generated supervisor verdict.

    Records the comparison and returns it for logging. Acts on nothing: the
    caller keeps whatever verdict it already had.
    """
    if not is_shadow_enabled():
        return None

    options = ["pass", "needs_retry", "abort"]
    question = (
        "Did the worker adequately fulfil this task's expected output?"
    )
    context = (
        f"Goal: {user_query}\n"
        f"Task: {task_dict.get('name', '')}\n"
        f"Task description: {task_dict.get('description', '')}\n"
        f"Expected output: {task_dict.get('expected_output', '')}\n\n"
        f"Worker output:\n{worker_output[:2500]}"
    )

    readout = await read_decision(question, options, context)
    if readout is None:
        return None

    agrees = readout.decision == generated_decision
    comparison = {
        "kind": "supervisor_verdict",
        "workflow_id": workflow_id or "",
        "task_id": task_dict.get("id", ""),
        "generated": {
            "decision": generated_decision,
            "confidence": generated_confidence,
        },
        "readout": readout.to_dict(),
        "agrees": agrees,
    }

    logger.info(
        "Shadow decision on '%s': generated=%s readout=%s (%s, p=%s) agree=%s",
        task_dict.get("name", ""),
        generated_decision,
        readout.decision,
        readout.level,
        f"{readout.confidence:.3f}" if readout.confidence is not None else "n/a",
        agrees,
    )

    _record_shadow(comparison)
    return comparison


async def classify_risk_level(
    *, user_query: str, task: dict[str, Any]
) -> Decision | None:
    """Re-score one task's risk level as a focused typed decision (Phase 5).

    The planner emits ``risk_level`` as a single field inside a large DAG
    generation, alongside task names and dependency graphs, with no confidence
    attached — yet that field is what fires the human approval gate. This asks
    the question on its own.

    Returns None when no backend is configured; the planner's own value stands.
    """
    options = ["low", "medium", "high", "critical"]
    question = (
        "What is the blast radius of performing this task? "
        "low = read-only; medium = local writes or system modification; "
        "high = external mutation with wide blast radius; "
        "critical = destructive or irreversible."
    )
    context = (
        f"Goal: {user_query}\n"
        f"Task: {task.get('name', '')}\n"
        f"Description: {task.get('description', '')}\n"
        f"Required skills: {', '.join(task.get('required_skills', []) or [])}\n"
        f"Expected output: {task.get('expected_output', '')}"
    )
    return await read_decision(question, options, context)


async def shadow_risk_level(
    *, user_query: str, task: dict[str, Any], workflow_id: str | None = None
) -> dict[str, Any] | None:
    """Compare a focused risk readout against the planner's assigned level."""
    if not is_shadow_enabled():
        return None

    readout = await classify_risk_level(user_query=user_query, task=task)
    if readout is None:
        return None

    planner_risk = task.get("risk_level", "")
    planner_risk = str(getattr(planner_risk, "value", planner_risk))
    agrees = readout.decision == planner_risk

    # The medium/high boundary is where the approval gate sits, so a
    # disagreement that crosses it matters more than one that does not.
    gated = {"high", "critical"}
    crosses_gate = (planner_risk in gated) != (readout.decision in gated)

    comparison = {
        "kind": "risk_level",
        "workflow_id": workflow_id or "",
        "task_id": task.get("id", ""),
        "generated": {"decision": planner_risk, "confidence": None},
        "readout": readout.to_dict(),
        "agrees": agrees,
        "crosses_approval_gate": crosses_gate,
    }

    if crosses_gate:
        logger.info(
            "Shadow risk readout disagrees ACROSS the approval gate on '%s': "
            "planner=%s readout=%s (p=%s)",
            task.get("name", ""),
            planner_risk,
            readout.decision,
            f"{readout.confidence:.3f}" if readout.confidence is not None else "n/a",
        )

    _record_shadow(comparison)
    return comparison


def _record_shadow(comparison: dict[str, Any]) -> None:
    """Append a shadow comparison to the capture corpus, if capture is on."""
    if not decision_capture.is_enabled():
        return
    try:
        from datetime import datetime, timezone

        decision_capture._append(  # noqa: SLF001 - same-package capture writer
            "shadow_comparison",
            {
                "schema": 1,
                "kind": "shadow_comparison",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                **comparison,
            },
        )
    except Exception as e:
        logger.debug("Failed to record shadow comparison: %s", e)


def summarize_shadow(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Agreement rate between generated decisions and typed readouts."""
    if not records:
        return {"n": 0, "agreement": None, "by_kind": {}}

    by_kind: dict[str, dict[str, Any]] = {}
    for r in records:
        kind = r.get("kind", "unknown")
        bucket = by_kind.setdefault(
            kind, {"n": 0, "agree": 0, "crosses_gate": 0, "disagreements": {}}
        )
        bucket["n"] += 1
        if r.get("agrees"):
            bucket["agree"] += 1
        else:
            gen = (r.get("generated") or {}).get("decision")
            got = (r.get("readout") or {}).get("decision")
            key = f"{gen}->{got}"
            bucket["disagreements"][key] = bucket["disagreements"].get(key, 0) + 1
        if r.get("crosses_approval_gate"):
            bucket["crosses_gate"] += 1

    for bucket in by_kind.values():
        bucket["agreement"] = bucket["agree"] / bucket["n"] if bucket["n"] else None

    total = sum(b["n"] for b in by_kind.values())
    agreed = sum(b["agree"] for b in by_kind.values())

    return {
        "n": total,
        "agreement": agreed / total if total else None,
        "by_kind": by_kind,
    }
