"""
Phase 2 Injectors - User Context

注入到 messages[1] (role: "user", systemInjection: true)

包含：
- UserMemoryInjector: 用户记忆
- PlaybookHintInjector: 匹配的 Playbook 策略提示
- KnowledgeContextInjector: 本地知识库上下文

缓存策略：
- UserMemoryInjector: SESSION（5min 缓存）
- PlaybookHintInjector: SESSION
- KnowledgeContextInjector: DYNAMIC（每轮不同）
"""

from .knowledge_context import KnowledgeContextInjector
from .playbook_hint import PlaybookHintInjector
from .user_memory import UserMemoryInjector

__all__ = [
    "KnowledgeContextInjector",
    "PlaybookHintInjector",
    "UserMemoryInjector",
]


def get_phase2_injectors():
    """
    获取所有 Phase 2 Injector 实例

    Returns:
        Phase 2 Injector 列表
    """
    return [
        UserMemoryInjector(),
        PlaybookHintInjector(),
        KnowledgeContextInjector(),
    ]
