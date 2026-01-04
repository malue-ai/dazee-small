"""
Context 模块

提供上下文管理功能：
- Context: 对话上下文管理（消息加载、token 计算、压缩）
- RuntimeContext: Agent 运行时状态管理
"""

from core.context.conversation import Context, create_context
from core.context.runtime import RuntimeContext, create_runtime_context

__all__ = [
    "Context",
    "create_context",
    "RuntimeContext", 
    "create_runtime_context",
]

