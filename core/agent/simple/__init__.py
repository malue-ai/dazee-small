"""
单智能体模块

架构设计（V8.0）：

┌─────────────────────────────────────────────────┐
│              SimpleAgent (核心实现)              │
│  ├── ToolExecutionMixin                         │
│  └── RVRLoopMixin                               │
├─────────────────────────────────────────────────┤
│                      ↓                           │
│              RVRBAgent (继承 + Mixin)            │
│  ├── SimpleAgent（继承）                         │
│  └── BacktrackMixin（混入回溯能力）              │
└─────────────────────────────────────────────────┘

调用关系：
    AgentFactory._create_simple_agent() → SimpleAgent
    AgentFactory.from_schema()          → SimpleAgent
    
    # 需要回溯能力时
    create_simple_agent(strategy="rvr-b") → RVRBAgent

使用方式：
    # 方式 1：直接使用 SimpleAgent（推荐，由 Factory 创建）
    from core.agent.simple import SimpleAgent
    
    # 方式 2：使用 RVRBAgent（需要回溯能力时）
    from core.agent.simple import RVRBAgent
    agent = RVRBAgent(event_manager=em, max_backtracks=3)
    
    # 方式 3：工厂函数
    from core.agent.simple import create_simple_agent
    agent = create_simple_agent(strategy="rvr-b", event_manager=em)
"""

from typing import Dict

# 核心实现
from core.agent.simple.simple_agent import SimpleAgent

# 回溯增强版
from core.agent.simple.rvrb_agent import RVRBAgent

# Mixin（供扩展使用）
from core.agent.simple.mixins import BacktrackMixin, RVRBState

# 错误处理
from core.agent.simple.errors import (
    create_error_tool_result,
    create_timeout_tool_results,
    create_fallback_tool_result,
    record_tool_error,
)


def get_available_strategies() -> Dict[str, str]:
    """
    获取可用的执行策略
    
    Returns:
        策略名称到描述的映射
    """
    return {
        "simple": "SimpleAgent - 标准 RVR 循环",
        "rvr-b": "RVRBAgent - RVR + Backtrack 回溯",
    }


def create_simple_agent(
    strategy: str = "simple",
    **kwargs
):
    """
    创建单智能体实例（工厂函数）
    
    Args:
        strategy: 执行策略
            - "simple": SimpleAgent，标准 RVR 循环（默认）
            - "rvr-b" 或 "rvrb": RVRBAgent，带回溯能力
        **kwargs: 传递给 Agent 构造函数的参数
            - model: 模型名称
            - max_turns: 最大轮次
            - event_manager: EventManager 实例（必需）
            - max_backtracks: 最大回溯次数（仅 RVRBAgent）
        
    Returns:
        SimpleAgent 或 RVRBAgent 实例
    """
    strategy = strategy.lower().replace("-", "").replace("_", "")
    
    if strategy in ("simple", "rvr"):
        return SimpleAgent(**kwargs)
    elif strategy in ("rvrb",):
        return RVRBAgent(**kwargs)
    else:
        raise ValueError(
            f"未知的执行策略: {strategy}。"
            f"支持的策略: {list(get_available_strategies().keys())}"
        )


__all__ = [
    # 核心
    "SimpleAgent",
    # 回溯增强
    "RVRBAgent",
    # Mixin
    "BacktrackMixin",
    "RVRBState",
    # 工厂
    "create_simple_agent",
    "get_available_strategies",
    # 错误处理
    "create_error_tool_result",
    "create_timeout_tool_results",
    "create_fallback_tool_result",
    "record_tool_error",
]
