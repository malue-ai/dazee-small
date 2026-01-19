"""
人工校准工作流
用于校准 LLM-as-Judge 的评分标准，提高评估可靠性
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
from .models import Task, Trial, GradeResult, GraderType
from .graders.model_based import ModelBasedGraders


@dataclass
class CalibrationCase:
    """校准案例"""
    task_id: str
    trial: Trial
    llm_grades: List[GradeResult]  # LLM 给出的评分
    human_grades: List[GradeResult]  # 人工给出的评分
    agreement: float  # 一致性（0-1）
    timestamp: str
    notes: str = ""


@dataclass
class CalibrationReport:
    """校准报告"""
    total_cases: int
    avg_agreement: float
    grader_performance: Dict[str, Dict[str, float]]  # grader_name -> {agreement, precision, recall}
    disagreement_patterns: List[str]  # 不一致的模式
    recommendations: List[str]
    timestamp: str


class CalibrationWorkflow:
    """人工校准工作流"""
    
    def __init__(
        self,
        model_graders: ModelBasedGraders,
        calibration_dir: Path = Path("evaluation/calibration")
    ):
        """
        初始化校准工作流
        
        Args:
            model_graders: 模型评分器实例
            calibration_dir: 校准数据存储目录
        """
        self.model_graders = model_graders
        self.calibration_dir = Path(calibration_dir)
        self.calibration_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_calibration_set(
        self,
        tasks: List[Task],
        sample_size: int = 50,
        strategy: str = "diverse"
    ) -> List[CalibrationCase]:
        """
        创建校准集
        
        Args:
            tasks: 待校准的任务列表
            sample_size: 样本大小
            strategy: 采样策略 (diverse/random/edge_cases)
            
        Returns:
            校准案例列表
        """
        calibration_cases = []
        
        if strategy == "diverse":
            # 多样性采样：覆盖不同类型、难度的任务
            selected_tasks = self._sample_diverse(tasks, sample_size)
        elif strategy == "edge_cases":
            # 边界案例采样：专注于困难、模糊的案例
            selected_tasks = self._sample_edge_cases(tasks, sample_size)
        else:
            # 随机采样
            import random
            selected_tasks = random.sample(tasks, min(sample_size, len(tasks)))
        
        for task in selected_tasks:
            # 执行任务（这里假设已经有执行结果）
            # 实际应该调用 EvaluationHarness 执行
            trial = Trial(
                trial_number=1,
                status="pending",
                outcome=None,
                grades=[],
                timestamp=datetime.utcnow().isoformat()
            )
            
            # 使用 LLM 进行评分
            llm_grades = await self._run_llm_graders(task, trial)
            
            calibration_cases.append(CalibrationCase(
                task_id=task.task_id,
                trial=trial,
                llm_grades=llm_grades,
                human_grades=[],  # 待人工填写
                agreement=0.0,
                timestamp=datetime.utcnow().isoformat()
            ))
        
        # 保存校准集
        self._save_calibration_set(calibration_cases)
        
        return calibration_cases
    
    def submit_human_grades(
        self,
        task_id: str,
        human_grades: List[GradeResult]
    ) -> CalibrationCase:
        """
        提交人工评分
        
        Args:
            task_id: 任务 ID
            human_grades: 人工评分结果
            
        Returns:
            更新后的校准案例
        """
        # 加载校准集
        calibration_cases = self._load_calibration_set()
        
        # 找到对应案例
        case = next((c for c in calibration_cases if c.task_id == task_id), None)
        if not case:
            raise ValueError(f"Task {task_id} not found in calibration set")
        
        # 更新人工评分
        case.human_grades = human_grades
        
        # 计算一致性
        case.agreement = self._calculate_agreement(case.llm_grades, case.human_grades)
        
        # 保存更新
        self._save_calibration_set(calibration_cases)
        
        return case
    
    def generate_calibration_report(self) -> CalibrationReport:
        """生成校准报告"""
        calibration_cases = self._load_calibration_set()
        
        # 过滤出已完成人工标注的案例
        completed_cases = [c for c in calibration_cases if c.human_grades]
        
        if not completed_cases:
            return CalibrationReport(
                total_cases=0,
                avg_agreement=0.0,
                grader_performance={},
                disagreement_patterns=[],
                recommendations=["暂无已完成的校准案例"],
                timestamp=datetime.utcnow().isoformat()
            )
        
        # 计算平均一致性
        avg_agreement = sum(c.agreement for c in completed_cases) / len(completed_cases)
        
        # 分析每个 grader 的表现
        grader_performance = self._analyze_grader_performance(completed_cases)
        
        # 识别不一致模式
        disagreement_patterns = self._identify_disagreement_patterns(completed_cases)
        
        # 生成改进建议
        recommendations = self._generate_calibration_recommendations(
            avg_agreement,
            grader_performance,
            disagreement_patterns
        )
        
        report = CalibrationReport(
            total_cases=len(completed_cases),
            avg_agreement=avg_agreement,
            grader_performance=grader_performance,
            disagreement_patterns=disagreement_patterns,
            recommendations=recommendations,
            timestamp=datetime.utcnow().isoformat()
        )
        
        # 保存报告
        self._save_calibration_report(report)
        
        return report
    
    def update_grader_prompts(self, report: CalibrationReport) -> None:
        """
        根据校准报告更新 grader prompts
        
        Args:
            report: 校准报告
        """
        # 对于表现不佳的 grader，更新 prompt
        for grader_name, perf in report.grader_performance.items():
            if perf["agreement"] < 0.70:
                print(f"⚠️  {grader_name} 一致性较低 ({perf['agreement']:.1%})，建议更新 prompt")
                # 这里可以实现自动或半自动的 prompt 优化
                # 例如：基于不一致案例生成新的示例，加入到 prompt 中
    
    async def _run_llm_graders(
        self,
        task: Task,
        trial: Trial
    ) -> List[GradeResult]:
        """运行所有 LLM graders"""
        grades = []
        
        if not trial.outcome or not trial.outcome.transcript:
            return grades
        
        transcript = trial.outcome.transcript
        
        # 运行各种 model-based graders
        grading_methods = [
            ("intent_understanding", self.model_graders.grade_intent_understanding),
            ("over_engineering", self.model_graders.grade_over_engineering),
            ("response_quality", self.model_graders.grade_response_quality),
            ("logical_coherence", self.model_graders.grade_logical_coherence),
        ]
        
        for grader_name, grading_func in grading_methods:
            result = await grading_func(task.input.query, transcript)
            result.grader_name = grader_name
            grades.append(result)
        
        return grades
    
    def _calculate_agreement(
        self,
        llm_grades: List[GradeResult],
        human_grades: List[GradeResult]
    ) -> float:
        """
        计算 LLM 和人工评分的一致性
        
        使用 Cohen's Kappa 或简单的匹配率
        """
        if not llm_grades or not human_grades:
            return 0.0
        
        # 按 grader_name 匹配
        matches = 0
        total = 0
        
        for llm_grade in llm_grades:
            human_grade = next(
                (h for h in human_grades if h.grader_name == llm_grade.grader_name),
                None
            )
            if human_grade:
                total += 1
                # 检查 passed 是否一致
                if llm_grade.passed == human_grade.passed:
                    matches += 1
                # 如果有分数，也检查分数是否接近（差距 ≤1）
                if llm_grade.score and human_grade.score:
                    if abs(llm_grade.score - human_grade.score) <= 1.0:
                        matches += 0.5  # 部分匹配
        
        return matches / total if total > 0 else 0.0
    
    def _analyze_grader_performance(
        self,
        cases: List[CalibrationCase]
    ) -> Dict[str, Dict[str, float]]:
        """分析每个 grader 的表现"""
        grader_stats = {}
        
        # 收集所有 grader 的评分
        for case in cases:
            for llm_grade in case.llm_grades:
                grader_name = llm_grade.grader_name
                if grader_name not in grader_stats:
                    grader_stats[grader_name] = {
                        "tp": 0, "fp": 0, "tn": 0, "fn": 0, "agreements": []
                    }
                
                # 找到对应的人工评分
                human_grade = next(
                    (h for h in case.human_grades if h.grader_name == grader_name),
                    None
                )
                
                if human_grade:
                    llm_pass = llm_grade.passed
                    human_pass = human_grade.passed
                    
                    # 计算混淆矩阵
                    if llm_pass and human_pass:
                        grader_stats[grader_name]["tp"] += 1
                    elif llm_pass and not human_pass:
                        grader_stats[grader_name]["fp"] += 1
                    elif not llm_pass and not human_pass:
                        grader_stats[grader_name]["tn"] += 1
                    else:
                        grader_stats[grader_name]["fn"] += 1
                    
                    # 记录一致性
                    agreement = 1.0 if llm_pass == human_pass else 0.0
                    grader_stats[grader_name]["agreements"].append(agreement)
        
        # 计算指标
        performance = {}
        for grader_name, stats in grader_stats.items():
            tp, fp, tn, fn = stats["tp"], stats["fp"], stats["tn"], stats["fn"]
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            agreement = sum(stats["agreements"]) / len(stats["agreements"]) if stats["agreements"] else 0.0
            
            performance[grader_name] = {
                "agreement": agreement,
                "precision": precision,
                "recall": recall
            }
        
        return performance
    
    def _identify_disagreement_patterns(
        self,
        cases: List[CalibrationCase]
    ) -> List[str]:
        """识别不一致的模式"""
        patterns = []
        
        # 找出一致性低的案例
        low_agreement_cases = [c for c in cases if c.agreement < 0.5]
        
        if len(low_agreement_cases) > len(cases) * 0.3:
            patterns.append(
                f"有 {len(low_agreement_cases)} 个案例（{len(low_agreement_cases)/len(cases):.1%}）"
                "一致性较低，LLM 评分与人工评分差异较大"
            )
        
        # 分析特定 grader 的问题
        grader_disagreements = {}
        for case in low_agreement_cases:
            for llm_grade in case.llm_grades:
                human_grade = next(
                    (h for h in case.human_grades if h.grader_name == llm_grade.grader_name),
                    None
                )
                if human_grade and llm_grade.passed != human_grade.passed:
                    grader_name = llm_grade.grader_name
                    grader_disagreements[grader_name] = grader_disagreements.get(grader_name, 0) + 1
        
        for grader_name, count in sorted(grader_disagreements.items(), key=lambda x: x[1], reverse=True):
            if count >= 3:
                patterns.append(f"{grader_name} 有 {count} 次与人工评分不一致")
        
        return patterns
    
    def _generate_calibration_recommendations(
        self,
        avg_agreement: float,
        grader_performance: Dict[str, Dict[str, float]],
        disagreement_patterns: List[str]
    ) -> List[str]:
        """生成校准建议"""
        recommendations = []
        
        # 整体一致性
        if avg_agreement < 0.70:
            recommendations.append(
                f"整体一致性 ({avg_agreement:.1%}) 较低，建议增加校准样本量或优化 grader prompts"
            )
        elif avg_agreement < 0.85:
            recommendations.append(
                f"整体一致性 ({avg_agreement:.1%}) 中等，建议针对表现较差的 grader 进行优化"
            )
        else:
            recommendations.append(
                f"整体一致性 ({avg_agreement:.1%}) 良好，LLM-as-Judge 可靠性较高"
            )
        
        # 针对特定 grader 的建议
        for grader_name, perf in grader_performance.items():
            if perf["agreement"] < 0.70:
                recommendations.append(
                    f"{grader_name}: 一致性 {perf['agreement']:.1%}，"
                    f"精确率 {perf['precision']:.1%}，召回率 {perf['recall']:.1%}"
                    " - 建议重新设计评分规则或增加示例"
                )
        
        return recommendations
    
    def _sample_diverse(self, tasks: List[Task], sample_size: int) -> List[Task]:
        """多样性采样"""
        # 简化实现：按任务类别分层采样
        # 实际可以更复杂，考虑难度、长度等
        import random
        return random.sample(tasks, min(sample_size, len(tasks)))
    
    def _sample_edge_cases(self, tasks: List[Task], sample_size: int) -> List[Task]:
        """边界案例采样"""
        # 优先选择：
        # 1. 多轮对话
        # 2. 有检查点的任务
        # 3. 工具调用复杂的任务
        edge_cases = [
            t for t in tasks
            if (t.turns and len(t.turns) > 1) or (t.checkpoints and len(t.checkpoints) > 0)
        ]
        import random
        return random.sample(edge_cases, min(sample_size, len(edge_cases)))
    
    def _save_calibration_set(self, cases: List[CalibrationCase]) -> None:
        """保存校准集"""
        output_file = self.calibration_dir / "calibration_set.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump([self._case_to_dict(c) for c in cases], f, indent=2, ensure_ascii=False)
    
    def _load_calibration_set(self) -> List[CalibrationCase]:
        """加载校准集"""
        input_file = self.calibration_dir / "calibration_set.json"
        if not input_file.exists():
            return []
        
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [self._dict_to_case(d) for d in data]
    
    def _save_calibration_report(self, report: CalibrationReport) -> None:
        """保存校准报告"""
        output_file = self.calibration_dir / f"report_{report.timestamp.replace(':', '-')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "total_cases": report.total_cases,
                "avg_agreement": report.avg_agreement,
                "grader_performance": report.grader_performance,
                "disagreement_patterns": report.disagreement_patterns,
                "recommendations": report.recommendations,
                "timestamp": report.timestamp
            }, f, indent=2, ensure_ascii=False)
    
    def _case_to_dict(self, case: CalibrationCase) -> dict:
        """转换为字典（用于序列化）"""
        return {
            "task_id": case.task_id,
            "trial": case.trial.model_dump() if hasattr(case.trial, "model_dump") else {},
            "llm_grades": [g.model_dump() if hasattr(g, "model_dump") else {} for g in case.llm_grades],
            "human_grades": [g.model_dump() if hasattr(g, "model_dump") else {} for g in case.human_grades],
            "agreement": case.agreement,
            "timestamp": case.timestamp,
            "notes": case.notes
        }
    
    def _dict_to_case(self, data: dict) -> CalibrationCase:
        """从字典恢复"""
        # 简化实现，实际需要完整反序列化
        return CalibrationCase(
            task_id=data["task_id"],
            trial=Trial(**data["trial"]) if data.get("trial") else None,
            llm_grades=[GradeResult(**g) for g in data.get("llm_grades", [])],
            human_grades=[GradeResult(**g) for g in data.get("human_grades", [])],
            agreement=data.get("agreement", 0.0),
            timestamp=data.get("timestamp", ""),
            notes=data.get("notes", "")
        )


def format_calibration_report(report: CalibrationReport) -> str:
    """格式化校准报告"""
    lines = []
    lines.append("=" * 80)
    lines.append("人工校准报告")
    lines.append("=" * 80)
    lines.append(f"校准案例数: {report.total_cases}")
    lines.append(f"平均一致性: {report.avg_agreement:.1%}")
    lines.append(f"生成时间: {report.timestamp}")
    lines.append("")
    
    lines.append("Grader 表现")
    lines.append("-" * 80)
    for grader_name, perf in report.grader_performance.items():
        lines.append(f"  {grader_name}:")
        lines.append(f"    一致性: {perf['agreement']:.1%}")
        lines.append(f"    精确率: {perf['precision']:.1%}")
        lines.append(f"    召回率: {perf['recall']:.1%}")
    
    lines.append("")
    lines.append("不一致模式")
    lines.append("-" * 80)
    for pattern in report.disagreement_patterns:
        lines.append(f"  - {pattern}")
    
    lines.append("")
    lines.append("改进建议")
    lines.append("-" * 80)
    for i, rec in enumerate(report.recommendations, 1):
        lines.append(f"  {i}. {rec}")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)
