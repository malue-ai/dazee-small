"""
Phase 3 Injectors - Runtime

追加到 messages[n] (最后一条用户消息)

包含：
- GTDTodoInjector: GTD Todo 状态
- PageEditorContextInjector: 页面编辑器上下文

缓存策略：
- GTDTodoInjector: DYNAMIC（不缓存）
- PageEditorContextInjector: DYNAMIC（不缓存）

优先级（从高到低）：
1. GTDTodoInjector (80)
2. PageEditorContextInjector (70)
"""

from .gtd_todo import GTDTodoInjector
from .page_editor import PageEditorContextInjector

__all__ = [
    "GTDTodoInjector",
    "PageEditorContextInjector",
]


def get_phase3_injectors():
    """
    获取所有 Phase 3 Injector 实例

    Returns:
        Phase 3 Injector 列表
    """
    return [
        GTDTodoInjector(),
        PageEditorContextInjector(),
    ]
