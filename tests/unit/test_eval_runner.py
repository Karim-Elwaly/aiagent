"""
Unit test for eval benchmark report comparator.
"""

import json
from pathlib import Path
from tests.eval.runner import compare_reports


def test_compare_reports(tmp_path):
    """Verify compare_reports computes deltas and produces formatted table."""
    rep1 = {
        "pass_rate": 0.70,
        "tool_call_accuracy": 0.75,
        "avg_steps": 3.5,
        "avg_elapsed_ms": 2500.0,
    }
    rep2 = {
        "pass_rate": 0.95,
        "tool_call_accuracy": 0.98,
        "avg_steps": 2.2,
        "avg_elapsed_ms": 1800.0,
    }

    f1 = tmp_path / "baseline_results.json"
    f2 = tmp_path / "hermes_results.json"

    f1.write_text(json.dumps(rep1), encoding="utf-8")
    f2.write_text(json.dumps(rep2), encoding="utf-8")

    summary = compare_reports(f1, f2)
    assert "+25.0%" in summary  # Pass rate delta
    assert "+23.0%" in summary  # Tool call accuracy delta
    assert "-1.30" in summary   # Steps delta
    assert "-700.0ms" in summary # Latency delta
