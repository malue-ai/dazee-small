"""
Human Graders（人工评分器）

人工评估接口和工作流，特点：
- 黄金标准：人工评分作为参考标准
- 定期校准：用于校准 LLM Judge
- 抽样评估：每周抽样 100 条进行评估
- 复杂案例：处理 LLM 无法判断的复杂案例

工作流：
1. 自动抽取需要人工复核的案例（低置信度、边界案例）
2. 人工在 Web UI 中进行评分
3. 对比人工评分 vs LLM 评分，计算一致性
4. 调整 LLM Judge 的 Prompt 和阈值
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum

from evaluation.models import (
    GradeResult,
    GraderType,
    Trial,
    Transcript,
)

logger = logging.getLogger(__name__)


class HumanReviewStatus(str, Enum):
    """人工复核状态"""
    PENDING = "pending"           # 待复核
    IN_PROGRESS = "in_progress"   # 复核中
    COMPLETED = "completed"       # 已完成
    SKIPPED = "skipped"           # 已跳过


class HumanReviewRecord:
    """人工复核记录"""
    
    def __init__(
        self,
        trial_id: str,
        reviewer: str,
        score: float,
        passed: bool,
        explanation: Optional[str] = None,
        reviewed_at: Optional[datetime] = None
    ):
        self.trial_id = trial_id
        self.reviewer = reviewer
        self.score = score
        self.passed = passed
        self.explanation = explanation
        self.reviewed_at = reviewed_at or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "reviewer": self.reviewer,
            "score": self.score,
            "passed": self.passed,
            "explanation": self.explanation,
            "reviewed_at": self.reviewed_at.isoformat(),
        }


class HumanGrader:
    """
    人工评分器
    
    使用方式：
        grader = HumanGrader()
        
        # 获取待复核案例
        pending = grader.get_pending_reviews(limit=100)
        
        # 提交人工评分
        grader.submit_review(
            trial_id="trial_123",
            reviewer="alice",
            score=4.5,
            passed=True,
            explanation="回答准确完整"
        )
        
        # 计算一致性
        agreement = grader.calculate_agreement(trial_id="trial_123")
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化人工评分器
        
        Args:
            storage_path: 存储路径（用于持久化复核记录）
        """
        self.storage_path = storage_path
        self.reviews: Dict[str, HumanReviewRecord] = {}  # trial_id -> review
        self._load_reviews()
    
    def _load_reviews(self) -> None:
        """从存储加载复核记录"""
        if not self.storage_path:
            return
        
        try:
            import json
            from pathlib import Path
            
            path = Path(self.storage_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for record_data in data.get("reviews", []):
                        record = HumanReviewRecord(
                            trial_id=record_data["trial_id"],
                            reviewer=record_data["reviewer"],
                            score=record_data["score"],
                            passed=record_data["passed"],
                            explanation=record_data.get("explanation"),
                            reviewed_at=datetime.fromisoformat(record_data["reviewed_at"]),
                        )
                        self.reviews[record.trial_id] = record
        except Exception as e:
            logger.warning(f"加载复核记录失败: {e}")
    
    def _save_reviews(self) -> None:
        """保存复核记录到存储"""
        if not self.storage_path:
            return
        
        try:
            import json
            from pathlib import Path
            
            path = Path(self.storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "reviews": [r.to_dict() for r in self.reviews.values()],
                "updated_at": datetime.now().isoformat(),
            }
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存复核记录失败: {e}")
    
    def get_pending_reviews(
        self,
        trials: List[Trial],
        limit: int = 100,
        criteria: Optional[Dict[str, Any]] = None
    ) -> List[Trial]:
        """
        获取待人工复核的案例
        
        Args:
            trials: 试验列表
            limit: 返回数量限制
            criteria: 筛选条件
                - min_confidence: 最低置信度阈值（低于此值的需要复核）
                - score_range: 分数范围（边界案例）
                - random_sample: 随机抽样比例
            
        Returns:
            List[Trial]: 待复核的试验列表
        """
        criteria = criteria or {}
        min_confidence = criteria.get("min_confidence", 0.7)
        score_range = criteria.get("score_range", (3.0, 4.0))  # 边界案例
        random_sample = criteria.get("random_sample", 0.1)  # 10% 随机抽样
        
        pending = []
        
        for trial in trials:
            # 跳过已复核的
            if trial.trial_id in self.reviews:
                continue
            
            # 检查是否需要复核
            needs_review = False
            
            # 1. 低置信度案例
            for gr in trial.grade_results:
                if gr.confidence is not None and gr.confidence < min_confidence:
                    needs_review = True
                    break
                if gr.needs_human_review:
                    needs_review = True
                    break
            
            # 2. 边界案例（分数在临界值附近）
            if not needs_review:
                avg_score = trial.average_score
                if avg_score is not None:
                    if score_range[0] <= avg_score * 5 <= score_range[1]:  # 转换为1-5分制
                        needs_review = True
            
            # 3. 随机抽样
            if not needs_review:
                import random
                if random.random() < random_sample:
                    needs_review = True
            
            if needs_review:
                pending.append(trial)
        
        # 限制数量
        return pending[:limit]
    
    def submit_review(
        self,
        trial_id: str,
        reviewer: str,
        score: float,
        passed: bool,
        explanation: Optional[str] = None
    ) -> HumanReviewRecord:
        """
        提交人工评分
        
        Args:
            trial_id: 试验ID
            reviewer: 复核人
            score: 评分（0-1或1-5）
            passed: 是否通过
            explanation: 评分说明
            
        Returns:
            HumanReviewRecord: 复核记录
        """
        # 标准化分数到 0-1
        if score > 1.0:
            score = score / 5.0
        
        record = HumanReviewRecord(
            trial_id=trial_id,
            reviewer=reviewer,
            score=score,
            passed=passed,
            explanation=explanation,
        )
        
        self.reviews[trial_id] = record
        self._save_reviews()
        
        logger.info(f"✅ 人工复核完成: {trial_id} by {reviewer}, score={score:.2f}, passed={passed}")
        
        return record
    
    def get_review(self, trial_id: str) -> Optional[HumanReviewRecord]:
        """获取复核记录"""
        return self.reviews.get(trial_id)
    
    def calculate_agreement(
        self,
        trial: Trial,
        human_review: Optional[HumanReviewRecord] = None
    ) -> Dict[str, Any]:
        """
        计算人工评分与 LLM 评分的一致性
        
        Args:
            trial: 试验记录
            human_review: 人工复核记录（如果为None，则从存储中查找）
            
        Returns:
            Dict: 一致性分析结果
        """
        if human_review is None:
            human_review = self.get_review(trial.trial_id)
        
        if human_review is None:
            return {
                "error": "未找到人工复核记录",
                "agreement": None,
            }
        
        # 获取 LLM 评分
        llm_scores = []
        for gr in trial.grade_results:
            if gr.grader_type == GraderType.MODEL and gr.score is not None:
                llm_scores.append(gr.score)
        
        if not llm_scores:
            return {
                "error": "未找到 LLM 评分",
                "agreement": None,
            }
        
        # 计算平均 LLM 评分
        avg_llm_score = sum(llm_scores) / len(llm_scores)
        human_score = human_review.score
        
        # 计算一致性（使用 Cohen's Kappa 的简化版本）
        # 对于连续分数，使用相关系数
        score_diff = abs(avg_llm_score - human_score)
        agreement = max(0.0, 1.0 - score_diff)  # 差异越小，一致性越高
        
        # 判断是否通过的一致性
        llm_passed = any(gr.passed for gr in trial.grade_results if gr.grader_type == GraderType.MODEL)
        passed_agreement = 1.0 if llm_passed == human_review.passed else 0.0
        
        return {
            "human_score": human_score,
            "llm_score": avg_llm_score,
            "score_agreement": agreement,
            "passed_agreement": passed_agreement,
            "overall_agreement": (agreement + passed_agreement) / 2.0,
            "score_diff": score_diff,
        }
    
    def get_calibration_stats(
        self,
        trials: List[Trial],
        time_range_days: int = 7
    ) -> Dict[str, Any]:
        """
        获取校准统计信息（用于调整 LLM Judge）
        
        Args:
            trials: 试验列表
            time_range_days: 时间范围（天）
            
        Returns:
            Dict: 统计信息
        """
        cutoff = datetime.now() - timedelta(days=time_range_days)
        
        agreements = []
        score_diffs = []
        
        for trial in trials:
            review = self.get_review(trial.trial_id)
            if review and review.reviewed_at >= cutoff:
                agreement = self.calculate_agreement(trial, review)
                if "overall_agreement" in agreement:
                    agreements.append(agreement["overall_agreement"])
                    score_diffs.append(agreement["score_diff"])
        
        if not agreements:
            return {
                "total_reviews": 0,
                "avg_agreement": None,
                "avg_score_diff": None,
            }
        
        return {
            "total_reviews": len(agreements),
            "avg_agreement": sum(agreements) / len(agreements),
            "avg_score_diff": sum(score_diffs) / len(score_diffs),
            "min_agreement": min(agreements),
            "max_agreement": max(agreements),
        }
    
    def generate_review_report(
        self,
        trials: List[Trial],
        output_path: Optional[str] = None
    ) -> str:
        """
        生成人工复核报告
        
        Args:
            trials: 试验列表
            output_path: 输出路径（可选）
            
        Returns:
            str: Markdown 格式的报告
        """
        lines = [
            "# 人工复核报告",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 统计摘要",
            "",
        ]
        
        stats = self.get_calibration_stats(trials)
        lines.extend([
            f"- 总复核数: {stats['total_reviews']}",
            f"- 平均一致性: {stats['avg_agreement']:.2%}" if stats['avg_agreement'] else "- 平均一致性: N/A",
            f"- 平均分数差异: {stats['avg_score_diff']:.3f}" if stats['avg_score_diff'] else "- 平均分数差异: N/A",
            "",
            "## 详细记录",
            "",
            "| 试验ID | 复核人 | 人工评分 | LLM评分 | 一致性 | 说明 |",
            "|--------|--------|----------|---------|--------|------|",
        ])
        
        for trial in trials:
            review = self.get_review(trial.trial_id)
            if review:
                agreement = self.calculate_agreement(trial, review)
                llm_score = agreement.get("llm_score", "N/A")
                overall_agreement = agreement.get("overall_agreement", "N/A")
                
                lines.append(
                    f"| {trial.trial_id} | {review.reviewer} | {review.score:.2f} | "
                    f"{llm_score:.2f if isinstance(llm_score, float) else llm_score} | "
                    f"{overall_agreement:.2% if isinstance(overall_agreement, float) else overall_agreement} | "
                    f"{review.explanation or ''} |"
                )
        
        report = "\n".join(lines)
        
        if output_path:
            from pathlib import Path
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
        
        return report
