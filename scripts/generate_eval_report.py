"""
小搭子测评报告生成脚本

Usage:
    # 从 JSON 报告生成 Markdown
    python scripts/generate_eval_report.py --report-id <id>

    # 从最近一次合并报告生成
    python scripts/generate_eval_report.py --latest

    # 指定输出目录
    python scripts/generate_eval_report.py --latest --output evaluation/reports/
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.harness import EvaluationHarness
from evaluation.models import EvaluationReport

REPORTS_DIR = PROJECT_ROOT / "evaluation" / "reports"


# ---------------------------------------------------------------------------
# Report loading
# ---------------------------------------------------------------------------


def find_latest_combined() -> Path | None:
    """Find the latest combined_*.json in reports dir."""
    candidates = sorted(REPORTS_DIR.glob("combined_*.json"), reverse=True)
    return candidates[0] if candidates else None


def find_report_by_id(report_id: str) -> Path | None:
    """Find a report JSON by its id prefix."""
    for p in REPORTS_DIR.glob("*.json"):
        if report_id in p.stem:
            return p
    return None


def load_combined(path: Path) -> dict:
    """Load a combined report JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def generate_combined_markdown(combined: dict, detail_reports: list[EvaluationReport]) -> str:
    """Generate a comprehensive Markdown report from combined data and detail reports."""
    lines = [
        "# 小搭子能力测评报告",
        "",
        f"**生成时间**: {combined.get('timestamp', datetime.now().isoformat())}",
        "",
        "---",
        "",
        "## 总览",
        "",
    ]

    feas = combined.get("feasibility", {})
    eff = combined.get("efficiency", {})

    f_score = feas.get("score")
    e_score = eff.get("score")

    if f_score is not None:
        total = feas.get("total", 0)
        passed = feas.get("passed", 0)
        lines.append(f"| 维度 | 得分 | 详情 |")
        lines.append(f"|------|------|------|")
        lines.append(f"| 可行性 | {f_score:.1%} | {passed}/{total} PASS |")
    if e_score is not None:
        lines.append(f"| 效率性 | {e_score:.2f} | 加权平均 |")

    if f_score is not None and e_score is not None:
        overall = 0.6 * f_score + 0.4 * e_score
        gate = f_score >= 0.75 and e_score >= 0.55
        lines.extend([
            "",
            f"**综合得分**: {overall:.2%}",
            f"**发布门禁**: {'PASS' if gate else 'BLOCKED'}",
        ])

    # Detail per suite
    if detail_reports:
        lines.extend(["", "---", "", "## 套件详情", ""])
        for r in detail_reports:
            lines.extend([
                f"### {r.suite_name}",
                "",
                f"| 指标 | 值 |",
                f"|------|-----|",
                f"| 任务数 | {r.total_tasks} |",
                f"| 通过 | {r.passed_tasks} |",
                f"| 失败 | {r.failed_tasks} |",
                f"| 通过率 | {r.pass_rate:.1%} |",
                f"| 总 Token | {r.total_token_usage.total_tokens} |",
                f"| 耗时 | {r.total_duration_seconds:.1f}s |",
                "",
            ])

            # Per-task detail
            lines.append("| 任务 | 通过率 | 平均分 | 稳定性 |")
            lines.append("|------|--------|--------|--------|")
            for tr in r.task_results:
                avg = f"{tr.average_score:.2f}" if tr.average_score is not None else "N/A"
                stable = "稳定" if tr.is_stable else "不稳定"
                lines.append(
                    f"| {tr.task_id} | {tr.pass_rate:.0%} | {avg} | {stable} |"
                )
            lines.append("")

    # Failures
    failures = []
    for r in detail_reports:
        for tr in r.task_results:
            if tr.pass_rate < 0.5:
                failures.append((r.suite_name, tr.task_id, tr.task_description))

    if failures:
        lines.extend(["---", "", "## 失败用例", ""])
        lines.append("| 套件 | 用例 ID | 描述 |")
        lines.append("|------|--------|------|")
        for suite, tid, desc in failures:
            lines.append(f"| {suite} | {tid} | {desc[:60]} |")
        lines.append("")

    # Recommendations placeholder
    lines.extend([
        "---",
        "",
        "## 改进建议",
        "",
        "> 基于失败用例和效率性得分，按「闭环优化流程」进行修复和回归验证。",
        "> 详见 `docs/benchmark/xiaodazi_eval.md` 第五节。",
        "",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate xiaodazi eval report")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--report-id", type=str, help="Report ID (prefix match)")
    group.add_argument("--latest", action="store_true", help="Use latest combined report")
    parser.add_argument(
        "--output",
        type=str,
        default=str(REPORTS_DIR),
        help="Output directory",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load combined report
    if args.latest:
        combined_path = find_latest_combined()
        if not combined_path:
            print("ERROR: No combined_*.json found in evaluation/reports/")
            sys.exit(1)
    else:
        combined_path = find_report_by_id(args.report_id)
        if not combined_path:
            print(f"ERROR: No report found matching id '{args.report_id}'")
            sys.exit(1)

    combined = load_combined(combined_path)
    print(f"  Loaded combined report: {combined_path.name}")

    # Load detail reports
    detail_reports: list[EvaluationReport] = []
    for rid in combined.get("reports", []):
        rpath = find_report_by_id(rid)
        if rpath:
            try:
                detail_reports.append(EvaluationHarness.load_report(rpath))
            except Exception as e:
                print(f"  WARNING: Could not load detail report {rid}: {e}")

    # Generate markdown
    md_content = generate_combined_markdown(combined, detail_reports)

    # Write output
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"xiaodazi_eval_report_{ts}.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"  Report generated: {out_file}")
    print(f"  ({len(detail_reports)} detail reports included)")


if __name__ == "__main__":
    main()
