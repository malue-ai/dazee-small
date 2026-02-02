"""
SimpleAgent 工具执行模块

职责：
- 单个工具执行（含 Plan 特判、HITL 处理）
- 并行/串行工具执行核心逻辑
- 流式工具执行 + SSE 事件发送
- 服务端工具事件处理
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING
from logger import get_logger
from core.agent.simple.simple_agent_errors import (
    create_error_tool_result,
    record_tool_error
)

if TYPE_CHECKING:
    from core.context.prompt_manager import PromptManager
    from core.orchestration import E2EPipelineTracer

logger = get_logger(__name__)


class ToolExecutionMixin:
    """
    工具执行 Mixin 类
    
    提供工具执行相关的方法，供 SimpleAgent 混入使用。
    
    依赖的属性（由 SimpleAgent 提供）：
    - event_manager: EventManager
    - tool_executor: ToolExecutor
    - plan_todo_tool: PlanTodoTool
    - _plan_cache: dict
    - _serial_only_tools: set
    - allow_parallel_tools: bool
    - max_parallel_tools: int
    - context_engineering: ContextEngineeringManager
    - broadcaster: EventBroadcaster
    - _tracer: E2EPipelineTracer
    - _current_conversation_id: str
    """
    
    async def _execute_single_tool(
        self,
        tool_call: Dict,
        session_id: str,
        ctx=None
    ) -> Dict[str, Any]:
        """
        执行单个工具（纯执行逻辑，不发送 SSE 事件）
        
        支持所有工具类型：
        - 普通工具：通过 tool_executor 执行
        - plan_todo：特殊处理，更新 plan 缓存
        - request_human_confirmation：HITL 工具，等待用户响应
        
        Args:
            tool_call: 工具调用信息 {id, name, input}
            session_id: 会话ID
            ctx: RuntimeContext（可选，用于 PromptManager）
            
        Returns:
            执行结果字典
        """
        from core.context.prompt_manager import get_prompt_manager
        
        tool_name = tool_call['name']
        tool_input = tool_call['input'] or {}
        tool_id = tool_call['id']
        
        logger.debug(f"🔧 执行工具: {tool_name}")
        
        try:
            # 为工具注入上下文
            session_context = await self.event_manager.storage.get_session_context(session_id)
            tool_input.setdefault("session_id", session_id)
            if session_context.get("user_id"):
                tool_input.setdefault("user_id", session_context.get("user_id"))
            conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
            tool_input.setdefault("conversation_id", conv_id)
            
            # ===== 特殊工具处理 =====
            if tool_name == "plan_todo":
                result = await self._execute_plan_todo(tool_input)
            elif tool_name == "request_human_confirmation":
                result = await self._handle_human_confirmation(
                    tool_input=tool_input,
                    session_id=session_id,
                    tool_id=tool_id
                )
            else:
                # ===== 通用工具执行 =====
                result = await self.tool_executor.execute(tool_name, tool_input)
            
            # 触发 PromptManager
            if ctx:
                get_prompt_manager().on_tool_result(ctx, tool_name=tool_name, result=result)
            
            return {
                "tool_id": tool_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "result": result,
                "is_error": False,
                "error_msg": None
            }
            
        except Exception as e:
            error_msg = f"工具执行失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            
            # 错误保留（Context Engineering）
            record_tool_error(self.context_engineering, tool_name, e, tool_input)
            
            return create_error_tool_result(tool_id, tool_name, e, tool_input)
    
    async def _execute_plan_todo(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 plan_todo 特殊工具
        
        Args:
            tool_input: 工具输入参数
            
        Returns:
            执行结果
        """
        operation = tool_input.get('operation', 'create_plan')
        data = tool_input.get('data', {})
        
        result = await self.plan_todo_tool.execute(
            operation=operation,
            data=data,
            current_plan=self._plan_cache.get("plan")
        )
        
        # 更新 plan 缓存
        if result.get("status") == "success" and "plan" in result:
            self._plan_cache["plan"] = result.get("plan")
            logger.info(f"📋 Plan 操作完成: {operation}")
        
        return result
    
    async def _handle_human_confirmation(
        self,
        tool_input: Dict[str, Any],
        session_id: str,
        tool_id: str
    ) -> Dict[str, Any]:
        """
        处理 HITL（Human-in-the-Loop）确认请求
        
        流程：
        1. 解析工具输入，创建 ConfirmationRequest
        2. 通过 EventBroadcaster 发送 SSE 事件到前端
        3. 等待用户通过 HTTP POST 响应
        4. 返回结果给 Agent
        
        Args:
            tool_input: 工具输入参数
            session_id: 会话ID
            tool_id: 工具调用ID
            
        Returns:
            确认结果
        """
        from core.confirmation_manager import get_confirmation_manager, ConfirmationType
        
        # 1. 解析参数
        question = tool_input.get("question", "")
        confirmation_type_str = tool_input.get("confirmation_type", "yes_no")
        options = tool_input.get("options")
        default_value = tool_input.get("default_value")
        questions = tool_input.get("questions")  # form 类型
        description = tool_input.get("description", "")
        timeout = tool_input.get("timeout", 60)
        
        # 解析确认类型
        try:
            conf_type = ConfirmationType(confirmation_type_str)
        except ValueError:
            conf_type = ConfirmationType.YES_NO
        
        # yes_no 类型使用默认选项
        if conf_type == ConfirmationType.YES_NO and not options:
            options = ["confirm", "cancel"]
        
        # form 类型给更多时间
        if conf_type == ConfirmationType.FORM and timeout == 60:
            timeout = 120
        
        logger.info(f"🤝 HITL 请求: type={confirmation_type_str}, question={question[:50]}...")
        
        # 2. 创建确认请求
        manager = get_confirmation_manager()
        
        metadata = {}
        if description:
            metadata["description"] = description
        if default_value is not None:
            metadata["default_value"] = default_value
        if conf_type == ConfirmationType.FORM:
            metadata["form_type"] = "form"
            metadata["questions"] = questions or []
        
        request = manager.create_request(
            question=question,
            options=options,
            timeout=timeout,
            confirmation_type=conf_type,
            session_id=session_id,
            metadata=metadata
        )
        
        logger.info(f"✅ 确认请求已创建: request_id={request.request_id}")
        
        # 3. 发送 SSE 事件到前端
        await self.broadcaster.emit_confirmation_request(
            session_id=session_id,
            request_id=request.request_id,
            question=question,
            options=options,
            confirmation_type=confirmation_type_str,
            timeout=timeout,
            description=description,
            questions=questions if conf_type == ConfirmationType.FORM else None,
            metadata=metadata
        )
        
        # 4. 等待用户响应
        result = await manager.wait_for_response(request.request_id, timeout)
        
        # 5. 处理结果
        if result.get("timed_out"):
            logger.warning(f"⏰ 用户响应超时 ({timeout}s)")
            return {
                "success": False,
                "timed_out": True,
                "response": "timeout",
                "message": f"用户未在 {timeout} 秒内响应"
            }
        
        response = result.get("response")
        
        # form 类型：尝试解析 JSON
        if conf_type == ConfirmationType.FORM and isinstance(response, str):
            try:
                import json as json_module
                response = json_module.loads(response)
            except json.JSONDecodeError:
                logger.warning(f"无法解析 form 响应为 JSON: {response[:100] if response else ''}")
        
        logger.info(f"✅ 用户已响应: {type(response).__name__}")
        
        return {
            "success": True,
            "timed_out": False,
            "response": response,
            "metadata": result.get("metadata", {})
        }
    
    async def _execute_tools_core(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx=None
    ) -> Dict[str, Dict[str, Any]]:
        """
        执行工具的核心逻辑（支持并行执行，不发送 SSE 事件）
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话ID
            ctx: RuntimeContext（可选）
            
        Returns:
            {tool_id: result_dict} 映射
        """
        # 分离可并行的工具和必须串行的特殊工具
        parallel_tools = []
        serial_tools = []
        
        for tc in tool_calls:
            tool_name = tc.get('name', '')
            if tool_name in self._serial_only_tools:
                serial_tools.append(tc)
            else:
                parallel_tools.append(tc)
        
        results = {}
        
        # ===== 并行执行可并行的工具 =====
        if parallel_tools and self.allow_parallel_tools and len(parallel_tools) > 1:
            logger.info(f"⚡ 并行执行 {len(parallel_tools)} 个工具: {[t['name'] for t in parallel_tools]}")
            
            # 限制并行数量
            tools_to_execute = parallel_tools[:self.max_parallel_tools]
            if len(parallel_tools) > self.max_parallel_tools:
                serial_tools = parallel_tools[self.max_parallel_tools:] + serial_tools
                logger.warning(f"⚠️ 超出最大并行数 {self.max_parallel_tools}，部分工具将串行执行")
            
            # 追踪工具调用
            for tc in tools_to_execute:
                if self._tracer:
                    self._tracer.log_tool_call(tc['name'])
            
            # 并行执行
            parallel_results = await asyncio.gather(
                *[self._execute_single_tool(tc, session_id, ctx) for tc in tools_to_execute],
                return_exceptions=True
            )
            
            # 处理结果
            for tc, result in zip(tools_to_execute, parallel_results):
                tool_id = tc['id']
                if isinstance(result, Exception):
                    results[tool_id] = create_error_tool_result(
                        tool_id, tc['name'], result, tc.get('input', {})
                    )
                else:
                    results[tool_id] = result
        else:
            # 不启用并行或只有一个工具，全部串行执行
            serial_tools = parallel_tools + serial_tools
        
        # ===== 串行执行特殊工具 =====
        for tc in serial_tools:
            tool_id = tc['id']
            
            # 追踪工具调用
            if self._tracer:
                self._tracer.log_tool_call(tc['name'])
            
            results[tool_id] = await self._execute_single_tool(tc, session_id, ctx)
        
        return results
    
    async def _execute_tools_stream(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行工具调用并发送 SSE 事件（统一入口）
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话ID
            ctx: RuntimeContext
            
        Yields:
            content_start, content_delta, content_stop 等事件
        """
        from core.agent.content_handler import create_content_handler
        from core.context.prompt_manager import get_prompt_manager
        
        # 创建 ContentHandler
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        # 分离流式工具和普通工具
        stream_tools = []
        normal_tools = []
        
        for tc in tool_calls:
            tool_name = tc.get('name', '')
            if tool_name in self._serial_only_tools or self.tool_executor.supports_stream(tool_name):
                stream_tools.append(tc)
            else:
                normal_tools.append(tc)
        
        # ===== 先执行可并行的普通工具 =====
        normal_results = {}
        if normal_tools:
            normal_results = await self._execute_tools_core(normal_tools, session_id, ctx)
        
        # ===== 按原始顺序发送事件 =====
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            # 已执行的普通工具
            if tool_id in normal_results:
                result_info = normal_results[tool_id]
                result = result_info.get("result", {})
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                
                yield await content_handler.emit_block(
                    session_id=session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.get("is_error", False)
                    }
                )
                continue
            
            # ===== 处理需要特殊处理的工具 =====
            logger.debug(f"🔧 处理工具: {tool_name}")
            
            if self._tracer:
                self._tracer.log_tool_call(tool_name)
            
            if self.tool_executor.supports_stream(tool_name):
                # ===== 流式工具执行 =====
                logger.info(f"🌊 流式执行工具: {tool_name}")
                
                # 注入上下文
                session_context = await self.event_manager.storage.get_session_context(session_id)
                tool_input.setdefault("session_id", session_id)
                if session_context.get("user_id"):
                    tool_input.setdefault("user_id", session_context.get("user_id"))
                conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
                tool_input.setdefault("conversation_id", conv_id)
                
                async def stream_generator():
                    async for chunk in self.tool_executor.execute_stream(tool_name, tool_input):
                        yield chunk
                
                async for event in content_handler.emit_block_stream(
                    session_id=session_id,
                    block_type="tool_result",
                    initial={"tool_use_id": tool_id, "is_error": False},
                    delta_source=stream_generator()
                ):
                    yield event
                
                get_prompt_manager().on_tool_result(ctx, tool_name=tool_name, result={"streamed": True})
            else:
                # ===== 串行工具执行 =====
                result_info = await self._execute_single_tool(tool_call, session_id, ctx)
                result = result_info.get("result", {})
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                
                yield await content_handler.emit_block(
                    session_id=session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.get("is_error", False)
                    }
                )
    
    async def _emit_server_tool_blocks_stream(
        self,
        raw_content: List[Dict],
        session_id: str,
        ctx
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送服务端工具（如 web_search）的事件到前端
        
        服务端工具的特点：
        - 由 Anthropic 服务器执行
        - 类型为 server_tool_use 和 *_tool_result
        
        前端接口统一使用 tool_use / tool_result
        
        Args:
            raw_content: LLM 响应的原始内容块列表
            session_id: 会话ID
            ctx: RuntimeContext
            
        Yields:
            content_start, content_stop 等事件
        """
        from core.agent.content_handler import create_content_handler
        
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        for block in raw_content:
            block_type = block.get("type", "")
            
            # server_tool_use → tool_use
            if block_type == "server_tool_use":
                yield await content_handler.emit_block(
                    session_id=session_id,
                    block_type="tool_use",
                    content={
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": block.get("input", {})
                    }
                )
                logger.debug(f"🌐 发送服务端工具调用事件: {block.get('name')}")
            
            # *_tool_result → tool_result
            elif block_type.endswith("_tool_result") and block_type != "tool_result":
                content = block.get("content", [])
                content_str = self._format_server_tool_result(content)
                
                yield await content_handler.emit_block(
                    session_id=session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": content_str,
                        "is_error": False
                    }
                )
                logger.debug(f"🌐 发送服务端工具结果事件: {block_type}")
    
    def _format_server_tool_result(self, content) -> str:
        """
        格式化服务端工具结果内容
        
        Args:
            content: 原始内容（可能是列表或字符串）
            
        Returns:
            格式化后的字符串
        """
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "web_search_result":
                        title = item.get("title", "")
                        url = item.get("url", "")
                        text_parts.append(f"[{title}]({url})")
                elif hasattr(item, 'model_dump'):
                    # Pydantic v2 对象
                    dumped = item.model_dump()
                    if dumped.get("type") == "text":
                        text_parts.append(dumped.get("text", ""))
                    elif dumped.get("type") == "web_search_result":
                        title = dumped.get("title", "")
                        url = dumped.get("url", "")
                        text_parts.append(f"[{title}]({url})")
                    else:
                        text_parts.append(str(dumped))
                elif hasattr(item, 'to_dict'):
                    text_parts.append(str(item.to_dict()))
                else:
                    text_parts.append(str(item))
            return "\n".join(text_parts) if text_parts else "[服务端工具结果]"
        else:
            return str(content)
    
    async def _execute_tools(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx
    ) -> List[Dict]:
        """
        执行工具调用（非流式模式，返回结果列表）
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话ID
            ctx: RuntimeContext
            
        Returns:
            工具结果列表
        """
        from core.agent.content_handler import create_content_handler
        
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        results = []
        
        # 追踪工具调用
        for tc in tool_calls:
            if self._tracer:
                self._tracer.log_tool_call(tc['name'])
        
        # 发送所有 tool_use 事件
        for tool_call in tool_calls:
            tool_id = tool_call['id']
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            
            await content_handler.emit_block(
                session_id=session_id,
                block_type="tool_use",
                content={
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_input
                }
            )
        
        # 执行所有工具
        execution_results = await self._execute_tools_core(tool_calls, session_id, ctx)
        
        # 发送 tool_result 事件
        for tool_call in tool_calls:
            tool_id = tool_call['id']
            result_info = execution_results.get(tool_id, {})
            result = result_info.get("result", {})
            result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            is_error = result_info.get("is_error", False)
            
            await content_handler.emit_block(
                session_id=session_id,
                block_type="tool_result",
                content={
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": is_error
                }
            )
            
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_content,
                "is_error": is_error
            })
            
            logger.debug(f"{'✅' if not is_error else '❌'} 工具执行{'成功' if not is_error else '失败'}: {tool_call['name']}")
        
        return results
