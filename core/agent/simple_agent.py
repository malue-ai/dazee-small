"""
SimpleAgent - 精简版核心 Agent

职责：
- 只做编排（Orchestrator）
- 协调各个独立模块完成任务
- 实现 RVR（Read-Reason-Act-Observe-Validate-Write-Repeat）循环

设计原则：
- 单一职责：只负责编排，不包含业务逻辑
- 依赖注入：所有依赖通过构造函数注入
- 可测试：模块独立，便于单元测试

架构：
┌─────────────────────────────────────────┐
│              SimpleAgent                │
│  ┌─────────────┐  ┌─────────────────┐  │
│  │IntentAnalyzer│  │  ToolSelector   │  │
│  └─────────────┘  └─────────────────┘  │
│  ┌─────────────┐  ┌─────────────────┐  │
│  │ EventManager │  │  ToolExecutor   │  │
│  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────┘
"""

# 1. 标准库
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator

# 2. 第三方库（无）

# 3. 本地模块（延迟导入，避免循环依赖）

logger = logging.getLogger(__name__)


class SimpleAgent:
    """
    精简版 Agent - 编排层
    
    只负责协调各模块，不包含具体业务逻辑
    
    使用方式：
        agent = SimpleAgent(event_manager=event_manager)
        async for event in agent.chat(user_input, session_id=session_id):
            yield event
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        max_turns: int = 20,
        event_manager=None,
        workspace_dir: str = None
    ):
        """
        初始化 Agent
        
        Args:
            model: 模型名称
            max_turns: 最大轮次
            event_manager: EventManager 实例（必需）
            workspace_dir: 工作目录
        """
        if event_manager is None:
            raise ValueError("event_manager 是必需参数")
        
        self.model = model
        self.max_turns = max_turns
        self.event_manager = event_manager
        self.workspace_dir = workspace_dir
        
        # ===== 初始化各模块 =====
        self._init_modules()
        
        # ===== 状态 =====
        self.plan_state = {"plan": None, "todo": None, "tool_calls": []}
        self.invocation_stats = {"direct": 0, "code_execution": 0, "programmatic": 0, "streaming": 0}
        
        logger.info(f"✅ SimpleAgent 初始化完成 (model={model})")
    
    def _init_modules(self):
        """初始化各独立模块"""
        # 1. 能力注册表
        from core.tool.capability import create_capability_registry
        self.capability_registry = create_capability_registry()
        
        # 2. 意图分析器（使用 Haiku）
        from core.agent.intent_analyzer import create_intent_analyzer
        from core.llm import create_claude_service
        
        self.intent_llm = create_claude_service(
            model="claude-3-5-haiku-20241022",  # 营销名 "Haiku 4.5" 的正确 API ID
            enable_thinking=False,
            enable_caching=False,
            tools=[]
        )
        self.intent_analyzer = create_intent_analyzer(
            llm_service=self.intent_llm,
            enable_llm=True
        )
        
        # 3. 工具选择器
        from core.tool import create_tool_selector
        self.tool_selector = create_tool_selector(registry=self.capability_registry)
        
        # 4. 工具执行器
        from core.tool import create_tool_executor
        
        tool_context = {
            "event_manager": self.event_manager,
            "workspace_dir": self.workspace_dir
        }
        self.tool_executor = create_tool_executor(
            self.capability_registry,
            tool_context=tool_context
        )
        
        # 5. Plan/Todo 工具（纯计算，不持有状态）
        from tools.plan_todo_tool import create_plan_todo_tool
        self.plan_todo_tool = create_plan_todo_tool(registry=self.capability_registry)
        
        # 6. 执行 LLM（Sonnet）
        from core.llm import ToolType
        self.llm = create_claude_service(
            model=self.model,
            enable_thinking=True,
            enable_caching=False,
            tools=[ToolType.BASH, ToolType.TEXT_EDITOR, ToolType.WEB_SEARCH]
        )
        
        # 注册自定义工具到 LLM（必须在 plan_todo_tool 初始化之后）
        self._register_tools_to_llm()
    
    def _register_tools_to_llm(self):
        """注册工具到 LLM Service"""
        tool_schemas = self.capability_registry.get_tool_schemas()
        for schema in tool_schemas:
            if schema['name'] == 'plan_todo':
                schema['input_schema'] = self.plan_todo_tool.get_input_schema()
            
            self.llm.add_custom_tool(
                name=schema['name'],
                description=schema['description'],
                input_schema=schema['input_schema']
            )
    
    async def chat(
        self,
        user_input: Any,
        history_messages: List[Dict[str, str]] = None,
        session_id: str = None,
        enable_stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Agent 统一执行入口
        
        编排流程：
        1. 意图分析 → IntentAnalyzer
        2. 工具选择 → ToolSelector
        3. RVR 循环 → LLM + ToolExecutor
        4. 事件发射 → EventManager
        
        Args:
            user_input: 用户输入
            history_messages: 历史消息
            session_id: 会话ID
            enable_stream: 是否流式输出
            
        Yields:
            事件字典
        """
        from core.context.runtime import create_runtime_context
        from core.llm import Message, LLMResponse
        
        history_messages = history_messages or []
        
        # 生成 session_id
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.warning(f"未提供 session_id，生成临时 ID: {session_id}")
        
        # ===== 1. 意图分析 =====
        logger.info("🎯 开始意图分析...")
        intent = await self.intent_analyzer.analyze(user_input)
        
        # 获取执行配置
        exec_config = self.intent_analyzer.get_execution_config(intent)
        system_prompt = exec_config.system_prompt
        
        # ===== 2. 工具选择 =====
        logger.info("🔧 开始工具选择...")
        
        # 确定所需能力
        plan = self.plan_state.get("plan")
        if plan and plan.get('required_capabilities'):
            required_capabilities = plan['required_capabilities']
        else:
            required_capabilities = self.capability_registry.get_capabilities_for_task_type(
                intent.task_type.value
            )
        
        # 获取可用 API
        available_apis = self.tool_selector.get_available_apis(self.tool_executor)
        
        # 选择工具
        selection = self.tool_selector.select(
            required_capabilities=required_capabilities,
            context={
                "plan": plan,
                "task_type": intent.task_type.value,
                "available_apis": available_apis
            }
        )
        
        # 转换为 LLM 格式
        tools_for_llm = self.tool_selector.get_tools_for_llm(selection, self.llm)
        
        logger.info(f"📋 选择工具: {selection.tool_names}")
        
        # ===== 3. 构建消息 =====
        messages = []
        for msg in history_messages:
            messages.append(Message(role=msg["role"], content=msg["content"]))
        messages.append(Message(role="user", content=user_input))
        
        # ===== 4. RVR 循环 =====
        ctx = create_runtime_context(session_id=session_id, max_turns=self.max_turns)
        
        for turn in range(self.max_turns):
            ctx.next_turn()
            logger.info(f"{'='*60}")
            logger.info(f"🔄 Turn {turn + 1}/{self.max_turns}")
            logger.info(f"{'='*60}")
            
            # 调用 LLM
            if enable_stream:
                async for event in self._process_stream(
                    messages, system_prompt, tools_for_llm, ctx, session_id
                ):
                    yield event
                    
                    # 检查是否有工具调用需要处理
                    if event.get("type") == "llm_response_complete":
                        response = event.get("data", {}).get("response")
                        if response:
                            # 处理工具调用
                            if response.stop_reason == "tool_use" and response.tool_calls:
                                # 执行工具（yield 出所有 tool_use/tool_result 事件）
                                tool_results = []
                                async for tool_event in self._execute_tools_stream(
                                    response.tool_calls, session_id, ctx
                                ):
                                    # yield 工具事件给 ChatEventHandler
                                    yield tool_event
                                    # 收集工具结果（最后一个事件包含结果）
                                    if tool_event.get("type") == "tool_execution_complete":
                                        tool_results = tool_event.get("data", {}).get("results", [])
                                
                                # 更新消息（用于下一轮 LLM 调用）
                                messages.append(Message(role="assistant", content=response.raw_content))
                                messages.append(Message(role="user", content=tool_results))
                            else:
                                # 没有工具调用，任务完成
                                ctx.set_completed(response.content, response.stop_reason)
                                break
            else:
                # 非流式模式
                response = await self.llm.create_message_async(
                    messages=messages,
                    system=system_prompt,
                    tools=tools_for_llm
                )
                
                if response.content:
                    yield {"type": "content", "data": {"text": response.content}}
                
                if response.stop_reason != "tool_use":
                    ctx.set_completed(response.content, response.stop_reason)
                    break
                
                # 执行工具（非流式模式）
                tool_results = await self._execute_tools(response.tool_calls, session_id, ctx)
                messages.append(Message(role="assistant", content=response.raw_content))
                messages.append(Message(role="user", content=tool_results))
            
            if ctx.is_completed():
                break
        
        # ===== 5. 发送完成事件 =====
        yield await self.event_manager.message.emit_message_stop(session_id=session_id)
        logger.info(f"✅ Agent 执行完成: turns={ctx.current_turn}")
    
    async def _process_stream(
        self,
        messages: List,
        system_prompt: str,
        tools: List,
        ctx,
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理流式 LLM 响应
        
        委托给 EventManager 处理事件发射
        """
        from core.llm import LLMResponse
        
        stream_generator = self.llm.create_message_stream(
            messages=messages,
            system=system_prompt,
            tools=tools
        )
        
        final_response = None
        
        async for llm_response in stream_generator:
            # 处理 thinking
            if llm_response.thinking and llm_response.is_stream:
                if ctx.block.needs_transition("thinking"):
                    if ctx.block.is_block_open():
                        yield await self.event_manager.content.emit_content_stop(
                            session_id=session_id,
                            index=ctx.block.current_index
                        )
                    
                    block_idx = ctx.block.start_new_block("thinking")
                    yield await self.event_manager.content.emit_content_start(
                        session_id=session_id,
                        index=block_idx,
                        content_block={"type": "thinking", "thinking": ""}
                    )
                
                yield await self.event_manager.content.emit_content_delta(
                    session_id=session_id,
                    index=ctx.block.current_index,
                    delta={"type": "thinking_delta", "thinking": llm_response.thinking}
                )
                ctx.stream.append_thinking(llm_response.thinking)
            
            # 处理 content
            if llm_response.content and llm_response.is_stream:
                if ctx.block.needs_transition("text"):
                    if ctx.block.is_block_open():
                        yield await self.event_manager.content.emit_content_stop(
                            session_id=session_id,
                            index=ctx.block.current_index
                        )
                    
                    block_idx = ctx.block.start_new_block("text")
                    yield await self.event_manager.content.emit_content_start(
                        session_id=session_id,
                        index=block_idx,
                        content_block={"type": "text", "text": ""}
                    )
                
                yield await self.event_manager.content.emit_content_delta(
                    session_id=session_id,
                    index=ctx.block.current_index,
                    delta={"type": "text_delta", "text": llm_response.content}
                )
                ctx.stream.append_content(llm_response.content)
            
            # 保存最终响应
            if not llm_response.is_stream:
                final_response = llm_response
        
        # 关闭最后一个 block
        if ctx.block.is_block_open():
            yield await self.event_manager.content.emit_content_stop(
                session_id=session_id,
                index=ctx.block.current_index
            )
        
        # 返回最终响应
        if final_response:
            yield {
                "type": "llm_response_complete",
                "data": {"response": final_response}
            }
    
    async def _execute_tools_stream(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx  # RuntimeContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行工具调用（流式版本，yield 出所有事件）
        
        这个方法会 yield 出 content_start/content_delta/content_stop 事件，
        让 ChatEventHandler 能收集 tool_use 和 tool_result 信息。
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话ID
            ctx: RuntimeContext
            
        Yields:
            content_start, content_delta, content_stop 等事件
        """
        import json
        
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            logger.debug(f"🔧 执行工具: {tool_name}")
            
            # ===== 发送 tool_use content block =====
            # 关闭之前的 block
            if ctx.block.is_block_open():
                yield await self.event_manager.content.emit_content_stop(
                    session_id=session_id,
                    index=ctx.block.current_index
                )
            
            # 发送 tool_use start 事件
            tool_use_index = ctx.block.start_new_block("tool_use")
            tool_use_block = {
                "type": "tool_use",
                "id": tool_id,
                "name": tool_name,
                "input": tool_input
            }
            
            # 发送到 SSE（给前端）并 yield 给 handler（用于持久化）
            yield await self.event_manager.content.emit_content_start(
                session_id=session_id,
                index=tool_use_index,
                content_block=tool_use_block
            )
            
            # 关闭 tool_use block
            yield await self.event_manager.content.emit_content_stop(
                session_id=session_id,
                index=tool_use_index
            )
            ctx.block.close_current_block()
            
            # ===== 执行工具 =====
            try:
                # 特殊处理：plan_todo 工具
                if tool_name == "plan_todo":
                    operation = tool_input.get('operation', 'create_plan')
                    data = tool_input.get('data', {})
                    current_plan = self.plan_state.get("plan")
                    result = await self.plan_todo_tool.execute(
                        operation=operation,
                        data=data,
                        current_plan=current_plan
                    )
                    
                    # 更新 plan_state
                    if result.get("status") == "success" and "plan" in result:
                        new_plan = result.get("plan")
                        self.plan_state["plan"] = new_plan
                        
                        session_context = await self.event_manager.storage.get_session_context(session_id)
                        conversation_id = session_context.get("conversation_id")
                        
                        if operation == "create_plan":
                            await self.event_manager.conversation.emit_conversation_plan_created(
                                session_id=session_id,
                                conversation_id=conversation_id,
                                plan=new_plan
                            )
                            logger.info(f"📋 Plan 已创建: {new_plan.get('goal', '')}")
                        else:
                            await self.event_manager.conversation.emit_conversation_plan_updated(
                                session_id=session_id,
                                conversation_id=conversation_id,
                                plan=new_plan
                            )
                            logger.info(f"📋 Plan 已更新: operation={operation}")
                else:
                    # 🛡️ 为所有工具注入上下文（user_id, session_id, conversation_id）
                    # 工具可以通过 kwargs 获取这些信息
                    session_context = await self.event_manager.storage.get_session_context(session_id)
                    tool_input.setdefault("session_id", session_id)
                    if session_context.get("user_id"):
                        tool_input.setdefault("user_id", session_context.get("user_id"))
                    if session_context.get("conversation_id"):
                        tool_input.setdefault("conversation_id", session_context.get("conversation_id"))
                    
                    # 执行工具
                    result = await self.tool_executor.execute(tool_name, tool_input)
                
                # ===== 发送 tool_result content block =====
                tool_result_index = ctx.block.start_new_block("tool_result")
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": False
                }
                
                # 发送到 SSE 并 yield 给 handler
                yield await self.event_manager.content.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=tool_result_block
                )
                
                yield await self.event_manager.content.emit_content_stop(
                    session_id=session_id,
                    index=tool_result_index
                )
                ctx.block.close_current_block()
                
                # 收集结果
                results.append(tool_result_block)
                
            except Exception as e:
                error_msg = f"工具执行失败: {str(e)}"
                logger.error(f"❌ {error_msg}")
                
                tool_result_index = ctx.block.start_new_block("tool_result")
                error_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": error_msg,
                    "is_error": True
                }
                
                yield await self.event_manager.content.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=error_result_block
                )
                
                yield await self.event_manager.content.emit_content_stop(
                    session_id=session_id,
                    index=tool_result_index
                )
                ctx.block.close_current_block()
                
                results.append(error_result_block)
        
        # 最后 yield 完成事件（包含所有结果）
        yield {
            "type": "tool_execution_complete",
            "data": {"results": results}
        }
    
    async def _execute_tools(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx  # RuntimeContext
    ) -> List[Dict]:
        """
        执行工具调用
        
        使用 content_* 事件发送 tool_use 和 tool_result 信息
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话ID
            ctx: RuntimeContext（用于管理 block 索引）
            
        Returns:
            工具结果列表
        """
        import json
        
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            logger.debug(f"🔧 执行工具: {tool_name}")
            
            # ===== 发送 tool_use content block =====
            # 关闭之前的 block
            if ctx.block.is_block_open():
                await self.event_manager.content.emit_content_stop(
                    session_id=session_id,
                    index=ctx.block.current_index
                )
            
            # 发送 tool_use 事件
            tool_use_index = ctx.block.start_new_block("tool_use")
            await self.event_manager.content.emit_content_start(
                session_id=session_id,
                index=tool_use_index,
                content_block={
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": tool_input
                }
            )
            
            # 关闭 tool_use block
            await self.event_manager.content.emit_content_stop(
                session_id=session_id,
                index=tool_use_index
            )
            ctx.block.close_current_block()
            
            # ===== 执行工具 =====
            try:
                # 特殊处理：plan_todo 工具
                if tool_name == "plan_todo":
                    operation = tool_input.get('operation', 'create_plan')
                    data = tool_input.get('data', {})
                    # 传入当前 plan（从 plan_state 获取）
                    current_plan = self.plan_state.get("plan")
                    result = await self.plan_todo_tool.execute(
                        operation=operation,
                        data=data,
                        current_plan=current_plan
                    )
                    
                    # 更新 plan_state（如果工具返回了新的 plan）
                    if result.get("status") == "success" and "plan" in result:
                        new_plan = result.get("plan")
                        self.plan_state["plan"] = new_plan
                        
                        # 🎯 根据操作类型发送不同的事件
                        # 获取 conversation_id（从 session context）
                        session_context = await self.event_manager.storage.get_session_context(session_id)
                        conversation_id = session_context.get("conversation_id")
                        
                        if operation == "create_plan":
                            # 首次创建 plan，使用语义化事件
                            await self.event_manager.conversation.emit_conversation_plan_created(
                                session_id=session_id,
                                conversation_id=conversation_id,
                                plan=new_plan
                            )
                            logger.info(f"📋 Plan 已创建: {new_plan.get('goal', '')}")
                        else:
                            # 更新 plan（update_step/add_step），使用统一的 delta 事件
                            await self.event_manager.conversation.emit_conversation_plan_updated(
                            session_id=session_id,
                                conversation_id=conversation_id,
                            plan=new_plan
                        )
                        logger.info(f"📋 Plan 已更新: operation={operation}")
                else:
                    # 🛡️ 为所有工具注入上下文（user_id, session_id, conversation_id）
                    # 工具可以通过 kwargs 获取这些信息
                    session_context = await self.event_manager.storage.get_session_context(session_id)
                    tool_input.setdefault("session_id", session_id)
                    if session_context.get("user_id"):
                        tool_input.setdefault("user_id", session_context.get("user_id"))
                    if session_context.get("conversation_id"):
                        tool_input.setdefault("conversation_id", session_context.get("conversation_id"))

                    # 通用工具执行
                    result = await self.tool_executor.execute(tool_name, tool_input)
                
                # ===== 发送 tool_result content block =====
                tool_result_index = ctx.block.start_new_block("tool_result")
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": False
                }
                
                await self.event_manager.content.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=tool_result_block
                )
                await self.event_manager.content.emit_content_stop(
                    session_id=session_id,
                    index=tool_result_index
                )
                ctx.block.close_current_block()
                
                results.append(tool_result_block)
                logger.debug(f"✅ 工具执行成功: {tool_name}")
                
            except Exception as e:
                logger.error(f"❌ 工具执行失败: {tool_name}, error={e}")
                
                # 发送错误的 tool_result
                tool_result_index = ctx.block.start_new_block("tool_result")
                error_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps({"success": False, "error": str(e)}),
                    "is_error": True
                }
                
                await self.event_manager.content.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=error_result_block
                )
                await self.event_manager.content.emit_content_stop(
                    session_id=session_id,
                    index=tool_result_index
                )
                ctx.block.close_current_block()
                
                results.append(error_result_block)
        
        return results
    
    # ===== 辅助方法 =====
    
    def get_plan(self) -> Optional[Dict]:
        """获取当前计划"""
        return self.plan_state.get("plan")
    
    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        plan = self.plan_state.get("plan")
        if not plan:
            return {"total": 0, "completed": 0, "progress": 0.0}
        
        total = len(plan.get("steps", []))
        completed = sum(1 for s in plan.get("steps", []) if s.get("status") == "completed")
        return {
            "total": total,
            "completed": completed,
            "progress": completed / total if total > 0 else 0.0
        }


def create_simple_agent(
    model: str = "claude-sonnet-4-5-20250929",
    workspace_dir: str = None,
    event_manager=None
) -> SimpleAgent:
    """
    创建 SimpleAgent
    
    Args:
        model: 模型名称
        workspace_dir: 工作目录
        event_manager: EventManager 实例（必需）
        
    Returns:
        SimpleAgent 实例
    """
    if event_manager is None:
        raise ValueError("event_manager 是必需参数")
    
    return SimpleAgent(
        model=model,
        workspace_dir=workspace_dir,
        event_manager=event_manager
    )

