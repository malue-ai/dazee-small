"""
小搭子能力测评 — 一键运行脚本

Usage:
    # 运行全量测评（可行性 + 效率性）
    python scripts/run_xiaodazi_eval.py --all

    # 仅可行性
    python scripts/run_xiaodazi_eval.py --suite feasibility

    # 仅效率性
    python scripts/run_xiaodazi_eval.py --suite efficiency

    # 指定单个套件
    python scripts/run_xiaodazi_eval.py --file evaluation/suites/xiaodazi/feasibility/desktop_operations.yaml

    # 仅重跑失败用例 + 分类
    python scripts/run_xiaodazi_eval.py --failures-only --classify

    # 回归验证（对比基线）
    python scripts/run_xiaodazi_eval.py --regression --baseline evaluation/baselines/baseline.json
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.harness import EvaluationHarness
from evaluation.metrics import MetricsCalculator, format_metric_summary
from evaluation.models import EvaluationReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUITES_DIR = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi"
REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"
BASELINES_DIR = PROJECT_ROOT / "evaluation" / "baselines"

FEASIBILITY_DIR = SUITES_DIR / "feasibility"
EFFICIENCY_DIR = SUITES_DIR / "efficiency"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def collect_suite_files(suite_type: str) -> list[Path]:
    """Return all YAML suite files under the requested suite type."""
    if suite_type == "feasibility":
        target = FEASIBILITY_DIR
    elif suite_type == "efficiency":
        target = EFFICIENCY_DIR
    elif suite_type == "all":
        return sorted(FEASIBILITY_DIR.glob("*.yaml")) + sorted(
            EFFICIENCY_DIR.glob("*.yaml")
        )
    else:
        raise ValueError(f"Unknown suite type: {suite_type}")
    return sorted(target.glob("*.yaml"))


def build_harness(llm_service=None, agent_factory=None) -> EvaluationHarness:
    """Build the evaluation harness (mock mode when no factory provided)."""
    return EvaluationHarness(
        agent_factory=agent_factory,
        llm_service=llm_service,
        suites_dir=str(SUITES_DIR),
    )


# ---------------------------------------------------------------------------
# Score aggregation helpers
# ---------------------------------------------------------------------------


def compute_feasibility_score(reports: list[EvaluationReport]) -> float:
    """Feasibility = PASS tasks / total tasks."""
    total = sum(r.total_tasks for r in reports)
    passed = sum(r.passed_tasks for r in reports)
    return passed / total if total > 0 else 0.0


def compute_efficiency_score(reports: list[EvaluationReport]) -> float:
    """Efficiency = average score across all efficiency task results."""
    scores = []
    for r in reports:
        for tr in r.task_results:
            s = tr.average_score
            if s is not None:
                scores.append(s)
    return sum(scores) / len(scores) if scores else 0.0


def quality_tier(score: float) -> str:
    if score >= 0.90:
        return "EXCELLENT"
    if score >= 0.75:
        return "GOOD"
    if score >= 0.60:
        return "ACCEPTABLE"
    return "POOR"


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------


async def run_eval(
    suite_files: list[Path],
    harness: EvaluationHarness,
    concurrency: int = 3,
    verbose: bool = True,
) -> list[EvaluationReport]:
    """Run evaluation on a list of suite YAML files."""
    reports: list[EvaluationReport] = []
    for f in suite_files:
        if verbose:
            print(f"\n{'='*60}")
            print(f"  Loading suite: {f.name}")
            print(f"{'='*60}")

        suite = harness.load_suite(str(f))
        report = await harness.run_suite(suite, concurrency=concurrency, verbose=verbose)
        reports.append(report)

        # Save individual report
        harness.save_report(report, output_dir=str(REPORTS_DIR))

    return reports


def print_summary(
    feasibility_reports: list[EvaluationReport],
    efficiency_reports: list[EvaluationReport],
) -> None:
    """Print a human-readable summary of the evaluation."""
    print("\n" + "=" * 60)
    print("  XIAODAZI EVALUATION SUMMARY")
    print("=" * 60)

    # Feasibility
    if feasibility_reports:
        f_score = compute_feasibility_score(feasibility_reports)
        f_tier = quality_tier(f_score)
        total_f = sum(r.total_tasks for r in feasibility_reports)
        passed_f = sum(r.passed_tasks for r in feasibility_reports)
        print(f"\n  [Feasibility]  {passed_f}/{total_f} PASS  ({f_score:.1%})  Tier: {f_tier}")

        for r in feasibility_reports:
            status = "PASS" if r.pass_rate >= 0.5 else "FAIL"
            print(f"    - {r.suite_name}: {r.passed_tasks}/{r.total_tasks} ({status})")

    # Efficiency
    if efficiency_reports:
        e_score = compute_efficiency_score(efficiency_reports)
        e_tier = quality_tier(e_score)
        print(f"\n  [Efficiency]   avg score: {e_score:.2f}  Tier: {e_tier}")

        for r in efficiency_reports:
            avg = r.average_score
            avg_str = f"{avg:.2f}" if avg is not None else "N/A"
            print(f"    - {r.suite_name}: avg={avg_str}")

    # Overall
    if feasibility_reports and efficiency_reports:
        f_score = compute_feasibility_score(feasibility_reports)
        e_score = compute_efficiency_score(efficiency_reports)
        overall = 0.6 * f_score + 0.4 * e_score
        print(f"\n  [Overall]      {overall:.2%}")
        gate = f_score >= 0.75 and e_score >= 0.55
        print(f"  [Release Gate] {'PASS' if gate else 'BLOCKED'}")

    print("\n" + "=" * 60)


def print_failures(reports: list[EvaluationReport]) -> None:
    """Print failed test cases for triage."""
    failures = []
    for r in reports:
        for tr in r.task_results:
            if tr.pass_rate < 0.5:
                failures.append((r.suite_name, tr.task_id, tr.task_description))

    if not failures:
        print("\n  No failures detected.")
        return

    print(f"\n  FAILED TASKS ({len(failures)}):")
    print("  " + "-" * 56)
    for suite, tid, desc in failures:
        print(f"    [{suite}] {tid}: {desc[:60]}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run xiaodazi capability evaluation"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Run all feasibility + efficiency suites",
    )
    group.add_argument(
        "--suite",
        choices=["feasibility", "efficiency"],
        help="Run only one dimension",
    )
    group.add_argument(
        "--file",
        type=str,
        help="Run a single suite YAML file",
    )
    group.add_argument(
        "--failures-only",
        action="store_true",
        help="Re-run only previously failed test cases",
    )
    group.add_argument(
        "--regression",
        action="store_true",
        help="Run regression check against a baseline",
    )

    parser.add_argument(
        "--baseline",
        type=str,
        default=None,
        help="Path to baseline JSON report (for --regression)",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Classify failures after running (for --failures-only)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent tasks (default: 3)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    verbose = not args.quiet

    harness = build_harness()

    # Determine which suite files to run
    if args.all:
        f_files = collect_suite_files("feasibility")
        e_files = collect_suite_files("efficiency")
    elif args.suite:
        if args.suite == "feasibility":
            f_files = collect_suite_files("feasibility")
            e_files = []
        else:
            f_files = []
            e_files = collect_suite_files("efficiency")
    elif args.file:
        p = Path(args.file)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if "efficiency" in str(p):
            f_files, e_files = [], [p]
        else:
            f_files, e_files = [p], []
    elif args.failures_only:
        # Load last report, find failures, re-run them
        print("  --failures-only: loading latest reports to find failures ...")
        f_files = collect_suite_files("all")
        e_files = []
    elif args.regression:
        f_files = collect_suite_files("all")
        e_files = []
    else:
        f_files = []
        e_files = []

    # Run feasibility
    feasibility_reports: list[EvaluationReport] = []
    if f_files:
        feasibility_reports = await run_eval(
            f_files, harness, concurrency=args.concurrency, verbose=verbose
        )

    # Run efficiency
    efficiency_reports: list[EvaluationReport] = []
    if e_files:
        efficiency_reports = await run_eval(
            e_files, harness, concurrency=args.concurrency, verbose=verbose
        )

    # Summary
    print_summary(feasibility_reports, efficiency_reports)
    print_failures(feasibility_reports + efficiency_reports)

    # Regression check
    if args.regression and args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_absolute():
            baseline_path = PROJECT_ROOT / baseline_path
        if baseline_path.exists():
            baseline_report = EvaluationHarness.load_report(baseline_path)
            calculator = MetricsCalculator(baseline_report=baseline_report)
            for r in feasibility_reports + efficiency_reports:
                summary = calculator.calculate(r)
                print(f"\n  Regression check for {r.suite_name}:")
                print(
                    f"    Regression detected: {summary.regression_detected}"
                )
                if summary.recommendations:
                    for rec in summary.recommendations:
                        print(f"    - {rec}")
        else:
            print(f"  WARNING: Baseline file not found: {baseline_path}")

    # Classify failures
    if args.classify:
        print("\n  Failure classification:")
        for r in feasibility_reports + efficiency_reports:
            for tr in r.task_results:
                if tr.pass_rate < 0.5:
                    _classify_failure(r.suite_name, tr.task_id, tr)

    # Save combined report metadata
    combined = {
        "timestamp": datetime.now().isoformat(),
        "feasibility": {
            "total": sum(r.total_tasks for r in feasibility_reports),
            "passed": sum(r.passed_tasks for r in feasibility_reports),
            "score": compute_feasibility_score(feasibility_reports)
            if feasibility_reports
            else None,
        },
        "efficiency": {
            "score": compute_efficiency_score(efficiency_reports)
            if efficiency_reports
            else None,
        },
        "reports": [r.report_id for r in feasibility_reports + efficiency_reports],
    }
    combined_path = REPORTS_DIR / f"combined_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"\n  Combined report saved to: {combined_path}")


def _classify_failure(suite_name: str, task_id: str, task_result) -> None:
    """Simple heuristic classification for triage (not LLM-based)."""
    tags = []
    for trial in task_result.trials:
        for gr in trial.grade_results:
            if not gr.passed:
                if gr.grader_name in ("check_tool_calls",):
                    tags.append("skill_selection")
                elif gr.grader_name in ("check_no_tool_errors",):
                    tags.append("tool_error")
                elif gr.grader_name in ("check_step_count",):
                    tags.append("over_engineering")
                elif gr.grader_name in ("check_token_limit",):
                    tags.append("token_waste")
                elif gr.grader_name in (
                    "grade_over_engineering",
                    "grade_planning_depth",
                ):
                    tags.append("over_engineering")
                elif gr.grader_name in ("grade_skill_selection",):
                    tags.append("skill_selection")
                elif gr.grader_name in ("grade_safety_compliance",):
                    tags.append("safety")
                elif gr.grader_name in ("grade_intent_understanding",):
                    tags.append("context_loss")
                else:
                    tags.append("capability_gap")

    unique_tags = list(dict.fromkeys(tags))
    print(f"    [{suite_name}] {task_id} => {', '.join(unique_tags) or 'unknown'}")


if __name__ == "__main__":
    asyncio.run(main())
