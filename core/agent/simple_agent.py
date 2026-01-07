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
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator

# 2. 第三方库（无）

# 3. 本地模块
from core.agent.intent_analyzer import create_intent_analyzer
from core.context.runtime import create_runtime_context
from core.events.broadcaster import EventBroadcaster
from core.llm import Message, LLMResponse, ToolType, create_claude_service
from core.tool import create_tool_executor, create_tool_selector
from core.tool.capability import create_capability_registry
from core.orchestration import create_pipeline_tracer, E2EPipelineTracer
from core.confirmation_manager import get_confirmation_manager, ConfirmationType
from logger import get_logger
from tools.plan_todo_tool import create_plan_todo_tool
from utils.usage_tracker import create_usage_tracker


logger = get_logger(__name__)


class SimpleAgent:
    """
    精简版 Agent - 编排层
    
    只负责协调各模块，不包含具体业务逻辑
    
    设计哲学：System Prompt → Schema → Agent
    - System Prompt 定义 Agent 的行为规范和能力边界
    - Schema 配置组件的启用状态和参数
    - Agent 根据 Schema 动态初始化组件
    
    使用方式：
        # 方式 1: 从 AgentFactory 创建（推荐）
        agent = await AgentFactory.from_prompt(system_prompt, event_manager)
        
        # 方式 2: 直接创建（使用默认配置）
        agent = SimpleAgent(event_manager=event_manager)
        async for event in agent.chat(user_input, session_id=session_id):
            yield event
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        max_turns: int = 20,
        event_manager=None,
        workspace_dir: str = None,
        conversation_service=None,
        schema=None,  # 🆕 AgentSchema 配置
        system_prompt: str = None  # 🆕 System Prompt（作为运行时指令）
    ):
        """
        初始化 Agent
        
        Args:
            model: 模型名称
            max_turns: 最大轮次
            event_manager: EventManager 实例（必需）
            workspace_dir: 工作目录
            conversation_service: ConversationService 实例（用于消息持久化）
            schema: AgentSchema 配置（定义组件启用状态和参数）
            system_prompt: System Prompt（运行时传给 LLM 的系统指令）
        """
        if event_manager is None:
            raise ValueError("event_manager 是必需参数")
        
        # ===== 核心配置 =====
        self.model = model
        self.max_turns = max_turns
        self.event_manager = event_manager  # 保留引用（兼容）
        self.workspace_dir = workspace_dir
        
        # 🆕 Schema 驱动：存储 Schema 配置
        from core.schemas import DEFAULT_AGENT_SCHEMA
        self.schema = schema if schema is not None else DEFAULT_AGENT_SCHEMA
        
        # 🆕 System Prompt：存储系统指令（如果未提供，使用默认）
        self.system_prompt = system_prompt
        
        # 从 Schema 读取运行时参数（覆盖传入的参数）
        if schema is not None:
            self.model = schema.model
            self.max_turns = schema.max_turns
        
        # 🆕 使用 EventBroadcaster 作为事件发送的统一入口
        # 传入 conversation_service 用于自动持久化
        self.broadcaster = EventBroadcaster(event_manager, conversation_service)
        
        # ===== 根据 Schema 动态初始化各模块 =====
        self._init_modules()
        
        # ===== 状态（Manus Context Isolation 原则） =====
        # ⚠️ 这是工具返回值的缓存，不是隐式状态
        # 所有更新都通过 plan_todo 工具显式执行，此处仅缓存以避免重复调用
        # 参考: docs/12-CONTEXT_ENGINEERING_OPTIMIZATION.md
        self._plan_cache = {"plan": None, "todo": None, "tool_calls": []}
        self.invocation_stats = {"direct": 0, "code_execution": 0, "programmatic": 0, "streaming": 0}
        
        # ===== Usage 统计（使用 UsageTracker） =====
        self.usage_tracker = create_usage_tracker()
        
        # ===== 🆕 E2E Pipeline Tracer（V4.2 Code-First 优化） =====
        # 追踪器按 session 创建，在 chat() 中初始化
        self._tracer: Optional[E2EPipelineTracer] = None
        self.enable_tracing = True  # 默认启用追踪
        
        logger.info(f"✅ SimpleAgent 初始化完成 (model={self.model}, schema={self.schema.name})")
    
    def _init_modules(self):
        """
        根据 Schema 动态初始化各独立模块
        
        设计哲学：Schema 驱动组件初始化
        - 如果 Schema 中组件 enabled=False，则不创建该组件
        - 组件配置参数从 Schema 中读取
        """
        # 1. 能力注册表（总是需要）
        self.capability_registry = create_capability_registry()
        
        # 2. 意图分析器（根据 Schema 决定是否创建）
        if self.schema.intent_analyzer.enabled:
            intent_config = self.schema.intent_analyzer
            self.intent_llm = create_claude_service(
                model=intent_config.llm_model,  # 从 Schema 读取
                enable_thinking=False,
                enable_caching=False,
                tools=[],
                max_tokens=8192  # Claude 3.5 Haiku 最大支持 8192
            )
            self.intent_analyzer = create_intent_analyzer(
                llm_service=self.intent_llm,
                enable_llm=intent_config.use_llm  # 从 Schema 读取
            )
            logger.debug(f"✓ IntentAnalyzer 已启用 (model={intent_config.llm_model})")
        else:
            self.intent_llm = None
            self.intent_analyzer = None
            logger.debug("○ IntentAnalyzer 未启用")
        
        # 3. 工具选择器（根据 Schema 决定是否创建）
        if self.schema.tool_selector.enabled:
            self.tool_selector = create_tool_selector(registry=self.capability_registry)
            logger.debug(f"✓ ToolSelector 已启用 (strategy={self.schema.tool_selector.selection_strategy})")
        else:
            self.tool_selector = None
            logger.debug("○ ToolSelector 未启用")
        
        # 4. 工具执行器（总是需要）        
        tool_context = {
            "event_manager": self.event_manager,
            "workspace_dir": self.workspace_dir
        }
        self.tool_executor = create_tool_executor(
            self.capability_registry,
            tool_context=tool_context
        )
        
        # 5. Plan/Todo 工具（根据 Schema 决定是否创建）
        if self.schema.plan_manager.enabled:
            self.plan_todo_tool = create_plan_todo_tool(registry=self.capability_registry)
            logger.debug(f"✓ PlanManager 已启用 (max_steps={self.schema.plan_manager.max_steps})")
        else:
            self.plan_todo_tool = None
            logger.debug("○ PlanManager 未启用")
        
        # 6. 执行 LLM（Sonnet）
        self.llm = create_claude_service(
            model=self.model,  # 使用 Schema 中的 model
            enable_thinking=True,
            enable_caching=False,
            tools=[ToolType.BASH, ToolType.TEXT_EDITOR, ToolType.WEB_SEARCH]
        )
        
        # 注册自定义工具到 LLM（如果有 plan_todo_tool）
        if self.plan_todo_tool:
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
        messages: List[Dict[str, str]] = None,
        session_id: str = None,
        message_id: str = None,
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
            messages: 完整的消息列表
            session_id: 会话ID
            message_id: 消息ID（用于事件关联）
            enable_stream: 是否流式输出
            
        Yields:
            事件字典
        """
        messages = messages or []
        self._current_message_id = message_id
        
        # 生成 session_id
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.warning(f"未提供 session_id，生成临时 ID: {session_id}")
        
        # ===== 🆕 初始化 E2E Pipeline Tracer（V4.2 Code-First 优化） =====
        session_context = await self.event_manager.storage.get_session_context(session_id)
        conversation_id = session_context.get("conversation_id", "default")
        # 存储为实例变量，供工具执行时使用
        self._current_conversation_id = conversation_id
        
        if self.enable_tracing:
            self._tracer = create_pipeline_tracer(
                session_id=session_id,
                conversation_id=conversation_id
            )
            # 设置用户 Query
            user_query = messages[-1]["content"] if messages else ""
            self._tracer.set_user_query(user_query[:200])
        
        # ===== 1. 意图分析（根据 Schema 决定是否执行） =====
        if self.schema.intent_analyzer.enabled and self.intent_analyzer:
            # 🆕 追踪意图分析阶段
            if self._tracer:
                stage = self._tracer.create_stage("intent_analysis")
                stage.start()
                stage.set_input({"message_count": len(messages)})
            
            logger.info("🎯 开始意图分析...")
            intent = await self.intent_analyzer.analyze(messages)
            
            # 发送意图识别结果给前端
            intent_delta = {
                "type": "intent",
                "content": json.dumps({
                    "task_type": intent.task_type.value,
                    "complexity": intent.complexity.value,
                    "needs_plan": intent.needs_plan,
                    "confidence": intent.confidence
                }, ensure_ascii=False)
            }
            yield await self.broadcaster.emit_message_delta(
                session_id=session_id,
                delta=intent_delta
            )
            logger.info(f"🎯 意图识别完成: {intent.task_type.value}, complexity={intent.complexity.value}")
            
            # 🆕 完成追踪
            if self._tracer:
                stage.complete({
                    "task_type": intent.task_type.value,
                    "complexity": intent.complexity.value,
                    "needs_plan": intent.needs_plan
                })
        else:
            # 不执行意图分析，使用默认配置
            logger.info("○ 跳过意图分析（Schema 未启用）")
            from core.agent.types import IntentResult, TaskType, Complexity
            intent = IntentResult(
                task_type=TaskType.GENERAL,
                complexity=Complexity.MEDIUM,
                needs_plan=self.schema.plan_manager.enabled,
                confidence=1.0
            )
            
            # 🆕 记录跳过
            if self._tracer:
                stage = self._tracer.create_stage("intent_analysis")
                stage.skip("Schema 未启用")
        
        # 🆕 System Prompt 选择（设计哲学：极简原则）
        # 
        # 设计理念：
        # - 用户只定义一套 System Prompt（从 AgentFactory 传入）
        # - 如果有自定义 System Prompt，直接使用
        # - 如果没有，使用默认 UNIVERSAL_AGENT_PROMPT
        # - 不做复杂的分层，保持简单
        
        if self.system_prompt:
            # 使用用户定义的 System Prompt（唯一真相来源）
            system_prompt = self.system_prompt
            logger.info("✅ 使用用户定义的 System Prompt")
        else:
            # 使用框架默认 Prompt
            from prompts.universal_agent_prompt import UNIVERSAL_AGENT_PROMPT
            system_prompt = UNIVERSAL_AGENT_PROMPT
            logger.info("✅ 使用框架默认 System Prompt")
        
        # 🆕 追加 Workspace 路径信息（让 Claude 的 text_editor 使用正确路径）
        # 注意：session_context 和 conversation_id 已在 tracer 初始化时获取
        
        # 获取 workspace 绝对路径并确保目录存在
        from core.workspace_manager import get_workspace_manager
        workspace_manager = get_workspace_manager(self.workspace_dir or "./workspace")
        workspace_path = workspace_manager.get_workspace_root(conversation_id)
        workspace_path.mkdir(parents=True, exist_ok=True)  # 确保目录存在
        
        workspace_instruction = f"""

# 工作目录（CRITICAL）
所有文件操作必须在工作目录下进行：
- 工作目录: {workspace_path}
- 创建文件示例: {workspace_path}/index.html
- ❌ 禁止使用 /tmp 或其他系统目录
"""
        system_prompt = system_prompt + workspace_instruction
        
        # ===== 2. 工具选择（Schema 驱动优先） =====
        # 🆕 追踪工具选择阶段
        if self._tracer:
            tool_stage = self._tracer.create_stage("tool_selection")
            tool_stage.start()
        
        logger.info("🔧 开始工具选择...")
        
        # 确定所需能力（优先级：Schema > Plan > Intent 推断）
        plan = self._plan_cache.get("plan")
        selection_source = "intent"  # 记录选择来源
        
        if self.schema.tools:
            # 优先使用 Schema 配置（Prompt 驱动设计哲学）
            required_capabilities = self.schema.tools
            selection_source = "schema"
            logger.debug(f"✓ 使用 Schema 配置的工具: {self.schema.tools}")
        elif plan and plan.get('required_capabilities'):
            # 其次使用 Plan 指定的能力
            required_capabilities = plan['required_capabilities']
            selection_source = "plan"
            logger.debug("✓ 使用 Plan 指定的能力")
        else:
            # 最后通过意图推断（兜底）
            required_capabilities = self.capability_registry.get_capabilities_for_task_type(
                intent.task_type.value
            )
            logger.debug(f"✓ 通过意图推断能力: {intent.task_type.value}")
        
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
        
        # 🆕 完成追踪
        if self._tracer:
            tool_stage.set_input({
                "required_capabilities": required_capabilities[:5] if required_capabilities else [],
                "selection_source": selection_source
            })
            tool_stage.complete({
                "tool_count": len(selection.tool_names),
                "tools": selection.tool_names[:5]
            })
        
        # ===== 3. 构建消息 =====
        # 直接使用传入的 messages（调用方已准备好完整列表）
        # 转换为 Message 对象（后续 RVR 循环会 append 新消息）
        llm_messages = [
            Message(role=msg["role"], content=msg["content"])
            for msg in messages
        ]
        
        # ===== 4. RVR 循环 =====
        ctx = create_runtime_context(session_id=session_id, max_turns=self.max_turns)
        
        for turn in range(self.max_turns):
            ctx.next_turn()
            logger.info(f"{'='*60}")
            logger.info(f"🔄 Turn {turn + 1}/{self.max_turns}")
            logger.info(f"{'='*60}")
            
            # 调用 LLM（Extended Thinking 由 System Prompt 和 Claude 自主决定）
            if enable_stream:
                # 流式处理 LLM 响应
                async for event in self._process_stream(
                    llm_messages, system_prompt, tools_for_llm, ctx, session_id
                ):
                    yield event
                    
                # 流结束后，从 ctx 获取 LLM 响应
                response = ctx.last_llm_response
                if response:
                    # 处理工具调用
                    if response.stop_reason == "tool_use" and response.tool_calls:
                        # 🆕 区分客户端工具和服务端工具
                        # - 客户端工具（tool_use）：需要我们执行并返回 tool_result
                        # - 服务端工具（server_tool_use）：Anthropic 服务器已执行，结果在 raw_content 中
                        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
                        server_tools = [tc for tc in response.tool_calls if tc.get("type") == "server_tool_use"]
                        
                        if server_tools:
                            logger.info(f"🌐 服务端工具已执行: {[t.get('name') for t in server_tools]}")
                            # 🆕 发送服务端工具的事件到前端
                            async for server_event in self._emit_server_tool_blocks_stream(
                                response.raw_content, session_id, ctx
                            ):
                                yield server_event
                        
                        tool_results = []
                        if client_tools:
                            # 只执行客户端工具
                            async for tool_event in self._execute_tools_stream(
                                client_tools, session_id, ctx
                            ):
                                yield tool_event
                                # 从 content_start 事件中收集 tool_result
                                if tool_event.get("type") == "content_start":
                                    content_block = tool_event.get("data", {}).get("content_block", {})
                                    if content_block.get("type") == "tool_result":
                                        tool_results.append(content_block)
                        
                        # 更新消息（用于下一轮 LLM 调用）
                        llm_messages.append(Message(role="assistant", content=response.raw_content))
                        
                        # 🆕 只有当有客户端工具结果时才添加 user message
                        if tool_results:
                            llm_messages.append(Message(role="user", content=tool_results))
                        # 如果只有服务端工具，不需要添加 user message，直接进入下一轮
                    else:
                        # 没有工具调用，任务完成
                        ctx.set_completed(response.content, response.stop_reason)
                        break
            else:
                # 非流式模式
                response = await self.llm.create_message_async(
                    messages=llm_messages,
                    system=system_prompt,
                    tools=tools_for_llm
                )
                
                # 🔢 累积 usage 统计
                self.usage_tracker.accumulate(response)
                
                if response.content:
                    yield {"type": "content", "data": {"text": response.content}}
                
                if response.stop_reason != "tool_use":
                    ctx.set_completed(response.content, response.stop_reason)
                    break
                
                # 🆕 区分客户端工具和服务端工具（非流式模式）
                client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
                server_tools = [tc for tc in response.tool_calls if tc.get("type") == "server_tool_use"]
                
                if server_tools:
                    logger.info(f"🌐 服务端工具已执行: {[t.get('name') for t in server_tools]}")
                    # 🆕 发送服务端工具的事件（非流式模式也需要）
                    async for server_event in self._emit_server_tool_blocks_stream(
                        response.raw_content, session_id, ctx
                    ):
                        yield server_event
                
                llm_messages.append(Message(role="assistant", content=response.raw_content))
                
                if client_tools:
                    # 只执行客户端工具
                    tool_results = await self._execute_tools(client_tools, session_id, ctx)
                    llm_messages.append(Message(role="user", content=tool_results))
            
            if ctx.is_completed():
                break
        
        # ===== 5. 完成追踪 =====
        # 🆕 记录最终响应并完成追踪
        if self._tracer:
            final_response = ctx.stream.content if hasattr(ctx, 'stream') else ""
            self._tracer.set_final_response(final_response[:500] if final_response else "")
            # 🐛 修复：不再覆盖 tool_calls，使用 log_tool_call 记录的值
            # self._tracer.stats["tool_calls"] = len(self._plan_cache.get("tool_calls", []))
            self._tracer.finish()
        
        # ===== 6. 发送完成事件 =====
        # 🆕 传递 usage 统计给 broadcaster（用于持久化）
        # 转换字段名以匹配 broadcaster 期望的格式
        stats = self.usage_stats
        await self.broadcaster.accumulate_usage(session_id, {
            "input_tokens": stats.get("total_input_tokens", 0),
            "output_tokens": stats.get("total_output_tokens", 0),
            "cache_read_tokens": stats.get("total_cache_read_tokens", 0),
            "cache_creation_tokens": stats.get("total_cache_creation_tokens", 0),
        })
        
        yield await self.broadcaster.emit_message_stop(
            session_id=session_id,
            message_id=self._current_message_id
        )
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
        Extended Thinking 由 LLM Service 配置和 System Prompt 控制
        """
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
                        yield await self.broadcaster.emit_content_stop(
                            session_id=session_id,
                            index=ctx.block.current_index
                        )
                    
                    block_idx = ctx.block.start_new_block("thinking")
                    yield await self.broadcaster.emit_content_start(
                        session_id=session_id,
                        index=block_idx,
                        content_block={"type": "thinking", "thinking": ""}
                    )
                
                yield await self.broadcaster.emit_content_delta(
                    session_id=session_id,
                    index=ctx.block.current_index,
                    delta={"type": "thinking_delta", "thinking": llm_response.thinking}
                )
                ctx.stream.append_thinking(llm_response.thinking)
            
            # 处理 content
            if llm_response.content and llm_response.is_stream:
                if ctx.block.needs_transition("text"):
                    if ctx.block.is_block_open():
                        yield await self.broadcaster.emit_content_stop(
                            session_id=session_id,
                            index=ctx.block.current_index
                        )
                    
                    block_idx = ctx.block.start_new_block("text")
                    yield await self.broadcaster.emit_content_start(
                        session_id=session_id,
                        index=block_idx,
                        content_block={"type": "text", "text": ""}
                    )
                
                yield await self.broadcaster.emit_content_delta(
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
            yield await self.broadcaster.emit_content_stop(
                session_id=session_id,
                index=ctx.block.current_index
            )
        
        # 保存最终响应到 ctx（供 RVR 循环使用）
        if final_response:
            # 🔢 累积 usage 统计
            self.usage_tracker.accumulate(final_response)
            # 存到 ctx，不再通过事件传递
            ctx.last_llm_response = final_response
    
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
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            logger.debug(f"🔧 执行工具: {tool_name}")
            
            # 🆕 追踪工具执行（V4.2 Code-First）
            if self._tracer:
                self._tracer.log_tool_call(tool_name)
            
            # ===== 发送 tool_use content block =====
            # 关闭之前的 block
            if ctx.block.is_block_open():
                yield await self.broadcaster.emit_content_stop(
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
            yield await self.broadcaster.emit_content_start(
                session_id=session_id,
                index=tool_use_index,
                content_block=tool_use_block
            )
            
            # 关闭 tool_use block
            yield await self.broadcaster.emit_content_stop(
                session_id=session_id,
                index=tool_use_index
            )
            ctx.block.close_current_block()
            
            # ===== 执行工具 =====
            try:
                # plan_todo 工具需要 current_plan 参数
                if tool_name == "plan_todo":
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
                
                # 🆕 HITL 工具：Agent 负责发送 SSE 事件并等待用户响应
                elif tool_name == "request_human_confirmation":
                    result = await self._handle_human_confirmation(
                        tool_input=tool_input,
                        session_id=session_id,
                        tool_id=tool_id
                    )
                else:
                    # 🛡️ 为所有工具注入上下文（user_id, session_id, conversation_id）
                    session_context = await self.event_manager.storage.get_session_context(session_id)
                    tool_input.setdefault("session_id", session_id)
                    if session_context.get("user_id"):
                        tool_input.setdefault("user_id", session_context.get("user_id"))
                    # 确保 conversation_id 始终有值（使用 session_id 作为默认值）
                    conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
                    tool_input.setdefault("conversation_id", conv_id)
                    
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
                yield await self.broadcaster.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=tool_result_block
                )
                
                yield await self.broadcaster.emit_content_stop(
                    session_id=session_id,
                    index=tool_result_index
                )
                ctx.block.close_current_block()
                # 注意：特殊工具的 message_delta 由 broadcaster.emit_content_start 自动发送
                
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
                
                yield await self.broadcaster.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=error_result_block
                )
                
                yield await self.broadcaster.emit_content_stop(
                    session_id=session_id,
                    index=tool_result_index
                )
                ctx.block.close_current_block()
    
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
        
        # 3. 通过 EventBroadcaster 发送 SSE 事件到前端（使用 message_delta 格式）
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
    
    async def _emit_server_tool_blocks_stream(
        self,
        raw_content: List[Dict],
        session_id: str,
        ctx  # RuntimeContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送服务端工具（如 web_search）的事件到前端
        
        服务端工具的特点：
        - 由 Anthropic 服务器执行，不需要我们执行
        - 调用和结果已经包含在 raw_content 中
        - 类型为 server_tool_use 和 *_tool_result（如 web_search_tool_result）
        
        🔑 设计原则：
        - 前端不需要知道什么是 server_tool_use
        - 统一使用 tool_use / tool_result，保持接口一致
        - 方便兼容 OpenAI 等其他 LLM
        
        Args:
            raw_content: LLM 响应的原始内容块列表
            session_id: 会话ID
            ctx: RuntimeContext
            
        Yields:
            content_start, content_stop 等事件（统一使用 tool_use/tool_result）
        """
        for block in raw_content:
            block_type = block.get("type", "")
            
            # 处理 server_tool_use → 转换为 tool_use
            if block_type == "server_tool_use":
                # 关闭之前的 block
                if ctx.block.is_block_open():
                    yield await self.broadcaster.emit_content_stop(
                        session_id=session_id,
                        index=ctx.block.current_index
                    )
                
                # 发送标准 tool_use 事件（前端不需要知道是服务端工具）
                block_idx = ctx.block.start_new_block("tool_use")
                yield await self.broadcaster.emit_content_start(
                    session_id=session_id,
                    index=block_idx,
                    content_block={
                        "type": "tool_use",  # 统一为 tool_use
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": block.get("input", {})
                    }
                )
                yield await self.broadcaster.emit_content_stop(
                    session_id=session_id,
                    index=block_idx
                )
                ctx.block.close_current_block()
                logger.debug(f"🌐 发送服务端工具调用事件（统一为 tool_use）: {block.get('name')}")
            
            # 处理 *_tool_result → 转换为 tool_result
            elif block_type.endswith("_tool_result") and block_type != "tool_result":
                # 关闭之前的 block
                if ctx.block.is_block_open():
                    yield await self.broadcaster.emit_content_stop(
                        session_id=session_id,
                        index=ctx.block.current_index
                    )
                
                # 发送标准 tool_result 事件
                block_idx = ctx.block.start_new_block("tool_result")
                
                # 处理 content 字段（可能是列表或字符串）
                content = block.get("content", [])
                if isinstance(content, list):
                    # 提取文本内容
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                    content_str = "\n".join(text_parts) if text_parts else json.dumps(content, ensure_ascii=False)
                else:
                    content_str = str(content)
                
                yield await self.broadcaster.emit_content_start(
                    session_id=session_id,
                    index=block_idx,
                    content_block={
                        "type": "tool_result",  # 统一为 tool_result
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": content_str,
                        "is_error": False
                    }
                )
                yield await self.broadcaster.emit_content_stop(
                    session_id=session_id,
                    index=block_idx
                )
                ctx.block.close_current_block()
                logger.debug(f"🌐 发送服务端工具结果事件（统一为 tool_result）: {block_type}")
    
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
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            logger.debug(f"🔧 执行工具: {tool_name}")
            
            # 🆕 追踪工具执行（V4.2 Code-First）
            if self._tracer:
                self._tracer.log_tool_call(tool_name)
            
            # ===== 发送 tool_use content block =====
            # 关闭之前的 block
            if ctx.block.is_block_open():
                await self.broadcaster.emit_content_stop(
                    session_id=session_id,
                    index=ctx.block.current_index
                )
            
            # 发送 tool_use 事件
            tool_use_index = ctx.block.start_new_block("tool_use")
            await self.broadcaster.emit_content_start(
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
            await self.broadcaster.emit_content_stop(
                session_id=session_id,
                index=tool_use_index
            )
            ctx.block.close_current_block()
            
            # ===== 执行工具 =====
            try:
                # plan_todo 工具需要 current_plan 参数
                if tool_name == "plan_todo":
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
                else:
                    # 为所有工具注入上下文（user_id, session_id, conversation_id）
                    session_context = await self.event_manager.storage.get_session_context(session_id)
                    tool_input.setdefault("session_id", session_id)
                    if session_context.get("user_id"):
                        tool_input.setdefault("user_id", session_context.get("user_id"))
                    conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
                    tool_input.setdefault("conversation_id", conv_id)

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
                
                await self.broadcaster.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=tool_result_block
                )
                await self.broadcaster.emit_content_stop(
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
                
                await self.broadcaster.emit_content_start(
                    session_id=session_id,
                    index=tool_result_index,
                    content_block=error_result_block
                )
                await self.broadcaster.emit_content_stop(
                    session_id=session_id,
                    index=tool_result_index
                )
                ctx.block.close_current_block()
                
                results.append(error_result_block)
        
        return results
    
    # ===== 辅助方法 =====
    
    @property
    def usage_stats(self) -> dict:
        """
        获取 usage 统计（兼容属性）
        
        Returns:
            usage 统计字典
        """
        return self.usage_tracker.get_stats()
    
    def get_plan(self) -> Optional[Dict]:
        """获取当前计划"""
        return self._plan_cache.get("plan")
    
    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        plan = self._plan_cache.get("plan")
        if not plan:
            return {"total": 0, "completed": 0, "progress": 0.0}
        
        total = len(plan.get("steps", []))
        completed = sum(1 for s in plan.get("steps", []) if s.get("status") == "completed")
        return {
            "total": total,
            "completed": completed,
            "progress": completed / total if total > 0 else 0.0
        }
    
    # ===== 🆕 V4.2 Code-First 追踪方法 =====
    
    def get_trace_report(self) -> Optional[Dict[str, Any]]:
        """
        获取最近一次执行的追踪报告
        
        Returns:
            追踪报告字典，包含：
            - session_id: 会话ID
            - stages: 各阶段执行详情
            - stats: 统计信息
            - user_query: 用户查询
            - final_response: 最终响应
        """
        if self._tracer:
            return self._tracer.to_dict()
        return None
    
    def set_tracing_enabled(self, enabled: bool):
        """
        启用或禁用追踪
        
        Args:
            enabled: 是否启用追踪
        """
        self.enable_tracing = enabled
        logger.info(f"{'✅ 启用' if enabled else '❌ 禁用'} E2E Pipeline 追踪")


def create_simple_agent(
    model: str = "claude-sonnet-4-5-20250929",
    workspace_dir: str = None,
    event_manager=None,
    conversation_service=None
) -> SimpleAgent:
    """
    创建 SimpleAgent
    
    Args:
        model: 模型名称
        workspace_dir: 工作目录
        event_manager: EventManager 实例（必需）
        conversation_service: ConversationService 实例（用于消息持久化）
        
    Returns:
        SimpleAgent 实例
    """
    if event_manager is None:
        raise ValueError("event_manager 是必需参数")
    
    return SimpleAgent(
        model=model,
        workspace_dir=workspace_dir,
        event_manager=event_manager,
        conversation_service=conversation_service
    )

