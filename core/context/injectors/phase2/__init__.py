"""
Phase 2 Injectors - User Context

注入到 messages[1] (role: "user", systemInjection: true)

包含：
- UserMemoryInjector: 用户记忆（从 Mem0 获取）
- KnowledgeInjector: 知识库（从 Ragie 获取）

缓存策略：
- UserMemoryInjector: SESSION（5min 缓存）
- KnowledgeInjector: DYNAMIC（不缓存）

优先级（从高到低）：
1. UserMemoryInjector (90)
2. KnowledgeInjector (80)
"""

from .knowledge import KnowledgeInjector
from .user_memory import UserMemoryInjector

__all__ = [
    "UserMemoryInjector",
    "KnowledgeInjector",
]


def get_phase2_injectors():
    """
    获取所有 Phase 2 Injector 实例

    Returns:
        Phase 2 Injector 列表
    """
    return [
        UserMemoryInjector(),
        KnowledgeInjector(),
    ]
