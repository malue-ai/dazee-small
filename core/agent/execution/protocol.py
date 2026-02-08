"""
ExecutorProtocol - 统一执行协议

定义 Agent 执行器的统一接口，所有执行策略（RVR/RVR-B/Multi）
都实现此协议。

设计原则：
- Executor 是纯策略对象，不持有 Agent 状态
- 通过 ExecutionContext 传递所需的依赖
- 返回 AsyncGenerator 支持流式输出

使用方式：
    executor = RVRExecutor(config=ExecutorConfig(...))

    async for event in executor.execute(
        messages=messages,
        context=ExecutionContext(llm=llm, tools=tools, ...)
    ):
        yield event
"""

import asyncio
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)

if TYPE_CHECKING:
    from core.context.compaction import ContextStrategy
    from core.context.runtime import RuntimeContext
    from core.events.broadcaster import EventBroadcaster
    from core.llm.base import BaseLLMService
    from core.routing.types import IntentResult
    from core.termination.protocol import BaseTerminator
    from core.tool.executor import ToolExecutor


@dataclass
class ExecutorConfig:
    """
    执行器配置

    包含执行策略的通用配置参数。
    """

    # 主循环不再使用 max_turns 硬性限制（LLM-First：大模型自主决定终止）
    # 终止由 AdaptiveTerminator 信号驱动：LLM end_turn / 用户停止 / 费用超限 / 时长超限
    enable_stream: bool = True
    allow_parallel_tools: bool = True
    max_parallel_tools: int = 5

    # Token 管理
    token_budget: int = 180000
    safe_threshold_margin: int = 20000

    # 回溯配置（RVR-B）
    enable_backtrack: bool = False
    max_backtrack_attempts: int = 3

    # 终止策略（信号驱动，替代硬性 max_turns）
    terminator: Optional["BaseTerminator"] = None

    # 扩展配置
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    """
    执行上下文

    包含执行过程中需要的所有依赖和状态。
    """

    # 核心依赖
    llm: "BaseLLMService"
    session_id: str
    conversation_id: str = ""  # 对话 ID

    # 工具相关
    tool_executor: Optional["ToolExecutor"] = None
    tools_for_llm: List[Dict[str, Any]] = field(default_factory=list)

    # 事件广播
    broadcaster: Optional["EventBroadcaster"] = None

    # 上下文
    system_prompt: Any = None  # str 或 List[Dict]
    intent: Optional["IntentResult"] = None
    runtime_ctx: Optional["RuntimeContext"] = None
    context_strategy: Optional["ContextStrategy"] = None

    # 状态
    plan_cache: Dict[str, Any] = field(default_factory=dict)

    # V11: 外部停止信号（用户主动停止）
    stop_event: Optional[asyncio.Event] = None

    # 扩展
    # V10.1: 可包含 usage_tracker, context_engineering, tracer 等
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """
    执行结果

    包含执行完成后的状态和统计信息。
    """

    success: bool
    final_content: Optional[str] = None
    stop_reason: Optional[str] = None
    turns_used: int = 0

    # 统计
    total_tokens: int = 0
    tool_calls_count: int = 0

    # 错误信息
    error: Optional[str] = None

    # 扩展
    extra: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ExecutorProtocol(Protocol):
    """
    执行器协议

    所有执行策略都必须实现此协议。
    """

    @property
    def name(self) -> str:
        """执行器名称"""
        ...

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行主循环

        Args:
            messages: 初始消息列表
            context: 执行上下文
            config: 执行配置（可选，使用默认配置）
            **kwargs: 额外参数

        Yields:
            SSE 事件字典
        """
        ...

    def supports_backtrack(self) -> bool:
        """是否支持回溯"""
        ...


class BaseExecutor:
    """
    执行器基类

    提供通用的执行器功能。
    """

    def __init__(self, config: Optional[ExecutorConfig] = None):
        """
        初始化执行器

        Args:
            config: 执行配置
        """
        self.config = config or ExecutorConfig()

    @property
    def name(self) -> str:
        """执行器名称"""
        return self.__class__.__name__

    def supports_backtrack(self) -> bool:
        """是否支持回溯"""
        return False

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行主循环（子类实现）"""
        raise NotImplementedError("子类必须实现 execute 方法")
        yield  # 使其成为 generator
