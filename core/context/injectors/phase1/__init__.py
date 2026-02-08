"""
Phase 1 Injectors - System Message

注入到 messages[0] (role: "system")

包含：
- SystemRoleInjector: 角色定义（从 instance_cache 获取）
- ToolSystemRoleProvider: 工具定义（从 capabilities.yaml 获取）
- HistorySummaryProvider: 历史摘要（从 compaction/summarizer 获取）

缓存策略：
- SystemRoleInjector: STABLE（1h 缓存）
- ToolSystemRoleProvider: STABLE（1h 缓存）
- HistorySummaryProvider: DYNAMIC（不缓存）

优先级（从高到低）：
1. SystemRoleInjector (100)
2. ToolSystemRoleProvider (80)
3. HistorySummaryProvider (60)
"""

from .history_summary import HistorySummaryProvider
from .skill_focus import SkillFocusHintInjector
from .system_role import SystemRoleInjector
from .tool_provider import ToolSystemRoleProvider

__all__ = [
    "SystemRoleInjector",
    "ToolSystemRoleProvider",
    "SkillFocusHintInjector",
    "HistorySummaryProvider",
]


def get_phase1_injectors():
    """
    获取所有 Phase 1 Injector 实例

    Returns:
        Phase 1 Injector 列表
    """
    return [
        SystemRoleInjector(),
        ToolSystemRoleProvider(),
        SkillFocusHintInjector(),
        HistorySummaryProvider(),
    ]
