"""
上下文提供者实现

包含：
- MemoryProvider（用户记忆）- 需要检索
- ConversationMetadataProvider（对话元数据）- 从 DB 读取

注意：历史对话不在这里，由 ChatService 直接管理
原因：当前会话历史已在 messages 中，跨会话检索太慢

V11.0: 移除 KnowledgeProvider（云端 Ragie），本地知识检索由后续模块实现
"""

from .memory import MemoryProvider
from .metadata import (
    ConversationMetadataProvider,
    load_context_metadata,
    load_plan_for_context,
)

__all__ = [
    "MemoryProvider",
    "ConversationMetadataProvider",
    "load_plan_for_context",
    "load_context_metadata",
]
