"""
End-to-end verification of the xiaodazi evaluation closed-loop automation.

Features:
  - Each step saves results to a checkpoint JSON file
  - On re-run, completed steps are skipped (checkpoint resume)
  - Use --clean to start fresh

Steps:
  1. Load all 11 YAML suites
  2. Run evaluation via EvaluationHarness (mock mode)
  3. Verify code-based graders
  4. Verify model-based graders (mock)
  5. Aggregate scores
  6. Extract & classify failures via LoopAutomation
  7. Export regression YAML suite
  8. Generate triage report
  9. Generate combined eval report
  10. Harness grader dispatch integration

Usage:
    source .venv/bin/activate
    python scripts/verify_eval_loop.py          # run with checkpoint resume
    python scripts/verify_eval_loop.py --clean   # start fresh
    python scripts/verify_eval_loop.py --from 6  # resume from step 6
"""

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CHECKPOINT_FILE = PROJECT_ROOT / "evaluation" / "reports" / "_verify_checkpoint.json"

# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def load_checkpoint() -> dict:
    """Load checkpoint from disk."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_steps": [], "step_results": {}, "updated_at": None}


def save_checkpoint(ckpt: dict) -> None:
    """Persist checkpoint to disk."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ckpt["updated_at"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, ensure_ascii=False, indent=2, default=str)


def step_done(ckpt: dict, step: int) -> bool:
    return step in ckpt["completed_steps"]


def mark_done(ckpt: dict, step: int, result: Any = None) -> None:
    if step not in ckpt["completed_steps"]:
        ckpt["completed_steps"].append(step)
    ckpt["step_results"][str(step)] = result
    save_checkpoint(ckpt)


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"
checks: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = ""):
    checks.append((name, condition, detail))
    status = PASS if condition else FAIL
    msg = f"  [{status}] {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


# ============================================================================
# Step 1: Load all YAML suites
# ============================================================================

def step1_load_suites(ckpt: dict):
    print("\n=== Step 1: Load all YAML suites ===")
    from evaluation.harness import EvaluationHarness

    harness = EvaluationHarness(suites_dir=str(PROJECT_ROOT / "evaluation" / "suites"))

    feasibility_dir = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / "feasibility"
    efficiency_dir = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / "efficiency"

    f_files = sorted(feasibility_dir.glob("*.yaml"))
    e_files = sorted(efficiency_dir.glob("*.yaml"))

    check("Feasibility YAML count", len(f_files) == 7, f"found {len(f_files)}")
    check("Efficiency YAML count", len(e_files) == 4, f"found {len(e_files)}")

    suite_info = []
    total_tasks = 0
    for f in f_files + e_files:
        suite = harness.load_suite(str(f))
        suite_info.append({"name": f.name, "id": suite.id, "tasks": len(suite.tasks)})
        total_tasks += len(suite.tasks)
        check(f"Load {f.name}", len(suite.tasks) > 0, f"{len(suite.tasks)} tasks")

    check("Total task count >= 39", total_tasks >= 39, f"total={total_tasks}")

    mark_done(ckpt, 1, {"suites": suite_info, "total_tasks": total_tasks})


# ============================================================================
# Step 2: Run evaluation (mock mode)
# ============================================================================

async def step2_run_evaluation(ckpt: dict):
    print("\n=== Step 2: Run evaluation (mock mode) ===")
    from evaluation.harness import EvaluationHarness

    harness = EvaluationHarness(suites_dir=str(PROJECT_ROOT / "evaluation" / "suites"))

    feasibility_dir = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / "feasibility"
    efficiency_dir = PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi" / "efficiency"
    all_files = sorted(feasibility_dir.glob("*.yaml")) + sorted(efficiency_dir.glob("*.yaml"))

    report_ids = []
    report_summaries = []
    for f in all_files:
        suite = harness.load_suite(str(f))
        report = await harness.run_suite(suite, concurrency=5, verbose=False)
        harness.save_report(report, output_dir=str(PROJECT_ROOT / "evaluation" / "reports"))
        report_ids.append(report.report_id)
        summary = {
            "report_id": report.report_id,
            "suite_id": report.suite_id,
            "suite_name": report.suite_name,
            "total": report.total_tasks,
            "passed": report.passed_tasks,
            "failed": report.failed_tasks,
            "rate": f"{report.pass_rate:.0%}",
        }
        report_summaries.append(summary)
        check(
            f"Report {report.suite_name}",
            report.total_tasks > 0,
            f"tasks={report.total_tasks}, passed={report.passed_tasks}, rate={report.pass_rate:.0%}",
        )

    check("All suites executed", len(report_ids) == len(all_files), f"{len(report_ids)} reports")

    mark_done(ckpt, 2, {"report_ids": report_ids, "summaries": report_summaries})


# ============================================================================
# Step 3: Verify code-based graders
# ============================================================================

def step3_verify_code_graders(ckpt: dict):
    print("\n=== Step 3: Verify code-based graders ===")
    from evaluation.graders.code_based import CodeBasedGraders
    from evaluation.models import Transcript, TokenUsage, ToolCall, Message

    g = CodeBasedGraders()
    results = {}

    # check_step_count — optimal
    t = Transcript(
        messages=[],
        tool_calls=[ToolCall(name="s", arguments={}), ToolCall(name="w", arguments={})],
        token_usage=TokenUsage(input_tokens=100, output_tokens=50),
    )
    r = g.check_step_count(t, optimal_steps=2, max_acceptable_steps=3)
    check("check_step_count(optimal)", r.passed and r.score == 1.0, f"score={r.score}")
    results["step_count_optimal"] = r.passed

    # check_step_count — between optimal and max
    t2 = Transcript(
        messages=[],
        tool_calls=[ToolCall(name=f"t{i}", arguments={}) for i in range(3)],
        token_usage=TokenUsage(input_tokens=100, output_tokens=50),
    )
    r2 = g.check_step_count(t2, optimal_steps=2, max_acceptable_steps=4)
    check("check_step_count(acceptable)", r2.passed and 0.5 < r2.score < 1.0, f"score={r2.score:.2f}")
    results["step_count_acceptable"] = r2.passed

    # check_step_count — exceeds
    t3 = Transcript(
        messages=[],
        tool_calls=[ToolCall(name=f"t{i}", arguments={}) for i in range(6)],
        token_usage=TokenUsage(input_tokens=100, output_tokens=50),
    )
    r3 = g.check_step_count(t3, optimal_steps=2, max_acceptable_steps=3)
    check("check_step_count(exceeds)", not r3.passed and r3.score == 0.2, f"score={r3.score}")
    results["step_count_exceeds"] = not r3.passed

    # check_tool_calls pass / fail
    t4 = Transcript(messages=[], tool_calls=[ToolCall(name="nodes", arguments={})], token_usage=TokenUsage())
    r4 = g.check_tool_calls(t4, expected_tools=["nodes"])
    check("check_tool_calls(pass)", r4.passed, "")
    r5 = g.check_tool_calls(t4, expected_tools=["observe_screen"])
    check("check_tool_calls(fail)", not r5.passed, f"missing={r5.details.get('missing')}")
    results["tool_calls"] = r4.passed and not r5.passed

    # check_token_limit pass / fail
    t6 = Transcript(messages=[], tool_calls=[], token_usage=TokenUsage(input_tokens=3000, output_tokens=1500))
    r6 = g.check_token_limit(t6, max_tokens=5000)
    r7 = g.check_token_limit(t6, max_tokens=2000)
    check("check_token_limit(pass)", r6.passed, f"total={t6.token_usage.total_tokens}")
    check("check_token_limit(fail)", not r7.passed, f"total={t6.token_usage.total_tokens}")
    results["token_limit"] = r6.passed and not r7.passed

    # check_no_tool_errors
    t8 = Transcript(
        messages=[],
        tool_calls=[ToolCall(name="ok", arguments={}), ToolCall(name="bad", arguments={}, error="boom")],
        token_usage=TokenUsage(),
    )
    r8 = g.check_no_tool_errors(t8)
    check("check_no_tool_errors(has error)", not r8.passed, f"errors={r8.details.get('error_count')}")
    results["no_tool_errors"] = not r8.passed

    # check_response_contains
    t9 = Transcript(
        messages=[Message(role="assistant", content="已成功打开访达应用")],
        tool_calls=[], token_usage=TokenUsage(),
    )
    r9 = g.check_response_contains(t9, keywords=["访达"])
    r10 = g.check_response_contains(t9, keywords=["红色"])
    check("check_response_contains(pass)", r9.passed, "")
    check("check_response_contains(fail)", not r10.passed, f"missing={r10.details.get('missing')}")
    results["response_contains"] = r9.passed and not r10.passed

    # check_execution_time
    t11 = Transcript(messages=[], tool_calls=[], token_usage=TokenUsage(), duration_ms=5000)
    r11 = g.check_execution_time(t11, max_duration_ms=10000)
    r12 = g.check_execution_time(t11, max_duration_ms=3000)
    check("check_execution_time(pass)", r11.passed, f"duration={t11.duration_ms}")
    check("check_execution_time(fail)", not r12.passed, f"duration={t11.duration_ms}")
    results["execution_time"] = r11.passed and not r12.passed

    mark_done(ckpt, 3, results)


# ============================================================================
# Step 4: Verify model-based graders (mock)
# ============================================================================

async def step4_verify_model_graders(ckpt: dict):
    print("\n=== Step 4: Verify model-based graders (mock mode) ===")
    from evaluation.graders.model_based import ModelBasedGraders
    from evaluation.models import Transcript, TokenUsage, ToolCall

    g = ModelBasedGraders(llm_service=None)
    results = {}

    t = Transcript(
        messages=[],
        tool_calls=[ToolCall(name="nodes", arguments={})],
        token_usage=TokenUsage(input_tokens=100, output_tokens=50),
    )

    r1 = await g.grade_skill_selection("帮我打开访达", t, optimal_tools=["nodes"])
    check("grade_skill_selection(mock)", r1.score is not None, f"score={r1.score}")
    results["skill_selection"] = r1.score is not None

    r2 = await g.grade_planning_depth("1+1=?", t, expected_planning="none")
    check("grade_planning_depth(mock)", r2.score is not None, f"score={r2.score}")
    results["planning_depth"] = r2.score is not None

    r3 = await g.grade_over_engineering("1+1=?", t)
    check("grade_over_engineering(mock)", r3.score is not None, f"score={r3.score}")
    results["over_engineering"] = r3.score is not None

    r4 = await g.grade_response_quality("写篇文章", "这是一篇关于远程办公的文章...")
    check("grade_response_quality(mock)", r4.score is not None, f"score={r4.score}")
    results["response_quality"] = r4.score is not None

    r5 = await g.grade_safety_compliance("删除所有文件", "即将删除，请确认")
    check("grade_safety_compliance(mock)", r5.score is not None, f"score={r5.score}")
    results["safety_compliance"] = r5.score is not None

    mark_done(ckpt, 4, results)


# ============================================================================
# Step 5: Aggregate scores
# ============================================================================

def step5_aggregate_scores(ckpt: dict):
    print("\n=== Step 5: Aggregate scores ===")

    step2_data = ckpt["step_results"].get("2", {})
    summaries = step2_data.get("summaries", [])

    f_total = sum(s["total"] for s in summaries if "feasibility" in s.get("suite_id", ""))
    f_passed = sum(s["passed"] for s in summaries if "feasibility" in s.get("suite_id", ""))
    f_score = f_passed / f_total if f_total > 0 else 0.0
    check("Feasibility tasks counted", f_total > 0, f"total={f_total}, passed={f_passed}, score={f_score:.1%}")

    e_total = sum(s["total"] for s in summaries if "efficiency" in s.get("suite_id", ""))
    e_passed = sum(s["passed"] for s in summaries if "efficiency" in s.get("suite_id", ""))
    e_score = e_passed / e_total if e_total > 0 else 0.0
    check("Efficiency tasks counted", e_total > 0, f"total={e_total}, passed={e_passed}, score={e_score:.1%}")

    overall = 0.6 * f_score + 0.4 * e_score
    gate = f_score >= 0.75 and e_score >= 0.55
    check("Overall score computed", True, f"overall={overall:.2%}")
    check("Release gate computed", True, f"gate={'PASS' if gate else 'BLOCKED'}")

    mark_done(ckpt, 5, {
        "feasibility": {"total": f_total, "passed": f_passed, "score": f_score},
        "efficiency": {"total": e_total, "passed": e_passed, "score": e_score},
        "overall": overall,
        "gate": gate,
    })


# ============================================================================
# Step 6: Extract & classify failures
# ============================================================================

def step6_extract_classify(ckpt: dict):
    print("\n=== Step 6: Extract & classify failures ===")
    from evaluation.loop_automation import LoopAutomation, ISSUE_CATEGORIES
    from evaluation.harness import EvaluationHarness

    loop = LoopAutomation(
        reports_dir=str(PROJECT_ROOT / "evaluation" / "reports"),
        regression_output_dir=str(PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi"),
    )

    step2_data = ckpt["step_results"].get("2", {})
    report_ids = step2_data.get("report_ids", [])

    all_classified = []
    seen_rids = set()
    for rid in report_ids:
        if rid in seen_rids:
            continue
        seen_rids.add(rid)
        rpath = PROJECT_ROOT / "evaluation" / "reports" / f"{rid}.json"
        if not rpath.exists():
            continue
        report = EvaluationHarness.load_report(rpath)
        classified = loop.extract_and_classify(report)
        all_classified.extend(classified)

    check("Failures extracted", True, f"total_failures={len(all_classified)}")

    cats: dict[str, int] = {}
    for cf in all_classified:
        cats[cf.category] = cats.get(cf.category, 0) + 1
    for cat, count in sorted(cats.items()):
        desc = ISSUE_CATEGORIES.get(cat, "?")
        print(f"    {cat}: {count}  ({desc})")

    check("All categories valid", all(c.category in ISSUE_CATEGORIES for c in all_classified), "")

    # Serialize for checkpoint
    classified_data = [cf.to_dict() for cf in all_classified]
    mark_done(ckpt, 6, {"count": len(all_classified), "classified": classified_data})


# ============================================================================
# Step 7: Export regression YAML
# ============================================================================

def step7_export_regression(ckpt: dict):
    print("\n=== Step 7: Export regression YAML ===")
    from evaluation.loop_automation import LoopAutomation, ClassifiedFailure

    loop = LoopAutomation(
        reports_dir=str(PROJECT_ROOT / "evaluation" / "reports"),
        regression_output_dir=str(PROJECT_ROOT / "evaluation" / "suites" / "xiaodazi"),
    )

    step6_data = ckpt["step_results"].get("6", {})
    classified_data = step6_data.get("classified", [])

    # Reconstruct ClassifiedFailure objects
    all_classified = [
        ClassifiedFailure(
            suite_name=d["suite_name"],
            task_id=d["task_id"],
            task_description=d["task_description"],
            category=d["category"],
            failing_graders=d["failing_graders"],
            pass_rate=d["pass_rate"],
        )
        for d in classified_data
    ]

    if not all_classified:
        # Create synthetic for testing the pipeline
        all_classified = [
            ClassifiedFailure("test_suite", "SYNTH_001", "Synthetic failure", "capability_gap",
                              ["grade_response_quality"], 0.0)
        ]
        print("    (no failures, using synthetic)")

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "regression_test.yaml"
        result_path = loop.export_regression_suite(
            all_classified, suite_name="regression_verify", output_file=str(out_path),
        )
        check("Regression YAML created", result_path.exists(), result_path.name)

        import yaml
        with open(result_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        task_count = len(data.get("tasks", []))
        check("YAML has tasks", task_count > 0, f"tasks={task_count}")
        check("YAML has metadata", "metadata" in data, "")

        well_formed = all("id" in t and "graders" in t and t["id"].startswith("REG_")
                          for t in data.get("tasks", []))
        check("All regression tasks well-formed", well_formed, "")

    # Also export a real one for later use
    real_path = loop.export_regression_suite(all_classified, suite_name="regression_auto")
    mark_done(ckpt, 7, {"regression_yaml": str(real_path), "task_count": task_count})


# ============================================================================
# Step 8: Generate triage report
# ============================================================================

def step8_triage_report(ckpt: dict):
    print("\n=== Step 8: Generate triage report ===")
    from evaluation.loop_automation import LoopAutomation, ClassifiedFailure

    loop = LoopAutomation(reports_dir=str(PROJECT_ROOT / "evaluation" / "reports"))

    step6_data = ckpt["step_results"].get("6", {})
    classified_data = step6_data.get("classified", [])
    all_classified = [
        ClassifiedFailure(d["suite_name"], d["task_id"], d["task_description"],
                          d["category"], d["failing_graders"], d["pass_rate"])
        for d in classified_data
    ]
    if not all_classified:
        all_classified = [ClassifiedFailure("test", "T1", "test", "capability_gap",
                                            ["grade_response_quality"], 0.0)]

    triage = loop.generate_triage_report(all_classified)
    check("Triage report generated", len(triage) > 100, f"length={len(triage)} chars")
    check("Triage has title", "# 失败用例分类报告" in triage, "")
    check("Triage has table", "|" in triage, "")

    # Save to disk
    triage_path = PROJECT_ROOT / "evaluation" / "reports" / f"triage_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(triage_path, "w", encoding="utf-8") as f:
        f.write(triage)
    print(f"    Saved to {triage_path.name}")

    for line in triage.split("\n")[:8]:
        print(f"    {line}")

    mark_done(ckpt, 8, {"triage_path": str(triage_path), "length": len(triage)})


# ============================================================================
# Step 9: Generate combined eval report
# ============================================================================

def step9_combined_report(ckpt: dict):
    print("\n=== Step 9: Generate combined eval report ===")
    from evaluation.harness import EvaluationHarness

    step2_data = ckpt["step_results"].get("2", {})
    step5_data = ckpt["step_results"].get("5", {})
    report_ids = step2_data.get("report_ids", [])

    # Load detail reports (deduplicate by suite_id)
    detail_reports = []
    seen_suite_ids = set()
    for rid in report_ids:
        rpath = PROJECT_ROOT / "evaluation" / "reports" / f"{rid}.json"
        if rpath.exists():
            try:
                r = EvaluationHarness.load_report(rpath)
                if r.suite_id not in seen_suite_ids:
                    detail_reports.append(r)
                    seen_suite_ids.add(r.suite_id)
            except Exception:
                pass

    # Build combined data from step5
    combined_data = {
        "timestamp": datetime.now().isoformat(),
        "feasibility": step5_data.get("feasibility", {}),
        "efficiency": step5_data.get("efficiency", {}),
        "reports": report_ids,
    }

    from scripts.generate_eval_report import generate_combined_markdown
    md = generate_combined_markdown(combined_data, detail_reports)
    check("Combined report generated", len(md) > 200, f"length={len(md)} chars")
    check("Report has title", "# 小搭子能力测评报告" in md, "")
    check("Report has gate", "发布门禁" in md, "")

    report_path = PROJECT_ROOT / "evaluation" / "reports" / f"xiaodazi_eval_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"    Saved to {report_path.name}")

    for line in md.split("\n")[:12]:
        print(f"    {line}")

    mark_done(ckpt, 9, {"report_path": str(report_path), "length": len(md)})


# ============================================================================
# Step 10: Harness grader dispatch integration
# ============================================================================

async def step10_harness_dispatch(ckpt: dict):
    print("\n=== Step 10: Harness grader dispatch ===")
    from evaluation.harness import EvaluationHarness
    from evaluation.models import (
        Transcript, TokenUsage, ToolCall, Message,
        GraderConfig, GraderType, Task, TaskInput,
    )

    harness = EvaluationHarness()
    results = {}

    t = Transcript(
        messages=[Message(role="assistant", content="done")],
        tool_calls=[ToolCall(name="search", arguments={}), ToolCall(name="write", arguments={})],
        token_usage=TokenUsage(input_tokens=100, output_tokens=50),
    )

    # check_step_count dispatch
    config = GraderConfig(type=GraderType.CODE, name="check_step_count", check="check_step_count(2, 3)")
    r = harness._run_code_grader(config, t, None)
    check("Harness → check_step_count", r.grader_name == "check_step_count", f"passed={r.passed}")
    results["dispatch_step_count"] = r.grader_name == "check_step_count"

    # grade_skill_selection dispatch
    task = Task(id="t1", description="test", input=TaskInput(user_query="帮我打开访达"),
                metadata={"optimal_tools": ["nodes"]})
    config2 = GraderConfig(type=GraderType.MODEL, name="grade_skill_selection",
                           rubric="grade_skill_selection", min_score=4)
    r2 = await harness._run_model_grader(config2, task, t)
    check("Harness → grade_skill_selection", r2.grader_name == "grade_skill_selection", f"score={r2.score}")
    results["dispatch_skill_selection"] = r2.grader_name == "grade_skill_selection"

    # grade_planning_depth dispatch
    task2 = Task(id="t2", description="test", input=TaskInput(user_query="1+1=?"),
                 metadata={"expected_planning": "none"})
    config3 = GraderConfig(type=GraderType.MODEL, name="grade_planning_depth",
                           rubric="grade_planning_depth", min_score=4)
    r3 = await harness._run_model_grader(config3, task2, t)
    check("Harness → grade_planning_depth", r3.grader_name == "grade_planning_depth", f"score={r3.score}")
    results["dispatch_planning_depth"] = r3.grader_name == "grade_planning_depth"

    mark_done(ckpt, 10, results)


# ============================================================================
# Main
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Verify xiaodazi eval loop (with checkpoint)")
    parser.add_argument("--clean", action="store_true", help="Remove checkpoint and start fresh")
    parser.add_argument("--from", dest="from_step", type=int, default=None,
                        help="Force resume from this step (invalidates later steps)")
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.clean and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("  Checkpoint cleared.")

    ckpt = load_checkpoint()

    if args.from_step:
        # Invalidate this step and all later ones
        ckpt["completed_steps"] = [s for s in ckpt["completed_steps"] if s < args.from_step]
        for k in list(ckpt["step_results"].keys()):
            if int(k) >= args.from_step:
                del ckpt["step_results"][k]
        save_checkpoint(ckpt)
        print(f"  Resuming from step {args.from_step}")

    if ckpt["completed_steps"]:
        print(f"  Checkpoint found: steps {ckpt['completed_steps']} already done (updated {ckpt.get('updated_at', '?')})")

    print("=" * 60)
    print("  XIAODAZI EVALUATION CLOSED-LOOP VERIFICATION")
    print("=" * 60)

    # Step 1
    if step_done(ckpt, 1):
        print(f"\n=== Step 1: Load all YAML suites === [{SKIP}] (checkpoint)")
    else:
        step1_load_suites(ckpt)

    # Step 2
    if step_done(ckpt, 2):
        print(f"\n=== Step 2: Run evaluation === [{SKIP}] (checkpoint)")
    else:
        await step2_run_evaluation(ckpt)

    # Step 3
    if step_done(ckpt, 3):
        print(f"\n=== Step 3: Code-based graders === [{SKIP}] (checkpoint)")
    else:
        step3_verify_code_graders(ckpt)

    # Step 4
    if step_done(ckpt, 4):
        print(f"\n=== Step 4: Model-based graders === [{SKIP}] (checkpoint)")
    else:
        await step4_verify_model_graders(ckpt)

    # Step 5
    if step_done(ckpt, 5):
        print(f"\n=== Step 5: Aggregate scores === [{SKIP}] (checkpoint)")
    else:
        step5_aggregate_scores(ckpt)

    # Step 6
    if step_done(ckpt, 6):
        print(f"\n=== Step 6: Extract & classify === [{SKIP}] (checkpoint)")
    else:
        step6_extract_classify(ckpt)

    # Step 7
    if step_done(ckpt, 7):
        print(f"\n=== Step 7: Export regression === [{SKIP}] (checkpoint)")
    else:
        step7_export_regression(ckpt)

    # Step 8
    if step_done(ckpt, 8):
        print(f"\n=== Step 8: Triage report === [{SKIP}] (checkpoint)")
    else:
        step8_triage_report(ckpt)

    # Step 9
    if step_done(ckpt, 9):
        print(f"\n=== Step 9: Combined report === [{SKIP}] (checkpoint)")
    else:
        step9_combined_report(ckpt)

    # Step 10
    if step_done(ckpt, 10):
        print(f"\n=== Step 10: Harness dispatch === [{SKIP}] (checkpoint)")
    else:
        await step10_harness_dispatch(ckpt)

    # Final summary
    print("\n" + "=" * 60)
    total = len(checks)
    passed = sum(1 for _, ok, _ in checks if ok)
    failed = total - passed
    skipped_steps = sum(1 for s in range(1, 11) if step_done(ckpt, s) and s not in
                        [s2 for s2 in ckpt["completed_steps"] if str(s2) in
                         {str(s3) for _, s3, _ in []}])

    print(f"  CHECKS: {total}  |  PASSED: {passed}  |  FAILED: {failed}")
    print(f"  CHECKPOINT: {CHECKPOINT_FILE.name}")
    if failed > 0:
        print(f"\n  FAILED CHECKS:")
        for name, ok, detail in checks:
            if not ok:
                print(f"    - {name}: {detail}")
    else:
        print("  ALL CHECKS PASSED")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
