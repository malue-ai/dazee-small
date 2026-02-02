"""
评估指标计算模块
计算核心指标：准确率、完整度、效率、用户满意度等
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from statistics import mean, stdev
from .models import EvaluationReport, TaskResult, GraderType


@dataclass
class MetricResult:
    """单个指标结果"""
    name: str
    value: float
    threshold: float
    passed: bool
    unit: str = ""
    description: str = ""


@dataclass
class MetricSummary:
    """指标汇总"""
    overall_score: float
    metrics: List[MetricResult]
    quality_tier: str  # EXCELLENT, GOOD, ACCEPTABLE, POOR
    regression_detected: bool
    recommendations: List[str]


class MetricsCalculator:
    """评估指标计算器"""
    
    # 质量分层阈值
    QUALITY_THRESHOLDS = {
        "EXCELLENT": 0.90,
        "GOOD": 0.75,
        "ACCEPTABLE": 0.60,
        "POOR": 0.0
    }
    
    def __init__(self, baseline_report: Optional[EvaluationReport] = None):
        """
        初始化指标计算器
        
        Args:
            baseline_report: 基线评测报告，用于回归检测
        """
        self.baseline_report = baseline_report
    
    def calculate(self, report: EvaluationReport) -> MetricSummary:
        """
        计算所有指标
        
        Args:
            report: 评测报告
            
        Returns:
            指标汇总
        """
        metrics = []
        
        # 1. 准确率指标
        accuracy_metrics = self._calculate_accuracy(report)
        metrics.extend(accuracy_metrics)
        
        # 2. 完整度指标
        completeness_metrics = self._calculate_completeness(report)
        metrics.extend(completeness_metrics)
        
        # 3. 效率指标
        efficiency_metrics = self._calculate_efficiency(report)
        metrics.extend(efficiency_metrics)
        
        # 4. 质量指标
        quality_metrics = self._calculate_quality(report)
        metrics.extend(quality_metrics)
        
        # 5. 稳定性指标
        stability_metrics = self._calculate_stability(report)
        metrics.extend(stability_metrics)
        
        # 计算总体得分（加权平均）
        overall_score = self._calculate_overall_score(metrics)
        
        # 判断质量分层
        quality_tier = self._determine_quality_tier(overall_score)
        
        # 回归检测
        regression_detected = self._detect_regression(report)
        
        # 生成改进建议
        recommendations = self._generate_recommendations(metrics, report)
        
        return MetricSummary(
            overall_score=overall_score,
            metrics=metrics,
            quality_tier=quality_tier,
            regression_detected=regression_detected,
            recommendations=recommendations
        )
    
    def _calculate_accuracy(self, report: EvaluationReport) -> List[MetricResult]:
        """计算准确率相关指标"""
        metrics = []
        
        # Code-based grader 通过率
        code_passed = sum(
            1 for r in report.results
            for t in r.trials
            for g in t.grades
            if g.grader_type == GraderType.CODE and g.passed
        )
        code_total = sum(
            1 for r in report.results
            for t in r.trials
            for g in t.grades
            if g.grader_type == GraderType.CODE
        )
        if code_total > 0:
            code_pass_rate = code_passed / code_total
            metrics.append(MetricResult(
                name="code_pass_rate",
                value=code_pass_rate,
                threshold=0.95,
                passed=code_pass_rate >= 0.95,
                unit="%",
                description="代码级检查通过率（工具调用、格式、语法等）"
            ))
        
        # Model-based grader 通过率
        model_passed = sum(
            1 for r in report.results
            for t in r.trials
            for g in t.grades
            if g.grader_type == GraderType.MODEL and g.passed
        )
        model_total = sum(
            1 for r in report.results
            for t in r.trials
            for g in t.grades
            if g.grader_type == GraderType.MODEL
        )
        if model_total > 0:
            model_pass_rate = model_passed / model_total
            metrics.append(MetricResult(
                name="model_pass_rate",
                value=model_pass_rate,
                threshold=0.80,
                passed=model_pass_rate >= 0.80,
                unit="%",
                description="模型级检查通过率（意图理解、质量、逻辑等）"
            ))
        
        # 整体任务成功率
        task_passed = sum(1 for r in report.results if r.passed)
        task_total = len(report.results)
        if task_total > 0:
            task_success_rate = task_passed / task_total
            metrics.append(MetricResult(
                name="task_success_rate",
                value=task_success_rate,
                threshold=0.85,
                passed=task_success_rate >= 0.85,
                unit="%",
                description="整体任务成功率（所有 grader 全部通过）"
            ))
        
        return metrics
    
    def _calculate_completeness(self, report: EvaluationReport) -> List[MetricResult]:
        """计算完整度相关指标"""
        metrics = []
        
        # 响应完整性（检查是否有空响应、截断等）
        complete_responses = sum(
            1 for r in report.results
            for t in r.trials
            if t.outcome and t.outcome.transcript and t.outcome.transcript.messages
        )
        total_trials = sum(len(r.trials) for r in report.results)
        if total_trials > 0:
            response_completeness = complete_responses / total_trials
            metrics.append(MetricResult(
                name="response_completeness",
                value=response_completeness,
                threshold=0.98,
                passed=response_completeness >= 0.98,
                unit="%",
                description="响应完整性（无空响应、无截断）"
            ))
        
        # 工具调用成功率
        successful_tool_calls = sum(
            1 for r in report.results
            for t in r.trials
            if t.outcome and t.outcome.transcript
            for tool_call in t.outcome.transcript.tool_calls
            if tool_call.get("status") == "success"
        )
        total_tool_calls = sum(
            1 for r in report.results
            for t in r.trials
            if t.outcome and t.outcome.transcript
            for _ in t.outcome.transcript.tool_calls
        )
        if total_tool_calls > 0:
            tool_success_rate = successful_tool_calls / total_tool_calls
            metrics.append(MetricResult(
                name="tool_success_rate",
                value=tool_success_rate,
                threshold=0.90,
                passed=tool_success_rate >= 0.90,
                unit="%",
                description="工具调用成功率"
            ))
        
        return metrics
    
    def _calculate_efficiency(self, report: EvaluationReport) -> List[MetricResult]:
        """计算效率相关指标"""
        metrics = []
        
        # 平均执行时间
        execution_times = [
            t.outcome.execution_time
            for r in report.results
            for t in r.trials
            if t.outcome and t.outcome.execution_time
        ]
        if execution_times:
            avg_execution_time = mean(execution_times)
            metrics.append(MetricResult(
                name="avg_execution_time",
                value=avg_execution_time,
                threshold=30.0,
                passed=avg_execution_time <= 30.0,
                unit="s",
                description="平均执行时间"
            ))
        
        # Token 使用效率（输出/输入比）
        token_ratios = [
            t.outcome.token_usage.completion_tokens / max(t.outcome.token_usage.prompt_tokens, 1)
            for r in report.results
            for t in r.trials
            if t.outcome and t.outcome.token_usage
        ]
        if token_ratios:
            avg_token_ratio = mean(token_ratios)
            metrics.append(MetricResult(
                name="token_efficiency",
                value=avg_token_ratio,
                threshold=0.5,
                passed=avg_token_ratio <= 0.5,
                unit="",
                description="Token 使用效率（输出/输入比，越低越好）"
            ))
        
        # 工具调用效率（平均调用次数）
        tool_call_counts = [
            len(t.outcome.transcript.tool_calls)
            for r in report.results
            for t in r.trials
            if t.outcome and t.outcome.transcript
        ]
        if tool_call_counts:
            avg_tool_calls = mean(tool_call_counts)
            metrics.append(MetricResult(
                name="avg_tool_calls",
                value=avg_tool_calls,
                threshold=5.0,
                passed=avg_tool_calls <= 5.0,
                unit="",
                description="平均工具调用次数（合理范围内越少越好）"
            ))
        
        return metrics
    
    def _calculate_quality(self, report: EvaluationReport) -> List[MetricResult]:
        """计算质量相关指标"""
        metrics = []
        
        # LLM-as-Judge 平均得分
        model_scores = [
            g.score
            for r in report.results
            for t in r.trials
            for g in t.grades
            if g.grader_type == GraderType.MODEL and g.score is not None
        ]
        if model_scores:
            avg_quality_score = mean(model_scores)
            metrics.append(MetricResult(
                name="avg_quality_score",
                value=avg_quality_score,
                threshold=7.0,
                passed=avg_quality_score >= 7.0,
                unit="/10",
                description="LLM-as-Judge 平均质量得分"
            ))
        
        # 高置信度评分占比
        high_confidence_grades = sum(
            1 for r in report.results
            for t in r.trials
            for g in t.grades
            if g.grader_type == GraderType.MODEL and g.confidence and g.confidence >= 0.8
        )
        total_model_grades = sum(
            1 for r in report.results
            for t in r.trials
            for g in t.grades
            if g.grader_type == GraderType.MODEL and g.confidence is not None
        )
        if total_model_grades > 0:
            high_confidence_rate = high_confidence_grades / total_model_grades
            metrics.append(MetricResult(
                name="high_confidence_rate",
                value=high_confidence_rate,
                threshold=0.70,
                passed=high_confidence_rate >= 0.70,
                unit="%",
                description="高置信度评分占比（>=0.8）"
            ))
        
        # 需要人工复审的比例（应该较低）
        needs_review = sum(
            1 for r in report.results
            for t in r.trials
            for g in t.grades
            if g.needs_human_review
        )
        total_grades = sum(
            1 for r in report.results
            for t in r.trials
            for _ in t.grades
        )
        if total_grades > 0:
            review_rate = needs_review / total_grades
            metrics.append(MetricResult(
                name="human_review_rate",
                value=review_rate,
                threshold=0.15,
                passed=review_rate <= 0.15,
                unit="%",
                description="需要人工复审的比例（应 ≤15%）"
            ))
        
        return metrics
    
    def _calculate_stability(self, report: EvaluationReport) -> List[MetricResult]:
        """计算稳定性相关指标"""
        metrics = []
        
        # 多次试验一致性（同一任务多次试验的结果应该一致）
        consistency_scores = []
        for result in report.results:
            if len(result.trials) > 1:
                trial_results = [all(g.passed for g in t.grades) for t in result.trials]
                if trial_results:
                    consistency = sum(trial_results) / len(trial_results)
                    consistency_scores.append(consistency)
        
        if consistency_scores:
            avg_consistency = mean(consistency_scores)
            metrics.append(MetricResult(
                name="trial_consistency",
                value=avg_consistency,
                threshold=0.80,
                passed=avg_consistency >= 0.80,
                unit="%",
                description="多次试验一致性（同一任务重复执行的稳定性）"
            ))
        
        # 错误率
        error_count = sum(
            1 for r in report.results
            for t in r.trials
            if t.outcome and t.outcome.error
        )
        total_trials = sum(len(r.trials) for r in report.results)
        if total_trials > 0:
            error_rate = error_count / total_trials
            metrics.append(MetricResult(
                name="error_rate",
                value=error_rate,
                threshold=0.05,
                passed=error_rate <= 0.05,
                unit="%",
                description="执行错误率（应 ≤5%）"
            ))
        
        return metrics
    
    def _calculate_overall_score(self, metrics: List[MetricResult]) -> float:
        """
        计算总体得分（加权平均）
        
        权重分配：
        - 准确率: 40%
        - 质量: 30%
        - 完整度: 15%
        - 稳定性: 10%
        - 效率: 5%
        """
        weights = {
            "code_pass_rate": 0.15,
            "model_pass_rate": 0.15,
            "task_success_rate": 0.10,
            "avg_quality_score": 0.20,
            "high_confidence_rate": 0.10,
            "response_completeness": 0.10,
            "tool_success_rate": 0.05,
            "trial_consistency": 0.08,
            "error_rate": 0.02,
            "avg_execution_time": 0.02,
            "token_efficiency": 0.02,
            "avg_tool_calls": 0.01,
        }
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for metric in metrics:
            if metric.name in weights:
                weight = weights[metric.name]
                # 归一化到 0-1
                if metric.name == "avg_quality_score":
                    normalized_value = metric.value / 10.0
                elif metric.name in ["avg_execution_time", "token_efficiency", "avg_tool_calls", "error_rate", "human_review_rate"]:
                    # 这些是"越低越好"的指标，需要反转
                    normalized_value = max(0, 1 - (metric.value / metric.threshold))
                else:
                    normalized_value = metric.value
                
                weighted_sum += normalized_value * weight
                total_weight += weight
        
        if total_weight > 0:
            return weighted_sum / total_weight
        return 0.0
    
    def _determine_quality_tier(self, overall_score: float) -> str:
        """判断质量分层"""
        for tier, threshold in self.QUALITY_THRESHOLDS.items():
            if overall_score >= threshold:
                return tier
        return "POOR"
    
    def _detect_regression(self, report: EvaluationReport) -> bool:
        """检测回归（与基线对比）"""
        if not self.baseline_report:
            return False
        
        # 对比关键指标
        current_metrics = self.calculate(report)
        baseline_metrics = self.calculate(self.baseline_report)
        
        # 如果整体得分下降超过 5%，视为回归
        score_drop = baseline_metrics.overall_score - current_metrics.overall_score
        if score_drop > 0.05:
            return True
        
        # 检查关键指标是否有显著下降
        critical_metrics = ["task_success_rate", "code_pass_rate", "model_pass_rate"]
        for metric_name in critical_metrics:
            current = next((m for m in current_metrics.metrics if m.name == metric_name), None)
            baseline = next((m for m in baseline_metrics.metrics if m.name == metric_name), None)
            if current and baseline:
                if baseline.value - current.value > 0.10:  # 下降超过 10%
                    return True
        
        return False
    
    def _generate_recommendations(
        self, 
        metrics: List[MetricResult], 
        report: EvaluationReport
    ) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 检查未通过的关键指标
        for metric in metrics:
            if not metric.passed:
                if metric.name == "task_success_rate":
                    recommendations.append(
                        f"任务成功率 ({metric.value:.1%}) 低于阈值 ({metric.threshold:.1%})，"
                        "建议检查失败案例并优化 prompt 或工具实现"
                    )
                elif metric.name == "code_pass_rate":
                    recommendations.append(
                        f"代码级检查通过率 ({metric.value:.1%}) 较低，"
                        "建议检查工具调用格式、响应结构等基础问题"
                    )
                elif metric.name == "model_pass_rate":
                    recommendations.append(
                        f"模型级检查通过率 ({metric.value:.1%}) 较低，"
                        "建议优化意图理解、响应质量或逻辑连贯性"
                    )
                elif metric.name == "avg_quality_score":
                    recommendations.append(
                        f"平均质量得分 ({metric.value:.1f}/10) 较低，"
                        "建议人工复审低分案例并调整 grader rubric"
                    )
                elif metric.name == "avg_execution_time":
                    recommendations.append(
                        f"平均执行时间 ({metric.value:.1f}s) 过长，"
                        "建议优化 Agent 规划策略或工具执行效率"
                    )
                elif metric.name == "trial_consistency":
                    recommendations.append(
                        f"多次试验一致性 ({metric.value:.1%}) 较低，"
                        "说明 Agent 行为不稳定，建议检查随机性或工具可靠性"
                    )
                elif metric.name == "error_rate":
                    recommendations.append(
                        f"错误率 ({metric.value:.1%}) 较高，"
                        "建议检查异常处理和容错机制"
                    )
        
        # 检查需要人工复审的高比例
        review_metric = next((m for m in metrics if m.name == "human_review_rate"), None)
        if review_metric and review_metric.value > 0.20:
            recommendations.append(
                f"需要人工复审的比例 ({review_metric.value:.1%}) 较高，"
                "建议优化 LLM-as-Judge 的 prompt 或增加训练数据以提高置信度"
            )
        
        # 如果没有建议，说明表现良好
        if not recommendations:
            recommendations.append("评测结果整体良好，继续保持！")
        
        return recommendations


def format_metric_summary(summary: MetricSummary) -> str:
    """格式化指标汇总为可读文本"""
    lines = []
    lines.append("=" * 80)
    lines.append("评估指标汇总")
    lines.append("=" * 80)
    lines.append(f"总体得分: {summary.overall_score:.2%}")
    lines.append(f"质量分层: {summary.quality_tier}")
    lines.append(f"回归检测: {'⚠️  发现回归' if summary.regression_detected else '✅ 无回归'}")
    lines.append("")
    
    # 按类别分组
    accuracy_metrics = [m for m in summary.metrics if m.name in ["code_pass_rate", "model_pass_rate", "task_success_rate"]]
    quality_metrics = [m for m in summary.metrics if m.name in ["avg_quality_score", "high_confidence_rate", "human_review_rate"]]
    completeness_metrics = [m for m in summary.metrics if m.name in ["response_completeness", "tool_success_rate"]]
    efficiency_metrics = [m for m in summary.metrics if m.name in ["avg_execution_time", "token_efficiency", "avg_tool_calls"]]
    stability_metrics = [m for m in summary.metrics if m.name in ["trial_consistency", "error_rate"]]
    
    def format_metrics_group(title: str, metrics: List[MetricResult]):
        lines.append(f"\n{title}")
        lines.append("-" * 80)
        for metric in metrics:
            status = "✅" if metric.passed else "❌"
            if metric.unit == "%":
                value_str = f"{metric.value:.1%}"
                threshold_str = f"{metric.threshold:.1%}"
            elif metric.unit == "/10":
                value_str = f"{metric.value:.1f}/10"
                threshold_str = f">={metric.threshold:.1f}"
            else:
                value_str = f"{metric.value:.2f}{metric.unit}"
                threshold_str = f"<={metric.threshold:.2f}{metric.unit}" if metric.name in ["avg_execution_time", "error_rate"] else f">={metric.threshold:.2f}{metric.unit}"
            
            lines.append(f"  {status} {metric.description}")
            lines.append(f"     当前值: {value_str} | 阈值: {threshold_str}")
    
    format_metrics_group("📊 准确率指标", accuracy_metrics)
    format_metrics_group("⭐ 质量指标", quality_metrics)
    format_metrics_group("✓ 完整度指标", completeness_metrics)
    format_metrics_group("⚡ 效率指标", efficiency_metrics)
    format_metrics_group("🔒 稳定性指标", stability_metrics)
    
    lines.append("\n" + "=" * 80)
    lines.append("改进建议")
    lines.append("=" * 80)
    for i, rec in enumerate(summary.recommendations, 1):
        lines.append(f"{i}. {rec}")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)
