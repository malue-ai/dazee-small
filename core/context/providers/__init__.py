"""
上下文提供者实现

包含：
- ConversationMetadataProvider（对话元数据）- 从 DB 读取

注意：
- 用户记忆由 core.context.injectors.phase2.UserMemoryInjector 处理
- 历史对话不在这里，由 ChatService 直接管理
"""

from .metadata import (
    ConversationMetadataProvider,
    load_context_metadata,
    load_plan_for_context,
)

__all__ = [
    "ConversationMetadataProvider",
    "load_plan_for_context",
    "load_context_metadata",
]
