"""
RVRExecutor - RVR 执行策略

实现 React-Validate-Reflect 循环。

V10.1 P1 解耦：
- 所有方法迁移到 Executor 中
- 不再依赖 agent 对象
- 从 ExecutionContext 获取所有依赖

职责：
- 标准 RVR 主循环
- 流式 LLM 响应处理
- 工具调用处理
- 消息构建和更新
- 上下文长度管理（Token 裁剪）

注意：
- 本模块实现标准 RVR 循环
- 如需回溯能力，请使用 RVRBExecutor
"""

from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from core.agent.errors import create_fallback_tool_result, create_timeout_tool_results
from core.agent.execution.protocol import (
    BaseExecutor,
    ExecutionContext,
    ExecutorConfig,
)
from core.context import stable_json_dumps
from core.context.compaction import trim_by_token_budget
from core.llm.base import count_request_tokens
from logger import get_logger
from utils.message_utils import (
    append_assistant_message,
    append_user_message,
    dict_list_to_messages,
    messages_to_dict_list,
)

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext
    from core.events.broadcaster import EventBroadcaster
    from core.llm.base import BaseLLMService, LLMResponse
    from core.routing.types import IntentResult
    from core.tool.executor import ToolExecutor
    from models.usage import UsageTracker

logger = get_logger(__name__)

# ==================== 图片剥离辅助函数 ====================

IMAGE_PLACEHOLDER = "[截图已省略，仅保留最近轮次的截图]"


def _content_has_image(content) -> bool:
    """递归检查 content 是否包含 image block"""
    if isinstance(content, list):
        return any(
            (isinstance(b, dict) and b.get("type") == "image")
            or (isinstance(b, dict) and b.get("type") == "tool_result"
                and _content_has_image(b.get("content")))
            for b in content
        )
    if isinstance(content, dict):
        return content.get("type") == "image"
    return False


def _strip_images_from_blocks(blocks: list) -> list:
    """
    递归替换 content blocks 中的 image block 为文本占位符

    保留 text block 和 tool_use/tool_result 的结构，仅替换 image。
    """
    result = []
    for block in blocks:
        if not isinstance(block, dict):
            result.append(block)
            continue

        block_type = block.get("type", "")

        if block_type == "image":
            # 替换 base64 图片为文本占位符
            result.append({"type": "text", "text": IMAGE_PLACEHOLDER})
        elif block_type == "tool_result":
            inner = block.get("content")
            if isinstance(inner, list) and _content_has_image(inner):
                result.append({
                    **block,
                    "content": _strip_images_from_blocks(inner),
                })
            else:
                result.append(block)
        else:
            result.append(block)

    return result


class RVRExecutor(BaseExecutor):
    """
    RVR 执行器（V10.1 解耦版）

    实现标准的 React-Validate-Reflect-Repeat 循环。
    所有方法都在 Executor 内部实现，不依赖外部 Agent。

    使用方式：
        executor = RVRExecutor()

        async for event in executor.execute(
            messages=messages,
            context=ExecutionContext(
                llm=llm,
                session_id=session_id,
                tool_executor=tool_executor,
                broadcaster=broadcaster,
                ...
            )
        ):
            yield event
    """

    @property
    def name(self) -> str:
        return "RVRExecutor"

    def supports_backtrack(self) -> bool:
        return False

    # ==================== 工具方法 ====================

    def _extract_system_prompt_text(self, system_prompt) -> str:
        """
        从 system_prompt 中提取纯文本（支持 string 和 list 格式）
        """
        if isinstance(system_prompt, list):
            parts = []
            for block in system_prompt:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "".join(parts)
        return system_prompt or ""

    @staticmethod
    def _strip_old_images(
        messages: List[Dict], preserve_last_n: int = 2
    ) -> List[Dict]:
        """
        剥离非最近 N 条消息中的 base64 图片数据

        observe_screen 等工具返回的截图以 base64 嵌入 tool_result，
        每张图片 ~0.6MB，会快速耗尽 200K token 上下文窗口。
        将旧消息中的图片替换为文本占位符，保留最近消息的图片。

        Args:
            messages: 消息列表（dict 格式）
            preserve_last_n: 保留最近 N 条消息的图片不剥离

        Returns:
            处理后的消息列表（浅拷贝，仅修改含图片的消息）
        """
        if not messages:
            return messages

        stripped_count = 0
        result = []

        # 保留最后 N 条消息的图片
        strip_boundary = len(messages) - preserve_last_n

        for i, msg in enumerate(messages):
            if i >= strip_boundary:
                result.append(msg)
                continue

            content = msg.get("content")
            if not isinstance(content, list):
                result.append(msg)
                continue

            # 检查是否包含图片 block
            has_image = any(
                isinstance(block, dict) and block.get("type") == "image"
                for block in content
            )

            if not has_image:
                # 递归检查 tool_result 内部
                has_image = any(
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and _content_has_image(block.get("content"))
                    for block in content
                )

            if not has_image:
                result.append(msg)
                continue

            # 替换图片为占位符
            new_content = _strip_images_from_blocks(content)
            stripped_count += 1
            result.append({**msg, "content": new_content})

        if stripped_count > 0:
            logger.info(f"🖼️ 已剥离 {stripped_count} 条消息中的 base64 图片")

        return result

    def _trim_messages_if_needed(
        self,
        llm_messages: List,
        system_prompt_text: str,
        safe_threshold: int,
        context_strategy,
        turn: int = 0,
        tools_for_llm: List[Dict] = None,  # 工具定义，用于更准确的 token 估算
    ) -> List:
        """
        如果消息超过安全阈值，执行裁剪

        始终剥离旧消息中的 base64 图片，避免截图累积撑爆上下文窗口。
        """
        from core.context.compaction import fast_prefilter_messages

        messages_for_estimate = [
            {"role": m.role, "content": m.content} if hasattr(m, "role") else m
            for m in llm_messages
        ]

        # 始终剥离旧消息中的 base64 图片（保留最近 2 条消息的图片）
        messages_for_estimate = self._strip_old_images(messages_for_estimate)

        # 快速字符级预过滤（<1ms）：在昂贵的 token 计算前截断超大消息
        messages_for_estimate = fast_prefilter_messages(messages_for_estimate)

        # 使用统一的 token 计算方法（包含工具定义）
        estimated_tokens = count_request_tokens(
            messages_for_estimate, system_prompt_text, tools_for_llm
        )

        if estimated_tokens <= safe_threshold:
            if turn == 0:
                logger.debug(
                    f"📊 上下文长度正常: 估算 {estimated_tokens:,} tokens < 安全阈值 {safe_threshold:,}"
                )
            # 返回剥离图片后的消息（而非原始消息），防止截图累积超限
            return dict_list_to_messages(messages_for_estimate)

        preserve_first = (
            getattr(context_strategy, "preserve_first_messages", 4) if context_strategy else 4
        )
        preserve_last = (
            getattr(context_strategy, "preserve_last_messages", 8) if context_strategy else 8
        )
        preserve_tool_results = (
            getattr(context_strategy, "preserve_tool_results", True) if context_strategy else True
        )

        logger.warning(
            f"⚠️ Turn {turn + 1}: 上下文长度警告: 估算 {estimated_tokens:,} tokens > 安全阈值 {safe_threshold:,}"
        )

        trimmed_messages, trim_stats = trim_by_token_budget(
            messages=messages_for_estimate,
            token_budget=safe_threshold,
            preserve_first_messages=preserve_first,
            preserve_last_messages=preserve_last,
            preserve_tool_results=preserve_tool_results,
            system_prompt=system_prompt_text,
        )
        trimmed_tokens = trim_stats.estimated_tokens

        logger.info(
            f"✂️ 历史消息已裁剪: {len(messages_for_estimate)} → {len(trimmed_messages)} 条消息, "
            f"token 估算: {estimated_tokens:,} → {trimmed_tokens:,}"
        )

        if trimmed_tokens > safe_threshold:
            logger.warning(f"⚠️ 裁剪后仍超过阈值，进行激进裁剪...")

            aggressive_budget = int(safe_threshold * 0.6)
            aggressively_trimmed, aggressive_stats = trim_by_token_budget(
                messages=trimmed_messages,
                token_budget=aggressive_budget,
                preserve_first_messages=2,
                preserve_last_messages=6,
                preserve_tool_results=False,
                system_prompt=system_prompt_text,
            )
            aggressive_tokens = aggressive_stats.estimated_tokens

            logger.info(
                f"✂️ 激进裁剪: {len(trimmed_messages)} → {len(aggressively_trimmed)} 条消息, "
                f"token 估算: {trimmed_tokens:,} → {aggressive_tokens:,}"
            )

            return dict_list_to_messages(aggressively_trimmed)

        return dict_list_to_messages(trimmed_messages)

    # ==================== LLM 流式处理 ====================

    async def _process_stream(
        self,
        llm: "BaseLLMService",
        messages: List,
        system_prompt,
        tools: List,
        ctx: "RuntimeContext",
        session_id: str,
        broadcaster: "EventBroadcaster",
        usage_tracker: "UsageTracker",
        is_first_turn: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式处理 LLM 响应（从 Agent 迁移）

        Args:
            llm: LLM 服务
            messages: 消息列表
            system_prompt: 系统提示词
            tools: 工具定义
            ctx: RuntimeContext
            session_id: Session ID
            broadcaster: 事件广播器
            usage_tracker: 使用跟踪器
            is_first_turn: 是否首轮

        Yields:
            SSE 事件
        """
        from core.agent.content_handler import create_content_handler

        # 创建 ContentHandler（传入 session_id 用于快捷方法）
        content_handler = create_content_handler(broadcaster, ctx.block, session_id=session_id)

        final_response = None

        try:
            # 调用 LLM Stream
            async for response in llm.create_message_stream(
                messages=messages, system=system_prompt, tools=tools
            ):
                # LLMResponse 对象 → 根据字段判断事件类型
                # 注意：只处理流式增量（is_stream=True），跳过最终汇总响应（is_stream=False）

                if response.thinking and response.is_stream:
                    # 思考过程（流式增量）
                    await content_handler.handle_thinking(response.thinking)
                    yield {"type": "thinking_delta", "data": {"thinking": response.thinking}}

                if response.content and response.is_stream:
                    # 内容增量（流式增量）
                    await content_handler.handle_text(response.content)
                    yield {"type": "content_delta", "data": {"text": response.content}}

                if response.tool_use_start:
                    # 工具调用开始
                    await content_handler.handle_tool_use_start(
                        tool_id=response.tool_use_start.get("id"),
                        tool_name=response.tool_use_start.get("name"),
                    )
                    yield {"type": "tool_use_start", "data": response.tool_use_start}

                if response.input_delta:
                    # 工具输入增量
                    await content_handler.handle_tool_input_delta(response.input_delta)
                    yield {"type": "input_delta", "data": {"input": response.input_delta}}

                # 检查是否是最终响应（有 tool_calls 或 stop_reason，或者是非流式汇总）
                if (
                    response.tool_calls
                    or response.stop_reason != "end_turn"
                    or not response.is_stream
                ):
                    final_response = response

        finally:
            # 关闭最后一个 block
            await content_handler.stop_block(session_id)

        # 保存最终响应
        if final_response:
            ctx.last_llm_response = final_response
            ctx.touch_activity()  # 更新活动时间（idle_timeout 检测）
            # 累积 usage
            usage_tracker.accumulate(final_response)

    # ==================== 工具处理 ====================

    async def _handle_tool_calls(
        self,
        response: "LLMResponse",
        llm_messages: List,
        session_id: str,
        conversation_id: str,
        ctx: "RuntimeContext",
        tool_executor: "ToolExecutor",
        broadcaster: "EventBroadcaster",
        context_engineering=None,
        plan_cache: Dict = None,
        plan_todo_tool=None,
        event_manager=None,
        state_manager=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理工具调用（流式，V10.2 使用 ToolExecutionFlow）

        Args:
            response: LLM 响应
            llm_messages: 消息列表（会被修改）
            session_id: Session ID
            conversation_id: Conversation ID
            ctx: RuntimeContext
            tool_executor: 工具执行器
            broadcaster: 事件广播器
            context_engineering: 上下文工程（可选）
            plan_cache: Plan 缓存（可选）
            plan_todo_tool: Plan 工具（可选）
            event_manager: 事件管理器（可选）
            state_manager: 状态一致性管理器（可选，V11）

        Yields:
            SSE 事件
        """
        from core.agent.content_handler import create_content_handler
        from core.agent.tools.flow import (
            ToolExecutionContext,
            ToolExecutionFlow,
            create_tool_execution_flow,
        )

        tool_calls = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]

        if not tool_calls:
            return

        # 创建 ToolExecutionContext
        tool_context = ToolExecutionContext(
            session_id=session_id,
            conversation_id=conversation_id,
            tool_executor=tool_executor,
            broadcaster=broadcaster,
            event_manager=event_manager,
            context_engineering=context_engineering,
            plan_cache=plan_cache or {},
            plan_todo_tool=plan_todo_tool,
            state_manager=state_manager,
        )

        # 创建 ToolExecutionFlow（带特殊处理器）
        flow = create_tool_execution_flow()
        content_handler = create_content_handler(broadcaster, ctx.block, session_id=session_id)

        # 使用 ToolExecutionFlow 执行
        tool_results = []
        async for event in flow.execute_stream(tool_calls, tool_context, content_handler):
            # 跳过空事件
            if event is None:
                continue

            yield event

            # 从事件中提取结果用于消息构建
            if event.get("type") == "tool_result" or (
                isinstance(event.get("content"), dict) and "tool_use_id" in event.get("content", {})
            ):
                content = event.get("content", {})
                if content:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": content.get("tool_use_id"),
                            "content": content.get("content", ""),
                            "is_error": content.get("is_error", False),
                        }
                    )

        # 如果没有从事件提取到结果，使用同步执行结果
        if not tool_results:
            results = await flow.execute(tool_calls, tool_context)
            for tool_id, result_info in results.items():
                result = result_info.result
                result_content = result if isinstance(result, str) else stable_json_dumps(result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.is_error,
                    }
                )

        # 更新消息历史
        # 添加 assistant 消息（包含 tool_use）
        assistant_content = (
            response.raw_content_blocks if hasattr(response, "raw_content_blocks") else []
        )
        if not assistant_content and response.tool_calls:
            # 构建 content blocks
            assistant_content = []
            if response.content:
                assistant_content.append({"type": "text", "text": response.content})
            for tc in response.tool_calls:
                if tc.get("type") == "tool_use":
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc.get("input", {}),
                        }
                    )

        append_assistant_message(llm_messages, assistant_content)

        # 添加 user 消息（包含 tool_result）
        append_user_message(llm_messages, tool_results)

        # 更新连续失败计数（供终止策略与自动回滚使用）
        if any(r.get("is_error") for r in tool_results):
            ctx.consecutive_failures += 1
        else:
            ctx.consecutive_failures = 0
        ctx.touch_activity()  # 工具执行完成，更新活动时间（idle_timeout 检测）

    async def _handle_last_turn_tools(
        self,
        response: "LLMResponse",
        llm_messages: List,
        system_prompt,
        ctx: "RuntimeContext",
        session_id: str,
        conversation_id: str,
        llm: "BaseLLMService",
        tool_executor: "ToolExecutor",
        broadcaster: "EventBroadcaster",
        usage_tracker: "UsageTracker",
        context_engineering=None,
        plan_cache: Dict = None,
        plan_todo_tool=None,
        event_manager=None,
        state_manager=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理最后一轮的工具调用

        在最后一轮，执行工具后需要再次调用 LLM 生成最终响应。
        """
        # 先执行工具（V10.2: 使用 ToolExecutionFlow）
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
            state_manager=state_manager,
        ):
            yield event

        # 再次调用 LLM 生成最终响应
        logger.info("🔄 最后一轮工具执行完成，生成最终响应...")

        async for event in self._process_stream(
            llm=llm,
            messages=llm_messages,
            system_prompt=system_prompt,
            tools=[],  # 最后一轮不提供工具
            ctx=ctx,
            session_id=session_id,
            broadcaster=broadcaster,
            usage_tracker=usage_tracker,
            is_first_turn=False,
        ):
            yield event

        final_response = ctx.last_llm_response
        if final_response:
            ctx.set_completed(final_response.content, final_response.stop_reason)

    # ==================== 主执行循环 ====================

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 RVR 主循环（V10.1 解耦版）

        Args:
            messages: 初始消息列表（dict 格式）
            context: 执行上下文（包含所有依赖）
            config: 执行配置
            **kwargs: 额外参数

        Yields:
            事件字典
        """
        cfg = config or self.config

        # 从 context 获取依赖（V10.1: 直接从 context 获取，不依赖 agent）
        llm = context.llm
        tool_executor = context.tool_executor
        broadcaster = context.broadcaster
        ctx = context.runtime_ctx
        session_id = context.session_id
        conversation_id = context.conversation_id
        system_prompt = context.system_prompt
        tools_for_llm = context.tools_for_llm
        intent = context.intent
        plan_cache = context.plan_cache

        # 验证必需依赖
        if not llm:
            logger.error("❌ RVRExecutor: llm 未提供")
            yield {"type": "error", "data": {"message": "执行器配置错误: llm 未提供"}}
            return

        if not ctx:
            logger.error("❌ RVRExecutor: runtime_ctx 未提供")
            yield {"type": "error", "data": {"message": "执行器配置错误: runtime_ctx 未提供"}}
            return

        # 获取额外依赖（从 context.extra）
        usage_tracker = context.extra.get("usage_tracker")
        if not usage_tracker:
            from models.usage import UsageTracker

            usage_tracker = UsageTracker()

        context_engineering = context.extra.get("context_engineering")
        plan_todo_tool = context.extra.get("plan_todo_tool")
        event_manager = context.extra.get("event_manager")
        state_manager = context.extra.get("state_manager")

        logger.info(f"🚀 RVRExecutor 开始执行 (signal-driven termination)")

        # 转换消息为 Message 对象
        llm_messages = dict_list_to_messages(messages)

        # Context Engineering: Todo 重写
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

        # 提取 system_prompt 文本并计算安全阈值
        system_prompt_text = self._extract_system_prompt_text(system_prompt)
        token_budget = (
            getattr(context.context_strategy, "token_budget", 180000)
            if context.context_strategy
            else 180000
        )
        safe_threshold = token_budget - 10000

        # 进入循环前检查并裁剪上下文
        llm_messages = self._trim_messages_if_needed(
            llm_messages, system_prompt_text, safe_threshold, context.context_strategy, turn=0
        )

        turn = 0
        while True:
            # 每轮调用 LLM 前刷新 Plan 注入（Plan 可能在上一轮工具调用中被更新）
            llm_messages = _refresh_plan_injection(llm_messages, inject_errors=(turn == 0))

            # 每轮开始时检查上下文长度
            if turn > 0:
                llm_messages = self._trim_messages_if_needed(
                    llm_messages,
                    system_prompt_text,
                    safe_threshold,
                    context.context_strategy,
                    turn=turn,
                )

            ctx.next_turn()
            ctx.touch_activity()  # 更新活动时间（用于 idle_timeout 检测）
            logger.info(f"{'='*60}")
            logger.info(f"🔄 Turn {turn + 1}")
            logger.info(f"{'='*60}")

            if cfg.enable_stream:
                # 流式处理
                async for event in self._process_stream(
                    llm=llm,
                    messages=llm_messages,
                    system_prompt=system_prompt,
                    tools=tools_for_llm,
                    ctx=ctx,
                    session_id=session_id,
                    broadcaster=broadcaster,
                    usage_tracker=usage_tracker,
                    is_first_turn=(turn == 0),
                ):
                    yield event

                response = ctx.last_llm_response
                if response:
                    # 阶段 5 验证：检查复杂任务是否创建 Plan
                    if turn == 0 and intent and intent.needs_plan and response.tool_calls:
                        self._validate_plan_creation(
                            response.tool_calls, context.extra.get("tracer")
                        )

                    # 处理工具调用
                    if response.stop_reason == "tool_use" and response.tool_calls:
                        # V11.1: HITL 危险操作确认（执行前拦截，等待用户决策）
                        hitl_rejected = False
                        if cfg.terminator:
                            try:
                                pending_names = [
                                    t.get("name") for t in response.tool_calls if t.get("name")
                                ]
                                from core.termination.protocol import TerminationAction

                                hitl_decision = cfg.terminator.evaluate(
                                    ctx,
                                    last_stop_reason="tool_use",
                                    pending_tool_names=pending_names,
                                )
                                if (
                                    hitl_decision.action == TerminationAction.ASK_USER
                                    and "hitl_confirm" in (hitl_decision.reason or "")
                                ):
                                    # 通知前端显示确认弹窗
                                    yield {
                                        "type": "hitl_confirm",
                                        "data": {
                                            "reason": hitl_decision.reason,
                                            "tools": pending_names,
                                            "message": "危险操作需用户确认",
                                        },
                                    }

                                    # 等待用户决策（approve / reject）
                                    wait_fn = (context.extra or {}).get(
                                        "wait_hitl_confirm_async"
                                    )
                                    if callable(wait_fn):
                                        user_choice = await wait_fn()
                                        if user_choice == "approve":
                                            logger.info(
                                                f"HITL 已批准: {pending_names}"
                                            )
                                            # 用户批准 → 继续执行工具
                                        else:
                                            # 用户拒绝 → 执行 on_rejection 策略
                                            logger.info(
                                                f"HITL 已拒绝: {pending_names}，"
                                                f"执行回退策略"
                                            )
                                            hitl_rejected = True
                                            async for evt in self._handle_hitl_rejection(
                                                context, ctx, cfg
                                            ):
                                                yield evt
                                            break
                                    else:
                                        # 无等待函数，保守停止（不执行危险操作）
                                        logger.warning(
                                            "HITL 确认: 无 wait 函数，"
                                            "保守停止（不执行危险操作）"
                                        )
                                        ctx.stop_reason = (
                                            hitl_decision.reason or "hitl_confirm"
                                        )
                                        break
                            except Exception as e:
                                logger.warning(
                                    f"HITL 检查异常，继续执行: {e}",
                                    exc_info=True,
                                )

                        if hitl_rejected:
                            break

                        # 处理工具调用（V10.2: 使用 ToolExecutionFlow）
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
                            state_manager=state_manager,
                        ):
                            yield event
                    else:
                        # 没有工具调用，任务完成
                        ctx.set_completed(response.content, response.stop_reason)
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
                    break

                # 处理工具调用（非流式）
                async for _ in self._handle_tool_calls(
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
                    state_manager=state_manager,
                ):
                    pass  # 非流式不 yield 事件

            turn += 1

            if ctx.is_completed():
                break

            # 终止策略：完全由 AdaptiveTerminator 信号驱动（无硬性 max_turns）
            if cfg.terminator and not ctx.is_completed():
                try:
                    from core.termination.protocol import TerminationAction

                    last_reason = (
                        getattr(ctx.last_llm_response, "stop_reason", None)
                        if ctx.last_llm_response
                        else None
                    )
                    # V11: 传入 stop_requested（外部停止信号）
                    _stop_requested = (
                        context.stop_event.is_set() if context.stop_event else False
                    )
                    decision = cfg.terminator.evaluate(
                        ctx,
                        last_stop_reason=last_reason,
                        stop_requested=_stop_requested,
                        pending_tool_names=None,
                    )
                    if decision.should_stop:
                        ctx.stop_reason = decision.reason or "terminator"
                        # V11.1: 连续失败 → 推送回滚选项（事件类型对齐前端）
                        if decision.action == TerminationAction.ROLLBACK_OPTIONS:
                            _state_mgr = (context.extra or {}).get("state_manager")
                            _options = (
                                _state_mgr.get_rollback_options(session_id)
                                if _state_mgr
                                else []
                            )
                            yield {
                                "type": "rollback_options",
                                "data": {
                                    "task_id": session_id,
                                    "options": _options,
                                    "reason": decision.reason,
                                },
                            }
                        break
                    # 长任务确认：yield 事件后等待用户点击「继续」
                    if (
                        decision.action == TerminationAction.ASK_USER
                        and decision.reason == "long_running_confirm"
                    ):
                        wait_fn = (context.extra or {}).get("wait_long_run_confirm_async")
                        if callable(wait_fn):
                            yield {
                                "type": "long_running_confirm",
                                "data": {
                                    "turn": ctx.current_turn,
                                    "message": f"任务已执行 {ctx.current_turn} 轮，是否继续？",
                                },
                            }
                            await wait_fn()
                            cfg.terminator.confirm_long_running()
                except Exception as e:
                    logger.warning(
                        f"terminator.evaluate() 异常，继续执行: {e}",
                        exc_info=True,
                    )

        logger.info(f"✅ RVRExecutor 执行完成: turns={ctx.current_turn}")

    # ==================== HITL 拒绝处理（V11.1）====================

    async def _handle_hitl_rejection(
        self,
        context: ExecutionContext,
        ctx: "RuntimeContext",
        cfg: ExecutorConfig,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户拒绝 HITL 确认后的回退策略

        根据 HITLConfig.on_rejection 配置执行：
        - "rollback": 自动回滚到任务快照
        - "stop": 直接停止，不回滚
        - "ask_rollback": 推送回滚选项，让用户决定是否回滚

        Args:
            context: 执行上下文
            ctx: 运行时上下文
            cfg: 执行器配置
        """
        session_id = context.session_id
        state_mgr = (context.extra or {}).get("state_manager")

        # 读取 on_rejection 策略
        on_rejection = "ask_rollback"  # 默认：询问用户
        if (
            cfg.terminator
            and hasattr(cfg.terminator, "config")
            and hasattr(cfg.terminator.config, "hitl")
        ):
            on_rejection = getattr(
                cfg.terminator.config.hitl, "on_rejection", "ask_rollback"
            )

        logger.info(
            f"HITL 拒绝处理: on_rejection={on_rejection}, session={session_id}"
        )

        if on_rejection == "rollback" and state_mgr:
            # 自动回滚
            snapshot_id = state_mgr.get_snapshot_for_task(session_id)
            if snapshot_id:
                rollback_msgs = state_mgr.rollback(snapshot_id)
                logger.info(f"HITL 拒绝 → 自动回滚完成: {rollback_msgs}")
                yield {
                    "type": "rollback_completed",
                    "data": {
                        "task_id": session_id,
                        "messages": rollback_msgs,
                        "trigger": "hitl_rejection",
                    },
                }
            else:
                logger.warning("HITL 拒绝 → 回滚失败: 未找到快照")
            ctx.stop_reason = "hitl_rejected_rollback"

        elif on_rejection == "ask_rollback":
            # 推送回滚选项给前端，让用户决定
            options = (
                state_mgr.get_rollback_options(session_id) if state_mgr else []
            )
            yield {
                "type": "rollback_options",
                "data": {
                    "task_id": session_id,
                    "options": options,
                    "reason": "用户拒绝危险操作",
                },
            }
            ctx.stop_reason = "hitl_rejected_ask_rollback"

        else:
            # "stop" 或未知策略 → 直接停止
            ctx.stop_reason = "hitl_rejected_stop"

    def _validate_plan_creation(self, tool_calls: List[Dict], tracer=None) -> None:
        """
        验证复杂任务是否在第一轮创建 Plan
        """
        first_tool_name = tool_calls[0].get("name", "")
        if first_tool_name == "plan":
            first_action = tool_calls[0].get("input", {}).get("action", "")
            if first_action == "create":
                logger.info("✅ 阶段 5 验证通过: 复杂任务第一个工具调用是 plan(action='create')")
            else:
                logger.warning(f"⚠️ 阶段 5 异常: plan action 不是 create，实际: {first_action}")
        else:
            logger.warning(f"⚠️ 阶段 5 异常: 复杂任务未创建 Plan！第一个工具: {first_tool_name}")
            if tracer:
                tracer.add_warning(f"Plan Creation 跳过: 第一个工具是 {first_tool_name}")


def create_rvr_executor(config: Optional[ExecutorConfig] = None) -> RVRExecutor:
    """创建 RVR 执行器"""
    return RVRExecutor(config=config)
