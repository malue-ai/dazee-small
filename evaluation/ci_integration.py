"""
CI/CD 集成脚本
在持续集成流程中自动运行评估并根据结果决定是否允许发布
"""
import sys
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from uuid import uuid4
import argparse

from .harness import EvaluationHarness
from .metrics import MetricsCalculator, format_metric_summary
from .alerts import AlertManager, AlertSeverity, console_notifier, file_notifier
from .dashboard import EvaluationDashboard
from .qos_config import QOS_EVAL_CONFIGS, QoSLevel
from .promptfoo_adapter import PromptfooAdapter
from .models import EvaluationReport, TokenUsage


class CIEvaluationRunner:
    """CI 评估运行器"""
    
    def __init__(
        self,
        suites_dir: Path = Path("evaluation/suites"),
        reports_dir: Path = Path("evaluation/reports"),
        baseline_report_path: Optional[Path] = None,
        strict_mode: bool = True
    ):
        """
        初始化 CI 评估运行器
        
        Args:
            suites_dir: 评测套件目录
            reports_dir: 评估报告目录
            baseline_report_path: 基线报告路径（用于回归检测）
            strict_mode: 严格模式（如果为 True，任何 CRITICAL 告警都会导致失败）
        """
        self.harness = EvaluationHarness(
            suites_dir=suites_dir,
            reports_dir=reports_dir
        )
        self.dashboard = EvaluationDashboard(reports_dir=reports_dir)
        self.baseline_report_path = baseline_report_path
        self.strict_mode = strict_mode
        
        # 设置告警管理器
        self.alert_manager = AlertManager()
        self.alert_manager.add_notifier(console_notifier)
        self.alert_manager.add_notifier(file_notifier("evaluation/alerts.log"))
        
        # Promptfoo 适配器
        self.promptfoo_adapter = PromptfooAdapter()
    
    async def run_for_qos_level(self, qos_level: QoSLevel) -> int:
        """
        为指定 QoS 等级运行评估
        
        Args:
            qos_level: QoS 等级
            
        Returns:
            退出码（0 表示成功，1 表示失败）
        """
        print(f"\n{'='*80}")
        print(f"开始运行 QoS {qos_level.value} 评估")
        print(f"{'='*80}\n")
        
        config = QOS_EVAL_CONFIGS[qos_level]
        
        # 步骤 1: 运行 Promptfoo 套件（快速回归）
        promptfoo_reports = await self._run_promptfoo_suites(config)
        all_reports = promptfoo_reports  # 先添加 Promptfoo 报告
        
        # 步骤 2: 运行 ZenFlux Agent 套件（全面评估）
        for suite_name in config.suites:
            print(f"\n📦 运行评测套件: {suite_name}")
            print(f"   试验次数: {config.trials}")
            print(f"   并发数: {config.concurrency}")
            
            try:
                report = await self.harness.run_suite(
                    suite_name=suite_name,
                    num_trials=config.trials,
                    concurrency=config.concurrency
                )
                all_reports.append(report)
                
                # 打印简要结果
                passed = sum(1 for r in report.results if r.passed)
                total = len(report.results)
                print(f"   结果: {passed}/{total} 任务通过")
                
            except Exception as e:
                print(f"   ❌ 评测套件运行失败: {e}")
                return 1
        
        # 合并所有报告并计算指标
        if not all_reports:
            print("\n❌ 没有成功的评估报告")
            return 1
        
        # 合并所有报告（Promptfoo + ZenFlux）
        main_report = self._merge_reports(all_reports)
        
        # 加载基线报告（如果有）
        baseline_report = None
        if self.baseline_report_path and self.baseline_report_path.exists():
            baseline_report = EvaluationHarness.load_report(self.baseline_report_path)
            print(f"\n📊 加载基线报告: {self.baseline_report_path}")
        
        # 计算指标
        calculator = MetricsCalculator(baseline_report=baseline_report)
        summary = calculator.calculate(main_report)
        
        # 打印指标摘要
        print("\n" + format_metric_summary(summary))
        
        # 检查告警
        alerts = self.alert_manager.check_all(summary)
        
        # 判断是否通过
        return self._determine_exit_code(summary, alerts, config)
    
    async def _run_promptfoo_suites(self, config) -> List[EvaluationReport]:
        """
        运行 Promptfoo 套件（快速回归测试）
        
        Args:
            config: QoS 配置
            
        Returns:
            List[EvaluationReport]: Promptfoo 转换后的报告列表
        """
        import subprocess
        import tempfile
        
        promptfoo_dir = self.suites_dir / "promptfoo"
        if not promptfoo_dir.exists():
            print("⚠️  Promptfoo 套件目录不存在，跳过")
            return []
        
        reports = []
        
        # 查找所有 Promptfoo YAML 配置文件
        promptfoo_configs = list(promptfoo_dir.glob("*.yaml"))
        if not promptfoo_configs:
            print("⚠️  未找到 Promptfoo 配置文件，跳过")
            return []
        
        print(f"\n🚀 运行 Promptfoo 套件（快速回归）")
        print(f"   找到 {len(promptfoo_configs)} 个配置文件\n")
        
        for config_file in promptfoo_configs:
            suite_name = config_file.stem
            print(f"   📦 运行: {suite_name}")
            
            try:
                # 运行 Promptfoo
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                    result_file = Path(tmp_file.name)
                
                # 检查是否安装了 promptfoo
                try:
                    result = subprocess.run(
                        ["npx", "promptfoo", "eval", "-c", str(config_file), "-o", str(result_file)],
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 分钟超时
                    )
                    
                    if result.returncode != 0:
                        print(f"      ⚠️  Promptfoo 运行失败: {result.stderr[:200]}")
                        continue
                    
                    # 转换结果
                    if result_file.exists():
                        report = self.promptfoo_adapter.convert_result(
                            result_file,
                            suite_name=f"promptfoo_{suite_name}"
                        )
                        reports.append(report)
                        
                        # 打印简要结果
                        passed = sum(1 for tr in report.task_results if tr.pass_rate >= 0.5)
                        total = len(report.task_results)
                        print(f"      ✅ 结果: {passed}/{total} 任务通过")
                    else:
                        print(f"      ⚠️  结果文件未生成")
                
                except FileNotFoundError:
                    print(f"      ⚠️  Promptfoo 未安装，跳过（需要: npm install -g promptfoo）")
                    continue
                except subprocess.TimeoutExpired:
                    print(f"      ⚠️  Promptfoo 运行超时")
                    continue
                except Exception as e:
                    print(f"      ⚠️  运行失败: {e}")
                    continue
                finally:
                    # 清理临时文件
                    if result_file.exists():
                        result_file.unlink()
            
            except Exception as e:
                print(f"      ❌ 处理失败: {e}")
                continue
        
        return reports
    
    def _merge_reports(self, reports: List[EvaluationReport]) -> EvaluationReport:
        """
        合并多个评估报告
        
        Args:
            reports: 报告列表
            
        Returns:
            EvaluationReport: 合并后的报告
        """
        if not reports:
            raise ValueError("无法合并空报告列表")
        
        if len(reports) == 1:
            return reports[0]
        
        # 合并所有任务结果
        all_task_results = []
        for report in reports:
            all_task_results.extend(report.task_results)
        
        # 计算统计信息
        total_tasks = len(all_task_results)
        passed_tasks = sum(1 for tr in all_task_results if tr.pass_rate >= 0.5)
        failed_tasks = total_tasks - passed_tasks
        unstable_tasks = sum(1 for tr in all_task_results if not tr.is_stable)
        
        # 汇总 Token 使用
        total_token_usage = TokenUsage()
        total_duration = 0.0
        
        for report in reports:
            total_token_usage.input_tokens += report.total_token_usage.input_tokens
            total_token_usage.output_tokens += report.total_token_usage.output_tokens
            total_token_usage.thinking_tokens += report.total_token_usage.thinking_tokens
            total_duration += report.total_duration_seconds
        
        # 创建合并后的报告
        merged_report = EvaluationReport(
            report_id=str(uuid4()),
            suite_id=f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            suite_name=f"合并报告 ({len(reports)} 个套件)",
            task_results=all_task_results,
            total_tasks=total_tasks,
            passed_tasks=passed_tasks,
            failed_tasks=failed_tasks,
            unstable_tasks=unstable_tasks,
            total_token_usage=total_token_usage,
            total_duration_seconds=total_duration,
            created_at=datetime.utcnow()
        )
        
        return merged_report
    
    async def run_all_qos_levels(self) -> int:
        """
        运行所有 QoS 等级的评估（用于全面回归测试）
        
        Returns:
            退出码（0 表示成功，1 表示失败）
        """
        print("\n" + "="*80)
        print("运行全面评估（所有 QoS 等级）")
        print("="*80)
        
        failed_levels = []
        
        for qos_level in QoSLevel:
            exit_code = await self.run_for_qos_level(qos_level)
            if exit_code != 0:
                failed_levels.append(qos_level.value)
        
        if failed_levels:
            print(f"\n❌ 以下 QoS 等级评估失败: {', '.join(failed_levels)}")
            return 1
        else:
            print(f"\n✅ 所有 QoS 等级评估通过")
            return 0
    
    def _determine_exit_code(
        self,
        summary,
        alerts,
        config
    ) -> int:
        """
        根据评估结果和告警决定退出码
        
        Args:
            summary: 指标汇总
            alerts: 告警列表
            config: QoS 配置
            
        Returns:
            退出码（0 表示成功，1 表示失败）
        """
        # 1. 检查总体得分是否达到阈值
        if summary.overall_score < config.min_overall_score:
            print(f"\n❌ 总体得分 ({summary.overall_score:.1%}) "
                  f"低于阈值 ({config.min_overall_score:.1%})")
            return 1
        
        # 2. 检查任务成功率是否达标
        task_success_rate = next(
            (m.value for m in summary.metrics if m.name == "task_success_rate"),
            0.0
        )
        if task_success_rate < config.min_task_success_rate:
            print(f"\n❌ 任务成功率 ({task_success_rate:.1%}) "
                  f"低于阈值 ({config.min_task_success_rate:.1%})")
            return 1
        
        # 3. 检查质量得分是否达标
        avg_quality_score = next(
            (m.value for m in summary.metrics if m.name == "avg_quality_score"),
            0.0
        )
        if avg_quality_score < config.min_quality_score:
            print(f"\n❌ 平均质量得分 ({avg_quality_score:.1f}/10) "
                  f"低于阈值 ({config.min_quality_score:.1f}/10)")
            return 1
        
        # 4. 在严格模式下，检查是否有 CRITICAL 告警
        if self.strict_mode:
            critical_alerts = [a for a in alerts if a.severity == AlertSeverity.CRITICAL]
            if critical_alerts:
                print(f"\n❌ 检测到 {len(critical_alerts)} 个严重告警，阻塞发布")
                for alert in critical_alerts:
                    print(f"   - {alert.title}")
                return 1
        
        # 5. 所有检查通过
        print(f"\n✅ 评估通过（总分: {summary.overall_score:.1%}, "
              f"分层: {summary.quality_tier}）")
        return 0


async def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description="ZenFlux Agent CI 评估工具"
    )
    parser.add_argument(
        "--qos-level",
        type=str,
        choices=["FREE", "BASIC", "PRO", "ENTERPRISE", "ALL"],
        default="BASIC",
        help="要运行的 QoS 等级（默认：BASIC）"
    )
    parser.add_argument(
        "--baseline",
        type=str,
        help="基线报告路径（用于回归检测）"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="严格模式：任何 CRITICAL 告警都会导致失败（默认：True）"
    )
    parser.add_argument(
        "--suites-dir",
        type=str,
        default="evaluation/suites",
        help="评测套件目录"
    )
    parser.add_argument(
        "--reports-dir",
        type=str,
        default="evaluation/reports",
        help="评估报告目录"
    )
    
    args = parser.parse_args()
    
    # 初始化运行器
    runner = CIEvaluationRunner(
        suites_dir=Path(args.suites_dir),
        reports_dir=Path(args.reports_dir),
        baseline_report_path=Path(args.baseline) if args.baseline else None,
        strict_mode=args.strict
    )
    
    # 运行评估
    if args.qos_level == "ALL":
        exit_code = await runner.run_all_qos_levels()
    else:
        qos_level = QoSLevel(args.qos_level)
        exit_code = await runner.run_for_qos_level(qos_level)
    
    # 生成看板
    print("\n" + "="*80)
    print("生成评估看板")
    print("="*80)
    dashboard_text = runner.dashboard.generate_dashboard(days=7)
    print(dashboard_text)
    
    # 导出看板数据
    runner.dashboard.export_to_json(Path(args.reports_dir) / "dashboard.json")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
