"""
注入上下文

职责：
1. 封装注入所需的所有上下文信息
2. 提供统一的数据访问接口
3. 支持懒加载和缓存

架构设计：
InjectionContext 是 Injector 的输入参数，包含：
- 用户信息（user_id, user_query）
- 会话信息（session_id, conversation_id）
- Agent 配置（prompt_cache, context_strategy）
- 运行时状态（runtime_context, intent）
- 工具信息（available_tools, selected_tools）
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext
    from core.prompt.instance_cache import InstancePromptCache


@dataclass
class InjectionContext:
    """
    注入上下文

    封装 Injector 执行所需的所有信息

    Attributes:
        user_id: 用户 ID
        user_query: 当前用户查询
        session_id: 会话 ID
        conversation_id: 对话 ID

        prompt_cache: 实例提示词缓存
        runtime_context: 运行时上下文

        intent: 意图识别结果
        task_complexity: 任务复杂度

        available_tools: 可用工具列表
        selected_tools: 已选择的工具列表

        history_messages: 历史消息列表
        variables: 前端变量

        metadata: 额外元数据
    """

    # 用户信息
    user_id: Optional[str] = None
    user_query: Optional[str] = None

    # 会话信息
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

    # Agent 配置
    prompt_cache: Optional["InstancePromptCache"] = None
    runtime_context: Optional["RuntimeContext"] = None

    # 意图和复杂度
    intent: Optional[Any] = None
    task_complexity: Optional[str] = None  # "simple", "medium", "complex"

    # 工具信息
    available_tools: List[Dict[str, Any]] = field(default_factory=list)
    selected_tools: List[Dict[str, Any]] = field(default_factory=list)

    # 历史消息
    history_messages: List[Dict[str, Any]] = field(default_factory=list)

    # 前端变量
    variables: Dict[str, Any] = field(default_factory=dict)

    # 额外元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 内部缓存（懒加载）
    _cache: Dict[str, Any] = field(default_factory=dict, repr=False)

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取上下文值

        优先从 metadata 获取，如果不存在则返回默认值

        Args:
            key: 键名
            default: 默认值

        Returns:
            值
        """
        return self.metadata.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        设置上下文值

        Args:
            key: 键名
            value: 值
        """
        self.metadata[key] = value

    def get_cached(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        用于 Injector 之间共享数据

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在则返回 None
        """
        return self._cache.get(key)

    def set_cached(self, key: str, value: Any) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
        """
        self._cache[key] = value

    @property
    def has_prompt_cache(self) -> bool:
        """是否有提示词缓存"""
        return self.prompt_cache is not None and self.prompt_cache.is_loaded

    @property
    def has_runtime_context(self) -> bool:
        """是否有运行时上下文"""
        return self.runtime_context is not None

    @property
    def has_history(self) -> bool:
        """是否有历史消息"""
        return bool(self.history_messages)

    @property
    def has_tools(self) -> bool:
        """是否有可用工具"""
        return bool(self.available_tools)

    def get_variable(self, name: str, default: Any = None) -> Any:
        """
        获取前端变量

        Args:
            name: 变量名
            default: 默认值

        Returns:
            变量值
        """
        var = self.variables.get(name, {})
        if isinstance(var, dict):
            return var.get("value", default)
        return var if var is not None else default

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于序列化）

        不包含 prompt_cache 和 runtime_context（不可序列化）
        """
        return {
            "user_id": self.user_id,
            "user_query": self.user_query,
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "task_complexity": self.task_complexity,
            "available_tools": [t.get("name", "") for t in self.available_tools],
            "selected_tools": [t.get("name", "") for t in self.selected_tools],
            "has_history": self.has_history,
            "variables": list(self.variables.keys()),
            "metadata": list(self.metadata.keys()),
        }

    def __repr__(self) -> str:
        return (
            f"InjectionContext("
            f"user_id={self.user_id!r}, "
            f"complexity={self.task_complexity!r}, "
            f"tools={len(self.available_tools)}, "
            f"history={len(self.history_messages)})"
        )
