"""
上下文提供者实现

包含：
- KnowledgeProvider（知识库 - Ragie）- 需要检索
- MemoryProvider（用户记忆 - Mem0）- 需要检索

注意：历史对话不在这里，由 ChatService 直接管理
原因：当前会话历史已在 messages 中，跨会话检索太慢
"""
from .knowledge import KnowledgeProvider
from .memory import MemoryProvider

__all__ = [
    "KnowledgeProvider",
    "MemoryProvider",
]
