"""
UAOS Evaluation Benchmark Runner

Executes the ~40 fixed evaluation benchmark prompts against a UniversalWorkerAgent.
Measures:
  - Tool-call accuracy (did the model correctly emit requested tool calls?)
  - Step efficiency (iterations taken to achieve final answer)
  - Grounding & keyword matching
  - Latency (execution time in ms)
  - Overall pass/fail rate

Results are serialized to data/eval/baseline_results.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config import ROOT_DIR, get_settings
from src.core.llm_client import LocalLLMClient
from src.core.models import Task, TaskStatus
from src.core.tool_context import ToolContext, reset_tool_context, set_tool_context
from src.persona.synthesizer import PersonaSynthesizer
from src.registry.auto_discover import register_all_tools
from src.registry.tool_registry import ToolRegistry, ToolSpec
from src.workers.universal_worker import UniversalWorkerAgent
from tests.eval.dataset import EVAL_DATASET, EvalCase

logger = logging.getLogger(__name__)

EVAL_OUTPUT_DIR = ROOT_DIR / "data" / "eval"


@dataclass
class EvalResult:
    case_id: str
    category: str
    passed: bool
    tool_call_success: bool
    tools_called: list[str]
    steps: int
    elapsed_ms: int
    output_snippet: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalSuiteReport:
    timestamp: str
    model: str
    total_cases: int
    passed_cases: int
    pass_rate: float
    tool_call_accuracy: float
    avg_steps: float
    avg_elapsed_ms: float
    category_summary: dict[str, dict[str, Any]]
    results: list[EvalResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def run_single_eval_case(
    case: EvalCase,
    worker: UniversalWorkerAgent,
    registry: ToolRegistry,
    synthesizer: PersonaSynthesizer,
) -> EvalResult:
    """Run an individual eval prompt and score the execution."""
    task = Task(
        id=case.id,
        name=f"Eval: {case.id}",
        description=case.prompt,
        required_skills=case.required_skills,
        expected_output="Direct, accurate execution results.",
        timeout_seconds=case.timeout_seconds,
    )

    # Resolve concrete tools
    tools = registry.resolve(case.required_skills) if case.required_skills else []
    # If no specific required skills, supply standard utility tools
    if not tools and case.expected_tools:
        for tname in case.expected_tools:
            spec = registry.get_tool_by_name(tname)
            if spec and spec not in tools:
                tools.append(spec)

    persona = synthesizer.synthesize(task=task, tools=tools)

    ctx = ToolContext(
        workflow_id=f"eval-wf-{case.id}",
        task_id=case.id,
        user_query=case.prompt,
    )
    token = set_tool_context(ctx)

    start_time = time.monotonic()
    error_msg = None
    task_res = None

    try:
        task_res = await asyncio.wait_for(
            worker.execute(
                task=task,
                persona=persona,
                tools=tools,
                user_query=case.prompt,
                workflow_id=f"eval-wf-{case.id}",
            ),
            timeout=float(case.timeout_seconds + 10),
        )
    except TimeoutError:
        error_msg = f"Timed out after {case.timeout_seconds}s"
    except Exception as e:
        error_msg = str(e)
    finally:
        reset_tool_context(token)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # Evaluate criteria
    tools_called = task_res.tool_calls_made if task_res else []
    output_text = task_res.output if task_res else ""

    # 1. Tool-call check
    if case.expected_tools:
        tool_call_success = any(t in tools_called for t in case.expected_tools)
    else:
        # If no tools expected, successful if it didn't hallucinate invalid calls
        tool_call_success = True

    # 2. Status check
    status_ok = task_res is not None and task_res.status == TaskStatus.COMPLETED

    # 3. Grounding / keywords check
    keywords_ok = True
    if case.expected_keywords:
        lower_out = output_text.lower()
        keywords_ok = any(kw.lower() in lower_out for kw in case.expected_keywords)

    passed = status_ok and tool_call_success and keywords_ok and not error_msg

    return EvalResult(
        case_id=case.id,
        category=case.category,
        passed=passed,
        tool_call_success=tool_call_success,
        tools_called=tools_called,
        steps=len(tools_called) + (1 if status_ok else 0),
        elapsed_ms=elapsed_ms,
        output_snippet=output_text[:300] if output_text else "",
        error=error_msg or (task_res.error if task_res else None),
    )


async def run_eval_suite(
    dataset: list[EvalCase] | None = None,
    output_file: Path | None = None,
) -> EvalSuiteReport:
    """Run full evaluation suite and generate benchmark metrics report."""
    cases = dataset or EVAL_DATASET
    settings = get_settings()

    registry = ToolRegistry()
    register_all_tools(registry)
    synthesizer = PersonaSynthesizer()

    worker_llm = LocalLLMClient(
        base_url=settings.llm_base_url,
        model=settings.worker_llm_model or settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
    )

    worker = UniversalWorkerAgent(
        llm=worker_llm,
        max_iterations=settings.worker_max_iterations,
        max_output_chars=settings.worker_max_output_chars,
    )

    results: list[EvalResult] = []
    cat_stats: dict[str, dict[str, Any]] = {}

    for case in cases:
        logger.info("Evaluating [%s] (%s): %s", case.id, case.category, case.prompt[:60])
        res = await run_single_eval_case(case, worker, registry, synthesizer)
        results.append(res)

        cat = case.category
        if cat not in cat_stats:
            cat_stats[cat] = {"total": 0, "passed": 0, "tool_ok": 0, "elapsed_ms": 0}
        cat_stats[cat]["total"] += 1
        if res.passed:
            cat_stats[cat]["passed"] += 1
        if res.tool_call_success:
            cat_stats[cat]["tool_ok"] += 1
        cat_stats[cat]["elapsed_ms"] += res.elapsed_ms

    total = len(results)
    passed_cnt = sum(1 for r in results if r.passed)
    tool_ok_cnt = sum(1 for r in results if r.tool_call_success)
    total_steps = sum(r.steps for r in results)
    total_time = sum(r.elapsed_ms for r in results)

    pass_rate = round(passed_cnt / total, 3) if total else 0.0
    tool_acc = round(tool_ok_cnt / total, 3) if total else 0.0
    avg_steps = round(total_steps / total, 2) if total else 0.0
    avg_time = round(total_time / total, 1) if total else 0.0

    report = EvalSuiteReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=settings.worker_llm_model or settings.llm_model,
        total_cases=total,
        passed_cases=passed_cnt,
        pass_rate=pass_rate,
        tool_call_accuracy=tool_acc,
        avg_steps=avg_steps,
        avg_elapsed_ms=avg_time,
        category_summary=cat_stats,
        results=results,
    )

    # Save to JSON
    target_out = output_file or (EVAL_OUTPUT_DIR / "baseline_results.json")
    target_out.parent.mkdir(parents=True, exist_ok=True)
    with open(target_out, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)

    logger.info(
        "Eval complete: %d/%d passed (%.1f%%), tool accuracy %.1f%%, saved to %s",
        passed_cnt,
        total,
        pass_rate * 100,
        tool_acc * 100,
        target_out,
    )
    return report


def compare_reports(file1: Path, file2: Path) -> str:
    """Print comparative summary between baseline and upgraded reports."""
    with open(file1, "r", encoding="utf-8") as f1, open(file2, "r", encoding="utf-8") as f2:
        d1 = json.load(f1)
        d2 = json.load(f2)

    lines = [
        f"\n=== Eval Benchmark Comparison: {file1.name} vs {file2.name} ===",
        f"{'Metric':<24} | {file1.stem:<20} | {file2.stem:<20} | Delta",
        f"{'-'*24}+-{'-'*20}-+-{'-'*20}-+-------",
        f"{'Pass Rate':<24} | {d1['pass_rate']*100:>6.1f}%{' '*13} | {d2['pass_rate']*100:>6.1f}%{' '*13} | {(d2['pass_rate']-d1['pass_rate'])*100:>+6.1f}%",
        f"{'Tool-Call Accuracy':<24} | {d1['tool_call_accuracy']*100:>6.1f}%{' '*13} | {d2['tool_call_accuracy']*100:>6.1f}%{' '*13} | {(d2['tool_call_accuracy']-d1['tool_call_accuracy'])*100:>+6.1f}%",
        f"{'Avg Steps / Task':<24} | {d1['avg_steps']:>6.2f}{' '*14} | {d2['avg_steps']:>6.2f}{' '*14} | {d2['avg_steps']-d1['avg_steps']:>+6.2f}",
        f"{'Avg Latency (ms)':<24} | {d1['avg_elapsed_ms']:>6.1f}ms{' '*12} | {d2['avg_elapsed_ms']:>6.1f}ms{' '*12} | {d2['avg_elapsed_ms']-d1['avg_elapsed_ms']:>+6.1f}ms",
    ]
    summary = "\n".join(lines)
    print(summary)
    return summary


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    parser = argparse.ArgumentParser(description="UAOS Evaluation Benchmark Runner")
    parser.add_argument("--mode", choices=["legacy", "auto", "native", "tags"], help="Override tool call mode")
    parser.add_argument("--category", choices=["host_info", "files", "math", "strategy", "soc"], help="Filter by category")
    parser.add_argument("--limit", type=int, help="Limit number of eval cases")
    parser.add_argument("--output", type=str, help="Output JSON path")
    parser.add_argument("--compare", nargs=2, metavar=("FILE1", "FILE2"), help="Compare two eval JSON reports")

    args = parser.parse_args()

    if args.compare:
        compare_reports(Path(args.compare[0]), Path(args.compare[1]))
        sys.exit(0)

    dataset = EVAL_DATASET
    if args.category:
        dataset = [c for c in dataset if c.category == args.category]
    if args.limit and args.limit > 0:
        dataset = dataset[:args.limit]

    if args.mode:
        get_settings().tool_call_mode = args.mode

    out_path = Path(args.output) if args.output else None
    asyncio.run(run_eval_suite(dataset=dataset, output_file=out_path))
