"""
任务复杂度评分器（Complexity Scorer）

评估用户任务的复杂度，用于路由决策：
- 简单任务（score <= 3）→ 单智能体
- 中等任务（3 < score <= 5）→ 单智能体（带Plan）
- 复杂任务（score > 5）→ 多智能体

评分维度：
1. 子任务数量
2. 工具依赖复杂度
3. 上下文依赖程度
4. 预估执行时间
5. 领域知识要求
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from core.agent.types import IntentResult, TaskType, Complexity

logger = logging.getLogger(__name__)


class ComplexityLevel(str, Enum):
    """复杂度等级"""
    SIMPLE = "simple"       # 简单：直接回答或单工具调用
    MEDIUM = "medium"       # 中等：需要规划，多步骤执行
    COMPLEX = "complex"     # 复杂：需要多智能体协作


@dataclass
class ComplexityScore:
    """
    复杂度评分结果
    
    Attributes:
        score: 总分（0-10）
        level: 复杂度等级
        dimensions: 各维度得分
        reasoning: 评分理由
        recommended_agent: 推荐的智能体类型
    """
    score: float = 0.0
    level: ComplexityLevel = ComplexityLevel.SIMPLE
    dimensions: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    recommended_agent: str = "single"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level.value,
            "dimensions": self.dimensions,
            "reasoning": self.reasoning,
            "recommended_agent": self.recommended_agent,
        }


class ComplexityScorer:
    """
    任务复杂度评分器
    
    使用方式：
        scorer = ComplexityScorer()
        score = scorer.score(intent_result, conversation_history)
        
        if score.score > 5:
            print("建议使用多智能体框架")
    """
    
    # 阈值配置
    SIMPLE_THRESHOLD = 3.0    # <= 3 为简单任务
    MEDIUM_THRESHOLD = 5.0    # <= 5 为中等任务
    COMPLEX_THRESHOLD = 7.0   # > 5 为复杂任务
    
    # 任务类型基础复杂度
    TASK_TYPE_BASE_SCORES = {
        TaskType.QUESTION_ANSWERING: 1.0,    # 问答：最简单
        TaskType.DATA_ANALYSIS: 3.0,         # 数据分析：中等
        TaskType.CONTENT_GENERATION: 4.0,    # 内容生成：中等偏上
        TaskType.CODE_DEVELOPMENT: 5.0,      # 代码开发：较复杂
        TaskType.WEB_SEARCH: 2.0,            # 网络搜索：简单
        TaskType.OTHER: 2.0,                 # 其他：默认简单
    }
    
    def __init__(self):
        """初始化复杂度评分器"""
        pass
    
    def score(
        self,
        intent_result: IntentResult,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> ComplexityScore:
        """
        评估任务复杂度
        
        Args:
            intent_result: 意图分析结果
            conversation_history: 对话历史（用于评估上下文依赖）
            
        Returns:
            ComplexityScore: 复杂度评分
        """
        dimensions = {}
        
        # 1. 任务类型基础分
        task_type_score = self._score_task_type(intent_result.task_type)
        dimensions["task_type"] = task_type_score
        
        # 2. 意图复杂度（从IntentResult中获取）
        intent_complexity_score = self._score_intent_complexity(intent_result.complexity)
        dimensions["intent_complexity"] = intent_complexity_score
        
        # 3. Plan需求
        plan_score = 2.0 if intent_result.needs_plan else 0.0
        dimensions["plan_requirement"] = plan_score
        
        # 4. 多智能体需求（来自意图分析）
        multi_agent_score = 3.0 if intent_result.needs_multi_agent else 0.0
        dimensions["multi_agent"] = multi_agent_score
        
        # 5. 上下文依赖
        context_score = self._score_context_dependency(
            conversation_history or [],
            intent_result.is_follow_up
        )
        dimensions["context_dependency"] = context_score
        
        # 计算加权总分
        weights = {
            "task_type": 0.25,
            "intent_complexity": 0.30,
            "plan_requirement": 0.15,
            "multi_agent": 0.20,
            "context_dependency": 0.10,
        }
        
        total_score = sum(
            dimensions[dim] * weights[dim]
            for dim in dimensions
        )
        
        # 归一化到 0-10 范围
        total_score = min(10.0, total_score * 1.5)
        
        # 确定复杂度等级
        if total_score <= self.SIMPLE_THRESHOLD:
            level = ComplexityLevel.SIMPLE
            recommended = "single"
        elif total_score <= self.MEDIUM_THRESHOLD:
            level = ComplexityLevel.MEDIUM
            recommended = "single"
        else:
            level = ComplexityLevel.COMPLEX
            recommended = "multi"
        
        # 生成评分理由
        reasoning = self._generate_reasoning(dimensions, total_score, level)
        
        result = ComplexityScore(
            score=round(total_score, 2),
            level=level,
            dimensions=dimensions,
            reasoning=reasoning,
            recommended_agent=recommended,
        )
        
        logger.info(
            f"📊 复杂度评分: score={result.score}, "
            f"level={result.level.value}, "
            f"recommended={result.recommended_agent}"
        )
        
        return result
    
    def _score_task_type(self, task_type: TaskType) -> float:
        """
        根据任务类型评分
        
        Args:
            task_type: 任务类型
            
        Returns:
            float: 任务类型分数
        """
        return self.TASK_TYPE_BASE_SCORES.get(task_type, 2.0)
    
    def _score_intent_complexity(self, complexity: Complexity) -> float:
        """
        根据意图复杂度评分
        
        Args:
            complexity: 意图复杂度
            
        Returns:
            float: 复杂度分数
        """
        complexity_scores = {
            Complexity.SIMPLE: 1.0,
            Complexity.MEDIUM: 3.0,
            Complexity.COMPLEX: 5.0,
        }
        return complexity_scores.get(complexity, 3.0)
    
    def _score_context_dependency(
        self,
        conversation_history: List[Dict[str, Any]],
        is_follow_up: bool
    ) -> float:
        """
        评估上下文依赖程度
        
        Args:
            conversation_history: 对话历史
            is_follow_up: 是否为追问
            
        Returns:
            float: 上下文依赖分数
        """
        score = 0.0
        
        # 对话历史长度
        history_len = len(conversation_history)
        if history_len > 20:
            score += 2.0
        elif history_len > 10:
            score += 1.0
        elif history_len > 5:
            score += 0.5
        
        # 追问场景
        if is_follow_up:
            score += 1.0
        
        return min(3.0, score)
    
    def _generate_reasoning(
        self,
        dimensions: Dict[str, float],
        total_score: float,
        level: ComplexityLevel
    ) -> str:
        """
        生成评分理由
        
        Args:
            dimensions: 各维度分数
            total_score: 总分
            level: 复杂度等级
            
        Returns:
            str: 评分理由
        """
        parts = []
        
        if dimensions.get("multi_agent", 0) > 0:
            parts.append("需要多智能体协作")
        
        if dimensions.get("plan_requirement", 0) > 0:
            parts.append("需要规划")
        
        if dimensions.get("task_type", 0) >= 4:
            parts.append("任务类型复杂")
        
        if dimensions.get("context_dependency", 0) >= 1.5:
            parts.append("上下文依赖较高")
        
        if not parts:
            parts.append("任务相对简单")
        
        return f"复杂度={level.value}（{total_score:.1f}分）：" + "、".join(parts)
