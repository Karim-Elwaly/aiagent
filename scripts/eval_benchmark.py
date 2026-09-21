"""
Benchmark scoring harness for produced investigation reports.

Scores a report against an evaluation spec (``evals/*.yaml``) and reports
precision, recall and F1 over the ground-truth stages, plus two hard gates:

* **Trap gate** - any benign item asserted as malicious fails the run.
* **Fabrication gate** - any known-fabricated artifact fails the run.

This script is the ONLY component permitted to read evaluation specs; nothing
under ``src/`` may reference them (charter R9). It is opt-in and never runs as
part of the unit suite.

Usage::

    python scripts/eval_benchmark.py --case case1 --report out/case1_report.md
    python scripts/eval_benchmark.py --all --reports-dir out/
    python scripts/eval_benchmark.py --all --reports-dir out/ --check-regression

Exit code is non-zero when a gate fails or, with ``--check-regression``, when F1
drops below the recorded baseline in ``evals/baseline.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals"
BASELINE_FILE = EVAL_DIR / "baseline.json"

# How close two terms must be to count as "in the same context", in characters.
CONTEXT_WINDOW = 400


@dataclass
class CaseResult:
    case_id: str
    name: str
    developed_against: bool
    matched: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    trap_hits: list[str] = field(default_factory=list)
    fabrications: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        total = len(self.matched) + len(self.missed)
        return len(self.matched) / total if total else 0.0

    @property
    def precision(self) -> float:
        """Share of asserted-malicious items that were genuinely malicious."""
        asserted = len(self.matched) + len(self.trap_hits) + len(self.fabrications)
        return len(self.matched) / asserted if asserted else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    @property
    def passed(self) -> bool:
        return not self.trap_hits and not self.fabrications


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _group_matches(report: str, group: list[str]) -> bool:
    return all(str(term).lower() in report for term in group)


def _occurrences(report: str, term: str) -> list[int]:
    term = term.lower()
    out, start = [], 0
    while True:
        idx = report.find(term, start)
        if idx < 0:
            return out
        out.append(idx)
        start = idx + len(term)


def _trap_is_hit(report: str, trap: dict) -> bool:
    """A trap is hit when the benign item is asserted malicious and not excused.

    Naming a benign item while explicitly labelling it benign / excluded is
    CORRECT behaviour and must not be penalised.
    """
    term = str(trap["term"]).lower()
    malicious = [t.lower() for t in trap.get("malicious_context", [])]
    benign = [t.lower() for t in trap.get("benign_context", [])]

    for idx in _occurrences(report, term):
        lo = max(0, idx - CONTEXT_WINDOW)
        hi = min(len(report), idx + len(term) + CONTEXT_WINDOW)
        window = report[lo:hi]
        if any(b in window for b in benign):
            continue  # correctly ruled out
        if any(m in window for m in malicious):
            return True
    return False


def score_report(spec: dict, report_text: str) -> CaseResult:
    report = _normalize(report_text)
    result = CaseResult(
        case_id=spec["case_id"],
        name=spec.get("name", spec["case_id"]),
        developed_against=bool(spec.get("developed_against", False)),
    )

    for stage in spec.get("stages", []):
        label = f"{stage['id']} {stage.get('technique', '')} {stage.get('label', '')}".strip()
        if any(_group_matches(report, group) for group in stage.get("match", [])):
            result.matched.append(label)
        else:
            result.missed.append(label)

    for trap in spec.get("traps", []):
        if _trap_is_hit(report, trap):
            result.trap_hits.append(f"{trap['id']} {trap.get('label', trap['term'])}")

    for marker in spec.get("fabrication_markers", []):
        if str(marker).lower() in report:
            result.fabrications.append(str(marker))

    return result


def load_spec(case_id: str) -> dict:
    path = EVAL_DIR / f"{case_id}.yaml"
    if not path.exists():
        raise SystemExit(f"No evaluation spec for {case_id!r} (expected {path})")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def available_cases() -> list[str]:
    return sorted(p.stem for p in EVAL_DIR.glob("*.yaml"))


def render(result: CaseResult) -> str:
    lines = [
        "",
        f"=== {result.case_id}: {result.name} ===",
        f"  role      : {'development' if result.developed_against else 'HOLD-OUT'}",
        f"  recall    : {result.recall:.2f}  ({len(result.matched)}/{len(result.matched) + len(result.missed)} stages)",
        f"  precision : {result.precision:.2f}",
        f"  f1        : {result.f1:.2f}",
    ]
    if result.missed:
        lines.append("  MISSED STAGES:")
        lines += [f"    - {m}" for m in result.missed]
    if result.trap_hits:
        lines.append("  FALSE POSITIVES (benign asserted malicious):")
        lines += [f"    - {t}" for t in result.trap_hits]
    if result.fabrications:
        lines.append("  FABRICATIONS:")
        lines += [f"    - {f}" for f in result.fabrications]
    lines.append(f"  gates     : {'PASS' if result.passed else 'FAIL'}")
    return "\n".join(lines)


def generalization_gap(results: list[CaseResult]) -> float | None:
    """R10: a large train/hold-out F1 gap indicates overfitting."""
    dev = [r.f1 for r in results if r.developed_against]
    held = [r.f1 for r in results if not r.developed_against]
    if not dev or not held:
        return None
    return (sum(dev) / len(dev)) - (sum(held) / len(held))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="Case id to score, e.g. case1")
    parser.add_argument("--report", help="Path to the produced report for --case")
    parser.add_argument("--all", action="store_true", help="Score every case in evals/")
    parser.add_argument(
        "--reports-dir",
        help="Directory holding <case_id>.md reports; used with --all",
    )
    parser.add_argument(
        "--check-regression",
        action="store_true",
        help="Fail if F1 drops below evals/baseline.json",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Record the current F1 scores as the new baseline",
    )
    parser.add_argument(
        "--max-generalization-gap",
        type=float,
        default=0.15,
        help="Maximum allowed development-minus-hold-out F1 gap (charter R10)",
    )
    args = parser.parse_args(argv)

    pairs: list[tuple[str, Path]] = []
    if args.all:
        if not args.reports_dir:
            parser.error("--all requires --reports-dir")
        reports_dir = Path(args.reports_dir)
        for case_id in available_cases():
            if case_id == "baseline":
                continue
            candidates = [reports_dir / f"{case_id}{ext}" for ext in (".md", ".txt")]
            found = next((c for c in candidates if c.exists()), None)
            if found is None:
                print(f"[skip] no report found for {case_id} in {reports_dir}")
                continue
            pairs.append((case_id, found))
    else:
        if not (args.case and args.report):
            parser.error("provide --case and --report, or --all with --reports-dir")
        pairs.append((args.case, Path(args.report)))

    if not pairs:
        print("Nothing to score.")
        return 1

    results: list[CaseResult] = []
    for case_id, report_path in pairs:
        if not report_path.exists():
            raise SystemExit(f"Report not found: {report_path}")
        spec = load_spec(case_id)
        result = score_report(spec, report_path.read_text(encoding="utf-8", errors="ignore"))
        results.append(result)
        print(render(result))

    failed = [r for r in results if not r.passed]

    gap = generalization_gap(results)
    if gap is not None:
        print(f"\ngeneralization gap (dev F1 - hold-out F1): {gap:+.2f}")
        if gap > args.max_generalization_gap:
            print(
                f"  FAIL: gap exceeds {args.max_generalization_gap:.2f} - "
                f"changes appear tuned to the development case (charter R10)"
            )
            failed.append(results[0])

    baseline = {}
    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))

    if args.check_regression:
        print("\nregression check:")
        for r in results:
            prior = baseline.get(r.case_id, {}).get("f1")
            if prior is None:
                print(f"  {r.case_id}: no baseline recorded (current F1 {r.f1:.2f})")
                continue
            verdict = "OK" if r.f1 >= prior else "REGRESSION"
            print(f"  {r.case_id}: {prior:.2f} -> {r.f1:.2f}  {verdict}")
            if r.f1 < prior:
                failed.append(r)

    if args.update_baseline:
        baseline.update(
            {
                r.case_id: {
                    "f1": round(r.f1, 4),
                    "precision": round(r.precision, 4),
                    "recall": round(r.recall, 4),
                }
                for r in results
            }
        )
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"\nbaseline written to {BASELINE_FILE}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
