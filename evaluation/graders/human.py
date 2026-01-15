"""
Human Graders（人工评分器）

黄金标准评分器，用于：
1. 定期抽样评估（每周100条）
2. 校准LLM评分器（Model-based Graders）
3. 处理复杂主观任务
4. 建立评分基准

特点：
- 最准确：人工判断是最终标准
- 昂贵：需要人力投入
- 缓慢：无法实时评估
- 主观性：需要多人评分求共识

使用策略：
- 定期抽样（每周100条）进行人工评分
- 与LLM评分对比，计算偏差
- 根据偏差调整LLM评分器的rubric
"""

import random
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from evaluation.models import (
    GradeResult,
    GraderType,
    Transcript,
    Trial,
    EvaluationReport,
)


class HumanGraders:
    """
    人工评分器（用于校准LLM评分器）
    
    使用方式：
        graders = HumanGraders(model_grader=model_based_graders)
        
        # 每周校准
        await graders.weekly_calibration(sample_size=100)
        
        # 查看校准报告
        report = graders.get_calibration_report()
    """
    
    def __init__(self, model_grader=None, storage=None):
        """
        初始化人工评分器
        
        Args:
            model_grader: 需要校准的LLM评分器
            storage: 存储服务（用于保存/加载评分数据）
        """
        self.model_grader = model_grader
        self.storage = storage
        self.calibration_history: List[Dict[str, Any]] = []
        self.pending_samples: List[Dict[str, Any]] = []
        
    # ===================
    # 抽样管理
    # ===================
    
    async def sample_from_production(
        self,
        sample_size: int = 100,
        time_range_days: int = 7,
        stratify_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        从生产环境随机抽样
        
        Args:
            sample_size: 抽样数量
            time_range_days: 时间范围（天）
            stratify_by: 分层抽样字段（如 "category", "qos_level"）
            
        Returns:
            List[Dict]: 抽样样本列表
        """
        # 实际实现需要连接生产数据库
        # 这里提供接口定义
        
        if self.storage is None:
            # 模拟数据（用于测试）
            return [
                {
                    "sample_id": f"sample_{i}",
                    "user_query": f"测试问题 {i}",
                    "agent_response": f"测试回答 {i}",
                    "transcript": None,
                    "category": random.choice(["conversation", "coding", "research"]),
                    "timestamp": datetime.now() - timedelta(days=random.randint(0, time_range_days)),
                }
                for i in range(sample_size)
            ]
        
        # 从存储获取样本
        samples = await self.storage.get_recent_conversations(
            days=time_range_days,
            limit=sample_size * 2  # 获取更多用于分层抽样
        )
        
        # 分层抽样
        if stratify_by and samples:
            strata = {}
            for s in samples:
                key = s.get(stratify_by, "unknown")
                if key not in strata:
                    strata[key] = []
                strata[key].append(s)
            
            # 按比例抽样
            result = []
            for key, stratum in strata.items():
                n = max(1, int(sample_size * len(stratum) / len(samples)))
                result.extend(random.sample(stratum, min(n, len(stratum))))
            
            return result[:sample_size]
        
        return random.sample(samples, min(sample_size, len(samples)))
    
    def add_pending_sample(self, sample: Dict[str, Any]) -> None:
        """
        添加待评分样本
        
        Args:
            sample: 样本数据
        """
        sample["added_at"] = datetime.now()
        sample["status"] = "pending"
        self.pending_samples.append(sample)
    
    def get_pending_samples(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取待评分样本
        
        Args:
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 待评分样本列表
        """
        pending = [s for s in self.pending_samples if s.get("status") == "pending"]
        return pending[:limit]
    
    # ===================
    # 人工评分记录
    # ===================
    
    def record_human_score(
        self,
        sample_id: str,
        rater_id: str,
        scores: Dict[str, float],
        comments: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        记录人工评分结果
        
        Args:
            sample_id: 样本ID
            rater_id: 评分员ID
            scores: 评分字典（如 {"intent": 4, "quality": 5}）
            comments: 评论（可选）
            
        Returns:
            Dict: 评分记录
        """
        record = {
            "sample_id": sample_id,
            "rater_id": rater_id,
            "scores": scores,
            "comments": comments,
            "timestamp": datetime.now().isoformat(),
        }
        
        # 更新样本状态
        for sample in self.pending_samples:
            if sample.get("sample_id") == sample_id:
                if "human_scores" not in sample:
                    sample["human_scores"] = []
                sample["human_scores"].append(record)
                
                # 如果有足够的评分员，标记为已完成
                if len(sample["human_scores"]) >= 3:
                    sample["status"] = "completed"
                break
        
        return record
    
    # ===================
    # 评分聚合
    # ===================
    
    @staticmethod
    def aggregate_human_scores(
        scores_list: List[Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        聚合多个评分员的评分
        
        Args:
            scores_list: 评分列表（每个元素是一个评分员的评分）
            
        Returns:
            Dict: 聚合结果（平均分、标准差、一致性）
        """
        if not scores_list:
            return {"average": {}, "std": {}, "agreement": 0.0}
        
        # 获取所有评分维度
        dimensions = set()
        for scores in scores_list:
            dimensions.update(scores.keys())
        
        # 计算每个维度的统计量
        result = {"average": {}, "std": {}}
        
        for dim in dimensions:
            values = [s.get(dim) for s in scores_list if s.get(dim) is not None]
            if values:
                result["average"][dim] = statistics.mean(values)
                result["std"][dim] = statistics.stdev(values) if len(values) > 1 else 0.0
        
        # 计算评分员间一致性（Inter-Rater Agreement）
        # 使用简化的 Krippendorff's Alpha 近似
        if len(scores_list) >= 2:
            total_variance = []
            for dim in dimensions:
                values = [s.get(dim) for s in scores_list if s.get(dim) is not None]
                if len(values) >= 2:
                    total_variance.append(statistics.variance(values))
            
            if total_variance:
                avg_variance = statistics.mean(total_variance)
                # 假设最大方差为 4（5分制评分的最大方差）
                result["agreement"] = max(0.0, 1.0 - avg_variance / 4.0)
            else:
                result["agreement"] = 1.0
        else:
            result["agreement"] = 1.0
        
        return result
    
    # ===================
    # LLM评分器校准
    # ===================
    
    async def collect_human_scores(
        self,
        samples: List[Dict[str, Any]],
        num_raters: int = 3
    ) -> List[Dict[str, Any]]:
        """
        收集人工评分（接口方法，实际评分通过UI或其他方式完成）
        
        Args:
            samples: 待评分样本
            num_raters: 每个样本需要的评分员数量
            
        Returns:
            List[Dict]: 带人工评分的样本列表
        """
        # 将样本添加到待评分队列
        for sample in samples:
            self.add_pending_sample(sample)
        
        # 返回待评分样本（实际评分需要人工完成）
        return self.pending_samples
    
    async def calibrate_with_llm(
        self,
        sample: Dict[str, Any],
        human_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        将人工评分与LLM评分对比
        
        Args:
            sample: 样本数据
            human_scores: 人工评分（聚合后）
            
        Returns:
            Dict: 对比结果
        """
        if self.model_grader is None:
            return {
                "sample_id": sample.get("sample_id"),
                "human_scores": human_scores,
                "llm_scores": {},
                "bias": {},
                "error": "LLM评分器未配置",
            }
        
        # 获取LLM评分
        llm_scores = {}
        
        # 意图理解评分
        if "intent" in human_scores:
            result = await self.model_grader.grade_intent_understanding(
                user_query=sample.get("user_query", ""),
                agent_response=sample.get("agent_response", ""),
            )
            llm_scores["intent"] = result.score * 5  # 转换为1-5分
        
        # 质量评分
        if "quality" in human_scores:
            result = await self.model_grader.grade_response_quality(
                user_query=sample.get("user_query", ""),
                agent_response=sample.get("agent_response", ""),
            )
            llm_scores["quality"] = result.details.get("weighted_score", 3.0)
        
        # 计算偏差
        bias = {}
        for dim in human_scores:
            if dim in llm_scores:
                bias[dim] = llm_scores[dim] - human_scores[dim]
        
        return {
            "sample_id": sample.get("sample_id"),
            "human_scores": human_scores,
            "llm_scores": llm_scores,
            "bias": bias,
        }
    
    def calculate_calibration_bias(
        self,
        comparisons: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        计算校准偏差统计
        
        Args:
            comparisons: 对比结果列表
            
        Returns:
            Dict: 偏差统计
        """
        if not comparisons:
            return {"mean_bias": {}, "bias_std": {}, "mse": {}}
        
        # 收集每个维度的偏差
        bias_by_dim: Dict[str, List[float]] = {}
        
        for comp in comparisons:
            for dim, bias in comp.get("bias", {}).items():
                if dim not in bias_by_dim:
                    bias_by_dim[dim] = []
                bias_by_dim[dim].append(bias)
        
        # 计算统计量
        result = {"mean_bias": {}, "bias_std": {}, "mse": {}}
        
        for dim, biases in bias_by_dim.items():
            if biases:
                result["mean_bias"][dim] = statistics.mean(biases)
                result["bias_std"][dim] = statistics.stdev(biases) if len(biases) > 1 else 0.0
                result["mse"][dim] = statistics.mean([b ** 2 for b in biases])
        
        return result
    
    # ===================
    # 每周校准流程
    # ===================
    
    async def weekly_calibration(
        self,
        sample_size: int = 100
    ) -> Dict[str, Any]:
        """
        每周校准流程（主入口）
        
        流程：
        1. 从生产环境随机抽样
        2. 人工评分（支持多个评分员，计算inter-rater agreement）
        3. 对比LLM评分器的结果
        4. 计算偏差，更新LLM评分器的rubric
        
        Args:
            sample_size: 抽样数量
            
        Returns:
            Dict: 校准报告
        """
        # 1. 抽样
        samples = await self.sample_from_production(sample_size)
        
        # 2. 收集人工评分（实际操作中，这一步需要人工完成）
        await self.collect_human_scores(samples, num_raters=3)
        
        # 3. 创建校准任务记录
        calibration_task = {
            "id": f"calibration_{datetime.now().strftime('%Y%m%d')}",
            "sample_size": sample_size,
            "samples": len(samples),
            "started_at": datetime.now().isoformat(),
            "status": "pending_human_scores",
            "pending_samples": len(self.get_pending_samples()),
        }
        
        self.calibration_history.append(calibration_task)
        
        return calibration_task
    
    async def complete_calibration(self) -> Dict[str, Any]:
        """
        完成校准流程（在人工评分完成后调用）
        
        Returns:
            Dict: 校准结果报告
        """
        # 获取已完成评分的样本
        completed_samples = [
            s for s in self.pending_samples 
            if s.get("status") == "completed"
        ]
        
        if not completed_samples:
            return {"error": "没有已完成的人工评分样本"}
        
        # 聚合人工评分并与LLM对比
        comparisons = []
        
        for sample in completed_samples:
            human_scores_list = [
                r.get("scores", {}) 
                for r in sample.get("human_scores", [])
            ]
            
            # 聚合人工评分
            aggregated = self.aggregate_human_scores(human_scores_list)
            
            # 与LLM对比
            comparison = await self.calibrate_with_llm(
                sample,
                aggregated["average"]
            )
            comparison["inter_rater_agreement"] = aggregated["agreement"]
            comparisons.append(comparison)
        
        # 计算总体偏差
        bias_stats = self.calculate_calibration_bias(comparisons)
        
        # 生成校准报告
        report = {
            "id": f"calibration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "completed_at": datetime.now().isoformat(),
            "total_samples": len(completed_samples),
            "bias_statistics": bias_stats,
            "recommendations": self._generate_recommendations(bias_stats),
            "comparisons": comparisons,
        }
        
        # 清理已完成的样本
        self.pending_samples = [
            s for s in self.pending_samples 
            if s.get("status") != "completed"
        ]
        
        return report
    
    def _generate_recommendations(
        self,
        bias_stats: Dict[str, Any]
    ) -> List[str]:
        """
        根据偏差统计生成调整建议
        
        Args:
            bias_stats: 偏差统计
            
        Returns:
            List[str]: 调整建议列表
        """
        recommendations = []
        
        for dim, mean_bias in bias_stats.get("mean_bias", {}).items():
            if abs(mean_bias) > 0.5:
                direction = "偏高" if mean_bias > 0 else "偏低"
                recommendations.append(
                    f"LLM评分器在 '{dim}' 维度上{direction} {abs(mean_bias):.2f} 分，"
                    f"建议调整评分标准（rubric）"
                )
        
        for dim, mse in bias_stats.get("mse", {}).items():
            if mse > 1.0:
                recommendations.append(
                    f"LLM评分器在 '{dim}' 维度上MSE较高 ({mse:.2f})，"
                    f"建议增加评分示例或细化评分标准"
                )
        
        if not recommendations:
            recommendations.append("LLM评分器与人工评分一致性良好，无需调整")
        
        return recommendations
    
    # ===================
    # 报告生成
    # ===================
    
    def get_calibration_report(self) -> Dict[str, Any]:
        """
        获取最新的校准报告摘要
        
        Returns:
            Dict: 校准报告摘要
        """
        return {
            "total_calibrations": len(self.calibration_history),
            "pending_samples": len(self.get_pending_samples()),
            "recent_calibrations": self.calibration_history[-5:],
        }
    
    def export_for_human_review(
        self,
        format: str = "json"
    ) -> str:
        """
        导出待评分样本供人工审查
        
        Args:
            format: 导出格式（json/csv）
            
        Returns:
            str: 导出的数据
        """
        samples = self.get_pending_samples()
        
        if format == "json":
            import json
            return json.dumps(samples, ensure_ascii=False, indent=2, default=str)
        
        elif format == "csv":
            import csv
            import io
            
            output = io.StringIO()
            if samples:
                writer = csv.DictWriter(
                    output, 
                    fieldnames=["sample_id", "user_query", "agent_response", "category"]
                )
                writer.writeheader()
                for s in samples:
                    writer.writerow({
                        "sample_id": s.get("sample_id"),
                        "user_query": s.get("user_query", "")[:200],
                        "agent_response": s.get("agent_response", "")[:200],
                        "category": s.get("category", ""),
                    })
            
            return output.getvalue()
        
        return ""
