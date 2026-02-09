"""
Injector 基类和枚举定义

职责：
1. 定义 Injector 的统一接口
2. 定义注入阶段（Phase 1/2/3）
3. 定义缓存策略（Stable/Session/Dynamic）

架构概述：
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: System Message (role: "system")                   │
│  ├── SystemRoleInjector     # 角色定义                       │
│  ├── ToolSystemRoleProvider # 工具定义                       │
│  └── HistorySummaryProvider # 历史摘要(极难触发)               │
├─────────────────────────────────────────────────────────────┤
│  Phase 2: User Context (role: "user", systemInjection: true)│
│  ├── UserMemoryInjector          # 用户记忆                  │
│  ├── PlaybookHintInjector        # 历史策略提示              │
│  └── KnowledgeContextInjector    # 本地知识库上下文          │
├─────────────────────────────────────────────────────────────┤
│  Phase 3: Runtime Injection (追加到最后一条消息)              │
│  ├── PageEditorContextInjector  # 页面编辑器上下文           │
│  └── GTDTodoInjector            # GTD Todo                  │
└─────────────────────────────────────────────────────────────┘
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .context import InjectionContext


class InjectionPhase(Enum):
    """
    注入阶段

    - SYSTEM: 注入到 messages[0] (role: "system")
    - USER_CONTEXT: 注入到 messages[1] (role: "user", systemInjection: true)
    - RUNTIME: 追加到 messages[n] (最后一条用户消息)
    """

    SYSTEM = 1  # Phase 1: 注入到 system message
    USER_CONTEXT = 2  # Phase 2: 注入到 user context message
    RUNTIME = 3  # Phase 3: 追加到最后一条用户消息


class CacheStrategy(Enum):
    """
    缓存策略

    与 Claude Prompt Caching 集成：
    - STABLE: 极稳定内容，1h 缓存（框架规则、工具定义）
    - SESSION: 会话级内容，5min 缓存（用户画像）
    - DYNAMIC: 动态内容，不缓存（历史摘要、实时数据）

    缓存层级映射：
    - STABLE → _cache_layer = 1, 2, 3（根据优先级）
    - SESSION → _cache_layer = 较低值
    - DYNAMIC → _cache_layer = 0（不缓存）
    """

    STABLE = "stable"  # 极稳定，1h 缓存（框架规则、工具定义）
    SESSION = "session"  # 会话级，5min 缓存（用户画像）
    DYNAMIC = "dynamic"  # 动态，不缓存（历史摘要、实时数据）


@dataclass
class InjectionResult:
    """
    注入结果

    Attributes:
        content: 注入的内容（None 表示跳过）
        xml_tag: XML 标签名（可选，用于包装内容）
        metadata: 元数据（可选，用于调试和监控）
    """

    content: Optional[str] = None
    xml_tag: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """内容是否为空"""
        return not self.content or not self.content.strip()

    def to_text(self) -> str:
        """
        转换为文本格式

        如果指定了 xml_tag，则包装为 XML 格式：
        <xml_tag>content</xml_tag>
        """
        if self.is_empty:
            return ""

        if self.xml_tag:
            return f"<{self.xml_tag}>\n{self.content}\n</{self.xml_tag}>"

        return self.content


class BaseInjector(ABC):
    """
    Injector 基类

    所有 Injector 都必须继承此类，并实现：
    - name: 返回 Injector 名称
    - phase: 返回注入阶段
    - inject: 执行注入，返回内容

    可选覆盖：
    - cache_strategy: 缓存策略（默认 DYNAMIC）
    - priority: 优先级（默认 50）
    - enabled: 是否启用（默认 True）

    使用示例：
    ```python
    class SystemRoleInjector(BaseInjector):
        @property
        def name(self) -> str:
            return "system_role"

        @property
        def phase(self) -> InjectionPhase:
            return InjectionPhase.SYSTEM

        @property
        def cache_strategy(self) -> CacheStrategy:
            return CacheStrategy.STABLE

        async def inject(self, context: InjectionContext) -> InjectionResult:
            role_prompt = await self._get_role_prompt(context)
            return InjectionResult(content=role_prompt)
    ```
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Injector 名称

        用于日志和调试，应该是唯一的标识符
        """
        pass

    @property
    @abstractmethod
    def phase(self) -> InjectionPhase:
        """
        注入阶段

        决定内容注入到 messages 的哪个位置
        """
        pass

    @property
    def cache_strategy(self) -> CacheStrategy:
        """
        缓存策略

        决定内容是否应该被缓存，以及缓存时间
        默认为 DYNAMIC（不缓存）
        """
        return CacheStrategy.DYNAMIC

    @property
    def priority(self) -> int:
        """
        优先级

        同一 Phase 内，优先级越高的 Injector 输出越靠前
        默认为 50
        范围：0-100
        """
        return 50

    @property
    def enabled(self) -> bool:
        """
        是否启用

        可以根据配置或条件动态返回
        默认为 True
        """
        return True

    @abstractmethod
    async def inject(self, context: "InjectionContext") -> InjectionResult:
        """
        执行注入

        Args:
            context: 注入上下文，包含所有需要的信息

        Returns:
            InjectionResult，包含注入的内容
            如果 content 为 None 或空字符串，则跳过此 Injector
        """
        pass

    async def should_inject(self, context: "InjectionContext") -> bool:
        """
        判断是否应该注入

        默认检查 enabled 属性，子类可以覆盖以实现更复杂的逻辑

        Args:
            context: 注入上下文

        Returns:
            True 表示应该注入，False 表示跳过
        """
        return self.enabled

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"phase={self.phase.name}, "
            f"cache={self.cache_strategy.name}, "
            f"priority={self.priority})"
        )
