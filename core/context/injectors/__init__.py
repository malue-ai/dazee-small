"""
Injector 模块

提供分阶段的上下文注入能力：
- Phase 1: System Message - 注入到 system message
- Phase 2: User Context - 注入到 user context message
- Phase 3: Runtime - 追加到最后一条用户消息

主要组件：
- BaseInjector: Injector 基类
- InjectionPhase: 注入阶段枚举
- CacheStrategy: 缓存策略枚举
- InjectionContext: 注入上下文
- InjectionOrchestrator: 编排器

使用示例：
```python
from core.context.injectors import (
    InjectionOrchestrator,
    InjectionContext,
    create_default_orchestrator,
)

# 获取已注册所有 Injector 的编排器
orchestrator = create_default_orchestrator()

# 创建上下文
context = InjectionContext(
    user_id="user_123",
    user_query="帮我写一段代码",
    prompt_cache=prompt_cache,
)

# 构建 system blocks
system_blocks = await orchestrator.build_system_blocks(context)

# 构建 messages
messages = await orchestrator.build_messages(context)
```
"""

from .base import (
    BaseInjector,
    CacheStrategy,
    InjectionPhase,
    InjectionResult,
)
from .context import InjectionContext
from .orchestrator import (
    InjectionOrchestrator,
    get_orchestrator,
    reset_orchestrator,
)

# Phase 1 Injectors
from .phase1 import (
    HistorySummaryProvider,
    SkillFocusHintInjector,
    SystemRoleInjector,
    ToolSystemRoleProvider,
    get_phase1_injectors,
)

# Phase 2 Injectors
from .phase2 import (
    KnowledgeContextInjector,
    PlaybookHintInjector,
    UserMemoryInjector,
    get_phase2_injectors,
)

# Phase 3 Injectors
from .phase3 import (
    GTDTodoInjector,
    PageEditorContextInjector,
    get_phase3_injectors,
)


def create_default_orchestrator() -> InjectionOrchestrator:
    """
    创建并注册所有默认 Injector 的编排器

    Returns:
        已注册所有 Injector 的 InjectionOrchestrator
    """
    orchestrator = InjectionOrchestrator()

    # 注册 Phase 1 Injectors
    orchestrator.register_many(get_phase1_injectors())

    # 注册 Phase 2 Injectors
    orchestrator.register_many(get_phase2_injectors())

    # 注册 Phase 3 Injectors
    orchestrator.register_many(get_phase3_injectors())

    return orchestrator


__all__ = [
    # 基类和枚举
    "BaseInjector",
    "InjectionPhase",
    "CacheStrategy",
    "InjectionResult",
    # 上下文
    "InjectionContext",
    # 编排器
    "InjectionOrchestrator",
    "get_orchestrator",
    "reset_orchestrator",
    "create_default_orchestrator",
    # Phase 1 Injectors
    "SystemRoleInjector",
    "ToolSystemRoleProvider",
    "SkillFocusHintInjector",
    "HistorySummaryProvider",
    "get_phase1_injectors",
    # Phase 2 Injectors
    "KnowledgeContextInjector",
    "PlaybookHintInjector",
    "UserMemoryInjector",
    "get_phase2_injectors",
    # Phase 3 Injectors
    "GTDTodoInjector",
    "PageEditorContextInjector",
    "get_phase3_injectors",
]
