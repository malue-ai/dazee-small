"""
ToolExecutionFlow - 统一工具执行流

职责：
- 单个工具执行（含 Plan 特判、HITL 处理）
- 并行/串行工具执行核心逻辑
- 流式工具执行 + SSE 事件发送
- 服务端工具事件处理

Agent 工具处理 — 流式工具执行与结果收集
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


def _tool_result_content(result: Any) -> Any:
    """
    Normalize tool result for tool_result block content.
    If result is a list of content blocks (each dict with "type"), pass through for multimodal.
    Otherwise stringify (str as-is, other serialized to JSON).
    """
    if isinstance(result, str):
        return result
    if (
        isinstance(result, list)
        and result
        and all(isinstance(b, dict) and "type" in b for b in result)
    ):
        return result
    return stable_json_dumps(result)


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
    serial_only_tools: set = field(default_factory=lambda: {"plan", "hitl"})
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
                result_content = _tool_result_content(result)

                # 通过 broadcaster 发送 SSE 事件（content_start + content_stop）
                await content_handler.emit_block(
                    session_id=context.session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.is_error,
                    },
                )

                # yield tool_result 事件用于消息构建（_handle_tool_calls 依赖此格式）
                yield {
                    "type": "tool_result",
                    "content": {
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.is_error,
                    },
                }
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
                result_content = _tool_result_content(result)

                # 通过 broadcaster 发送 SSE 事件
                await content_handler.emit_block(
                    session_id=context.session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.is_error,
                    },
                )

                # yield tool_result 事件用于消息构建
                yield {
                    "type": "tool_result",
                    "content": {
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.is_error,
                    },
                }


def create_tool_execution_flow() -> ToolExecutionFlow:
    """
    创建工具执行流

    Returns:
        ToolExecutionFlow 实例
    """
    from core.agent.tools.special import PlanTodoHandler

    flow = ToolExecutionFlow()
    flow.register_handler(PlanTodoHandler())

    # NOTE: HumanConfirmationHandler 已删除
    # hitl 工具通过 ToolExecutor → HITLTool.execute() 执行
    # broadcaster 在 content_stop 时自动发送表单事件

    return flow


# ==================== V11: 状态一致性钩子 ====================

# 破坏性命令集合（纯确定性安全边界检查，非语义判断）
_DESTRUCTIVE_COMMANDS = frozenset({
    "rm", "rmdir", "mv", "chmod", "chown",
    "truncate", "shred", "unlink",
})

# 写入类命令集合
_WRITE_COMMANDS = frozenset({
    "cp", "tee", "dd", "install",
    "sed", "awk", "patch",
})

# 目录递归捕获的安全上限
_DIR_CAPTURE_MAX_FILES = 200
_DIR_CAPTURE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _extract_paths_from_tokens(tokens: List[str]) -> List[str]:
    """
    从 shell 命令 token 列表中提取文件/目录路径。

    仅提取以 / 或 ~ 开头且在磁盘上存在的路径（安全边界检查）。
    """
    import os

    paths: List[str] = []
    for token in tokens:
        if token.startswith("-"):
            continue
        if token.startswith("/") or token.startswith("~"):
            expanded = os.path.expanduser(token)
            if os.path.exists(expanded):
                paths.append(expanded)
    return paths


def _detect_command_info(
    tool_input: Dict[str, Any],
) -> tuple:
    """
    从工具输入中检测 shell 命令类型和目标路径。

    Returns:
        (command_name, is_destructive, paths):
            command_name: 命令名（如 "rm"），非 shell 命令时为 ""
            is_destructive: 是否为破坏性命令
            paths: 提取到的文件/目录路径列表
    """
    import os
    import shlex

    all_paths: List[str] = []
    cmd_name = ""
    is_destructive = False

    for key, value in tool_input.items():
        if isinstance(value, str):
            # 直接路径值（如 {"path": "/Users/foo/file.txt"}）
            if value.startswith("/") or value.startswith("~"):
                expanded = os.path.expanduser(value)
                if os.path.exists(expanded):
                    all_paths.append(expanded)
            else:
                # 可能是 shell 命令字符串（如 "rm -rf /path/to/file"）
                try:
                    tokens = shlex.split(value)
                except ValueError:
                    continue
                if len(tokens) >= 2:
                    candidate_cmd = os.path.basename(tokens[0])
                    if candidate_cmd in _DESTRUCTIVE_COMMANDS or candidate_cmd in _WRITE_COMMANDS:
                        cmd_name = candidate_cmd
                        is_destructive = candidate_cmd in _DESTRUCTIVE_COMMANDS
                    all_paths.extend(_extract_paths_from_tokens(tokens))

        elif isinstance(value, list):
            # 命令数组（如 ["rm", "-rf", "/path/to/file"]）
            str_tokens = [t for t in value if isinstance(t, str)]
            if str_tokens:
                candidate_cmd = os.path.basename(str_tokens[0])
                if candidate_cmd in _DESTRUCTIVE_COMMANDS or candidate_cmd in _WRITE_COMMANDS:
                    cmd_name = candidate_cmd
                    is_destructive = candidate_cmd in _DESTRUCTIVE_COMMANDS
                all_paths.extend(_extract_paths_from_tokens(str_tokens))

    return cmd_name, is_destructive, all_paths


def _extract_file_paths(tool_input: Dict[str, Any]) -> List[str]:
    """
    从工具输入中提取文件/目录路径。

    支持：
    1. 直接路径值（如 {"path": "/Users/foo/file.txt"}）
    2. 命令数组（如 {"command": ["rm", "-rf", "/path"]}）
    3. 命令字符串（如 {"command": "rm -rf /path"}）

    仅提取已存在的绝对路径或 ~ 路径（安全边界检查，非语义判断）。
    """
    _, _, paths = _detect_command_info(tool_input)
    return paths


def _collect_dir_files(dir_path: str) -> List[str]:
    """
    递归收集目录下的所有文件路径，受安全上限约束。

    Returns:
        文件路径列表（截断到 _DIR_CAPTURE_MAX_FILES 且总大小不超过 _DIR_CAPTURE_MAX_BYTES）
    """
    import os

    files: List[str] = []
    total_size = 0

    try:
        for root, _dirs, filenames in os.walk(dir_path):
            for fname in filenames:
                if len(files) >= _DIR_CAPTURE_MAX_FILES:
                    logger.debug(
                        f"目录捕获达到文件数上限 {_DIR_CAPTURE_MAX_FILES}: {dir_path}"
                    )
                    return files
                fpath = os.path.join(root, fname)
                try:
                    fsize = os.path.getsize(fpath)
                except OSError:
                    continue
                if total_size + fsize > _DIR_CAPTURE_MAX_BYTES:
                    logger.debug(
                        f"目录捕获达到体积上限 {_DIR_CAPTURE_MAX_BYTES // (1024*1024)}MB: {dir_path}"
                    )
                    return files
                total_size += fsize
                files.append(fpath)
    except OSError as e:
        logger.debug(f"目录遍历失败 {dir_path}: {e}")

    return files


def _pre_capture_files(
    context: ToolExecutionContext,
    tool_input: Dict[str, Any],
) -> None:
    """
    工具执行前：提取 tool_input 中的文件/目录路径，备份到状态快照。

    对破坏性命令（rm, mv 等）额外递归捕获目录内容。
    """
    import os

    state_mgr = context.state_manager
    if not state_mgr:
        return

    cmd_name, is_destructive, paths = _detect_command_info(tool_input)

    for fp in paths:
        try:
            if os.path.isfile(fp):
                state_mgr.ensure_file_captured(context.session_id, fp)
            elif os.path.isdir(fp) and is_destructive:
                # 破坏性命令针对目录时，递归捕获目录下所有文件
                dir_files = _collect_dir_files(fp)
                if dir_files:
                    logger.info(
                        f"破坏性命令 '{cmd_name}' 目标为目录，"
                        f"预捕获 {len(dir_files)} 个文件: {fp}"
                    )
                for df in dir_files:
                    try:
                        state_mgr.ensure_file_captured(context.session_id, df)
                    except Exception as e:
                        logger.debug(f"目录内文件捕获跳过 {df}: {e}")
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

    根据命令类型记录准确的操作类型（file_write / file_delete / file_rename）。
    """
    import os

    state_mgr = context.state_manager
    if not state_mgr:
        return

    cmd_name, is_destructive, paths = _detect_command_info(tool_input)
    if not paths:
        return

    from core.state.operation_log import OperationRecord

    # 根据命令名推断操作类型
    if cmd_name in ("rm", "rmdir", "unlink", "shred"):
        action = "file_delete"
    elif cmd_name in ("mv",):
        action = "file_rename"
    else:
        action = "file_write"

    for fp in paths:
        try:
            record = OperationRecord(
                operation_id=f"op_{tool_name}_{id(result)}",
                action=action,
                target=fp,
                before_state=None,  # 已在 pre_capture 中备份到快照
                after_state=None,
            )
            state_mgr.record_operation(context.session_id, record)
        except Exception as e:
            logger.debug(f"操作记录跳过 {fp}: {e}")
