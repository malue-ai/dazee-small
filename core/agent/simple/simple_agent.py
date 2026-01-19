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

代码拆分（V7.6）：
- simple_agent.py: 主入口 + 初始化 + 属性
- simple_agent_context.py: 上下文 + Prompt + Memory
- simple_agent_tools.py: 工具调用 + Plan 特判 + HITL
- simple_agent_loop.py: RVR 主循环
- simple_agent_errors.py: 错误处理
"""

# 1. 标准库
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator

# 2. 第三方库（无）

# 3. 本地模块
from core.agent.intent_analyzer import create_intent_analyzer
from core.context.runtime import create_runtime_context
from core.context.context_engineering import (
    ContextEngineeringManager, 
    AgentState, 
    create_context_engineering_manager
)
from core.context.prompt_manager import get_prompt_manager, PromptManager
from core.events.broadcaster import EventBroadcaster
from core.llm import Message, LLMResponse, ToolType, create_claude_service
from core.tool import create_tool_executor, create_tool_selector
from core.tool.capability import create_capability_registry, create_invocation_selector
from core.orchestration import create_pipeline_tracer, E2EPipelineTracer
from core.confirmation_manager import get_confirmation_manager, ConfirmationType
from core.agent.types import IntentResult
from core.agent.content_handler import ContentHandler, create_content_handler
from logger import get_logger
from tools.plan_todo_tool import create_plan_todo_tool
from utils.usage_tracker import create_usage_tracker
from utils.message_utils import dict_list_to_messages

# 4. 拆分模块
from core.agent.simple.simple_agent_context import (
    get_task_complexity,
    build_system_prompt,
    build_cached_system_prompt
)
from core.agent.simple.simple_agent_tools import ToolExecutionMixin
from core.agent.simple.simple_agent_loop import RVRLoopMixin


logger = get_logger(__name__)


class SimpleAgent(ToolExecutionMixin, RVRLoopMixin):
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
        schema=None,  # AgentSchema 配置
        system_prompt: str = None,  # System Prompt（作为运行时指令）
        prompt_schema=None,  # V4.6: PromptSchema（提示词分层）
        prompt_cache=None,  # V4.6.2: InstancePromptCache（实例缓存）
        apis_config: Optional[List[Dict[str, Any]]] = None  # 预配置的 APIs
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
            prompt_schema: PromptSchema（提示词分层配置）
            prompt_cache: InstancePromptCache（实例提示词缓存）
            apis_config: 预配置的 API 列表（传给 api_calling 工具自动注入认证）
        """
        if event_manager is None:
            raise ValueError("event_manager 是必需参数")
        
        # ===== 核心配置 =====
        self.model = model
        self.max_turns = max_turns
        self.event_manager = event_manager
        self.workspace_dir = workspace_dir
        
        # Schema 驱动
        from core.schemas import DEFAULT_AGENT_SCHEMA
        self.schema = schema if schema is not None else DEFAULT_AGENT_SCHEMA
        
        # System Prompt
        self.system_prompt = system_prompt
        
        # V4.6: 提示词分层配置
        self.prompt_schema = prompt_schema
        self.prompt_cache = prompt_cache
        
        # 预配置的 APIs
        self.apis_config = apis_config or []
        
        # 上下文管理策略（三层防护）
        self._init_context_strategy(schema)
        
        # 从 Schema 读取运行时参数
        if schema is not None:
            self.model = schema.model
            self.max_turns = schema.max_turns
        
        # EventBroadcaster
        self.broadcaster = EventBroadcaster(event_manager, conversation_service)
        
        # 根据 Schema 动态初始化各模块
        self._init_modules()
        
        # 状态（Context Isolation 原则）
        self._plan_cache = {"plan": None, "todo": None, "tool_calls": []}
        self.invocation_stats = {"direct": 0, "code_execution": 0, "programmatic": 0, "streaming": 0}
        
        # V6.1: 上轮意图分析结果
        self._last_intent_result: Optional["IntentResult"] = None
        
        # 上下文工程管理器
        self.context_engineering = create_context_engineering_manager()
        
        # Usage 统计
        self.usage_tracker = create_usage_tracker()
        
        # E2E Pipeline Tracer
        self._tracer: Optional[E2EPipelineTracer] = None
        self.enable_tracing = True
        
        # V7.1: 原型标记
        self._is_prototype = False
        
        logger.info(f"✅ SimpleAgent 初始化完成 (model={self.model}, schema={self.schema.name})")
    
    def _init_context_strategy(self, schema):
        """初始化上下文管理策略"""
        from core.context.compaction import get_context_strategy, QoSLevel, ContextStrategy
        
        qos_level_str = os.getenv("QOS_LEVEL", "pro")
        try:
            qos_level = QoSLevel(qos_level_str)
        except ValueError:
            qos_level = QoSLevel.PRO
        
        base_strategy = get_context_strategy(qos_level=qos_level)
        
        # V7: 使用 Schema 中的 context_limits 覆盖默认策略
        if schema is not None and hasattr(schema, 'context_limits'):
            ctx_limits = schema.context_limits
            self.context_strategy = ContextStrategy(
                enable_memory_guidance=base_strategy.enable_memory_guidance,
                enable_history_trimming=base_strategy.enable_history_trimming,
                max_history_messages=base_strategy.max_history_messages,
                preserve_first_n=base_strategy.preserve_first_n,
                preserve_last_n=base_strategy.preserve_last_n,
                preserve_tool_results=base_strategy.preserve_tool_results,
                qos_level=qos_level,
                token_budget=ctx_limits.max_context_tokens,
                warning_threshold=ctx_limits.warning_threshold,
            )
            logger.debug(f"✓ 上下文策略: 使用 Schema context_limits 覆盖 (budget={ctx_limits.max_context_tokens:,})")
        else:
            self.context_strategy = base_strategy
        
        logger.debug(
            f"✓ 上下文策略: L1_memory={self.context_strategy.enable_memory_guidance}, "
            f"L2_trim={self.context_strategy.enable_history_trimming}, "
            f"budget={self.context_strategy.token_budget:,} tokens"
        )
    
    def clone_for_session(
        self,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None
    ) -> "SimpleAgent":
        """
        V7.1: 从原型克隆 Agent 实例（快速路径）
        
        复用原型中的重量级组件，仅重置会话级状态
        """
        # 创建新实例（绕过 __init__）
        clone = object.__new__(SimpleAgent)
        
        # ========== 复用原型的重量级组件 ==========
        clone.model = self.model
        clone.max_turns = self.max_turns
        clone.schema = self.schema
        clone.system_prompt = self.system_prompt
        clone.prompt_schema = self.prompt_schema
        clone.prompt_cache = self.prompt_cache
        clone.apis_config = self.apis_config
        clone.context_strategy = self.context_strategy
        
        # LLM Services
        clone.llm = self.llm
        clone.intent_llm = getattr(self, 'intent_llm', None)
        
        # 组件
        clone.capability_registry = self.capability_registry
        clone.tool_executor = self.tool_executor
        clone.tool_selector = getattr(self, 'tool_selector', None)
        clone.intent_analyzer = getattr(self, 'intent_analyzer', None)
        clone.plan_todo_tool = getattr(self, 'plan_todo_tool', None)
        clone.invocation_selector = self.invocation_selector
        clone.context_engineering = self.context_engineering
        
        # 工具配置
        clone.allow_parallel_tools = self.allow_parallel_tools
        clone.max_parallel_tools = self.max_parallel_tools
        clone._serial_only_tools = self._serial_only_tools
        
        # 实例级工具注册表
        clone._instance_registry = getattr(self, '_instance_registry', None)
        
        # MCP 相关
        clone._mcp_clients = getattr(self, '_mcp_clients', [])
        clone._mcp_tools = getattr(self, '_mcp_tools', [])
        
        # Workers 配置
        clone.workers_config = getattr(self, 'workers_config', [])
        
        # ========== 设置会话级参数 ==========
        clone.event_manager = event_manager
        clone.workspace_dir = workspace_dir
        
        # 更新工具执行器的上下文
        if clone.tool_executor and hasattr(clone.tool_executor, 'update_context'):
            clone.tool_executor.update_context({
                "event_manager": event_manager,
                "workspace_dir": workspace_dir,
            })
        
        # 创建新的 EventBroadcaster
        clone.broadcaster = EventBroadcaster(event_manager, conversation_service)
        
        # ========== 重置会话级状态 ==========
        clone._plan_cache = {"plan": None, "todo": None, "tool_calls": []}
        clone.invocation_stats = {"direct": 0, "code_execution": 0, "programmatic": 0, "streaming": 0}
        clone._last_intent_result = None
        clone._tracer = None
        clone.enable_tracing = True
        clone._current_message_id = None
        clone._current_conversation_id = None
        clone._current_user_id = None
        
        # 创建新的 UsageTracker
        clone.usage_tracker = create_usage_tracker()
        
        # 标记为非原型
        clone._is_prototype = False
        
        logger.debug(f"🚀 Agent 克隆完成 (model={clone.model}, schema={clone.schema.name})")
        
        return clone
    
    def _init_modules(self):
        """根据 Schema 动态初始化各独立模块"""
        # 1. 能力注册表
        self.capability_registry = create_capability_registry()
        
        # 2. 意图分析器
        if self.schema.intent_analyzer.enabled:
            intent_config = self.schema.intent_analyzer
            self.intent_llm = create_claude_service(
                model=intent_config.llm_model,
                enable_thinking=False,
                enable_caching=True,
                tools=[],
                max_tokens=8192
            )
            self.intent_analyzer = create_intent_analyzer(
                llm_service=self.intent_llm,
                enable_llm=intent_config.use_llm
            )
            logger.debug(f"✓ IntentAnalyzer 已启用 (model={intent_config.llm_model})")
        else:
            self.intent_llm = None
            self.intent_analyzer = None
            logger.debug("○ IntentAnalyzer 未启用")
        
        # 3. 工具选择器
        if self.schema.tool_selector.enabled:
            self.tool_selector = create_tool_selector(registry=self.capability_registry)
            logger.debug(f"✓ ToolSelector 已启用 (strategy={self.schema.tool_selector.selection_strategy})")
        else:
            self.tool_selector = None
            logger.debug("○ ToolSelector 未启用")
        
        # 4. 工具执行器
        tool_context = {
            "event_manager": self.event_manager,
            "workspace_dir": self.workspace_dir,
            "apis_config": self.apis_config,
        }
        self.tool_executor = create_tool_executor(
            self.capability_registry,
            tool_context=tool_context
        )
        
        # 5. Plan/Todo 工具
        if self.schema.plan_manager.enabled:
            self.plan_todo_tool = create_plan_todo_tool(registry=self.capability_registry)
            logger.debug(f"✓ PlanManager 已启用 (max_steps={self.schema.plan_manager.max_steps})")
        else:
            self.plan_todo_tool = None
            logger.debug("○ PlanManager 未启用")
        
        # 6. InvocationSelector
        self.invocation_selector = create_invocation_selector(
            enable_tool_search=True,
            enable_code_execution=True,
            enable_programmatic=True
        )
        logger.debug("✓ InvocationSelector 已初始化")
        
        # 7. 执行 LLM
        llm_enable_thinking = self.schema.enable_thinking if self.schema.enable_thinking is not None else True
        llm_enable_caching = self.schema.enable_caching if self.schema.enable_caching is not None else True
        
        llm_kwargs = {
            "model": self.model,
            "enable_thinking": llm_enable_thinking,
            "enable_caching": llm_enable_caching,
            "tools": [ToolType.BASH, ToolType.TEXT_EDITOR, ToolType.WEB_SEARCH],
        }
        
        if self.schema.temperature is not None:
            llm_kwargs["temperature"] = self.schema.temperature
        if self.schema.max_tokens is not None:
            llm_kwargs["max_tokens"] = self.schema.max_tokens
        
        self.llm = create_claude_service(**llm_kwargs)
        
        logger.debug(f"✓ 执行 LLM 初始化: thinking={llm_enable_thinking}, caching={llm_enable_caching}")
        
        # 注册自定义工具到 LLM
        if self.plan_todo_tool:
            self._register_tools_to_llm()
        
        # 启用 Claude Skills
        self._enable_registered_skills()
        
        # 8. 并行工具执行配置
        self.allow_parallel_tools = self.schema.allow_parallel_tools
        self.max_parallel_tools = self.schema.tool_selector.max_parallel_tools
        self._serial_only_tools = {"plan_todo", "request_human_confirmation"}
        logger.debug(f"✓ 并行工具配置: allow={self.allow_parallel_tools}, max={self.max_parallel_tools}")
    
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
    
    def _enable_registered_skills(self):
        """启用已注册到 Claude 的 Skills"""
        registered_skills = self.capability_registry.get_registered_skills()
        
        if registered_skills:
            self.llm.enable_skills(registered_skills)
            skill_names = [s.get('skill_id', 'unknown')[:20] + '...' for s in registered_skills]
            logger.info(f"🎯 已启用 {len(registered_skills)} 个 Claude Skills: {skill_names}")
        else:
            logger.debug("○ 没有已注册的 Claude Skills")
    
    async def chat(
        self,
        messages: List[Dict[str, str]] = None,
        session_id: str = None,
        message_id: str = None,
        enable_stream: bool = True,
        variables: Dict[str, Any] = None,
        intent: Optional["IntentResult"] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Agent 统一执行入口 - 7 阶段完整流程
        
        Args:
            messages: 完整的消息列表
            session_id: 会话ID
            message_id: 消息ID
            enable_stream: 是否流式输出
            variables: 前端上下文变量
            intent: 从路由层传入的意图分析结果
            
        Yields:
            事件字典
        """
        messages = messages or []
        self._current_message_id = message_id
        
        # 生成 session_id
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.warning(f"未提供 session_id，生成临时 ID: {session_id}")
        
        # ===== 阶段 1: 初始化会话上下文 =====
        session_context = await self.event_manager.storage.get_session_context(session_id)
        conversation_id = session_context.get("conversation_id", "default")
        user_id = session_context.get("user_id")
        self._current_conversation_id = conversation_id
        self._current_user_id = user_id
        
        # 初始化 PromptManager
        ctx = create_runtime_context(session_id=session_id, max_turns=self.max_turns)
        prompt_manager = get_prompt_manager()
        prompt_manager.on_session_start(ctx, conversation_id=conversation_id, user_id=user_id)
        
        if variables:
            prompt_manager.on_context_injected(ctx, variables=variables)
            logger.info(f"✅ 前端变量已注入 Prompt: {list(variables.keys())}")
        
        if self.enable_tracing:
            self._tracer = create_pipeline_tracer(session_id=session_id, conversation_id=conversation_id)
            user_query = messages[-1]["content"] if messages else ""
            self._tracer.set_user_query(user_query[:200])
        
        # ===== 阶段 2: Intent Analysis =====
        intent = self._process_intent(intent, ctx)
        yield await self.broadcaster.emit_message_delta(
            session_id=session_id,
            delta={
                "type": "intent",
                "content": json.dumps({
                    "task_type": intent.task_type.value,
                    "complexity": intent.complexity.value,
                    "needs_plan": intent.needs_plan,
                    "confidence": intent.confidence,
                    "skip_memory_retrieval": intent.skip_memory_retrieval,
                    "source": "routing_layer" if intent else "default"
                }, ensure_ascii=False)
            }
        )
        
        # ===== 阶段 3: Tool Selection =====
        tools_for_llm, selection = await self._select_tools(intent, ctx)
        
        # ===== 阶段 3.5: 沙盒环境预创建 =====
        await self._ensure_sandbox(selection.tool_names, conversation_id, user_id)
        
        # ===== 阶段 4: System Prompt 组装 =====
        user_query = messages[-1]["content"] if messages else ""
        system_prompt = build_system_prompt(
            intent=intent,
            prompt_cache=self.prompt_cache,
            prompt_manager=prompt_manager,
            context_strategy=self.context_strategy,
            system_prompt=self.system_prompt,
            llm_enable_caching=self.llm.config.enable_caching,
            user_id=user_id,
            user_query=user_query,
            ctx=ctx
        )
        
        # 记录已追加的片段
        if isinstance(system_prompt, str):
            appended = prompt_manager.get_appended_fragments(ctx)
            if appended:
                logger.debug(f"📝 已追加的 Prompt 片段: {appended}")
        
        # ===== 阶段 5-6: RVR Loop =====
        async for event in self._run_rvr_loop(
            messages=messages,
            system_prompt=system_prompt,
            tools_for_llm=tools_for_llm,
            ctx=ctx,
            session_id=session_id,
            intent=intent,
            enable_stream=enable_stream
        ):
            yield event
        
        # ===== 阶段 7: Final Output =====
        if self._tracer:
            final_response = ctx.accumulator.get_text_content()
            self._tracer.set_final_response(final_response[:500] if final_response else "")
            self._tracer.finish()
            logger.debug("✅ E2E Pipeline Report 已生成")
        
        # 累积 usage 统计
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
    
    def _process_intent(self, intent: Optional["IntentResult"], ctx) -> "IntentResult":
        """处理意图分析结果"""
        if intent is not None:
            logger.info(
                f"🔀 使用路由层意图结果: {intent.task_type.value}, "
                f"complexity={intent.complexity.value}"
            )
            self._last_intent_result = intent
            
            if self._tracer:
                stage = self._tracer.create_stage("intent_analysis")
                stage.start()
                stage.complete({
                    "task_type": intent.task_type.value,
                    "complexity": intent.complexity.value,
                    "needs_plan": intent.needs_plan,
                    "source": "routing_layer"
                })
            return intent
        
        # 未提供 intent，使用默认配置
        logger.warning("⚠️ 未提供意图结果，使用默认配置")
        from core.agent.types import IntentResult, TaskType, Complexity
        intent = IntentResult(
            task_type=TaskType.GENERAL,
            complexity=Complexity.MEDIUM,
            needs_plan=self.schema.plan_manager.enabled,
            confidence=1.0
        )
        
        if self._tracer:
            stage = self._tracer.create_stage("intent_analysis")
            stage.skip("未提供意图结果，使用默认配置")
        
        return intent
    
    async def _select_tools(self, intent: "IntentResult", ctx):
        """工具选择"""
        if self._tracer:
            tool_stage = self._tracer.create_stage("tool_selection")
            tool_stage.start()
        
        logger.info("🔧 开始工具选择...")
        
        plan = self._plan_cache.get("plan")
        selection_source = "intent"
        use_skill_path = False
        invocation_strategy = None
        
        # V4.4: Skill 路径
        if plan and plan.get('recommended_skill'):
            use_skill_path = True
            selection_source = "skill"
            skill_info = plan.get('recommended_skill')
            skill_name = skill_info.get('name', 'unknown') if isinstance(skill_info, dict) else skill_info
            logger.info(f"🎯 V4.4 Skill 路径: 使用 Claude Skill '{skill_name}'")
            
            invocation_strategy = self.invocation_selector.select_strategy(
                task_type=intent.task_type.value,
                selected_tools=[],
                plan_result=plan
            )
        
        # 确定所需能力
        if self.schema.tools:
            required_capabilities = self.schema.tools
            if not use_skill_path:
                selection_source = "schema"
        elif plan and plan.get('required_capabilities'):
            required_capabilities = plan['required_capabilities']
            if not use_skill_path:
                selection_source = "plan"
        else:
            required_capabilities = self.capability_registry.get_capabilities_for_task_type(
                intent.task_type.value
            )
        
        # 获取可用 API 并选择工具
        available_apis = self.tool_selector.get_available_apis(self.tool_executor)
        selection = self.tool_selector.select(
            required_capabilities=required_capabilities,
            context={"plan": plan, "task_type": intent.task_type.value, "available_apis": available_apis}
        )
        
        # V4.4: Tool 路径
        if not use_skill_path and len(selection.tool_names) > 0:
            total_tools = len(self.capability_registry.get_all_capabilities())
            invocation_strategy = self.invocation_selector.select_strategy(
                task_type=intent.task_type.value,
                selected_tools=selection.tool_names,
                total_available_tools=total_tools,
                plan_result=plan
            )
            if invocation_strategy:
                logger.info(f"🔧 V4.4 Tool 路径: 调用模式={invocation_strategy.type.value}")
                selection_source = f"tool:{invocation_strategy.type.value}"
        
        # 转换为 LLM 格式
        tools_for_llm = self.tool_selector.get_tools_for_llm(selection, self.llm)
        
        # 添加实例级工具
        if hasattr(self, '_instance_registry') and self._instance_registry:
            instance_tools = self._instance_registry.get_tools_for_claude()
            for tool_def in instance_tools:
                tools_for_llm.append(tool_def)
                if tool_def["name"] not in selection.tool_names:
                    selection.tool_names.append(tool_def["name"])
        elif hasattr(self, '_mcp_tools') and self._mcp_tools:
            for mcp_tool in self._mcp_tools:
                mcp_tool_def = {
                    "name": mcp_tool["name"],
                    "description": mcp_tool.get("description", ""),
                    "input_schema": mcp_tool.get("input_schema", {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    })
                }
                tools_for_llm.append(mcp_tool_def)
                if mcp_tool["name"] not in selection.tool_names:
                    selection.tool_names.append(mcp_tool["name"])
        
        logger.info(f"📋 选择工具: {selection.tool_names}")
        
        if self._tracer:
            tool_stage.set_input({
                "required_capabilities": required_capabilities[:5] if required_capabilities else [],
                "selection_source": selection_source,
                "use_skill_path": use_skill_path
            })
            tool_stage.complete({
                "tool_count": len(selection.tool_names),
                "tools": selection.tool_names[:5],
                "invocation_type": invocation_strategy.type.value if invocation_strategy else "skill"
            })
        
        return tools_for_llm, selection
    
    async def _ensure_sandbox(self, tool_names: List[str], conversation_id: str, user_id: str):
        """确保沙盒环境就绪"""
        sandbox_tools = {"bash", "str_replace_based_edit_tool", "text_editor"}
        sandbox_tools.update(t for t in tool_names if t.startswith("sandbox_"))
        needs_sandbox = bool(sandbox_tools & set(tool_names))
        
        if needs_sandbox:
            try:
                from infra.sandbox import get_sandbox_provider
                sandbox = get_sandbox_provider()
                
                if sandbox.is_available:
                    await sandbox.ensure_sandbox(conversation_id, user_id)
                    logger.info(f"🏖️ 沙盒环境已就绪: conversation_id={conversation_id}")
                else:
                    logger.warning("⚠️ 沙盒服务不可用，跳过预创建")
            except Exception as e:
                logger.warning(f"⚠️ 沙盒预创建失败: {e}")
    
    def _get_task_complexity(self, intent):
        """获取任务复杂度（委托给 context 模块）"""
        return get_task_complexity(intent)
    
    def _build_cached_system_prompt(self, intent, ctx, user_id: str = None, user_query: str = None):
        """构建多层缓存 System Prompt（委托给 context 模块）"""
        return build_cached_system_prompt(
            intent=intent,
            prompt_cache=self.prompt_cache,
            context_strategy=self.context_strategy,
            user_id=user_id,
            user_query=user_query
        )
    
    # ===== 辅助属性和方法 =====
    
    @property
    def usage_stats(self) -> dict:
        """获取 usage 统计"""
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
    
    def get_trace_report(self) -> Optional[Dict[str, Any]]:
        """获取追踪报告"""
        if self._tracer:
            return self._tracer.to_dict()
        return None
    
    def set_tracing_enabled(self, enabled: bool):
        """启用或禁用追踪"""
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
        conversation_service: ConversationService 实例
        
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
