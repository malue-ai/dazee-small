"""
SimpleAgent RVR 循环模块

职责：
- RVR（Read-Reason-Act-Observe-Validate-Write-Repeat）主循环
- 流式 LLM 响应处理
- 消息构建和更新
"""

import json
from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING
from logger import get_logger
from core.agent.simple.simple_agent_errors import (
    create_timeout_tool_results,
    create_fallback_tool_result
)
from utils.message_utils import (
    dict_list_to_messages,
    append_assistant_message,
    append_user_message
)

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext
    from core.agent.content_handler import ContentHandler

logger = get_logger(__name__)


class RVRLoopMixin:
    """
    RVR 循环 Mixin 类
    
    提供 RVR 主循环相关的方法，供 SimpleAgent 混入使用。
    
    依赖的属性（由 SimpleAgent 提供）：
    - llm: LLMService
    - max_turns: int
    - broadcaster: EventBroadcaster
    - usage_tracker: UsageTracker
    - _tracer: E2EPipelineTracer
    - context_engineering: ContextEngineeringManager
    - _plan_cache: dict
    """
    
    async def _run_rvr_loop(
        self,
        messages: List,
        system_prompt,
        tools_for_llm: List,
        ctx: "RuntimeContext",
        session_id: str,
        intent,
        enable_stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        RVR 主循环
        
        Read-Reason-Act-Observe-Validate-Write-Repeat
        
        Args:
            messages: 初始消息列表（dict 格式）
            system_prompt: 系统提示词
            tools_for_llm: LLM 工具列表
            ctx: RuntimeContext
            session_id: 会话 ID
            intent: IntentResult
            enable_stream: 是否启用流式
            
        Yields:
            事件字典
        """
        # 转换消息为 Message 对象
        llm_messages = dict_list_to_messages(messages)
        
        # Todo 重写（Context Engineering）
        if self.context_engineering and self._plan_cache.get("plan"):
            prepared_messages = self.context_engineering.prepare_messages_for_llm(
                messages=[{"role": m.role, "content": m.content} for m in llm_messages],
                plan=self._plan_cache.get("plan"),
                inject_plan=True,
                inject_errors=True
            )
            llm_messages = dict_list_to_messages(prepared_messages)
            logger.debug("✅ Context Engineering: Todo 重写完成，Plan 状态已注入消息末尾")
        
        for turn in range(self.max_turns):
            ctx.next_turn()
            logger.info(f"{'='*60}")
            logger.info(f"🔄 Turn {turn + 1}/{self.max_turns}")
            logger.info(f"{'='*60}")
            
            if enable_stream:
                # 流式处理
                async for event in self._process_stream(
                    llm_messages, system_prompt, tools_for_llm, ctx, session_id
                ):
                    yield event
                
                response = ctx.last_llm_response
                if response:
                    # 阶段 5 验证：检查复杂任务是否创建 Plan
                    if turn == 0 and intent.needs_plan and response.tool_calls:
                        self._validate_plan_creation(response.tool_calls)
                    
                    # 处理工具调用
                    if response.stop_reason == "tool_use" and response.tool_calls:
                        # 最后一轮检查
                        is_last_turn = (turn == self.max_turns - 1)
                        if is_last_turn:
                            async for event in self._handle_last_turn_tools(
                                response, llm_messages, system_prompt, ctx, session_id
                            ):
                                yield event
                            break
                        
                        # 处理工具调用
                        async for event in self._handle_tool_calls(
                            response, llm_messages, session_id, ctx
                        ):
                            yield event
                    else:
                        # 没有工具调用，任务完成
                        ctx.set_completed(response.content, response.stop_reason)
                        break
            else:
                # 非流式处理
                response = await self.llm.create_message_async(
                    messages=llm_messages,
                    system=system_prompt,
                    tools=tools_for_llm
                )
                
                self.usage_tracker.accumulate(response)
                
                if response.content:
                    yield {"type": "content", "data": {"text": response.content}}
                
                if response.stop_reason != "tool_use":
                    ctx.set_completed(response.content, response.stop_reason)
                    break
                
                # 最后一轮检查
                is_last_turn = (turn == self.max_turns - 1)
                if is_last_turn:
                    async for event in self._handle_last_turn_tools_non_stream(
                        response, llm_messages, system_prompt, ctx, session_id
                    ):
                        yield event
                    break
                
                # 处理工具调用（非流式）
                await self._handle_tool_calls_non_stream(
                    response, llm_messages, session_id, ctx
                )
            
            if ctx.is_completed():
                break
    
    def _validate_plan_creation(self, tool_calls: List[Dict]) -> None:
        """
        验证复杂任务是否在第一轮创建 Plan
        
        Args:
            tool_calls: 工具调用列表
        """
        first_tool_name = tool_calls[0].get('name', '')
        if first_tool_name == 'plan_todo':
            first_operation = tool_calls[0].get('input', {}).get('operation', '')
            if first_operation == 'create_plan':
                logger.info("✅ 阶段 5 验证通过: 复杂任务第一个工具调用是 plan_todo.create_plan()")
            else:
                logger.warning(f"⚠️ 阶段 5 异常: plan_todo 操作不是 create_plan，实际: {first_operation}")
        else:
            logger.warning(f"⚠️ 阶段 5 异常: 复杂任务未创建 Plan！第一个工具: {first_tool_name}")
            if self._tracer:
                self._tracer.add_warning(f"Plan Creation 跳过: 第一个工具是 {first_tool_name}")
    
    async def _handle_last_turn_tools(
        self,
        response,
        llm_messages: List,
        system_prompt,
        ctx: "RuntimeContext",
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理最后一轮的工具调用（强制生成文本回复）
        
        Args:
            response: LLM 响应
            llm_messages: 消息列表
            system_prompt: 系统提示词
            ctx: RuntimeContext
            session_id: 会话 ID
            
        Yields:
            事件字典
        """
        logger.warning(f"⚠️ 最后一轮收到工具调用，强制生成文本回复...")
        
        # 添加当前响应
        append_assistant_message(llm_messages, response.raw_content)
        
        # 为每个 tool_use 提供 tool_result
        tool_results = create_timeout_tool_results(response.tool_calls)
        
        # 添加 tool_result + 系统提示
        user_content = tool_results + [{
            "type": "text",
            "text": "⚠️ 系统提示：已达到最大执行轮次，无法继续执行工具。请直接给用户一个文字回复，总结当前进度和已完成的工作。"
        }]
        append_user_message(llm_messages, user_content)
        
        # 再调用一次 LLM，不传递 tools
        async for event in self._process_stream(
            llm_messages, system_prompt, [], ctx, session_id
        ):
            yield event
        
        final_response = ctx.last_llm_response
        if final_response:
            ctx.set_completed(final_response.content, "max_turns_reached")
    
    async def _handle_last_turn_tools_non_stream(
        self,
        response,
        llm_messages: List,
        system_prompt,
        ctx: "RuntimeContext",
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理最后一轮的工具调用（非流式模式）
        """
        logger.warning(f"⚠️ 最后一轮收到工具调用，强制生成文本回复...")
        
        append_assistant_message(llm_messages, response.raw_content)
        
        tool_results = create_timeout_tool_results(response.tool_calls)
        
        user_content = tool_results + [{
            "type": "text",
            "text": "⚠️ 系统提示：已达到最大执行轮次，无法继续执行工具。请直接给用户一个文字回复，总结当前进度和已完成的工作。"
        }]
        append_user_message(llm_messages, user_content)
        
        final_response = await self.llm.create_message_async(
            messages=llm_messages,
            system=system_prompt,
            tools=[]
        )
        self.usage_tracker.accumulate(final_response)
        
        if final_response.content:
            yield {"type": "content", "data": {"text": final_response.content}}
        
        ctx.set_completed(final_response.content, "max_turns_reached")
    
    async def _handle_tool_calls(
        self,
        response,
        llm_messages: List,
        session_id: str,
        ctx: "RuntimeContext"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理工具调用（流式模式）
        
        Args:
            response: LLM 响应
            llm_messages: 消息列表
            session_id: 会话 ID
            ctx: RuntimeContext
            
        Yields:
            事件字典
        """
        # 区分客户端工具和服务端工具
        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
        server_tools = [tc for tc in response.tool_calls if tc.get("type") == "server_tool_use"]
        
        # 发送服务端工具事件
        if server_tools:
            logger.info(f"🌐 服务端工具已执行: {[t.get('name') for t in server_tools]}")
            async for event in self._emit_server_tool_blocks_stream(
                response.raw_content, session_id, ctx
            ):
                yield event
        
        # 执行客户端工具
        if client_tools:
            async for event in self._execute_tools_stream(
                client_tools, session_id, ctx
            ):
                yield event
        
        # 收集 tool_results
        tool_results = []
        if client_tools:
            accumulator = self.broadcaster.get_accumulator(session_id)
            if accumulator:
                client_tool_ids = {tc.get("id") for tc in client_tools}
                for block in accumulator.all_blocks:
                    if block.get("type") == "tool_result" and block.get("tool_use_id") in client_tool_ids:
                        clean_block = {k: v for k, v in block.items() if k != "index"}
                        tool_results.append(clean_block)
        
        # 更新消息
        append_assistant_message(llm_messages, response.raw_content)
        
        # 兜底：确保每个 tool_use 都有对应的 tool_result
        if client_tools:
            collected_ids = {tr.get("tool_use_id") for tr in tool_results}
            for tc in client_tools:
                tool_id = tc.get("id")
                if tool_id and tool_id not in collected_ids:
                    tool_results.append(create_fallback_tool_result(tool_id, tc.get('name')))
        
        if client_tools and tool_results:
            append_user_message(llm_messages, tool_results)
    
    async def _handle_tool_calls_non_stream(
        self,
        response,
        llm_messages: List,
        session_id: str,
        ctx: "RuntimeContext"
    ) -> None:
        """
        处理工具调用（非流式模式）
        """
        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
        server_tools = [tc for tc in response.tool_calls if tc.get("type") == "server_tool_use"]
        
        if server_tools:
            logger.info(f"🌐 服务端工具已执行: {[t.get('name') for t in server_tools]}")
            async for _ in self._emit_server_tool_blocks_stream(
                response.raw_content, session_id, ctx
            ):
                pass
        
        append_assistant_message(llm_messages, response.raw_content)
        
        if client_tools:
            tool_results = await self._execute_tools(client_tools, session_id, ctx)
            append_user_message(llm_messages, tool_results)
    
    async def _process_stream(
        self,
        messages: List,
        system_prompt,
        tools: List,
        ctx: "RuntimeContext",
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理流式 LLM 响应
        
        使用 ContentHandler 的手动控制模式处理 LLM 的流式输出
        
        Args:
            messages: 消息列表
            system_prompt: 系统提示词
            tools: 工具列表
            ctx: RuntimeContext
            session_id: 会话 ID
            
        Yields:
            事件字典
        """
        from core.agent.content_handler import create_content_handler
        
        # 创建 ContentHandler
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        stream_generator = self.llm.create_message_stream(
            messages=messages,
            system=system_prompt,
            tools=tools
        )
        
        final_response = None
        
        async for llm_response in stream_generator:
            # 处理 thinking
            if llm_response.thinking and llm_response.is_stream:
                if content_handler.needs_transition("thinking"):
                    yield await content_handler.start_block(
                        session_id=session_id,
                        block_type="thinking",
                        initial={"thinking": ""}
                    )
                
                yield await content_handler.send_delta(
                    session_id=session_id,
                    delta=llm_response.thinking
                )
            
            # 处理 content（text）
            if llm_response.content and llm_response.is_stream:
                if content_handler.needs_transition("text"):
                    yield await content_handler.start_block(
                        session_id=session_id,
                        block_type="text",
                        initial={"text": ""}
                    )
                
                yield await content_handler.send_delta(
                    session_id=session_id,
                    delta=llm_response.content
                )
            
            # 处理 tool_use 开始
            if llm_response.tool_use_start and llm_response.is_stream:
                tool_info = llm_response.tool_use_start
                tool_type = tool_info.get("type", "tool_use")
                
                yield await content_handler.start_block(
                    session_id=session_id,
                    block_type=tool_type,
                    initial={
                        "id": tool_info.get("id", ""),
                        "name": tool_info.get("name", ""),
                        "input": {}
                    }
                )
            
            # 处理 tool_use 参数增量
            if llm_response.input_delta and llm_response.is_stream:
                yield await content_handler.send_delta(
                    session_id=session_id,
                    delta=llm_response.input_delta
                )
            
            # 保存最终响应
            if not llm_response.is_stream:
                final_response = llm_response
        
        # 关闭最后一个 block
        if content_handler.is_block_open():
            yield await content_handler.stop_block(session_id=session_id)
        
        # 保存最终响应到 ctx
        if final_response:
            self.usage_tracker.accumulate(final_response)
            ctx.last_llm_response = final_response
