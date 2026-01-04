"""
Agent 模块

提供 Agent 核心功能：
- SimpleAgent: 核心编排器（精简版）
- IntentAnalyzer: 意图分析器
- 类型定义: IntentResult, TaskType, Complexity 等

目录结构：
- simple_agent.py: 核心 Agent（只做编排）
- intent_analyzer.py: 意图分析器
- types.py: 类型定义
"""

from core.agent.types import (
    TaskType,
    Complexity,
    PromptLevel,
    IntentResult,
    ExecutionConfig
)
from core.agent.intent_analyzer import (
    IntentAnalyzer,
    create_intent_analyzer
)
from core.agent.simple_agent import (
    SimpleAgent,
    create_simple_agent
)

__all__ = [
    # 类型
    "TaskType",
    "Complexity", 
    "PromptLevel",
    "IntentResult",
    "ExecutionConfig",
    # 模块
    "IntentAnalyzer",
    "create_intent_analyzer",
    "SimpleAgent",
    "create_simple_agent",
]

