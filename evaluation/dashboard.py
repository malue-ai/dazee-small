"""
评估指标看板
提供实时评估指标监控和可视化（文本格式）
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
from .models import EvaluationReport
from .metrics import MetricsCalculator, MetricSummary, format_metric_summary


class EvaluationDashboard:
    """评估指标看板"""
    
    def __init__(self, reports_dir: Path = Path("evaluation/reports")):
        """
        初始化看板
        
        Args:
            reports_dir: 评估报告存储目录
        """
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def load_recent_reports(self, days: int = 7) -> List[EvaluationReport]:
        """
        加载最近的评估报告
        
        Args:
            days: 加载最近 N 天的报告
            
        Returns:
            评估报告列表
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        reports = []
        
        for report_file in self.reports_dir.glob("*.json"):
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    report = EvaluationReport(**data)
                    
                    # 检查时间戳
                    report_date = datetime.fromisoformat(report.timestamp.replace("Z", "+00:00"))
                    if report_date >= cutoff_date:
                        reports.append(report)
            except Exception as e:
                print(f"⚠️  加载报告失败 {report_file}: {e}")
        
        # 按时间排序
        reports.sort(key=lambda r: r.timestamp, reverse=True)
        
        return reports
    
    def generate_dashboard(self, days: int = 7) -> str:
        """
        生成看板（文本格式）
        
        Args:
            days: 显示最近 N 天的数据
            
        Returns:
            看板文本
        """
        reports = self.load_recent_reports(days)
        
        if not reports:
            return "暂无评估报告"
        
        lines = []
        lines.append("=" * 100)
        lines.append("ZenFlux Agent 评估指标看板")
        lines.append("=" * 100)
        lines.append(f"时间范围: 最近 {days} 天")
        lines.append(f"报告数量: {len(reports)}")
        lines.append(f"最后更新: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("")
        
        # 1. 趋势分析
        lines.append("📈 趋势分析")
        lines.append("-" * 100)
        trend = self._analyze_trend(reports)
        lines.append(f"  总体得分趋势: {trend['overall_score_trend']}")
        lines.append(f"  任务成功率趋势: {trend['task_success_rate_trend']}")
        lines.append(f"  质量得分趋势: {trend['quality_score_trend']}")
        lines.append("")
        
        # 2. 最新评估摘要
        lines.append("📊 最新评估摘要")
        lines.append("-" * 100)
        latest_report = reports[0]
        calculator = MetricsCalculator()
        latest_summary = calculator.calculate(latest_report)
        
        lines.append(f"  评估套件: {latest_report.suite_name}")
        lines.append(f"  评估时间: {latest_report.timestamp}")
        lines.append(f"  总体得分: {latest_summary.overall_score:.1%}")
        lines.append(f"  质量分层: {latest_summary.quality_tier}")
        lines.append(f"  任务成功率: {self._get_metric_value(latest_summary, 'task_success_rate'):.1%}")
        lines.append(f"  平均质量得分: {self._get_metric_value(latest_summary, 'avg_quality_score'):.1f}/10")
        lines.append("")
        
        # 3. 关键指标历史
        lines.append("📉 关键指标历史（最近 5 次评估）")
        lines.append("-" * 100)
        history_table = self._generate_history_table(reports[:5])
        lines.append(history_table)
        lines.append("")
        
        # 4. 失败案例Top 5
        lines.append("❌ 失败案例 Top 5")
        lines.append("-" * 100)
        failed_tasks = self._get_failed_tasks(latest_report, limit=5)
        for i, task in enumerate(failed_tasks, 1):
            lines.append(f"  {i}. {task['task_id']}")
            lines.append(f"     失败原因: {task['failure_reason']}")
        lines.append("")
        
        # 5. 告警信息
        lines.append("⚠️  告警信息")
        lines.append("-" * 100)
        alerts = self._check_alerts(latest_summary, reports)
        if alerts:
            for alert in alerts:
                lines.append(f"  {alert['severity']} {alert['message']}")
        else:
            lines.append("  ✅ 无告警")
        lines.append("")
        
        lines.append("=" * 100)
        
        return "\n".join(lines)
    
    def _analyze_trend(self, reports: List[EvaluationReport]) -> Dict[str, str]:
        """分析趋势"""
        if len(reports) < 2:
            return {
                "overall_score_trend": "数据不足",
                "task_success_rate_trend": "数据不足",
                "quality_score_trend": "数据不足"
            }
        
        calculator = MetricsCalculator()
        
        # 计算最近两次的指标
        latest_summary = calculator.calculate(reports[0])
        previous_summary = calculator.calculate(reports[1])
        
        def trend_indicator(current: float, previous: float) -> str:
            diff = current - previous
            if abs(diff) < 0.01:
                return f"持平 ({current:.1%})"
            elif diff > 0:
                return f"上升 ↗️ ({previous:.1%} → {current:.1%}, +{diff:.1%})"
            else:
                return f"下降 ↘️ ({previous:.1%} → {current:.1%}, {diff:.1%})"
        
        return {
            "overall_score_trend": trend_indicator(
                latest_summary.overall_score,
                previous_summary.overall_score
            ),
            "task_success_rate_trend": trend_indicator(
                self._get_metric_value(latest_summary, "task_success_rate"),
                self._get_metric_value(previous_summary, "task_success_rate")
            ),
            "quality_score_trend": trend_indicator(
                self._get_metric_value(latest_summary, "avg_quality_score") / 10.0,
                self._get_metric_value(previous_summary, "avg_quality_score") / 10.0
            )
        }
    
    def _generate_history_table(self, reports: List[EvaluationReport]) -> str:
        """生成历史记录表格"""
        calculator = MetricsCalculator()
        
        lines = []
        header = f"  {'时间':<20} | {'总分':<8} | {'成功率':<8} | {'质量':<8} | {'分层':<12}"
        lines.append(header)
        lines.append("  " + "-" * 95)
        
        for report in reports:
            summary = calculator.calculate(report)
            timestamp = report.timestamp[:19]  # 截取到秒
            overall = f"{summary.overall_score:.1%}"
            success = f"{self._get_metric_value(summary, 'task_success_rate'):.1%}"
            quality = f"{self._get_metric_value(summary, 'avg_quality_score'):.1f}/10"
            tier = summary.quality_tier
            
            line = f"  {timestamp:<20} | {overall:<8} | {success:<8} | {quality:<8} | {tier:<12}"
            lines.append(line)
        
        return "\n".join(lines)
    
    def _get_failed_tasks(
        self,
        report: EvaluationReport,
        limit: int = 5
    ) -> List[Dict[str, str]]:
        """获取失败的任务"""
        failed_tasks = []
        
        for result in report.results:
            if not result.passed:
                # 找出失败的 grader
                failed_graders = []
                for trial in result.trials:
                    for grade in trial.grades:
                        if not grade.passed:
                            failed_graders.append(f"{grade.grader_name} ({grade.reasoning})")
                
                failed_tasks.append({
                    "task_id": result.task_id,
                    "failure_reason": "; ".join(failed_graders[:2])  # 只显示前2个
                })
        
        return failed_tasks[:limit]
    
    def _check_alerts(
        self,
        latest_summary: MetricSummary,
        reports: List[EvaluationReport]
    ) -> List[Dict[str, str]]:
        """检查告警"""
        alerts = []
        
        # 1. 回归告警
        if latest_summary.regression_detected:
            alerts.append({
                "severity": "🔴 严重",
                "message": "检测到性能回归，请立即检查最新变更"
            })
        
        # 2. 质量分层告警
        if latest_summary.quality_tier == "POOR":
            alerts.append({
                "severity": "🔴 严重",
                "message": f"质量分层为 POOR（总分 {latest_summary.overall_score:.1%}），建议暂停发布"
            })
        elif latest_summary.quality_tier == "ACCEPTABLE":
            alerts.append({
                "severity": "🟡 警告",
                "message": f"质量分层为 ACCEPTABLE（总分 {latest_summary.overall_score:.1%}），建议优化后发布"
            })
        
        # 3. 关键指标告警
        for metric in latest_summary.metrics:
            if not metric.passed and metric.name in ["task_success_rate", "code_pass_rate", "error_rate"]:
                alerts.append({
                    "severity": "🟡 警告",
                    "message": f"{metric.description} 未达标：{metric.value:.1%}（阈值：{metric.threshold:.1%}）"
                })
        
        # 4. 连续下降告警
        if len(reports) >= 3:
            calculator = MetricsCalculator()
            recent_scores = [
                calculator.calculate(r).overall_score
                for r in reports[:3]
            ]
            if recent_scores[0] < recent_scores[1] < recent_scores[2]:
                alerts.append({
                    "severity": "🟡 警告",
                    "message": "总体得分连续 3 次下降，请关注质量趋势"
                })
        
        return alerts
    
    def _get_metric_value(self, summary: MetricSummary, metric_name: str) -> float:
        """获取指标值"""
        metric = next((m for m in summary.metrics if m.name == metric_name), None)
        return metric.value if metric else 0.0
    
    def export_to_json(self, output_file: Path) -> None:
        """导出看板数据为 JSON（用于外部可视化工具）"""
        reports = self.load_recent_reports(days=30)
        calculator = MetricsCalculator()
        
        dashboard_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "reports": []
        }
        
        for report in reports:
            summary = calculator.calculate(report)
            dashboard_data["reports"].append({
                "timestamp": report.timestamp,
                "suite_name": report.suite_name,
                "overall_score": summary.overall_score,
                "quality_tier": summary.quality_tier,
                "regression_detected": summary.regression_detected,
                "metrics": [
                    {
                        "name": m.name,
                        "value": m.value,
                        "threshold": m.threshold,
                        "passed": m.passed,
                        "description": m.description
                    }
                    for m in summary.metrics
                ]
            })
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 看板数据已导出到 {output_file}")
