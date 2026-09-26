"""
Unit tests for offline decision analysis (Phase 1 baseline metrics).

Verifies:
1. Accuracy is computed against hand-applied labels, per option
2. ECE detects the overconfidence the current system exhibits
3. Unreviewed (degraded) records are excluded from accuracy/calibration
   rather than silently inflating or deflating them
4. Records with no confidence are reported as unmeasured, not scored
5. Empty / unlabelled corpora degrade to None instead of raising
"""

import pytest

from src.core import decision_analysis


def _record(observed, label=None, confidence=0.9, degraded=False):
    return {
        "observed": {
            "decision": observed,
            "confidence": confidence,
            "degraded": degraded,
        },
        "label": label,
    }


def test_accuracy_counts_agreement_per_option():
    records = [
        _record("pass", label="pass"),
        _record("pass", label="pass"),
        _record("pass", label="needs_retry"),      # wrong
        _record("needs_retry", label="needs_retry"),
    ]

    result = decision_analysis.accuracy(records)

    assert result["n"] == 4
    assert result["accuracy"] == 0.75
    assert result["per_option"]["pass"] == {"n": 2, "correct": 2}
    # The mislabelled row is attributed to its true label, showing where the
    # system is weak rather than where it happened to guess.
    assert result["per_option"]["needs_retry"] == {"n": 2, "correct": 1}


def test_accuracy_without_labels_is_none():
    records = [_record("pass"), _record("needs_retry")]
    result = decision_analysis.accuracy(records)
    assert result["n"] == 0
    assert result["accuracy"] is None


def test_unreviewed_records_excluded_from_accuracy():
    """A verdict that was never produced is not a wrong answer — it is no answer."""
    records = [
        _record("pass", label="pass"),
        _record("unreviewed", label="needs_retry", confidence=None, degraded=True),
    ]

    result = decision_analysis.accuracy(records)

    assert result["n"] == 1
    assert result["accuracy"] == 1.0


def test_ece_detects_overconfidence():
    """Always claiming 0.95 while being right half the time must score badly."""
    records = [_record("pass", label="pass", confidence=0.95) for _ in range(5)]
    records += [_record("pass", label="needs_retry", confidence=0.95) for _ in range(5)]

    result = decision_analysis.expected_calibration_error(records)

    assert result["n"] == 10
    # stated 0.95, actual 0.5 -> gap 0.45
    assert result["ece"] == pytest.approx(0.45, abs=0.01)


def test_ece_rewards_honest_confidence():
    """Confidence that matches observed accuracy scores near zero."""
    records = [_record("pass", label="pass", confidence=0.9) for _ in range(9)]
    records += [_record("pass", label="needs_retry", confidence=0.9)]

    result = decision_analysis.expected_calibration_error(records)

    assert result["ece"] == pytest.approx(0.0, abs=0.01)


def test_ece_counts_missing_confidence_separately():
    """No confidence is 'unmeasured', not 'miscalibrated'."""
    records = [
        _record("pass", label="pass", confidence=None),
        _record("pass", label="pass", confidence=None),
        _record("pass", label="pass", confidence=0.8),
    ]

    result = decision_analysis.expected_calibration_error(records)

    assert result["missing_confidence"] == 2
    assert result["n"] == 1


def test_ece_with_no_usable_records_is_none():
    records = [_record("pass", label="pass", confidence=None)]
    result = decision_analysis.expected_calibration_error(records)
    assert result["ece"] is None
    assert result["missing_confidence"] == 1


def test_ece_includes_confidence_of_exactly_one():
    """Confidence 1.0 must land in the top bin, not be dropped on the edge."""
    records = [_record("pass", label="needs_retry", confidence=1.0) for _ in range(4)]
    result = decision_analysis.expected_calibration_error(records)
    assert result["n"] == 4
    assert result["ece"] == pytest.approx(1.0, abs=0.01)


def test_parse_failure_rate():
    records = [
        _record("pass", label="pass"),
        _record("unreviewed", degraded=True),
        _record("unreviewed", degraded=True),
        _record("needs_retry", label="needs_retry"),
    ]

    result = decision_analysis.parse_failure_rate(records)

    assert result["n"] == 4
    assert result["degraded"] == 2
    assert result["rate"] == 0.5


def test_empty_corpus_does_not_raise():
    assert decision_analysis.accuracy([])["accuracy"] is None
    assert decision_analysis.expected_calibration_error([])["ece"] is None
    assert decision_analysis.parse_failure_rate([])["rate"] is None
