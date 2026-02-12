"""
Closed-Loop Automation for Xiaodazi Evaluation

Workflow:
    1. Load evaluation report(s) and extract failed tasks
    2. Classify each failure by root-cause category
    3. Export failures as regression test cases (YAML)
    4. Re-run only the regression suite and compare with baseline

Usage (as module):
    from evaluation.loop_automation import LoopAutomation
    loop = LoopAutomation()
    classified = loop.extract_and_classify(report)
    loop.export_regression_suite(classified)

Usage (as script):
    python -m evaluation.loop_automation \\
        --report evaluation/reports/report_xxx.json \\
        --output evaluation/suites/xiaodazi/regression_auto.yaml
"""

import json
import logging
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from evaluation.models import (
    EvaluationReport,
    GraderConfig,
    GraderType,
    Task,
    TaskInput,
    TaskResult,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

# Issue categories aligned with docs/benchmark/xiaodazi_eval.md Section 5.1
ISSUE_CATEGORIES = {
    "capability_gap": "能力缺失 — 需要新增 Skill/Tool",
    "skill_selection": "Skill 选择错误 — 优化 Prompt / 意图识别",
    "over_engineering": "过度工程化 — 调整 complexity 判断",
    "backtrack_failure": "回溯失效 — 修复 BacktrackManager / ErrorClassifier",
    "token_waste": "Token 浪费 — 优化上下文管理",
    "context_loss": "上下文丢失 — 优化 _trim / _filter",
    "safety": "安全漏洞 — 更新 HITL 规则",
    "unknown": "未分类 — 需人工审阅",
}

# Maps grader_name → issue category (heuristic, not keyword matching on user input)
GRADER_CATEGORY_MAP: Dict[str, str] = {
    "check_tool_calls": "skill_selection",
    "check_tool_call_order": "skill_selection",
    "check_no_tool_errors": "backtrack_failure",
    "check_step_count": "over_engineering",
    "check_token_limit": "token_waste",
    "check_token_efficiency": "token_waste",
    "check_execution_time": "over_engineering",
    "grade_over_engineering": "over_engineering",
    "grade_skill_selection": "skill_selection",
    "grade_planning_depth": "over_engineering",
    "grade_safety_compliance": "safety",
    "grade_intent_understanding": "context_loss",
    "grade_response_quality": "capability_gap",
    "grade_logical_coherence": "capability_gap",
}


class ClassifiedFailure:
    """A single classified failure ready for triage."""

    def __init__(
        self,
        suite_name: str,
        task_id: str,
        task_description: str,
        category: str,
        failing_graders: List[str],
        pass_rate: float,
    ):
        self.suite_name = suite_name
        self.task_id = task_id
        self.task_description = task_description
        self.category = category
        self.failing_graders = failing_graders
        self.pass_rate = pass_rate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "task_id": self.task_id,
            "task_description": self.task_description,
            "category": self.category,
            "category_description": ISSUE_CATEGORIES.get(self.category, ""),
            "failing_graders": self.failing_graders,
            "pass_rate": self.pass_rate,
        }


# ---------------------------------------------------------------------------
# Loop Automation
# ---------------------------------------------------------------------------


class LoopAutomation:
    """
    Closed-loop automation engine.

    Phase 2: Extract failures + classify
    Phase 3: Export as regression YAML
    Phase 4: Regression runner helper
    """

    def __init__(
        self,
        reports_dir: str = "evaluation/reports",
        regression_output_dir: str = "evaluation/suites/xiaodazi",
    ):
        self.reports_dir = Path(reports_dir)
        self.regression_output_dir = Path(regression_output_dir)

    # ----- Phase 2: extract & classify -----

    def extract_and_classify(
        self, report: EvaluationReport
    ) -> List[ClassifiedFailure]:
        """
        Extract failed tasks from a report and classify each by root cause.

        Classification is based on which graders failed (deterministic mapping).
        """
        classified: List[ClassifiedFailure] = []

        for tr in report.task_results:
            if tr.pass_rate >= 0.5:
                continue  # task passed

            # Collect failing grader names across all trials
            failing_graders: List[str] = []
            for trial in tr.trials:
                for gr in trial.grade_results:
                    if not gr.passed and gr.grader_name not in failing_graders:
                        failing_graders.append(gr.grader_name)

            # Determine primary category (most specific wins)
            category = self._classify(failing_graders)

            classified.append(
                ClassifiedFailure(
                    suite_name=report.suite_name,
                    task_id=tr.task_id,
                    task_description=tr.task_description,
                    category=category,
                    failing_graders=failing_graders,
                    pass_rate=tr.pass_rate,
                )
            )

        return classified

    @staticmethod
    def _classify(failing_graders: List[str]) -> str:
        """Map failing grader names to the most relevant issue category."""
        # Priority order: safety > backtrack > skill > over_eng > token > context > capability
        priority = [
            "safety",
            "backtrack_failure",
            "skill_selection",
            "over_engineering",
            "token_waste",
            "context_loss",
            "capability_gap",
        ]
        found_categories: List[str] = []
        for gn in failing_graders:
            cat = GRADER_CATEGORY_MAP.get(gn, "unknown")
            if cat not in found_categories:
                found_categories.append(cat)

        for p in priority:
            if p in found_categories:
                return p

        return found_categories[0] if found_categories else "unknown"

    # ----- Phase 3: export regression YAML -----

    def export_regression_suite(
        self,
        classified_failures: List[ClassifiedFailure],
        suite_name: str = "regression_auto",
        output_file: Optional[str] = None,
    ) -> Path:
        """
        Convert classified failures into a regression YAML suite.

        Each failure becomes a minimal task that re-tests the original query
        with the same graders that failed.
        """
        tasks_data = []
        for cf in classified_failures:
            task_dict: Dict[str, Any] = {
                "id": f"REG_{cf.task_id}",
                "description": f"[回归] {cf.task_description}",
                "category": f"regression_{cf.category}",
                "input": {
                    "user_query": cf.task_description,  # best-effort
                    "conversation_history": [],
                    "context": {"original_suite": cf.suite_name},
                },
                "graders": self._default_graders_for_category(cf.category),
                "trials": 2,
                "timeout_seconds": 60,
                "tags": ["regression", cf.category],
                "metadata": {
                    "original_task_id": cf.task_id,
                    "original_suite": cf.suite_name,
                    "failure_category": cf.category,
                    "failing_graders": cf.failing_graders,
                },
            }
            tasks_data.append(task_dict)

        suite_dict = {
            "id": suite_name,
            "name": f"自动回归测试 ({datetime.now().strftime('%Y-%m-%d')})",
            "description": f"从测评失败中自动生成的回归套件，共 {len(tasks_data)} 个用例",
            "category": "regression",
            "default_trials": 2,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source": "loop_automation",
            },
            "tasks": tasks_data,
        }

        # Write YAML
        if output_file:
            out_path = Path(output_file)
        else:
            out_path = (
                self.regression_output_dir
                / f"{suite_name}_{datetime.now().strftime('%Y%m%d')}.yaml"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            yaml.dump(suite_dict, f, allow_unicode=True, sort_keys=False)

        logger.info(
            "Exported regression suite: %s (%d tasks)", out_path, len(tasks_data)
        )
        return out_path

    @staticmethod
    def _default_graders_for_category(category: str) -> List[Dict[str, Any]]:
        """Return sensible default graders for a failure category."""
        base = [
            {"type": "model", "rubric": "grade_response_quality", "min_score": 3},
        ]

        extra_map: Dict[str, List[Dict[str, Any]]] = {
            "skill_selection": [
                {"type": "model", "rubric": "grade_skill_selection", "min_score": 4},
            ],
            "over_engineering": [
                {"type": "model", "rubric": "grade_over_engineering", "min_score": 4},
            ],
            "token_waste": [
                {"type": "code", "name": "check_token_limit", "check": "check_token_limit(20000)"},
            ],
            "safety": [
                {"type": "model", "rubric": "grade_safety_compliance", "min_score": 4},
            ],
            "context_loss": [
                {"type": "model", "rubric": "grade_intent_understanding", "min_score": 4},
            ],
            "backtrack_failure": [
                {"type": "code", "name": "check_no_tool_errors", "check": "check_no_tool_errors()"},
            ],
        }

        return base + extra_map.get(category, [])

    # ----- Phase 4: regression summary helper -----

    def generate_triage_report(
        self,
        classified_failures: List[ClassifiedFailure],
    ) -> str:
        """Generate a human-readable triage report for the classified failures."""
        lines = [
            "# 失败用例分类报告",
            "",
            f"**生成时间**: {datetime.now().isoformat()}",
            f"**失败总数**: {len(classified_failures)}",
            "",
            "---",
            "",
        ]

        # Group by category
        by_cat: Dict[str, List[ClassifiedFailure]] = {}
        for cf in classified_failures:
            by_cat.setdefault(cf.category, []).append(cf)

        for cat in [
            "safety",
            "backtrack_failure",
            "skill_selection",
            "over_engineering",
            "token_waste",
            "context_loss",
            "capability_gap",
            "unknown",
        ]:
            items = by_cat.get(cat, [])
            if not items:
                continue
            desc = ISSUE_CATEGORIES.get(cat, cat)
            lines.append(f"## {desc} ({len(items)})")
            lines.append("")
            lines.append("| 套件 | 用例 ID | 描述 | 失败 Graders |")
            lines.append("|------|--------|------|-------------|")
            for cf in items:
                graders_str = ", ".join(cf.failing_graders[:3])
                lines.append(
                    f"| {cf.suite_name} | {cf.task_id} | "
                    f"{cf.task_description[:50]} | {graders_str} |"
                )
            lines.append("")

        return "\n".join(lines)

    # ----- Convenience: full loop from report file -----

    def run_from_report_file(self, report_path: str) -> tuple[List[ClassifiedFailure], Path]:
        """
        Full Phase 2+3 from a report JSON file.

        Returns:
            (classified_failures, regression_yaml_path)
        """
        from evaluation.harness import EvaluationHarness

        path = Path(report_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        report = EvaluationHarness.load_report(path)

        classified = self.extract_and_classify(report)
        if not classified:
            logger.info("No failures found in report %s", report_path)
            return classified, Path()

        # Export regression suite
        reg_path = self.export_regression_suite(classified)

        # Write triage report
        triage_md = self.generate_triage_report(classified)
        triage_path = self.reports_dir / f"triage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(triage_path, "w", encoding="utf-8") as f:
            f.write(triage_md)
        logger.info("Triage report written to %s", triage_path)

        return classified, reg_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cli_main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Closed-loop automation: extract failures, classify, export regression"
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Path to evaluation report JSON file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output YAML path for regression suite (optional)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    loop = LoopAutomation()

    classified, reg_path = loop.run_from_report_file(args.report)

    if not classified:
        print("  No failures found. Nothing to do.")
        sys.exit(0)

    print(f"\n  Classified {len(classified)} failures:")
    for cf in classified:
        print(f"    [{cf.category}] {cf.task_id}: {cf.task_description[:50]}")

    if reg_path and reg_path.exists():
        print(f"\n  Regression suite exported to: {reg_path}")

    # Also print triage
    triage = loop.generate_triage_report(classified)
    print("\n" + triage)


if __name__ == "__main__":
    _cli_main()
