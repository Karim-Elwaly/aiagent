"""
Live replay of captured decisions against permuted option orders.

Completes the Phase 1 baseline. The other metrics in
:mod:`src.core.decision_analysis` are computed from stored records; order-flip
rate cannot be, because it requires asking the model the *same* question again
with the answers listed in a different sequence. That is a live operation, so it
lives here rather than with corpus analysis.

What it measures: if the verdict changes when "pass", "needs_retry" and "abort"
are presented in a different order, the model is responding to position rather
than to evidence. AnyJev reports 0.230 for a raw logit readout on their
benchmark; the number that matters is the one measured here, on this corpus.

Replay calls the real LLM once per permutation per record, so it is slow and
should be run against a sample. It never writes to the corpus and never touches
a running workflow.

Usage:
    python -m src.core.decision_replay --limit 25
    python -m src.core.decision_replay --limit 25 --permutations 3 --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import logging
import sys
from typing import Any

from src.brain.prompts import (
    SUPERVISOR_DECISION_OPTIONS,
    SUPERVISOR_EVALUATION_PROMPT,
    format_decision_options,
)
from src.core import decision_capture
from src.core.config import get_settings
from src.core.llm_client import LocalLLMClient

logger = logging.getLogger(__name__)

_SYSTEM_MESSAGE = (
    "You are a strict, objective Investigation Supervisor. Output ONLY valid JSON."
)


def option_orders(limit: int | None = None) -> list[list[str]]:
    """Permutations of the supervisor's options, canonical order first."""
    names = list(SUPERVISOR_DECISION_OPTIONS)
    orders = [list(p) for p in itertools.permutations(names)]
    # Keep the production order first so it is always one of the compared runs.
    orders.sort(key=lambda o: o != names)
    return orders[:limit] if limit else orders


def build_prompt(inputs: dict[str, Any], order: list[str]) -> str:
    """Rebuild the supervisor prompt for a captured record under a given order."""
    prior_ids = inputs.get("prior_task_ids") or []
    prior_context = (
        "\n".join(f"- Task {tid}: (captured upstream output)" for tid in prior_ids)
        or "None"
    )
    return SUPERVISOR_EVALUATION_PROMPT.format(
        user_query=inputs.get("user_query", ""),
        task_name=inputs.get("task_name", ""),
        task_description=inputs.get("task_description", ""),
        expected_output=inputs.get("expected_output") or "Complete actionable task results",
        prior_context=prior_context,
        worker_output=(inputs.get("worker_output") or "")[:2500],
        decision_options=format_decision_options(order),
    )


async def _ask(llm: LocalLLMClient, prompt: str) -> tuple[str | None, str | None]:
    """Return ``(decision, error)``; a failure is reported, never invented."""
    # Imported here so this analysis tool does not pull the orchestrator (and
    # therefore temporalio) into scope at module import time.
    from src.orchestrator.activities import parse_supervisor_response

    try:
        resp = await llm.chat([
            {"role": "system", "content": _SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        return None, f"llm_error: {type(e).__name__}"

    try:
        decision, _conf, _fb, _mi = parse_supervisor_response(resp)
        return decision, None
    except Exception as e:
        return None, f"parse_error: {type(e).__name__}"


async def replay_record(
    llm: LocalLLMClient, record: dict[str, Any], permutations: int
) -> dict[str, Any]:
    """Ask one captured decision under several option orders."""
    inputs = record.get("inputs") or {}
    results: list[dict[str, Any]] = []

    for order in option_orders(permutations):
        decision, error = await _ask(llm, build_prompt(inputs, order))
        results.append({"order": order, "decision": decision, "error": error})

    verdicts = [r["decision"] for r in results if r["decision"]]
    distinct = sorted(set(verdicts))

    return {
        "fingerprint": record.get("fingerprint"),
        "task_name": inputs.get("task_name", ""),
        "original_decision": (record.get("observed") or {}).get("decision"),
        "runs": results,
        # Undecidable when fewer than two runs produced a verdict: a single
        # answer cannot disagree with itself, and counting that as "stable"
        # would quietly improve the score every time the model failed.
        "flipped": len(distinct) > 1 if len(verdicts) >= 2 else None,
        "distinct_decisions": distinct,
    }


async def measure_flip_rate(
    kind: str = decision_capture.KIND_SUPERVISOR,
    limit: int | None = None,
    permutations: int = 3,
) -> dict[str, Any]:
    """Order-flip rate over a sample of the captured corpus."""
    records = decision_capture.load_records(kind)
    if limit:
        records = records[:limit]

    if not records:
        return {"n": 0, "flip_rate": None, "records": [], "undecidable": 0}

    settings = get_settings()
    llm = LocalLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
    )

    replayed = []
    for i, record in enumerate(records, start=1):
        logger.info("Replaying %d/%d", i, len(records))
        replayed.append(await replay_record(llm, record, permutations))

    decidable = [r for r in replayed if r["flipped"] is not None]
    flipped = [r for r in decidable if r["flipped"]]

    return {
        "n": len(replayed),
        "decidable": len(decidable),
        "undecidable": len(replayed) - len(decidable),
        "flipped": len(flipped),
        "flip_rate": (len(flipped) / len(decidable)) if decidable else None,
        "permutations": permutations,
        "records": replayed,
    }


def format_report(result: dict[str, Any]) -> str:
    if result["n"] == 0:
        return (
            "No captured records to replay.\n"
            "Enable decision_capture_enabled and run some investigations first."
        )

    lines = [
        "=== Order-flip rate (supervisor verdict) ===",
        f"Replayed    : {result['n']} record(s) x {result['permutations']} option order(s)",
    ]
    if result["undecidable"]:
        lines.append(
            f"Undecidable : {result['undecidable']} (fewer than 2 usable verdicts)"
        )
    if result["flip_rate"] is None:
        lines.append("Flip rate   : n/a — no record produced two comparable verdicts.")
    else:
        lines.append(
            f"Flip rate   : {result['flip_rate']:.3f} "
            f"({result['flipped']}/{result['decidable']} changed answer on reorder)"
        )
        for r in result["records"]:
            if r["flipped"]:
                lines.append(
                    f"  FLIP {r['fingerprint']} {r['task_name'][:40]!r}: "
                    f"{r['distinct_decisions']}"
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="records to replay")
    parser.add_argument(
        "--permutations", type=int, default=3, help="option orders per record"
    )
    parser.add_argument("--json", dest="json_out", help="write full results here")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = asyncio.run(
        measure_flip_rate(limit=args.limit, permutations=args.permutations)
    )
    print(format_report(result))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\nFull results written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
