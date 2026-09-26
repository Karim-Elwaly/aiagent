"""
Offline analysis of captured LLM decisions.

Turns a corpus collected by :mod:`src.core.decision_capture` into the numbers
that justify (or refute) changing how decisions are read out of the model:

  accuracy    — agreement with hand-applied labels
  ECE         — expected calibration error: does a reported 0.9 mean 90% right?
  parse-fail  — share of decisions the supervisor never actually produced

These are the baseline. Any candidate replacement must be compared against them
on this corpus, not against a published benchmark on someone else's data.

Order-flip rate (how often the answer changes when the options are listed in a
different order) is deliberately not computed here: measuring it requires
re-running the model against permuted prompts, which is a live operation and
belongs with the replay tooling rather than with corpus analysis.

Usage:
    python -m src.core.decision_analysis supervisor_verdict
"""

from __future__ import annotations

import sys
from typing import Any

from src.core import decision_capture

# Decisions that mean "the supervisor never produced a verdict". These are
# excluded from accuracy and calibration, and reported separately — averaging
# them in would hide the failure inside an otherwise healthy-looking score.
_NON_VERDICTS = {"unreviewed"}


def _labelled(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("label")]


def accuracy(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Agreement between the observed decision and the hand-applied label."""
    labelled = [r for r in _labelled(records)
                if str((r.get("observed") or {}).get("decision")) not in _NON_VERDICTS]
    if not labelled:
        return {"n": 0, "accuracy": None, "per_option": {}}

    correct = 0
    per_option: dict[str, dict[str, int]] = {}
    for r in labelled:
        observed = str((r.get("observed") or {}).get("decision"))
        label = str(r.get("label"))
        bucket = per_option.setdefault(label, {"n": 0, "correct": 0})
        bucket["n"] += 1
        if observed == label:
            correct += 1
            bucket["correct"] += 1

    return {
        "n": len(labelled),
        "accuracy": correct / len(labelled),
        "per_option": per_option,
    }


def expected_calibration_error(
    records: list[dict[str, Any]], bins: int = 10
) -> dict[str, Any]:
    """Expected Calibration Error over records that carry a usable confidence.

    ECE is the average gap between stated confidence and observed accuracy,
    weighted by bin population. A model whose 0.9 predictions are right 90% of
    the time scores 0; one that always says 0.95 while being right 75% of the
    time scores about 0.20.

    Records without a confidence are excluded and counted separately: a verdict
    that reports no confidence is not miscalibrated, it is simply unmeasured.
    """
    usable = []
    missing_confidence = 0
    for r in _labelled(records):
        observed = r.get("observed") or {}
        if str(observed.get("decision")) in _NON_VERDICTS:
            continue
        conf = observed.get("confidence")
        if not isinstance(conf, (int, float)):
            missing_confidence += 1
            continue
        usable.append((float(conf), str(observed.get("decision")) == str(r.get("label"))))

    if not usable:
        return {
            "n": 0,
            "ece": None,
            "missing_confidence": missing_confidence,
            "bins": [],
        }

    bin_stats: list[dict[str, Any]] = []
    total_gap = 0.0
    for i in range(bins):
        lo = i / bins
        hi = (i + 1) / bins
        # Upper edge inclusive on the last bin so confidence == 1.0 is counted.
        members = [
            (c, ok) for c, ok in usable
            if (lo <= c < hi) or (i == bins - 1 and c == hi)
        ]
        if not members:
            continue
        avg_conf = sum(c for c, _ in members) / len(members)
        acc = sum(1 for _, ok in members if ok) / len(members)
        gap = abs(avg_conf - acc)
        total_gap += gap * len(members)
        bin_stats.append({
            "range": [round(lo, 2), round(hi, 2)],
            "n": len(members),
            "avg_confidence": round(avg_conf, 4),
            "accuracy": round(acc, 4),
            "gap": round(gap, 4),
        })

    return {
        "n": len(usable),
        "ece": total_gap / len(usable),
        "missing_confidence": missing_confidence,
        "bins": bin_stats,
    }


def parse_failure_rate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Share of decisions where no genuine verdict was obtained."""
    if not records:
        return {"n": 0, "degraded": 0, "rate": None}
    degraded = sum(1 for r in records if (r.get("observed") or {}).get("degraded"))
    return {"n": len(records), "degraded": degraded, "rate": degraded / len(records)}


def baseline_report(kind: str) -> dict[str, Any]:
    """Full baseline for one decision kind."""
    records = decision_capture.load_records(kind)
    return {
        "corpus": decision_capture.summarize(kind),
        "accuracy": accuracy(records),
        "calibration": expected_calibration_error(records),
        "parse_failures": parse_failure_rate(records),
    }


def _format_report(report: dict[str, Any]) -> str:
    corpus = report["corpus"]
    acc = report["accuracy"]
    cal = report["calibration"]
    pf = report["parse_failures"]

    lines = [
        f"=== Baseline: {corpus['kind']} ===",
        f"Corpus      : {corpus['total']} records ({corpus['unique']} unique), "
        f"{corpus['labelled']} labelled / {corpus['unlabelled']} unlabelled",
        f"Decision mix: {corpus['observed_decisions']}",
        "",
    ]

    if pf["rate"] is not None:
        lines.append(f"Parse failures: {pf['degraded']}/{pf['n']} ({pf['rate']:.1%})")

    if acc["n"] == 0:
        lines.append("Accuracy      : n/a — no labelled records yet.")
    else:
        lines.append(f"Accuracy      : {acc['accuracy']:.3f} over {acc['n']} labelled")
        for option, stats in sorted(acc["per_option"].items()):
            rate = stats["correct"] / stats["n"] if stats["n"] else 0.0
            lines.append(f"  {option:<14} {stats['correct']}/{stats['n']} ({rate:.1%})")

    if cal["ece"] is None:
        lines.append(
            f"Calibration   : n/a — {cal['missing_confidence']} labelled record(s) "
            "carry no confidence."
        )
    else:
        lines.append(
            f"Calibration   : ECE {cal['ece']:.3f} over {cal['n']} "
            f"({cal['missing_confidence']} without confidence)"
        )
        for b in cal["bins"]:
            lines.append(
                f"  {b['range'][0]:.1f}-{b['range'][1]:.1f}  n={b['n']:<4} "
                f"stated={b['avg_confidence']:.2f}  actual={b['accuracy']:.2f}  "
                f"gap={b['gap']:.2f}"
            )

    if corpus["labelled"] == 0 and corpus["total"] > 0:
        lines += [
            "",
            "No labels yet. Set the \"label\" field on each record to the correct "
            "answer to enable accuracy and calibration.",
        ]

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    kind = argv[1] if len(argv) > 1 else decision_capture.KIND_SUPERVISOR
    print(_format_report(baseline_report(kind)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
