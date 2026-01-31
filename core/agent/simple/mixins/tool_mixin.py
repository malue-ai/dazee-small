"""
工具执行 Mixin

职责：
- 执行工具调用
- 收集工具结果
- 处理工具错误

依赖的属性（由具体 Agent 类提供）：
- tool_executor: ToolExecutor
- broadcaster: EventBroadcaster
- context_engineering: ContextEngineeringManager
"""

import json
from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING

from logger import get_logger
from core.agent.simple.errors import (
    create_fallback_tool_result,
    record_tool_error,
)
from utils.message_utils import append_assistant_message, append_user_message

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext

logger = get_logger(__name__)


class ToolExecutionMixin:
    """
    工具执行 Mixin
    
    提供工具执行的通用实现。
    具体的错误处理策略由子类通过 `_handle_tool_error` 方法定制。
    """
    
    async def _execute_tools_stream(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx: "RuntimeContext"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行工具（流式模式）
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话 ID
            ctx: RuntimeContext
            
        Yields:
            tool_result 事件
        """
        from core.agent.content_handler import create_content_handler
        
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            # 执行工具（错误处理委托给 _handle_tool_error）
            result_content, is_error = await self._execute_single_tool(
                tool_name, tool_input, tool_id, session_id, ctx
            )
            
            yield await content_handler.emit_block(
                session_id=session_id,
                block_type="tool_result",
                content={
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": is_error
                }
            )
    
    async def _execute_tools(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx: "RuntimeContext"
    ) -> List[Dict]:
        """
        执行工具（非流式模式）
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话 ID
            ctx: RuntimeContext
            
        Returns:
            工具结果列表
        """
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            result_content, is_error = await self._execute_single_tool(
                tool_name, tool_input, tool_id, session_id, ctx
            )
            
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_content,
                "is_error": is_error
            })
        
        return results
    
    async def _execute_single_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_id: str,
        session_id: str,
        ctx: "RuntimeContext"
    ) -> tuple[str, bool]:
        """
        执行单个工具
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入
            tool_id: 工具 ID
            session_id: 会话 ID
            ctx: RuntimeContext
            
        Returns:
            (result_content, is_error): 结果内容和是否错误
        """
        try:
            result = await self.tool_executor.execute(tool_name, tool_input)
            result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            return result_content, False
            
        except Exception as e:
            logger.error(f"❌ 工具执行失败: {tool_name} - {e}")
            
            # 委托给具体实现处理错误
            return await self._handle_tool_error(
                error=e,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_id=tool_id,
                session_id=session_id,
                ctx=ctx
            )
    
    async def _handle_tool_error(
        self,
        error: Exception,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_id: str,
        session_id: str,
        ctx: "RuntimeContext"
    ) -> tuple[str, bool]:
        """
        处理工具执行错误
        
        默认实现：记录错误并返回错误信息。
        子类可以重写此方法实现不同的错误处理策略（如回溯）。
        
        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            tool_id: 工具 ID
            session_id: 会话 ID
            ctx: RuntimeContext
            
        Returns:
            (result_content, is_error): 结果内容和是否错误
        """
        # 记录错误
        if hasattr(self, 'context_engineering') and self.context_engineering:
            record_tool_error(self.context_engineering, tool_name, error, tool_input)
        
        result_content = json.dumps({"error": str(error)}, ensure_ascii=False)
        return result_content, True
    
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
        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
        server_tools = [tc for tc in response.tool_calls if tc.get("type") == "server_tool_use"]
        
        # 日志记录服务端工具
        if server_tools:
            logger.info(f"🌐 服务端工具已执行: {[t.get('name') for t in server_tools]}")
        
        # 执行客户端工具
        if client_tools:
            async for event in self._execute_tools_stream(
                client_tools, session_id, ctx
            ):
                yield event
        
        # 收集 tool_results
        tool_results = self._collect_tool_results(client_tools, session_id)
        
        # 更新消息
        append_assistant_message(llm_messages, response.raw_content)
        
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
        
        append_assistant_message(llm_messages, response.raw_content)
        
        if client_tools:
            tool_results = await self._execute_tools(client_tools, session_id, ctx)
            append_user_message(llm_messages, tool_results)
    
    def _collect_tool_results(
        self,
        client_tools: List[Dict],
        session_id: str
    ) -> List[Dict]:
        """
        从 accumulator 收集工具结果
        
        Args:
            client_tools: 客户端工具列表
            session_id: 会话 ID
            
        Returns:
            工具结果列表
        """
        tool_results = []
        
        if not client_tools:
            return tool_results
        
        accumulator = self.broadcaster.get_accumulator(session_id)
        if accumulator:
            client_tool_ids = {tc.get("id") for tc in client_tools}
            for block in accumulator.all_blocks:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in client_tool_ids:
                    clean_block = {k: v for k, v in block.items() if k != "index"}
                    tool_results.append(clean_block)
        
        # 兜底：确保每个 tool_use 都有对应的 tool_result
        collected_ids = {tr.get("tool_use_id") for tr in tool_results}
        for tc in client_tools:
            tool_id = tc.get("id")
            if tool_id and tool_id not in collected_ids:
                tool_results.append(create_fallback_tool_result(tool_id, tc.get('name')))
        
        return tool_results
