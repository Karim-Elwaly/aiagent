"""Unit tests for workflow resilience wiring (retry policy + planning fallback)."""

from src.core.resilience import get_profile
from src.orchestrator.workflow import (
    UAOSWorkflow,
    _NON_RETRYABLE_ERROR_TYPES,
    _llm_activity_retry_policy,
    _task_retry_policy,
)


def test_task_retry_policy_reflects_profile():
    profile = get_profile("extended")
    policy = _task_retry_policy(profile)
    assert policy.maximum_attempts == profile.max_attempts
    # Deterministic-failure exclusions preserved so they never pointlessly retry.
    for err in _NON_RETRYABLE_ERROR_TYPES:
        assert err in (policy.non_retryable_error_types or [])


def test_unlimited_policy_has_unbounded_attempts():
    policy = _task_retry_policy(get_profile("unlimited"))
    assert policy.maximum_attempts == 0  # Temporal: retry until the run deadline


def test_llm_activity_policy_has_no_task_exclusions():
    # Planning/assembly should ride through transient outages without the
    # task-specific non-retryable list blocking a retry.
    policy = _llm_activity_retry_policy(get_profile("standard"))
    assert not (policy.non_retryable_error_types or [])
    assert policy.maximum_attempts == get_profile("standard").max_attempts


def test_fallback_single_task_dag_is_valid_and_deterministic():
    wf = UAOSWorkflow()
    dag = wf._fallback_single_task_dag("investigate the incident")
    assert dag["tasks"]
    task = dag["tasks"][0]
    assert task["id"] == "t1"
    assert task["dependencies"] == []
    assert task["description"] == "investigate the incident"
    # Deterministic: same input → identical structure (safe for workflow replay).
    assert wf._fallback_single_task_dag("investigate the incident") == dag
