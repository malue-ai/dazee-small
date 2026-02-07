"""
路由层类型定义

统一的数据结构定义，用于意图识别和路由决策。

V11.0 小搭子架构简化：
- 固定使用 RVR-B 执行策略，移除 agent_type 选择
- IntentResult 仅保留 complexity、skip_memory 核心字段
"""

# 1. 标准库
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class Complexity(Enum):
    """任务复杂度"""

    SIMPLE = "simple"  # 简单：单步骤，无需规划
    MEDIUM = "medium"  # 中等：需要少量工具调用，需要规划
    COMPLEX = "complex"  # 复杂：需要规划和多步骤执行


@dataclass
class IntentResult:
    """
    意图分析结果（V11.0 小搭子简化版）

    核心字段：
    - complexity: 复杂度等级 (simple/medium/complex)
    - skip_memory: 是否跳过记忆检索
    - is_follow_up: 是否为追问

    推断字段（通过 property 计算）：
    - needs_plan: 从 complexity 推断
    """

    complexity: Complexity  # 复杂度等级
    skip_memory: bool  # 是否跳过记忆检索
    is_follow_up: bool = False  # 是否为追问
    wants_to_stop: bool = False  # 用户是否希望停止/取消当前任务（LLM 语义推断）
    confidence: float = 1.0  # 置信度（用于缓存命中判断）

    @property
    def needs_plan(self) -> bool:
        """是否需要规划（从 complexity 推断）"""
        return self.complexity != Complexity.SIMPLE

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "complexity": self.complexity.value,
            "skip_memory": self.skip_memory,
            "is_follow_up": self.is_follow_up,
            "wants_to_stop": self.wants_to_stop,
            "confidence": self.confidence,
            # 推断字段
            "needs_plan": self.needs_plan,
        }
