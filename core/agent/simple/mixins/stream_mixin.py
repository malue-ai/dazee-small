"""
流式处理 Mixin

职责：
- 处理流式 LLM 响应
- 管理 content block 状态
- 处理最后一轮工具调用

依赖的属性（由具体 Agent 类提供）：
- llm: LLMService
- broadcaster: EventBroadcaster
- usage_tracker: UsageTracker
"""

from typing import Dict, Any, List, AsyncGenerator, TYPE_CHECKING

from logger import get_logger
from core.agent.simple.errors import create_timeout_tool_results
from utils.message_utils import append_assistant_message, append_user_message

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext

logger = get_logger(__name__)


class StreamProcessingMixin:
    """
    流式处理 Mixin
    
    提供流式 LLM 响应处理的通用实现。
    """
    
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
            
            # 处理 content
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
    
    async def _handle_last_turn_tools(
        self,
        response,
        llm_messages: List,
        system_prompt,
        ctx: "RuntimeContext",
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理最后一轮的工具调用（流式模式）
        
        当达到最大轮次但 LLM 仍要调用工具时，
        强制生成文本回复总结当前进度。
        
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
        
        append_assistant_message(llm_messages, response.raw_content)
        
        tool_results = create_timeout_tool_results(response.tool_calls)
        
        user_content = tool_results + [{
            "type": "text",
            "text": "⚠️ 系统提示：已达到最大执行轮次，无法继续执行工具。请直接给用户一个文字回复，总结当前进度和已完成的工作。"
        }]
        append_user_message(llm_messages, user_content)
        
        # 不带工具的最终调用
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
