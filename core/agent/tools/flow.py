"""
ToolExecutionFlow - 统一工具执行流

职责：
- 单个工具执行（含 Plan 特判、HITL 处理）
- 并行/串行工具执行核心逻辑
- 流式工具执行 + SSE 事件发送
- 服务端工具事件处理

迁移自：core/agent/simple/simple_agent_tools.py
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from core.agent.errors import create_error_tool_result, record_tool_error
from core.context import stable_json_dumps
from logger import get_logger

if TYPE_CHECKING:
    from core.context.context_engineering import ContextEngineeringManager
    from core.events.broadcaster import EventBroadcaster
    from core.orchestration import E2EPipelineTracer
    from core.tool.executor import ToolExecutor

logger = get_logger(__name__)


@dataclass
class ToolExecutionContext:
    """
    工具执行上下文

    包含工具执行所需的所有依赖和状态。
    """

    session_id: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None

    # 依赖
    tool_executor: Optional["ToolExecutor"] = None
    broadcaster: Optional["EventBroadcaster"] = None
    event_manager: Any = None
    context_engineering: Optional["ContextEngineeringManager"] = None
    tracer: Optional["E2EPipelineTracer"] = None

    # Plan 相关
    plan_cache: Dict[str, Any] = field(default_factory=dict)
    plan_todo_tool: Any = None

    # 配置
    serial_only_tools: set = field(default_factory=lambda: {"plan", "request_human_confirmation"})
    allow_parallel: bool = True
    max_parallel: int = 5

    # V11: 状态一致性（用于文件操作记录）
    state_manager: Any = None  # Optional[StateConsistencyManager]

    # 扩展
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionResult:
    """
    工具执行结果
    """

    tool_id: str
    tool_name: str
    tool_input: Dict[str, Any]
    result: Any
    is_error: bool = False
    error_msg: Optional[str] = None


class SpecialToolHandler(ABC):
    """
    特殊工具处理器基类

    用于处理需要特殊逻辑的工具（如 plan_todo, HITL）。
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """处理的工具名称"""
        ...

    @abstractmethod
    async def execute(
        self, tool_input: Dict[str, Any], context: ToolExecutionContext, tool_id: str
    ) -> ToolExecutionResult:
        """执行工具"""
        ...


class ToolExecutionFlow:
    """
    工具执行流

    统一管理工具的执行流程，支持：
    - 并行/串行执行
    - 特殊工具处理（通过 handler 插件）
    - 流式输出
    - 错误处理

    使用方式：
        flow = ToolExecutionFlow()
        flow.register_handler(PlanTodoHandler())
        flow.register_handler(HumanConfirmationHandler())

        results = await flow.execute(tool_calls, context)
    """

    def __init__(self):
        """初始化执行流"""
        self._handlers: Dict[str, SpecialToolHandler] = {}

    def register_handler(self, handler: SpecialToolHandler) -> None:
        """
        注册特殊工具处理器

        Args:
            handler: 处理器实例
        """
        self._handlers[handler.tool_name] = handler
        logger.debug(f"✅ 注册特殊工具处理器: {handler.tool_name}")

    def has_handler(self, tool_name: str) -> bool:
        """检查是否有对应的处理器"""
        return tool_name in self._handlers

    async def execute_single(
        self,
        tool_call: Dict[str, Any],
        context: ToolExecutionContext,
        inject_context_fn: Optional[callable] = None,
    ) -> ToolExecutionResult:
        """
        执行单个工具

        Args:
            tool_call: 工具调用信息 {id, name, input}
            context: 执行上下文
            inject_context_fn: 上下文注入函数

        Returns:
            执行结果
        """
        tool_name = tool_call["name"]
        tool_input = tool_call["input"] or {}
        tool_id = tool_call["id"]

        logger.debug(f"🔧 执行工具: {tool_name}")

        try:
            # 获取会话上下文
            if context.event_manager and hasattr(context.event_manager, "storage"):
                session_context = await context.event_manager.storage.get_session_context(
                    context.session_id
                )
                context.user_id = session_context.get("user_id") or context.user_id
                context.conversation_id = (
                    session_context.get("conversation_id")
                    or context.conversation_id
                    or context.session_id
                )

            # 同步 ToolExecutor 上下文
            if context.tool_executor:
                context.tool_executor.update_context(
                    session_id=context.session_id,
                    conversation_id=context.conversation_id,
                    user_id=context.user_id,
                )

            # 上下文注入
            if inject_context_fn:
                tool_input = inject_context_fn(tool_name, tool_input)

            # 检查是否有特殊处理器
            if tool_name in self._handlers:
                return await self._handlers[tool_name].execute(tool_input, context, tool_id)

            # 通用工具执行
            if not context.tool_executor:
                raise ValueError("tool_executor 未配置")

            # V11: 文件操作前置捕获 — 提取 tool_input 中的文件路径，备份到快照
            _pre_capture_files(context, tool_input)

            result = await context.tool_executor.execute(tool_name, tool_input)

            # V11: 文件操作后置记录 — 记录到操作日志（支持回滚）
            _post_record_operation(context, tool_name, tool_input, result)

            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=tool_name,
                tool_input=tool_input,
                result=result,
                is_error=False,
            )

        except Exception as e:
            error_msg = f"工具执行失败: {str(e)}"
            logger.error(f"❌ {error_msg}")

            # 错误保留
            if context.context_engineering:
                record_tool_error(context.context_engineering, tool_name, e, tool_input)

            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=tool_name,
                tool_input=tool_input,
                result={"error": str(e)},
                is_error=True,
                error_msg=error_msg,
            )

    async def execute(
        self,
        tool_calls: List[Dict[str, Any]],
        context: ToolExecutionContext,
        inject_context_fn: Optional[callable] = None,
    ) -> Dict[str, ToolExecutionResult]:
        """
        执行多个工具（支持并行）

        Args:
            tool_calls: 工具调用列表
            context: 执行上下文
            inject_context_fn: 上下文注入函数

        Returns:
            {tool_id: result} 映射
        """
        # 分离可并行的工具和必须串行的特殊工具
        parallel_tools = []
        serial_tools = []

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            if tool_name in context.serial_only_tools or tool_name in self._handlers:
                serial_tools.append(tc)
            else:
                parallel_tools.append(tc)

        results: Dict[str, ToolExecutionResult] = {}

        # 并行执行
        if parallel_tools and context.allow_parallel and len(parallel_tools) > 1:
            logger.info(
                f"⚡ 并行执行 {len(parallel_tools)} 个工具: {[t['name'] for t in parallel_tools]}"
            )

            # 限制并行数量
            tools_to_execute = parallel_tools[: context.max_parallel]
            if len(parallel_tools) > context.max_parallel:
                serial_tools = parallel_tools[context.max_parallel :] + serial_tools
                logger.warning(f"⚠️ 超出最大并行数 {context.max_parallel}，部分工具将串行执行")

            # 追踪
            for tc in tools_to_execute:
                if context.tracer:
                    context.tracer.log_tool_call(tc["name"])

            # 并行执行
            parallel_results = await asyncio.gather(
                *[self.execute_single(tc, context, inject_context_fn) for tc in tools_to_execute],
                return_exceptions=True,
            )

            # 处理结果
            for tc, result in zip(tools_to_execute, parallel_results):
                tool_id = tc["id"]
                if isinstance(result, Exception):
                    results[tool_id] = ToolExecutionResult(
                        tool_id=tool_id,
                        tool_name=tc["name"],
                        tool_input=tc.get("input", {}),
                        result={"error": str(result)},
                        is_error=True,
                        error_msg=str(result),
                    )
                else:
                    results[tool_id] = result
        else:
            # 全部串行
            serial_tools = parallel_tools + serial_tools

        # 串行执行
        for tc in serial_tools:
            tool_id = tc["id"]

            if context.tracer:
                context.tracer.log_tool_call(tc["name"])

            results[tool_id] = await self.execute_single(tc, context, inject_context_fn)

        return results

    async def execute_stream(
        self,
        tool_calls: List[Dict[str, Any]],
        context: ToolExecutionContext,
        content_handler,
        inject_context_fn: Optional[callable] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行工具并发送 SSE 事件（流式）

        Args:
            tool_calls: 工具调用列表
            context: 执行上下文
            content_handler: ContentHandler 实例
            inject_context_fn: 上下文注入函数

        Yields:
            SSE 事件
        """
        # 分离流式和普通工具
        stream_tools = []
        normal_tools = []

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            if tool_name in context.serial_only_tools or tool_name in self._handlers:
                stream_tools.append(tc)
            elif context.tool_executor and context.tool_executor.supports_stream(tool_name):
                stream_tools.append(tc)
            else:
                normal_tools.append(tc)

        # 先执行普通工具
        normal_results: Dict[str, ToolExecutionResult] = {}
        if normal_tools:
            normal_results = await self.execute(normal_tools, context, inject_context_fn)

        # 按原始顺序发送事件
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"] or {}
            tool_id = tool_call["id"]

            # 已执行的普通工具
            if tool_id in normal_results:
                result_info = normal_results[tool_id]
                result = result_info.result
                result_content = result if isinstance(result, str) else stable_json_dumps(result)

                yield await content_handler.emit_block(
                    session_id=context.session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.is_error,
                    },
                )
                continue

            # 流式/特殊工具
            logger.debug(f"🔧 处理工具: {tool_name}")

            if context.tracer:
                context.tracer.log_tool_call(tool_name)

            if context.tool_executor and context.tool_executor.supports_stream(tool_name):
                # 流式工具
                logger.info(f"🌊 流式执行工具: {tool_name}")

                # 上下文注入
                if inject_context_fn:
                    tool_input = inject_context_fn(tool_name, tool_input)

                async def stream_generator():
                    async for chunk in context.tool_executor.execute_stream(tool_name, tool_input):
                        yield chunk

                async for event in content_handler.emit_block_stream(
                    session_id=context.session_id,
                    block_type="tool_result",
                    initial={"tool_use_id": tool_id, "is_error": False},
                    delta_source=stream_generator(),
                ):
                    yield event
            else:
                # 串行工具
                result_info = await self.execute_single(tool_call, context, inject_context_fn)
                result = result_info.result
                result_content = result if isinstance(result, str) else stable_json_dumps(result)

                yield await content_handler.emit_block(
                    session_id=context.session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.is_error,
                    },
                )


def create_tool_execution_flow() -> ToolExecutionFlow:
    """
    创建工具执行流

    Returns:
        ToolExecutionFlow 实例
    """
    from core.agent.tools.special import (
        HumanConfirmationHandler,
        PlanTodoHandler,
    )

    flow = ToolExecutionFlow()
    flow.register_handler(PlanTodoHandler())
    flow.register_handler(HumanConfirmationHandler())

    return flow


# ==================== V11: 状态一致性钩子 ====================


def _extract_file_paths(tool_input: Dict[str, Any]) -> List[str]:
    """
    从工具输入中提取文件路径。

    仅提取已存在的绝对路径或以 ~ 开头的路径（安全边界检查，非语义判断）。
    """
    import os

    paths: List[str] = []
    for value in tool_input.values():
        if not isinstance(value, str):
            continue
        # 绝对路径或 Home 路径
        if value.startswith("/") or value.startswith("~"):
            expanded = os.path.expanduser(value)
            if os.path.isfile(expanded):
                paths.append(expanded)
    return paths


def _pre_capture_files(
    context: ToolExecutionContext,
    tool_input: Dict[str, Any],
) -> None:
    """
    工具执行前：提取 tool_input 中的文件路径，备份到状态快照。
    """
    state_mgr = context.state_manager
    if not state_mgr:
        return

    file_paths = _extract_file_paths(tool_input)
    for fp in file_paths:
        try:
            state_mgr.ensure_file_captured(context.session_id, fp)
        except Exception as e:
            logger.debug(f"文件前置捕获跳过 {fp}: {e}")


def _post_record_operation(
    context: ToolExecutionContext,
    tool_name: str,
    tool_input: Dict[str, Any],
    result: Any,
) -> None:
    """
    工具执行后：将文件操作记录到操作日志。

    通过检查 tool_input 中的文件路径判断是否涉及文件操作。
    """
    state_mgr = context.state_manager
    if not state_mgr:
        return

    file_paths = _extract_file_paths(tool_input)
    if not file_paths:
        return

    from core.state.operation_log import OperationRecord

    for fp in file_paths:
        try:
            record = OperationRecord(
                operation_id=f"op_{tool_name}_{id(result)}",
                action="file_write",
                target=fp,
                before_state=None,  # 已在 pre_capture 中备份到快照
                after_state=None,
            )
            state_mgr.record_operation(context.session_id, record)
        except Exception as e:
            logger.debug(f"操作记录跳过 {fp}: {e}")
