"""
Agent 工具执行模块

这是 agent 内部的 Adapter 层，负责：
- 统一工具执行流（ToolExecutionFlow）
- 特殊工具处理（plan_todo）
- 并行/串行执行策略

目录结构：
- flow.py: ToolExecutionFlow（统一执行接口）
- special.py: 特殊工具处理器（PlanTodoHandler）

设计原则：
- 工具执行细节不在 Agent 中，在 flow 中
- 特殊工具通过 handler 插件处理
"""

from core.agent.tools.flow import (
    SpecialToolHandler,
    ToolExecutionContext,
    ToolExecutionFlow,
    ToolExecutionResult,
    create_tool_execution_flow,
)
from core.agent.tools.special import PlanTodoHandler

__all__ = [
    # Flow
    "ToolExecutionFlow",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "SpecialToolHandler",
    "create_tool_execution_flow",
    # Handlers
    "PlanTodoHandler",
]
