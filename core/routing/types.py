"""
路由层类型定义

统一的数据结构定义，用于意图识别和路由决策。

V10.0 重构：简化 IntentResult 为 3 个核心字段
- complexity: 复杂度等级
- agent_type: 执行引擎类型 (rvr/rvr-b/multi)
- skip_memory: 是否跳过记忆检索

V10.1 迁移：从 core/agent/types.py 迁移到 core/routing/types.py
- 目的：消除 routing 对 agent 的反向依赖
- core/agent/types.py 保留为向后兼容 wrapper
"""

# 1. 标准库
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

# 2. 第三方库（无）

# 3. 本地模块（无）


class Complexity(Enum):
    """任务复杂度"""

    SIMPLE = "simple"  # 简单：单步骤，无需规划
    MEDIUM = "medium"  # 中等：需要少量工具调用，需要规划
    COMPLEX = "complex"  # 复杂：需要规划和多步骤执行


@dataclass
class IntentResult:
    """
    意图分析结果（V10.0 简化版）

    核心字段：
    - complexity: 复杂度等级 (simple/medium/complex)
    - agent_type: 执行引擎类型 (rvr/rvr-b/multi)
    - skip_memory: 是否跳过记忆检索

    推断字段（通过 property 计算）：
    - needs_plan: 从 complexity 推断
    - execution_strategy: 从 complexity 推断
    """

    complexity: Complexity  # 复杂度等级
    agent_type: str  # 执行引擎: rvr | rvr-b | multi
    skip_memory: bool  # 是否跳过记忆检索
    confidence: float = 1.0  # 置信度（用于缓存命中判断）

    @property
    def needs_plan(self) -> bool:
        """是否需要规划（从 complexity 推断）"""
        return self.complexity != Complexity.SIMPLE

    @property
    def execution_strategy(self) -> str:
        """执行策略（从 complexity 推断）"""
        if self.agent_type == "multi":
            return "multi"
        return "rvr-b" if self.complexity == Complexity.COMPLEX else "rvr"

    @property
    def is_multi_agent(self) -> bool:
        """是否使用多智能体"""
        return self.agent_type == "multi"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "complexity": self.complexity.value,
            "agent_type": self.agent_type,
            "skip_memory": self.skip_memory,
            "confidence": self.confidence,
            # 推断字段
            "needs_plan": self.needs_plan,
            "execution_strategy": self.execution_strategy,
        }
