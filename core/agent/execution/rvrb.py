"""
RVRBExecutor - RVR-B 执行策略

实现 React-Validate-Reflect-Backtrack-Repeat 循环。

职责：
- 在 RVR 基础上增加回溯能力
- 工具执行失败时尝试回溯和重试
- 支持 checkpoint 和恢复

回溯类型：
- PLAN_REPLAN: Plan 重规划
- TOOL_REPLACE: 工具替换
- PARAM_ADJUST: 参数调整
- CONTEXT_ENRICH: 上下文补充
- INTENT_CLARIFY: 意图澄清

迁移自：core/agent/simple/mixins/backtrack_mixin.py
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from core.agent.backtrack import (
    BacktrackContext,
    BacktrackDecision,
    BacktrackManager,
    BacktrackResult,
    BacktrackType,
    ClassifiedError,
    ErrorClassifier,
    get_backtrack_manager,
    get_error_classifier,
)
from core.agent.errors import record_tool_error
from core.agent.execution.protocol import (
    BaseExecutor,
    ExecutionContext,
    ExecutorConfig,
)
from core.agent.execution.rvr import RVRExecutor
from core.context import stable_json_dumps
from logger import get_logger
from utils.message_utils import (
    append_assistant_message,
    append_user_message,
    dict_list_to_messages,
    messages_to_dict_list,
)

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext

logger = get_logger(__name__)


@dataclass
class RVRBState:
    """RVR-B 循环状态"""

    session_id: str
    turn: int = 0
    max_turns: int = 10
    backtrack_count: int = 0
    max_backtracks: int = 3

    # 执行历史
    execution_history: List[Dict[str, Any]] = field(default_factory=list)

    # 失败记录
    failed_tools: List[str] = field(default_factory=list)
    failed_strategies: List[str] = field(default_factory=list)

    # Plan 相关
    current_plan: Optional[Dict[str, Any]] = None
    current_step_index: int = 0

    # 最近的错误
    last_error: Optional[ClassifiedError] = None

    def record_execution(
        self, action: str, success: bool, result: Any = None, error: Optional[Exception] = None
    ):
        """记录执行历史"""
        self.execution_history.append(
            {
                "turn": self.turn,
                "action": action,
                "success": success,
                "result": str(result)[:200] if result else None,
                "error": str(error) if error else None,
            }
        )

        if len(self.execution_history) > 50:
            self.execution_history = self.execution_history[-50:]

    def record_tool_failure(self, tool_name: str):
        """记录工具失败"""
        if tool_name not in self.failed_tools:
            self.failed_tools.append(tool_name)

    def increment_backtrack(self):
        """增加回溯计数"""
        self.backtrack_count += 1

    def can_backtrack(self) -> bool:
        """是否还可以回溯"""
        return self.backtrack_count < self.max_backtracks

    def to_backtrack_context(self, error: ClassifiedError) -> BacktrackContext:
        """转换为 BacktrackContext"""
        return BacktrackContext(
            session_id=self.session_id,
            turn=self.turn,
            max_turns=self.max_turns,
            error=error,
            execution_history=self.execution_history,
            backtrack_count=self.backtrack_count,
            max_backtracks=self.max_backtracks,
            current_plan=self.current_plan,
            current_step_index=self.current_step_index,
            failed_tools=self.failed_tools.copy(),
            failed_strategies=self.failed_strategies.copy(),
        )


class RVRBExecutor(RVRExecutor):
    """
    RVR-B 执行器

    在 RVR 基础上增加回溯（Backtrack）能力。

    回溯策略：
    1. 检测工具执行失败
    2. 分类错误（基础设施层 vs 业务逻辑层）
    3. 业务逻辑层错误进行回溯评估
    4. 根据回溯类型执行恢复策略

    使用方式：
        executor = RVRBExecutor(config=ExecutorConfig(
            enable_backtrack=True,
            max_backtrack_attempts=3
        ))

        async for event in executor.execute(
            messages=messages,
            context=ExecutionContext(llm=llm, session_id=session_id, ...)
        ):
            yield event
    """

    def __init__(self, config: Optional[ExecutorConfig] = None):
        """初始化 RVR-B 执行器"""
        super().__init__(config)

        # 确保启用回溯
        if self.config:
            self.config.enable_backtrack = True

        # 回溯组件（延迟初始化）
        self._error_classifier: Optional[ErrorClassifier] = None
        self._backtrack_manager: Optional[BacktrackManager] = None

        # 状态管理
        self._rvrb_states: Dict[str, RVRBState] = {}

    @property
    def name(self) -> str:
        return "RVRBExecutor"

    def supports_backtrack(self) -> bool:
        return True

    def _get_error_classifier(self) -> ErrorClassifier:
        """获取错误分类器（延迟初始化）"""
        if self._error_classifier is None:
            self._error_classifier = get_error_classifier()
        return self._error_classifier

    def _get_backtrack_manager(self, llm) -> BacktrackManager:
        """获取回溯管理器（延迟初始化）"""
        if self._backtrack_manager is None:
            self._backtrack_manager = get_backtrack_manager(llm)
        return self._backtrack_manager

    def _get_rvrb_state(self, session_id: str, max_turns: int = 10) -> RVRBState:
        """获取或创建 RVR-B 状态"""
        if session_id not in self._rvrb_states:
            self._rvrb_states[session_id] = RVRBState(
                session_id=session_id,
                max_turns=max_turns,
                max_backtracks=self.config.max_backtrack_attempts if self.config else 3,
            )
        return self._rvrb_states[session_id]

    def _clear_rvrb_state(self, session_id: str):
        """清除 RVR-B 状态"""
        if session_id in self._rvrb_states:
            del self._rvrb_states[session_id]

    async def _evaluate_backtrack(
        self, error: Exception, tool_name: str, tool_input: Dict[str, Any], state: RVRBState, llm
    ) -> BacktrackResult:
        """
        评估是否需要回溯

        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            llm: LLM 服务

        Returns:
            BacktrackResult: 回溯决策
        """
        # 分类错误
        classifier = self._get_error_classifier()
        classified_error = classifier.classify_tool_error(
            error=error,
            tool_name=tool_name,
            tool_input=tool_input,
        )

        state.last_error = classified_error
        state.record_tool_failure(tool_name)

        # 基础设施层错误不需要回溯
        if classified_error.is_infrastructure_error():
            logger.info(f"📦 基础设施层错误，委托给 resilience 机制")
            return BacktrackResult(
                decision=BacktrackDecision.CONTINUE,
                backtrack_type=BacktrackType.NO_BACKTRACK,
                action={"delegate_to": "resilience"},
                reason="基础设施层错误",
                confidence=1.0,
            )

        # 检查是否还可以回溯
        if not state.can_backtrack():
            logger.warning(f"⚠️ 已达最大回溯次数 ({state.max_backtracks})")
            return BacktrackResult(
                decision=BacktrackDecision.FAIL_GRACEFULLY,
                backtrack_type=BacktrackType.NO_BACKTRACK,
                action={"message": "已达最大回溯次数"},
                reason=f"已尝试 {state.backtrack_count} 次回溯",
                confidence=1.0,
            )

        # 业务逻辑层错误，进行回溯评估
        manager = self._get_backtrack_manager(llm)
        backtrack_ctx = state.to_backtrack_context(classified_error)
        result = await manager.evaluate_and_decide(backtrack_ctx, use_llm=True)

        if result.decision == BacktrackDecision.BACKTRACK:
            state.increment_backtrack()

        return result

    async def _handle_tool_error_with_backtrack(
        self,
        error: Exception,
        tool_name: str,
        tool_input: Dict[str, Any],
        state: RVRBState,
        session_id: str,
        llm,
        tool_executor,
        context_engineering=None,
        tool_selector=None,
    ) -> tuple[str, bool, Optional[Dict]]:
        """
        带回溯的工具错误处理（V10.1 解耦）

        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            session_id: 会话 ID
            llm: LLM 服务
            tool_executor: 工具执行器
            context_engineering: 上下文工程（可选）
            tool_selector: 工具选择器（可选）

        Returns:
            (result_content, is_error, backtrack_event)
        """
        # 评估是否需要回溯
        backtrack_result = await self._evaluate_backtrack(
            error=error, tool_name=tool_name, tool_input=tool_input, state=state, llm=llm
        )

        backtrack_event = None

        if backtrack_result.decision == BacktrackDecision.BACKTRACK:
            logger.info(f"🔄 触发回溯: {backtrack_result.backtrack_type.value}")

            # 生成回溯事件
            backtrack_event = {"type": "backtrack", "data": backtrack_result.to_dict()}

            # 根据回溯类型处理
            if backtrack_result.backtrack_type == BacktrackType.TOOL_REPLACE:
                alt_result = await self._try_alternative_tool(
                    tool_name, tool_input, state, tool_executor, tool_selector
                )
                if alt_result:
                    state.record_execution(f"backtrack:tool_replace", True, alt_result)
                    return alt_result, False, backtrack_event

            # 其他回溯类型：返回错误信息，让 LLM 决定下一步
            result_content = stable_json_dumps(
                {"error": str(error), "backtrack": backtrack_result.to_dict()}
            )
            return result_content, True, backtrack_event

        # 不需要回溯，正常记录错误
        if context_engineering:
            record_tool_error(context_engineering, tool_name, error, tool_input)

        result_content = stable_json_dumps({"error": str(error)})
        state.record_execution(f"tool:{tool_name}", False, error=error)

        return result_content, True, None

    async def _try_alternative_tool(
        self,
        failed_tool: str,
        tool_input: Dict[str, Any],
        state: RVRBState,
        tool_executor,
        tool_selector=None,
    ) -> Optional[str]:
        """
        尝试使用替代工具（V10.1 解耦）

        Args:
            failed_tool: 失败的工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            tool_executor: 工具执行器
            tool_selector: 工具选择器（可选）

        Returns:
            替代工具的执行结果，或 None
        """
        if not tool_executor:
            return None

        if not tool_selector or not hasattr(tool_selector, "get_alternative_tools"):
            return None

        alternatives = tool_selector.get_alternative_tools(failed_tool)

        for alt_tool in alternatives:
            if alt_tool in state.failed_tools:
                continue

            try:
                logger.info(f"🔄 尝试替代工具: {alt_tool}")
                result = await tool_executor.execute(alt_tool, tool_input)
                result_content = result if isinstance(result, str) else stable_json_dumps(result)
                logger.info(f"✅ 替代工具成功: {alt_tool}")
                return result_content
            except Exception as e:
                logger.warning(f"⚠️ 替代工具也失败: {alt_tool} - {e}")
                state.record_tool_failure(alt_tool)
                continue

        return None

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 RVR-B 主循环

        Args:
            messages: 初始消息列表
            context: 执行上下文
            config: 执行配置
            **kwargs: 额外参数

        Yields:
            事件字典
        """
        cfg = config or self.config

        # V10.1: 从 context 获取依赖（解耦 agent）
        llm = context.llm
        tool_executor = context.tool_executor
        broadcaster = context.broadcaster
        ctx = context.runtime_ctx
        session_id = context.session_id
        conversation_id = context.conversation_id  # 🆕 用于沙盒关联
        system_prompt = context.system_prompt
        tools_for_llm = context.tools_for_llm
        intent = context.intent
        plan_cache = context.plan_cache

        # 验证必需依赖
        if not llm:
            logger.error("❌ RVRBExecutor: llm 未提供")
            yield {"type": "error", "data": {"message": "执行器配置错误: llm 未提供"}}
            return

        if not ctx:
            logger.error("❌ RVRBExecutor: runtime_ctx 未提供")
            yield {"type": "error", "data": {"message": "执行器配置错误: runtime_ctx 未提供"}}
            return

        # 获取额外依赖（V10.2 ToolExecutionFlow 需要）
        usage_tracker = context.extra.get("usage_tracker")
        if not usage_tracker:
            from core.billing.tracker import create_enhanced_usage_tracker

            usage_tracker = create_enhanced_usage_tracker(session_id)

        context_engineering = context.extra.get("context_engineering")
        plan_todo_tool = context.extra.get("plan_todo_tool")
        event_manager = context.extra.get("event_manager")

        logger.info(
            f"🚀 RVRBExecutor 开始执行: "
            f"max_turns={cfg.max_turns}, "
            f"max_backtrack={cfg.max_backtrack_attempts}"
        )

        # 初始化 RVR-B 状态
        state = self._get_rvrb_state(session_id, cfg.max_turns)
        state.current_plan = plan_cache.get("plan")

        # 转换消息
        llm_messages = dict_list_to_messages(messages)

        # Context Engineering
        def _refresh_plan_injection(_llm_messages: List, *, inject_errors: bool) -> List:
            if not context_engineering or not plan_cache.get("plan"):
                return _llm_messages
            prepared_messages = context_engineering.prepare_messages_for_llm(
                messages=messages_to_dict_list(_llm_messages),
                plan=plan_cache.get("plan"),
                inject_plan=True,
                inject_errors=inject_errors,
            )
            return dict_list_to_messages(prepared_messages)

        for turn in range(cfg.max_turns):
            # 每轮调用 LLM 前刷新 Plan 注入（Plan 可能在上一轮工具调用中被更新）
            llm_messages = _refresh_plan_injection(llm_messages, inject_errors=(turn == 0))

            ctx.next_turn()
            state.turn = turn

            logger.info(f"{'='*60}")
            logger.info(
                f"🔄 RVR-B Turn {turn + 1}/{cfg.max_turns} (backtracks: {state.backtrack_count}/{state.max_backtracks})"
            )
            logger.info(f"{'='*60}")

            if cfg.enable_stream:
                # 流式处理（V10.1: 使用父类的 _process_stream）
                async for event in self._process_stream(
                    llm=llm,
                    messages=llm_messages,
                    system_prompt=system_prompt,
                    tools=tools_for_llm,
                    ctx=ctx,
                    session_id=session_id,
                    broadcaster=broadcaster,
                    usage_tracker=usage_tracker,
                ):
                    yield event

                response = ctx.last_llm_response
                if response:
                    if response.stop_reason == "tool_use" and response.tool_calls:
                        is_last_turn = turn == cfg.max_turns - 1
                        if is_last_turn:
                            async for event in self._handle_last_turn_tools(
                                response,
                                llm_messages,
                                system_prompt,
                                ctx,
                                session_id,
                                llm,
                                tool_executor,
                                broadcaster,
                                usage_tracker,
                                context_engineering=context_engineering,
                                plan_cache=plan_cache,
                                plan_todo_tool=plan_todo_tool,
                                event_manager=event_manager,
                            ):
                                yield event
                            break

                        # 处理工具调用（带回溯，V10.2 使用 ToolExecutionFlow）
                        async for event in self._handle_tool_calls_with_backtrack_stream(
                            response,
                            llm_messages,
                            session_id,
                            conversation_id,
                            ctx,
                            state,
                            llm,
                            tool_executor,
                            broadcaster,
                            usage_tracker,
                            context_engineering=context_engineering,
                            plan_cache=plan_cache,
                            plan_todo_tool=plan_todo_tool,
                            event_manager=event_manager,
                        ):
                            yield event
                    else:
                        ctx.set_completed(response.content, response.stop_reason)
                        state.record_execution("complete", True, response.content)
                        break
            else:
                # 非流式处理
                response = await llm.create_message_async(
                    messages=llm_messages, system=system_prompt, tools=tools_for_llm
                )

                usage_tracker.accumulate(response)

                if response.content:
                    yield {"type": "content", "data": {"text": response.content}}

                if response.stop_reason != "tool_use":
                    ctx.set_completed(response.content, response.stop_reason)
                    state.record_execution("complete", True, response.content)
                    break

                is_last_turn = turn == cfg.max_turns - 1
                if is_last_turn:
                    # 非流式最后一轮
                    async for event in self._handle_tool_calls(
                        response,
                        llm_messages,
                        session_id,
                        conversation_id,
                        ctx,
                        tool_executor,
                        broadcaster,
                        context_engineering=context_engineering,
                        plan_cache=plan_cache,
                        plan_todo_tool=plan_todo_tool,
                        event_manager=event_manager,
                    ):
                        yield event

                    final_response = await llm.create_message_async(
                        messages=llm_messages, system=system_prompt, tools=[]
                    )
                    usage_tracker.accumulate(final_response)

                    if final_response.content:
                        yield {"type": "content", "data": {"text": final_response.content}}

                    ctx.set_completed(final_response.content, final_response.stop_reason)
                    break

                await self._handle_tool_calls_with_backtrack_non_stream(
                    response,
                    llm_messages,
                    session_id,
                    conversation_id,
                    ctx,
                    state,
                    llm,
                    tool_executor,
                    broadcaster,
                    usage_tracker,
                    context_engineering=context_engineering,
                    plan_cache=plan_cache,
                    plan_todo_tool=plan_todo_tool,
                    event_manager=event_manager,
                )

            if ctx.is_completed():
                break

        # 清理状态
        self._clear_rvrb_state(session_id)
        logger.info(f"✅ RVRBExecutor 执行完成: turns={ctx.current_turn}")

    async def _handle_tool_calls_with_backtrack_stream(
        self,
        response,
        llm_messages: List,
        session_id: str,
        conversation_id: str,  # 🆕 用于沙盒关联
        ctx: "RuntimeContext",
        state: RVRBState,
        llm,
        tool_executor,
        broadcaster,
        usage_tracker,
        context_engineering=None,
        plan_cache: Dict = None,
        plan_todo_tool=None,
        event_manager=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理工具调用（流式，带回溯，V10.2 使用 ToolExecutionFlow）"""
        from core.agent.content_handler import create_content_handler
        from core.agent.tools.flow import (
            ToolExecutionContext,
            ToolExecutionFlow,
            create_tool_execution_flow,
        )

        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]

        # 创建 ToolExecutionContext
        tool_context = ToolExecutionContext(
            session_id=session_id,
            conversation_id=conversation_id,  # 🆕 传递 conversation_id
            tool_executor=tool_executor,
            broadcaster=broadcaster,
            event_manager=event_manager,
            context_engineering=context_engineering,
            plan_cache=plan_cache or {},
            plan_todo_tool=plan_todo_tool,
        )

        flow = create_tool_execution_flow()
        content_handler = create_content_handler(broadcaster, ctx.block, session_id=session_id)
        tool_results = []

        for tool_call in client_tools:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"] or {}
            tool_id = tool_call["id"]

            try:
                # 使用 ToolExecutionFlow 执行单个工具
                result_info = await flow.execute_single(tool_call, tool_context)
                result = result_info.result
                result_content = result if isinstance(result, str) else stable_json_dumps(result)
                is_error = result_info.is_error

                if not is_error:
                    state.record_execution(f"tool:{tool_name}", True, result_content)
                else:
                    raise Exception(result_info.error_msg or "工具执行失败")

            except Exception as e:
                logger.error(f"❌ 工具执行失败: {tool_name} - {e}")

                # 带回溯的错误处理
                result_content, is_error, backtrack_event = (
                    await self._handle_tool_error_with_backtrack(
                        error=e,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        state=state,
                        session_id=session_id,
                        llm=llm,
                        tool_executor=tool_executor,
                        context_engineering=context_engineering,
                    )
                )

                # 发送回溯事件
                if backtrack_event:
                    yield backtrack_event

            yield await content_handler.emit_block(
                session_id=session_id,
                block_type="tool_result",
                content={"tool_use_id": tool_id, "content": result_content, "is_error": is_error},
            )

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": is_error,
                }
            )

        append_assistant_message(llm_messages, response.raw_content)

        if tool_results:
            append_user_message(llm_messages, tool_results)

    async def _handle_tool_calls_with_backtrack_non_stream(
        self,
        response,
        llm_messages: List,
        session_id: str,
        conversation_id: str,  # 🆕 用于沙盒关联
        ctx: "RuntimeContext",
        state: RVRBState,
        llm,
        tool_executor,
        broadcaster,
        usage_tracker,
        context_engineering=None,
        plan_cache: Dict = None,
        plan_todo_tool=None,
        event_manager=None,
    ) -> None:
        """处理工具调用（非流式，带回溯，V10.2 使用 ToolExecutionFlow）"""
        from core.agent.tools.flow import (
            ToolExecutionContext,
            ToolExecutionFlow,
            create_tool_execution_flow,
        )

        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]

        append_assistant_message(llm_messages, response.raw_content)

        # 创建 ToolExecutionContext
        tool_context = ToolExecutionContext(
            session_id=session_id,
            conversation_id=conversation_id,  # 🆕 传递 conversation_id
            tool_executor=tool_executor,
            broadcaster=broadcaster,
            event_manager=event_manager,
            context_engineering=context_engineering,
            plan_cache=plan_cache or {},
            plan_todo_tool=plan_todo_tool,
        )

        flow = create_tool_execution_flow()
        tool_results = []

        for tool_call in client_tools:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"] or {}
            tool_id = tool_call["id"]

            try:
                # 使用 ToolExecutionFlow 执行单个工具
                result_info = await flow.execute_single(tool_call, tool_context)
                result = result_info.result
                result_content = result if isinstance(result, str) else stable_json_dumps(result)
                is_error = result_info.is_error

                if not is_error:
                    state.record_execution(f"tool:{tool_name}", True, result_content)
                else:
                    raise Exception(result_info.error_msg or "工具执行失败")

            except Exception as e:
                logger.error(f"❌ 工具执行失败: {tool_name} - {e}")

                result_content, is_error, _ = await self._handle_tool_error_with_backtrack(
                    error=e,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    state=state,
                    session_id=session_id,
                    llm=llm,
                    tool_executor=tool_executor,
                    context_engineering=context_engineering,
                )

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": is_error,
                }
            )

        if tool_results:
            append_user_message(llm_messages, tool_results)


def create_rvrb_executor(
    config: Optional[ExecutorConfig] = None, max_backtracks: int = 3
) -> RVRBExecutor:
    """
    创建 RVR-B 执行器

    Args:
        config: 执行配置
        max_backtracks: 最大回溯次数

    Returns:
        RVRBExecutor 实例
    """
    cfg = config or ExecutorConfig()
    cfg.enable_backtrack = True
    cfg.max_backtrack_attempts = max_backtracks
    return RVRBExecutor(config=cfg)
