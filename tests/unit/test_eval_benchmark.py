"""
Tests for the benchmark scoring harness.

These exercise the SCORING LOGIC with synthetic specs and synthetic reports.
They deliberately do not read the real evaluation specs, so no evaluation-case
artifact enters the unit-test fixtures (charter R8).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from eval_benchmark import (  # noqa: E402
    CaseResult,
    generalization_gap,
    score_report,
)

SPEC = {
    "case_id": "synthetic",
    "name": "Synthetic Scoring Fixture",
    "developed_against": True,
    "stages": [
        {"id": "S1", "technique": "T0001", "label": "foothold", "match": [["foothold"], ["t0001"]]},
        {"id": "S2", "technique": "T0002", "label": "escalation", "match": [["escalated", "privilege"]]},
        {"id": "S3", "technique": "T0003", "label": "exfiltration", "match": [["exfiltration"]]},
    ],
    "traps": [
        {
            "id": "TRAP1",
            "label": "maintenance agent",
            "term": "patchagent",
            "malicious_context": ["malicious", "beacon"],
            "benign_context": ["benign", "excluded"],
        }
    ],
    "fabrication_markers": ["invented-artifact-xyz"],
}


def test_all_stages_matched_gives_perfect_recall():
    report = "The foothold was established. The actor escalated privilege. Then exfiltration occurred."
    result = score_report(SPEC, report)
    assert result.recall == 1.0
    assert result.precision == 1.0
    assert result.f1 == 1.0
    assert result.passed


def test_missed_stage_is_reported():
    report = "The foothold was established and the actor escalated privilege."
    result = score_report(SPEC, report)
    assert result.recall == pytest.approx(2 / 3)
    assert any("S3" in m for m in result.missed)


def test_alternative_phrasing_still_scores():
    """Any one match group satisfying is enough - phrasing must not be penalised."""
    report = "Technique T0001 observed. Privilege was escalated. Data exfiltration confirmed."
    result = score_report(SPEC, report)
    assert result.recall == 1.0


def test_matching_is_case_insensitive():
    report = "FOOTHOLD established; ESCALATED PRIVILEGE; EXFILTRATION."
    assert score_report(SPEC, report).recall == 1.0


def test_trap_asserted_malicious_fails_the_gate():
    report = "Foothold seen. patchagent was identified as a malicious beacon process."
    result = score_report(SPEC, report)
    assert result.trap_hits
    assert not result.passed
    assert result.precision < 1.0


def test_trap_correctly_excluded_does_not_count_against_the_report():
    report = (
        "The foothold was established. The actor escalated privilege. Then exfiltration occurred. "
        "patchagent traffic was reviewed and excluded as benign maintenance activity."
    )
    result = score_report(SPEC, report)
    assert not result.trap_hits
    assert result.passed
    assert result.f1 == 1.0


def test_trap_mentioned_far_from_malicious_language_is_not_a_hit():
    """Context window keeps unrelated prose from creating spurious trap hits."""
    report = "patchagent ran on schedule." + (" filler." * 200) + " A malicious beacon was found elsewhere."
    result = score_report(SPEC, report)
    assert not result.trap_hits


def test_fabrication_marker_fails_the_gate():
    report = "Foothold established via invented-artifact-xyz."
    result = score_report(SPEC, report)
    assert result.fabrications == ["invented-artifact-xyz"]
    assert not result.passed


def test_empty_report_scores_zero_without_crashing():
    result = score_report(SPEC, "")
    assert result.recall == 0.0
    assert result.precision == 0.0
    assert result.f1 == 0.0


def test_precision_penalises_false_positives_not_misses():
    """A report that finds less but invents nothing keeps perfect precision."""
    report = "Only the foothold was established."
    result = score_report(SPEC, report)
    assert result.precision == 1.0
    assert result.recall < 1.0


def test_generalization_gap_detects_overfitting():
    dev = CaseResult(case_id="dev", name="dev", developed_against=True)
    dev.matched = ["a", "b", "c", "d"]
    held = CaseResult(case_id="held", name="held", developed_against=False)
    held.matched = ["a"]
    held.missed = ["b", "c", "d"]

    gap = generalization_gap([dev, held])
    assert gap is not None and gap > 0.15


def test_generalization_gap_is_none_without_a_holdout():
    dev = CaseResult(case_id="dev", name="dev", developed_against=True)
    dev.matched = ["a"]
    assert generalization_gap([dev]) is None


def test_real_specs_are_wellformed():
    """The shipped specs must parse and declare exactly one hold-out arrangement."""
    import yaml

    eval_dir = ROOT / "evals"
    specs = [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in eval_dir.glob("*.yaml")
    ]
    assert specs, "no evaluation specs found"

    for spec in specs:
        assert spec.get("case_id")
        assert spec.get("stages"), f"{spec.get('case_id')} declares no stages"
        for stage in spec["stages"]:
            assert stage.get("id") and stage.get("match")
            assert all(isinstance(g, list) and g for g in stage["match"])
        for trap in spec.get("traps", []):
            assert trap.get("term") and trap.get("malicious_context")

    # R10: at least one case must be held out from development.
    assert any(not s.get("developed_against") for s in specs), (
        "charter R10 requires a hold-out case"
    )
