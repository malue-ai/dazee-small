"""
Phase 2 Injectors - User Context

注入到 messages[1] (role: "user", systemInjection: true)

包含：
- UserMemoryInjector: 用户记忆

缓存策略：
- UserMemoryInjector: SESSION（5min 缓存）
"""

from .user_memory import UserMemoryInjector

__all__ = [
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
    ]
