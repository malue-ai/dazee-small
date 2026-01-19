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
│  │ ToolSelector │  │  ToolExecutor   │  │
│  └─────────────┘  └─────────────────┘  │
│  ┌─────────────┐  ┌─────────────────┐  │
│  │ EventManager │  │  Broadcaster    │  │
│  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────┘

🆕 V7.0: IntentAnalyzer 已移至路由层 (core/routing/)
"""

# 1. 标准库
import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator

# 2. 第三方库（无）

# 3. 本地模块
from core.agent.types import IntentResult, TaskType, Complexity
from core.agent.content_handler import ContentHandler, create_content_handler
from core.context.runtime import create_runtime_context
from core.context.context_engineering import (
    ContextEngineeringManager, 
    AgentState, 
    create_context_engineering_manager
)
from core.context.compaction import (
    get_context_strategy,
    get_memory_guidance_prompt,
    QoSLevel,
    ContextStrategy
)
from core.context.prompt_manager import get_prompt_manager, get_prompt_manager_async, PromptManager
from core.events.broadcaster import EventBroadcaster
from core.llm import Message, LLMResponse, ToolType, create_claude_service
from core.orchestration import create_pipeline_tracer, E2EPipelineTracer
from core.prompt import TaskComplexity
from core.schemas import DEFAULT_AGENT_SCHEMA
from core.tool import create_tool_executor, create_tool_selector
from core.tool.capability import create_capability_registry, create_invocation_selector
from core.confirmation_manager import get_confirmation_manager, ConfirmationType
from logger import get_logger
from prompts.universal_agent_prompt import get_universal_agent_prompt
from tools.plan_todo_tool import create_plan_todo_tool
from utils.usage_tracker import create_usage_tracker
from utils.message_utils import (
    dict_list_to_messages,
    append_assistant_message,
    append_user_message
)


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
        conversation_service=None,
        schema=None,  # 🆕 AgentSchema 配置
        system_prompt: str = None,  # 🆕 System Prompt（作为运行时指令）
        prompt_schema=None,  # 🆕 V4.6: PromptSchema（提示词分层）
        prompt_cache=None,  # 🆕 V4.6.2: InstancePromptCache（实例缓存）
        apis_config: Optional[List[Dict[str, Any]]] = None  # 🆕 预配置的 APIs（用于 api_calling 自动注入）
    ):
        """
        初始化 Agent
        
        Args:
            model: 模型名称
            max_turns: 最大轮次
            event_manager: EventManager 实例（必需）
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
        self.event_manager = event_manager  # 保留引用（兼容）
        
        # 🆕 Schema 驱动：存储 Schema 配置
        self.schema = schema if schema is not None else DEFAULT_AGENT_SCHEMA
        
        # 🆕 System Prompt：存储系统指令（如果未提供，使用默认）
        self.system_prompt = system_prompt
        
        # 🆕 V4.6: 存储提示词分层配置
        self.prompt_schema = prompt_schema
        self.prompt_cache = prompt_cache
        
        # 🆕 预配置的 APIs（用于 api_calling 工具自动注入认证）
        self.apis_config = apis_config or []
        
        # 🆕 上下文管理策略（三层防护）
        # 配置来源：环境变量 QOS_LEVEL + Schema context_limits 覆盖
        qos_level_str = os.getenv("QOS_LEVEL", "pro")
        try:
            qos_level = QoSLevel(qos_level_str)
        except ValueError:
            qos_level = QoSLevel.PRO
        
        base_strategy = get_context_strategy(qos_level=qos_level)
        
        # 🆕 V7: 使用 Schema 中的 context_limits 覆盖默认策略
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
                # 🆕 从 Schema context_limits 覆盖
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
        
        # 从 Schema 读取运行时参数（覆盖传入的参数）
        if schema is not None:
            self.model = schema.model
            self.max_turns = schema.max_turns
        
        # 🆕 使用 EventBroadcaster 作为事件发送的统一入口
        # 传入 conversation_service 用于自动持久化
        self.broadcaster = EventBroadcaster(event_manager, conversation_service=conversation_service)
        
        # ===== 根据 Schema 动态初始化各模块 =====
        self._init_modules()
        
        # ===== 状态（Context Isolation 原则） =====
        # ⚠️ 这是工具返回值的缓存，不是隐式状态
        # 所有更新都通过 plan_todo 工具显式执行，此处仅缓存以避免重复调用
        # 参考: docs/12-CONTEXT_ENGINEERING_OPTIMIZATION.md
        self._plan_cache = {"plan": None, "todo": None, "tool_calls": []}
        self.invocation_stats = {"direct": 0, "code_execution": 0, "programmatic": 0, "streaming": 0}
        
        # 🆕 V6.1: 上轮意图分析结果（用于追问场景优化）
        # 存储 session 级别的意图结果，追问时复用 task_type
        self._last_intent_result: Optional["IntentResult"] = None
        
        # ===== 🆕 上下文工程管理器 =====
        # 整合 KV-Cache 优化、Todo 重写、工具遮蔽、可恢复压缩、结构化变异、错误保留
        self.context_engineering = create_context_engineering_manager()
        
        # ===== Usage 统计（使用 UsageTracker） =====
        self.usage_tracker = create_usage_tracker()
        
        # ===== 🆕 E2E Pipeline Tracer（V4.2 Code-First 优化） =====
        # 追踪器按 session 创建，在 chat() 中初始化
        self._tracer: Optional[E2EPipelineTracer] = None
        self.enable_tracing = True  # 默认启用追踪
        
        # 🆕 V7.1: 原型标记（由 AgentRegistry 设置）
        self._is_prototype = False
        
        logger.info(f"✅ SimpleAgent 初始化完成 (model={self.model}, schema={self.schema.name})")
    
    def clone_for_session(
        self,
        event_manager,
        conversation_service = None
    ) -> "SimpleAgent":
        """
        🆕 V7.1: 从原型克隆 Agent 实例（快速路径）
        
        复用原型中的重量级组件，仅重置会话级状态
        
        复用的组件（不重新创建）：
        - llm: LLM Service
        - capability_registry: 能力注册表
        - tool_executor: 工具执行器
        - tool_selector: 工具选择器
        - plan_todo_tool: Plan/Todo 工具
        - invocation_selector: 调用模式选择器
        - context_engineering: 上下文工程管理器
        - _instance_registry: 实例级工具注册表
        - _mcp_clients, _mcp_tools: MCP 相关
        
        🆕 V7.0: IntentAnalyzer 已移至路由层，不再在 SimpleAgent 中创建
        
        重置的状态（每个会话独立）：
        - event_manager, broadcaster: 事件管理
        - _plan_cache: Plan 缓存
        - invocation_stats: 调用统计
        - _last_intent_result: 意图结果
        - _tracer: Pipeline 追踪器
        - usage_tracker: Usage 统计
        
        Args:
            event_manager: 事件管理器（必需）
            conversation_service: 会话服务
            
        Returns:
            就绪的 Agent 实例
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
        
        # LLM Services（复用）
        clone.llm = self.llm
        
        # 组件（复用）
        clone.capability_registry = self.capability_registry
        clone.tool_executor = self.tool_executor
        clone.tool_selector = getattr(self, 'tool_selector', None)
        clone.plan_todo_tool = getattr(self, 'plan_todo_tool', None)
        clone.invocation_selector = self.invocation_selector
        clone.context_engineering = self.context_engineering
        
        # 工具配置（复用）
        clone.allow_parallel_tools = self.allow_parallel_tools
        clone.max_parallel_tools = self.max_parallel_tools
        clone._serial_only_tools = self._serial_only_tools
        
        # 实例级工具注册表（复用）
        clone._instance_registry = getattr(self, '_instance_registry', None)
        
        # MCP 相关（复用）
        clone._mcp_clients = getattr(self, '_mcp_clients', [])
        clone._mcp_tools = getattr(self, '_mcp_tools', [])
        
        # Workers 配置（复用）
        clone.workers_config = getattr(self, 'workers_config', [])
        
        # ========== 设置会话级参数 ==========
        clone.event_manager = event_manager
        
        # 更新工具执行器的上下文
        if clone.tool_executor and hasattr(clone.tool_executor, 'update_context'):
            clone.tool_executor.update_context({
                "event_manager": event_manager,
            })
        
        # 创建新的 EventBroadcaster
        clone.broadcaster = EventBroadcaster(
            event_manager,
            conversation_service=conversation_service
        )
        
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
        """
        根据 Schema 动态初始化各独立模块
        
        设计哲学：Schema 驱动组件初始化
        - 如果 Schema 中组件 enabled=False，则不创建该组件
        - 组件配置参数从 Schema 中读取
        """
        # 1. 能力注册表（总是需要）
        self.capability_registry = create_capability_registry()
        
        # 🆕 V7.0: IntentAnalyzer 已移至路由层 (core/routing/router.py)
        # 意图分析在 AgentRouter.route() 中完成，结果通过 intent 参数传入 chat()
        
        # 2. 工具选择器（根据 Schema 决定是否创建）
        if self.schema.tool_selector.enabled:
            self.tool_selector = create_tool_selector(registry=self.capability_registry)
            logger.debug(f"✓ ToolSelector 已启用 (strategy={self.schema.tool_selector.selection_strategy})")
        else:
            self.tool_selector = None
            logger.debug("○ ToolSelector 未启用")
        
        # 4. 工具执行器（总是需要）
        tool_context = {
            "event_manager": self.event_manager,
            "apis_config": self.apis_config,  # 🆕 用于 api_calling 自动注入认证
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
        
        # 6. 🆕 InvocationSelector（V4.4 条件激活）
        # 仅在无匹配 Skill 时生效，选择调用模式（DIRECT/PROGRAMMATIC/TOOL_SEARCH）
        self.invocation_selector = create_invocation_selector(
            enable_tool_search=True,  # 启用 Tool Search（工具数量 > 30 时使用）
            enable_code_execution=True,
            enable_programmatic=True
        )
        logger.debug("✓ InvocationSelector 已初始化（V4.4 条件激活）")
        
        # 7. 执行 LLM（Sonnet）
        # 🆕 V7: 从 Schema 读取 LLM 超参数，未配置则使用默认值
        llm_enable_thinking = self.schema.enable_thinking if self.schema.enable_thinking is not None else True
        llm_enable_caching = self.schema.enable_caching if self.schema.enable_caching is not None else True
        
        # 构建 LLM 参数（仅包含非 None 值）
        llm_kwargs = {
            "model": self.model,
            "enable_thinking": llm_enable_thinking,
            "enable_caching": llm_enable_caching,
            "tools": [ToolType.BASH, ToolType.TEXT_EDITOR, ToolType.WEB_SEARCH],
        }
        
        # 🆕 V7: 仅当 Schema 明确配置时才传递 LLM 超参数
        if self.schema.temperature is not None:
            llm_kwargs["temperature"] = self.schema.temperature
        if self.schema.max_tokens is not None:
            llm_kwargs["max_tokens"] = self.schema.max_tokens
        
        self.llm = create_claude_service(**llm_kwargs)
        
        logger.debug(f"✓ 执行 LLM 初始化: thinking={llm_enable_thinking}, caching={llm_enable_caching}, "
                     f"temperature={self.schema.temperature}, max_tokens={self.schema.max_tokens}")
        
        # 注册自定义工具到 LLM（如果有 plan_todo_tool）
        if self.plan_todo_tool:
            self._register_tools_to_llm()
        
        # 🆕 启用已注册的 Claude Skills
        self._enable_registered_skills()
        
        # 8. 🆕 并行工具执行配置
        self.allow_parallel_tools = self.schema.allow_parallel_tools
        self.max_parallel_tools = self.schema.tool_selector.max_parallel_tools
        # 必须串行执行的特殊工具
        self._serial_only_tools = {"plan_todo", "hitl"}
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
        """
        🆕 启用已注册到 Claude 的 Skills
        
        从 capabilities.yaml 读取已注册的 skill_id，
        调用 LLM service 的 enable_skills 方法激活 Skills Container
        """
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
        intent: Optional["IntentResult"] = None  # 🆕 V7: 从路由层传入的意图结果
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Agent 统一执行入口 - 7 阶段完整流程
        
        完整流程（参考 docs/00-ARCHITECTURE-V4.md L1693-1979）：
        阶段 1: Session/Agent 初始化 (在 SessionService.create_session 中完成)
        阶段 2: Intent Analysis - 使用路由层传入的意图结果（内部意图分析已移除）
        阶段 3: Tool Selection (Schema 驱动优先)
        阶段 4: System Prompt 组装 + LLM 调用准备
        阶段 5: Plan Creation (System Prompt 约束 + Claude 自主触发，在 RVR Turn 1 内部)
        阶段 6: RVR Loop (核心执行)
        阶段 7: Final Output & Tracing Report
        
        本方法从阶段 2 开始（阶段 1 在 SessionService 中完成）
        
        Args:
            messages: 完整的消息列表（已包含前端变量上下文）
            session_id: 会话ID
            message_id: 消息ID（用于事件关联）
            enable_stream: 是否流式输出
            variables: 前端上下文变量（如位置、时区等），直接注入到 Prompt
            intent: V7 从路由层传入的意图分析结果（必需，如未提供则使用默认配置）
            
        Yields:
            事件字典
        """
        messages = messages or []
        self._current_message_id = message_id
        
        # 生成 session_id
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.warning(f"未提供 session_id，生成临时 ID: {session_id}")
        
        # =====================================================================
        # 阶段 1: Session/Agent 初始化
        # =====================================================================
        # 说明: 此阶段在 SessionService.create_session() 中完成
        # 包括: CapabilityRegistry, IntentAnalyzer, ToolSelector, ToolExecutor,
        #       EventBroadcaster, E2EPipelineTracer, Claude Skills 启用
        # 本方法从阶段 2 开始执行
        
        # ===== 初始化会话上下文 =====
        session_context = await self.event_manager.storage.get_session_context(session_id)
        conversation_id = session_context.get("conversation_id", "default")
        user_id = session_context.get("user_id")  # 用于 System Prompt 注入
        # 🆕 前端变量直接从参数传入（不再从 Redis 读取），用于注入 System Prompt
        # 存储为实例变量，供后续使用
        self._current_conversation_id = conversation_id
        self._current_user_id = user_id
        
        # ===== 🆕 初始化 PromptManager（事件驱动 Prompt 追加） =====
        ctx = create_runtime_context(session_id=session_id, max_turns=self.max_turns)
        prompt_manager = await get_prompt_manager_async()  # 使用异步版本确保片段已加载
        
        # 会话开始 → 追加 sandbox_context
        prompt_manager.on_session_start(ctx, conversation_id=conversation_id, user_id=user_id)
        
        if self.enable_tracing:
            self._tracer = create_pipeline_tracer(
                session_id=session_id,
                conversation_id=conversation_id
            )
            # 设置用户 Query
            user_query = messages[-1]["content"] if messages else ""
            self._tracer.set_user_query(user_query[:200])
        
        # =====================================================================
        # 阶段 2: Intent Analysis
        # =====================================================================
        # V7: 意图分析已在路由层完成（AgentRouter），此处仅使用传入的意图结果
        # - 如果提供了 intent 参数（来自路由层），使用它
        # - 如果未提供 intent 参数，使用默认配置（不执行内部分析）
        # =====================================================================
        
        if intent is not None:
            # 使用路由层提供的意图结果
            logger.info(
                f"🔀 使用路由层意图结果: {intent.task_type.value}, "
                f"complexity={intent.complexity.value}"
            )
            # 保存本轮结果供下次追问使用
            self._last_intent_result = intent
            
            # 🆕 V7.5: 发送意图识别结果给前端（使用 intent_id 格式）
            intent_content = {
                "intent_id": intent.intent_id,
                "intent_name": intent.intent_name,
                "complexity": intent.complexity.value,
                "needs_plan": intent.needs_plan,
                "confidence": intent.confidence,
            }
            # 仅当 platform 有值时才添加
            if intent.platform:
                intent_content["platform"] = intent.platform
            
            intent_delta = {
                "type": "intent",
                "content": json.dumps(intent_content, ensure_ascii=False)
            }
            yield await self.broadcaster.emit_message_delta(
                session_id=session_id,
                delta=intent_delta
            )
            
            # 追踪意图分析阶段
            if self._tracer:
                stage = self._tracer.create_stage("intent_analysis")
                stage.start()
                stage.complete({
                    "intent_id": intent.intent_id,
                    "intent_name": intent.intent_name,
                    "complexity": intent.complexity.value,
                    "needs_plan": intent.needs_plan,
                    "source": "routing_layer"
                })
        else:
            # 未提供 intent 参数，使用默认配置（内部意图分析已移除）
            logger.warning("⚠️ 未提供意图结果，使用默认配置（建议启用路由层）")
            intent = IntentResult(
                task_type=TaskType.OTHER,  # 🆕 V7.5: 修复为 OTHER
                complexity=Complexity.MEDIUM,
                needs_plan=self.schema.plan_manager.enabled,
                intent_id=3,              # 🆕 V7.5: 默认综合咨询
                intent_name="综合咨询",    # 🆕 V7.5
                confidence=1.0
            )
            
            # 记录跳过
            if self._tracer:
                stage = self._tracer.create_stage("intent_analysis")
                stage.skip("未提供意图结果，使用默认配置")
        
        # =====================================================================
        # 阶段 3: Tool Selection (Schema 驱动优先)
        # =====================================================================
        # 选择优先级: Schema > Plan > Intent
        # V4.4 双路径分流: Skill 路径 vs Tool 路径
        
        # 🆕 追踪工具选择阶段
        if self._tracer:
            tool_stage = self._tracer.create_stage("tool_selection")
            tool_stage.start()
        
        logger.info("🔧 开始工具选择...")
        
        # 确定所需能力（优先级：Schema > Plan > Intent 推断）
        plan = self._plan_cache.get("plan")
        selection_source = "intent"  # 记录选择来源
        
        # 🆕 V4.4: 检查是否使用 Skill 路径
        use_skill_path = False
        invocation_strategy = None
        
        if plan and plan.get('recommended_skill'):
            # ========== Skill 路径 ==========
            # Plan 匹配到 Skill → 跳过 InvocationSelector → 使用 container.skills
            use_skill_path = True
            selection_source = "skill"
            skill_info = plan.get('recommended_skill')
            skill_name = skill_info.get('name', 'unknown') if isinstance(skill_info, dict) else skill_info
            logger.info(f"🎯 V4.4 Skill 路径: 使用 Claude Skill '{skill_name}'")
            
            # 检查 InvocationSelector 确认跳过
            invocation_strategy = self.invocation_selector.select_strategy(
                task_type=intent.task_type.value,
                selected_tools=[],
                plan_result=plan  # 传入 plan_result 触发跳过逻辑
            )
            if invocation_strategy is None:
                logger.debug("✓ InvocationSelector 已跳过（Skill 路径）")
        
        if self.schema.tools:
            # 优先使用 Schema 配置（Prompt 驱动设计哲学）
            required_capabilities = self.schema.tools
            if not use_skill_path:
                selection_source = "schema"
            logger.debug(f"✓ 使用 Schema 配置的工具: {self.schema.tools}")
        elif plan and plan.get('required_capabilities'):
            # 其次使用 Plan 指定的能力
            required_capabilities = plan['required_capabilities']
            if not use_skill_path:
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
        
        # 🆕 V4.4: Tool 路径 - 启用 InvocationSelector
        if not use_skill_path and len(selection.tool_names) > 0:
            # ========== Tool 路径 ==========
            # 无匹配 Skill → 启用 InvocationSelector → 选择调用模式
            total_tools = len(self.capability_registry.get_all_capabilities())
            invocation_strategy = self.invocation_selector.select_strategy(
                task_type=intent.task_type.value,
                selected_tools=selection.tool_names,
                total_available_tools=total_tools,
                plan_result=plan
            )
            if invocation_strategy:
                logger.info(f"🔧 V4.4 Tool 路径: 调用模式={invocation_strategy.type.value}, 原因={invocation_strategy.reason[:50]}...")
                selection_source = f"tool:{invocation_strategy.type.value}"
        
        # 转换为 LLM 格式
        tools_for_llm = self.tool_selector.get_tools_for_llm(selection, self.llm)
        
        # 🆕 V4.4 优化：从 InstanceToolRegistry 获取实例级工具
        # 统一添加实例级工具（MCP、REST API），确保 Plan 阶段和执行阶段使用相同工具列表
        if hasattr(self, '_instance_registry') and self._instance_registry:
            instance_tools = self._instance_registry.get_tools_for_claude()
            for tool_def in instance_tools:
                tools_for_llm.append(tool_def)
                if tool_def["name"] not in selection.tool_names:
                    selection.tool_names.append(tool_def["name"])
        # 兼容旧逻辑：直接添加 _mcp_tools
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
        
        # 🆕 完成追踪
        if self._tracer:
            tool_stage.set_input({
                "required_capabilities": required_capabilities[:5] if required_capabilities else [],
                "selection_source": selection_source,
                "use_skill_path": use_skill_path  # 🆕 记录路径类型
            })
            tool_stage.complete({
                "tool_count": len(selection.tool_names),
                "tools": selection.tool_names[:5],
                "invocation_type": invocation_strategy.type.value if invocation_strategy else "skill"  # 🆕 记录调用类型
            })
        
        # =====================================================================
        # 阶段 3.5: 沙盒环境预创建（确保后续工具调用有沙盒可用）
        # =====================================================================
        # 检查是否需要沙盒（选择了 bash/text_editor/sandbox_* 等工具）
        sandbox_tools = {"bash", "str_replace_based_edit_tool", "text_editor"}
        sandbox_tools.update(t for t in selection.tool_names if t.startswith("sandbox_"))
        needs_sandbox = bool(sandbox_tools & set(selection.tool_names))
        
        if needs_sandbox:
            try:
                from infra.sandbox import get_sandbox_provider
                sandbox = get_sandbox_provider()
                
                if sandbox.is_available:
                    # 预创建沙盒（后台执行，不阻塞主流程）
                    await sandbox.ensure_sandbox(conversation_id, user_id)
                    logger.info(f"🏖️ 沙盒环境已就绪: conversation_id={conversation_id}")
                else:
                    logger.warning("⚠️ 沙盒服务不可用，跳过预创建")
            except Exception as e:
                # 沙盒预创建失败不阻塞主流程，后续工具调用时会再次尝试
                logger.warning(f"⚠️ 沙盒预创建失败: {e}")
        
        # =====================================================================
        # 阶段 4: System Prompt 组装 + LLM 调用准备
        # =====================================================================
        # 4.1 选择 System Prompt（用户自定义 vs 框架默认，含沙盒上下文注入）
        # 4.2 构建 LLM Messages
        # 4.3 Todo 重写（Context Engineering - 对抗 Lost-in-the-Middle）
        
# 🆕 V4.6: 获取用户当前 query 和 Mem0 检索决策
        user_query = messages[-1]["content"] if messages else ""
        skip_memory = getattr(intent, 'skip_memory_retrieval', False)
        
        # 4.1 选择 System Prompt（🆕 V6.3: 支持多层缓存）
        # 优先级：prompt_cache 多层缓存 > 用户自定义 > 框架默认
        
        # 🆕 V5.1: 获取任务复杂度用于动态路由
        task_complexity = self._get_task_complexity(intent)
        
        # 🆕 V6.3: 使用多层缓存（prompt_cache 可用时）
        use_multi_layer_cache = (
            self.prompt_cache and 
            self.prompt_cache.is_loaded and 
            self.prompt_cache.system_prompt_simple and
            self.llm.config.enable_caching  # 确保 LLM 配置启用了缓存
        )
        
        if use_multi_layer_cache:
            # 🆕 V6.3: 使用多层缓存格式（Layer 1-3: 1h 缓存, Layer 4: 不缓存）
            system_prompt = self._build_cached_system_prompt(
                intent=intent,
                ctx=ctx,
                user_id=user_id,
                user_query=user_query
            )
            logger.info(f"✅ 多层缓存 System Prompt: complexity={task_complexity.value}, "
                       f"layers={len(system_prompt)}")
        elif self.prompt_cache and self.prompt_cache.is_loaded and self.prompt_cache.system_prompt_simple:
            # 单层缓存（向后兼容：LLM 配置未启用缓存）
            base_prompt = self.prompt_cache.get_full_system_prompt(task_complexity)
            system_prompt = prompt_manager.build_system_prompt(ctx, base_prompt=base_prompt)
            
            cached_size = len(self.prompt_cache.get_system_prompt(task_complexity))
            full_size = len(base_prompt)
            logger.info(f"✅ 单层缓存路由: complexity={task_complexity.value}, "
                       f"缓存={cached_size}字符 + 运行时={full_size - cached_size}字符 = {full_size}字符")
        elif self.system_prompt:
            # 使用用户定义的 System Prompt + PromptManager 追加内容
            enhanced_prompt = self.system_prompt
            
            # 🆕 追加 Memory Guidance Prompt（L1 策略，可配置）
            if self.context_strategy.enable_memory_guidance:
                memory_guidance = get_memory_guidance_prompt()
                enhanced_prompt = f"{self.system_prompt}\n\n{memory_guidance}"
            
            system_prompt = prompt_manager.build_system_prompt(ctx, base_prompt=enhanced_prompt)
            logger.info(f"✅ 使用用户定义的 System Prompt + PromptManager 追加 "
                       f"({len(self.system_prompt)}字符, L1={self.context_strategy.enable_memory_guidance})")
        else:
            # 使用框架默认 Prompt（根据意图识别结果决定是否检索 Mem0）+ PromptManager 追加
            base_prompt = get_universal_agent_prompt(
                conversation_id=conversation_id,
                user_id=user_id,
                user_query=user_query,
                skip_memory_retrieval=skip_memory  # 🆕 V4.6: 传递意图识别结果
            )
            system_prompt = prompt_manager.build_system_prompt(ctx, base_prompt=base_prompt)
            if skip_memory:
                logger.info("✅ 使用框架默认 System Prompt + PromptManager（跳过 Mem0 检索）")
            else:
                logger.info("✅ 使用框架默认 System Prompt + PromptManager（已检索 Mem0 画像）")
        
        # 记录已追加的片段（仅字符串模式）
        if isinstance(system_prompt, str):
            appended = prompt_manager.get_appended_fragments(ctx)
            if appended:
                logger.debug(f"📝 已追加的 Prompt 片段: {appended}")
        
        # 4.2 构建 LLM Messages
        llm_messages = dict_list_to_messages(messages)
        
        # 4.3 Todo 重写（Context Engineering）
        # 对抗 "Lost-in-the-Middle" 现象，让任务目标始终在注意力高区
        if self.context_engineering and self._plan_cache.get("plan"):
            prepared_messages = self.context_engineering.prepare_messages_for_llm(
                messages=[{"role": m.role, "content": m.content} for m in llm_messages],
                plan=self._plan_cache.get("plan"),
                inject_plan=True,
                inject_errors=True
            )
            # 转换回 Message 对象
            llm_messages = dict_list_to_messages(prepared_messages)
            logger.debug("✅ Context Engineering: Todo 重写完成，Plan 状态已注入消息末尾")
        
        # =====================================================================
        # 阶段 5: Plan Creation (System Prompt 约束 + Claude 自主触发)
        # =====================================================================
        # 说明: Plan 创建不是框架强制触发，而是由 System Prompt 约束 + Claude 自主决定
        # 
        # 触发机制:
        # - UNIVERSAL_AGENT_PROMPT 强制规则: "复杂任务的第一个工具调用必须是 plan_todo.create_plan()"
        # - Claude 在 RVR Turn 1 根据任务复杂度（complexity=complex）自主判断
        # - IntentAnalyzer 提供 needs_plan 提示作为参考
        # 
        # 执行位置: 阶段 6 (RVR 循环) Turn 1 内部
        # 
        # 验证: 通过 E2EPipelineTracer 检查复杂任务的第一个 tool_call 是否是 plan_todo
        
        # =====================================================================
        # 阶段 6: RVR Loop (核心执行)
        # =====================================================================
        # Read-Reason-Act-Observe-Validate-Write-Repeat 循环
        # [Read] Plan 状态（由 Claude 在 thinking 中读取）
        # [Reason] LLM Extended Thinking
        # [Act] Tool Calls 执行
        # [Observe] 工具结果 + ResultCompactor 精简
        # [Validate] 在 Extended Thinking 中验证
        # [Write] plan_todo.update_step()
        # [Repeat] if stop_reason == "tool_use"
        # 注：RuntimeContext ctx 已在阶段 1 初始化（与 PromptManager 一起）
        
        for turn in range(self.max_turns):
            ctx.next_turn()
            logger.info(f"{'='*60}")
            logger.info(f"🔄 Turn {turn + 1}/{self.max_turns}")
            logger.info(f"{'='*60}")
            
            # --------- RVR 子步骤 ---------
            # [Read] Plan 状态（由 Claude 在 Extended Thinking 中读取 plan_todo.get_plan()）
            # [Reason] LLM Extended Thinking（深度推理，选择工具和参数）
            # [Act] Tool Calls（执行选定的工具）
            # [Observe] 工具结果（ResultCompactor 自动精简）
            # [Validate] 在下一轮 thinking 中验证结果质量 
            # [Write] 更新状态（plan_todo.update_step()）
            # [Repeat] 如果 stop_reason == "tool_use" 则继续循环
            
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
                    # 🆕 阶段 5 验证: 检查复杂任务是否在第一轮创建 Plan
                    if turn == 0 and intent.needs_plan and response.tool_calls:
                        first_tool_name = response.tool_calls[0].get('name', '')
                        if first_tool_name == 'plan_todo':
                            first_operation = response.tool_calls[0].get('input', {}).get('operation', '')
                            if first_operation == 'create_plan':
                                logger.info("✅ 阶段 5 验证通过: 复杂任务第一个工具调用是 plan_todo.create_plan()")
                            else:
                                logger.warning(f"⚠️ 阶段 5 异常: plan_todo 操作不是 create_plan，实际: {first_operation}")
                        else:
                            logger.warning(f"⚠️ 阶段 5 异常: 复杂任务未创建 Plan！第一个工具: {first_tool_name}")
                            if self._tracer:
                                self._tracer.add_warning(f"Plan Creation 跳过: 第一个工具是 {first_tool_name}")
                    
                    # 处理工具调用
                    if response.stop_reason == "tool_use" and response.tool_calls:
                        # 🆕 最后一轮检查：如果是最后一轮且有工具调用，强制生成文本回复
                        is_last_turn = (turn == self.max_turns - 1)
                        if is_last_turn:
                            logger.warning(f"⚠️ 最后一轮（Turn {turn + 1}）收到工具调用，强制生成文本回复...")
                            # 添加当前响应作为 assistant 消息
                            append_assistant_message(llm_messages, response.raw_content)
                            
                            # 🔧 修复：必须为每个 tool_use 提供 tool_result，否则 Claude API 会报错
                            # Claude API 要求：每个 tool_use 后面必须紧跟包含对应 tool_result 的 user 消息
                            tool_results_for_last_turn = []
                            for tc in response.tool_calls:
                                if tc.get("type") == "tool_use":
                                    tool_results_for_last_turn.append({
                                        "type": "tool_result",
                                        "tool_use_id": tc.get("id"),
                                        "content": json.dumps({
                                            "error": "已达到最大执行轮次，工具未执行",
                                            "status": "skipped"
                                        }, ensure_ascii=False),
                                        "is_error": True
                                    })
                            
                            # 添加 tool_result + 系统提示
                            user_content = tool_results_for_last_turn + [{
                                "type": "text",
                                "text": "⚠️ 系统提示：已达到最大执行轮次，无法继续执行工具。请直接给用户一个文字回复，总结当前进度和已完成的工作。"
                            }]
                            append_user_message(llm_messages, user_content)
                            
                            # 再调用一次 LLM，不传递 tools 参数，强制生成文本
                            async for event in self._process_stream(
                                llm_messages, system_prompt, [], ctx, session_id  # 空 tools 列表
                            ):
                                yield event
                            # 标记完成
                            final_response = ctx.last_llm_response
                            if final_response:
                                ctx.set_completed(final_response.content, "max_turns_reached")
                            break
                        
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
                        
                        if client_tools:
                            # 执行客户端工具，发送事件给前端
                            async for tool_event in self._execute_tools_stream(
                                client_tools, session_id, ctx
                            ):
                                yield tool_event
                        
                        # 从 ContentAccumulator 获取 tool_results（流式和非流式统一处理）
                        tool_results = []
                        if client_tools:
                            accumulator = self.broadcaster.get_accumulator(session_id)
                            if accumulator:
                                client_tool_ids = {tc.get("id") for tc in client_tools}
                                for block in accumulator.all_blocks:
                                    if block.get("type") == "tool_result" and block.get("tool_use_id") in client_tool_ids:
                                        # 移除 index 字段（Claude API 不接受）
                                        clean_block = {k: v for k, v in block.items() if k != "index"}
                                        tool_results.append(clean_block)
                        
                        # 更新消息（用于下一轮 LLM 调用）
                        append_assistant_message(llm_messages, response.raw_content)
                        
                        # 🔒 兜底逻辑：确保每个 tool_use 都有对应的 tool_result
                        # 如果工具执行失败或事件收集失败，生成错误 tool_result
                        if client_tools:
                            collected_ids = {tr.get("tool_use_id") for tr in tool_results}
                            for tc in client_tools:
                                tool_id = tc.get("id")
                                if tool_id and tool_id not in collected_ids:
                                    logger.warning(f"⚠️ 工具 {tc.get('name')} (id={tool_id}) 缺少 tool_result，添加兜底结果")
                                    tool_results.append({
                                        "type": "tool_result",
                                        "tool_use_id": tool_id,
                                        "content": json.dumps({"error": "工具执行结果未收集到，请重试"}),
                                        "is_error": True
                                    })
                        
                        # 只有当有客户端工具时才添加 user message（现在 tool_results 一定不为空）
                        if client_tools and tool_results:
                            append_user_message(llm_messages, tool_results)
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
                
                # 🆕 最后一轮检查：如果是最后一轮且有工具调用，强制生成文本回复
                is_last_turn = (turn == self.max_turns - 1)
                if is_last_turn:
                    logger.warning(f"⚠️ 最后一轮（Turn {turn + 1}）收到工具调用，强制生成文本回复...")
                    append_assistant_message(llm_messages, response.raw_content)
                    
                    # 🔧 修复：必须为每个 tool_use 提供 tool_result，否则 Claude API 会报错
                    # Claude API 要求：每个 tool_use 后面必须紧跟包含对应 tool_result 的 user 消息
                    tool_results_for_last_turn = []
                    for tc in response.tool_calls:
                        if tc.get("type") == "tool_use":
                            tool_results_for_last_turn.append({
                                "type": "tool_result",
                                "tool_use_id": tc.get("id"),
                                "content": json.dumps({
                                    "error": "已达到最大执行轮次，工具未执行",
                                    "status": "skipped"
                                }, ensure_ascii=False),
                                "is_error": True
                            })
                    
                    # 添加 tool_result + 系统提示
                    user_content = tool_results_for_last_turn + [{
                        "type": "text",
                        "text": "⚠️ 系统提示：已达到最大执行轮次，无法继续执行工具。请直接给用户一个文字回复，总结当前进度和已完成的工作。"
                    }]
                    append_user_message(llm_messages, user_content)
                    
                    # 再调用一次 LLM，不传递 tools 参数
                    final_response = await self.llm.create_message_async(
                        messages=llm_messages,
                        system=system_prompt,
                        tools=[]  # 空 tools 列表，强制文本回复
                    )
                    self.usage_tracker.accumulate(final_response)
                    if final_response.content:
                        yield {"type": "content", "data": {"text": final_response.content}}
                    ctx.set_completed(final_response.content, "max_turns_reached")
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
                
                append_assistant_message(llm_messages, response.raw_content)
                
                if client_tools:
                    # 只执行客户端工具
                    tool_results = await self._execute_tools(client_tools, session_id, ctx)
                    append_user_message(llm_messages, tool_results)
            
            if ctx.is_completed():
                break
        
        # =====================================================================
        # 阶段 7: Final Output & Tracing Report
        # =====================================================================
        # 7.1 生成最终响应 (在 RVR 循环中已完成)
        # 7.2 发送完成事件
        # 7.3 E2E Pipeline Report
        
        # 7.3 完成追踪并生成报告
        if self._tracer:
            final_response = ctx.accumulator.get_text_content()
            self._tracer.set_final_response(final_response[:500] if final_response else "")
            self._tracer.finish()
            logger.debug("✅ E2E Pipeline Report 已生成")
        
        # 7.4 发送完成事件并累积 usage 统计
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
    
    def _get_task_complexity(self, intent):
        """
        🆕 V5.1: 从意图识别结果获取任务复杂度
        
        Args:
            intent: IntentResult 对象
            
        Returns:
            TaskComplexity 枚举值
        """
        if intent is None:
            return TaskComplexity.MEDIUM  # 默认中等复杂度
        
        # 从 intent 获取复杂度字符串
        complexity_str = getattr(intent, 'complexity', 'medium')
        if complexity_str is None:
            complexity_str = 'medium'
        
        # 如果是枚举类型，获取其值
        if hasattr(complexity_str, 'value'):
            complexity_str = complexity_str.value
        
        # 映射到 TaskComplexity 枚举
        complexity_map = {
            'simple': TaskComplexity.SIMPLE,
            'low': TaskComplexity.SIMPLE,
            'medium': TaskComplexity.MEDIUM,
            'high': TaskComplexity.COMPLEX,
            'complex': TaskComplexity.COMPLEX,
        }
        
        return complexity_map.get(complexity_str.lower(), TaskComplexity.MEDIUM)
    
    def _build_cached_system_prompt(
        self,
        intent,
        ctx,
        user_id: str = None,
        user_query: str = None
    ) -> List[Dict[str, Any]]:
        """
        构建多层缓存的系统提示词（用于 Claude Prompt Caching）
        
        缓存策略：
        - Layer 1: 框架规则（1h 缓存）
        - Layer 2: 实例提示词（1h 缓存）
        - Layer 3: Skills + 工具（1h 缓存）
        - Layer 4: Mem0 用户画像（不缓存）
        
        Args:
            intent: IntentResult 对象
            ctx: RuntimeContext
            user_id: 用户 ID（用于 Mem0 检索）
            user_query: 用户查询（用于 Mem0 语义检索）
            
        Returns:
            List[Dict] - Claude API 的 system blocks 格式
        """
        # 获取任务复杂度
        task_complexity = self._get_task_complexity(intent)
        
        # 检查是否跳过 Mem0 检索
        skip_memory = getattr(intent, 'skip_memory_retrieval', False)
        
        # 获取 Mem0 用户画像（仅当未跳过检索时）
        user_profile = None
        if not skip_memory and user_id and user_query:
            try:
                from prompts.universal_agent_prompt import _fetch_user_profile
                user_profile = _fetch_user_profile(user_id, user_query)
                if user_profile:
                    logger.debug(f"📝 Mem0 用户画像: {len(user_profile)} 字符")
            except Exception as e:
                logger.warning(f"⚠️ Mem0 检索失败: {e}")
        
        # 优先使用 prompt_cache 的多层缓存构建方法
        if self.prompt_cache and self.prompt_cache.is_loaded and self.prompt_cache.system_prompt_simple:
            system_blocks = self.prompt_cache.get_cached_system_blocks(
                complexity=task_complexity,
                user_profile=user_profile
            )
            
            # 🆕 追加 Memory Guidance Prompt（L1 策略：指导 Claude 使用 Memory Tool）
            # 可通过实例配置 context_management.enable_memory_guidance 控制
            if self.context_strategy.enable_memory_guidance:
                system_blocks.append({
                    "type": "text",
                    "text": f"\n\n{get_memory_guidance_prompt()}"
                    # 不添加 cache_control，每次都更新
                })
            
            logger.info(f"✅ 多层缓存 System Prompt: complexity={task_complexity.value}, "
                       f"layers={len(system_blocks)} (含 Context Awareness)")
            
            return system_blocks
        
        # Fallback: 使用框架默认 Prompt（单层缓存）
        base_prompt = get_universal_agent_prompt(
            user_id=user_id,
            user_query=user_query,
            skip_memory_retrieval=skip_memory
        )
        
        # 🆕 追加 Memory Guidance Prompt（L1 策略）
        memory_guidance = get_memory_guidance_prompt()
        full_prompt = f"{base_prompt}\n\n{memory_guidance}"
        
        # 单层格式（向后兼容）
        # 🔧 不在这里添加 cache_control，由 claude.py 统一处理
        system_blocks = [{
            "type": "text",
            "text": full_prompt
        }]
        
        logger.info(f"✅ System Prompt (fallback): {len(base_prompt)} 字符")
        
        return system_blocks
    
    async def _process_stream(
        self,
        messages: List,
        system_prompt,
        tools: List,
        ctx,
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理流式 LLM 响应
        
        使用 ContentHandler 的手动控制模式（start_block, send_delta, stop_block）
        处理 LLM 的流式输出（thinking, text, tool_use）
        
        Extended Thinking 由 LLM Service 配置和 System Prompt 控制
        """
        # 创建 ContentHandler（手动控制模式）
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        stream_generator = self.llm.create_message_stream(
            messages=messages,
            system=system_prompt,
            tools=tools
        )
        
        final_response = None
        
        async for llm_response in stream_generator:
            # ===== 处理 thinking =====
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
                # ContentAccumulator 通过 EventBroadcaster 自动累积
            
            # ===== 处理 content（text） =====
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
                # ContentAccumulator 通过 EventBroadcaster 自动累积
            
            # ===== 处理流式工具调用 - tool_use 开始 =====
            if llm_response.tool_use_start and llm_response.is_stream:
                tool_info = llm_response.tool_use_start
                tool_type = tool_info.get("type", "tool_use")
                
                # 每个新的 tool_use 都开启新的 block
                # start_block 会自动关闭前一个 block
                yield await content_handler.start_block(
                    session_id=session_id,
                    block_type=tool_type,
                    initial={
                        "id": tool_info.get("id", ""),
                        "name": tool_info.get("name", ""),
                        "input": {}  # input 后续流式发送
                    }
                )
            
            # ===== 处理流式工具调用 - 参数增量 =====
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
        
        # 保存最终响应到 ctx（供 RVR 循环使用）
        if final_response:
            # 🔢 累积 usage 统计
            self.usage_tracker.accumulate(final_response)
            # 存到 ctx，不再通过事件传递
            ctx.last_llm_response = final_response
    
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
        - hitl：HITL 工具，等待用户响应
        
        Args:
            tool_call: 工具调用信息 {id, name, input}
            session_id: 会话ID
            ctx: RuntimeContext（可选，用于 PromptManager）
            
        Returns:
            执行结果字典: {
                tool_id: str,
                tool_name: str,
                tool_input: dict,
                result: Any,
                is_error: bool,
                error_msg: Optional[str]
            }
        """
        tool_name = tool_call['name']
        tool_input = tool_call['input'] or {}
        tool_id = tool_call['id']
        
        logger.debug(f"🔧 执行工具: {tool_name}")
        
        try:
            # 🛡️ 为工具注入上下文（user_id, session_id, conversation_id）
            session_context = await self.event_manager.storage.get_session_context(session_id)
            tool_input.setdefault("session_id", session_id)
            if session_context.get("user_id"):
                tool_input.setdefault("user_id", session_context.get("user_id"))
            conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
            tool_input.setdefault("conversation_id", conv_id)
            
            # ===== 特殊工具处理 =====
            if tool_name == "plan_todo":
                # plan_todo 工具需要 current_plan 参数
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
            
            elif tool_name == "hitl":
                # HITL 工具：等待用户响应
                result = await self._handle_hitl(
                    tool_input=tool_input,
                    session_id=session_id,
                    tool_id=tool_id
                )
            
            else:
                # ===== 通用工具执行 =====
                result = await self.tool_executor.execute(tool_name, tool_input)
            
            # 触发 PromptManager（如 RAG 上下文追加）
            if ctx:
                (await get_prompt_manager_async()).on_tool_result(ctx, tool_name=tool_name, result=result)
            
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
            if self.context_engineering:
                self.context_engineering.record_error(
                    tool_name=tool_name,
                    error=e,
                    input_params=tool_input
                )
                logger.debug(f"📝 错误保留: {tool_name} 错误已记录")
            
            return {
                "tool_id": tool_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "result": {"error": str(e)},
                "is_error": True,
                "error_msg": error_msg
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
                # 超出限制的工具放回串行队列
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
                    results[tool_id] = {
                        "tool_id": tool_id,
                        "tool_name": tc['name'],
                        "tool_input": tc.get('input', {}),
                        "result": {"error": str(result)},
                        "is_error": True,
                        "error_msg": f"工具执行失败: {str(result)}"
                    }
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
        ctx  # RuntimeContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行工具调用并发送 SSE 事件（统一入口）
        
        使用 ContentHandler 发送事件，使用 _execute_tools_core 执行工具。
        支持：
        - 并行执行（可并行的工具使用 asyncio.gather）
        - 流式工具执行（支持 execute_stream 的工具）
        - 特殊工具（plan_todo, hitl）
        
        事件序列：content_start → content_stop（非流式）
                或 content_start → content_delta × N → content_stop（流式工具）
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话ID
            ctx: RuntimeContext
            
        Yields:
            content_start, content_delta, content_stop 等事件
        """
        # 创建 ContentHandler
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        # 分离流式工具和普通工具
        stream_tools = []
        normal_tools = []
        
        for tc in tool_calls:
            tool_name = tc.get('name', '')
            # 串行工具或支持流式的工具需要特殊处理
            if tool_name in self._serial_only_tools or self.tool_executor.supports_stream(tool_name):
                stream_tools.append(tc)
            else:
                normal_tools.append(tc)
        
        # ===== 先执行可并行的普通工具（批量执行，不发送事件） =====
        normal_results = {}
        if normal_tools:
            normal_results = await self._execute_tools_core(normal_tools, session_id, ctx)
        
        # ===== 按原始顺序发送事件 =====
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            # 检查是否是已执行的普通工具
            if tool_id in normal_results:
                result_info = normal_results[tool_id]
                result = result_info.get("result", {})
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                
                # 使用 ContentHandler 发送 tool_result（非流式）
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
            
            # 追踪工具执行
            if self._tracer:
                self._tracer.log_tool_call(tool_name)
            
            # 检测是否支持流式执行
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
                
                # 使用 ContentHandler 发送流式 tool_result
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
                
                # 触发 PromptManager
                (await get_prompt_manager_async()).on_tool_result(ctx, tool_name=tool_name, result={"streamed": True})
            else:
                # ===== 串行工具执行（plan_todo, HITL 等）=====
                result_info = await self._execute_single_tool(tool_call, session_id, ctx)
                result = result_info.get("result", {})
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                
                # 使用 ContentHandler 发送 tool_result（非流式）
                yield await content_handler.emit_block(
                    session_id=session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": tool_id,
                        "content": result_content,
                        "is_error": result_info.get("is_error", False)
                    }
                )
    
    async def _handle_hitl(
        self,
        tool_input: Dict[str, Any],
        session_id: str,
        tool_id: str
    ) -> Dict[str, Any]:
        """
        处理 HITL（Human-in-the-Loop）请求
        
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
            用户输入结果
        """
        # 1. 解析参数
        title = tool_input.get("title", "")
        input_type_str = tool_input.get("input_type", "form")
        questions = tool_input.get("questions")
        description = tool_input.get("description", "")
        timeout = tool_input.get("timeout", 120)
        
        # 解析输入类型
        try:
            input_type = ConfirmationType(input_type_str)
        except ValueError:
            input_type = ConfirmationType.FORM
        
        logger.info(f"🤝 HITL 请求: type={input_type_str}, title={title[:50]}...")
        
        # 2. 创建确认请求
        manager = get_confirmation_manager()
        
        metadata = {}
        if description:
            metadata["description"] = description
        if input_type == ConfirmationType.FORM:
            metadata["questions"] = questions or []
        
        request = manager.create_request(
            question=title,
            options=None,
            timeout=timeout,
            confirmation_type=input_type,
            session_id=session_id,
            metadata=metadata
        )
        
        logger.info(f"✅ HITL 请求已创建: request_id={request.request_id}")
        
        # 3. 通过 EventBroadcaster 发送 SSE 事件到前端
        await self.broadcaster.emit_confirmation_request(
            session_id=session_id,
            request_id=request.request_id,
            question=title,
            options=None,
            confirmation_type=input_type_str,
            timeout=timeout,
            description=description,
            questions=questions if input_type == ConfirmationType.FORM else None,
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
        if input_type == ConfirmationType.FORM and isinstance(response, str):
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
        
        使用 ContentHandler 统一发送事件。
        
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
        # 创建 ContentHandler
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        for block in raw_content:
            block_type = block.get("type", "")
            
            # 处理 server_tool_use → 转换为 tool_use
            if block_type == "server_tool_use":
                # 使用 ContentHandler 发送 tool_use（非流式）
                yield await content_handler.emit_block(
                    session_id=session_id,
                    block_type="tool_use",
                    content={
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "input": block.get("input", {})
                    }
                )
                logger.debug(f"🌐 发送服务端工具调用事件（统一为 tool_use）: {block.get('name')}")
            
            # 处理 *_tool_result → 转换为 tool_result
            elif block_type.endswith("_tool_result") and block_type != "tool_result":
                # 处理 content 字段（可能是列表或字符串）
                # 注意：Anthropic SDK 返回的对象（如 WebSearchResultBlock）不能直接 JSON 序列化
                content = block.get("content", [])
                if isinstance(content, list):
                    # 提取文本内容
                    text_parts = []
                    for item in content:
                        # 处理字典类型
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                            elif item.get("type") == "web_search_result":
                                # 格式化搜索结果
                                title = item.get("title", "")
                                url = item.get("url", "")
                                text_parts.append(f"[{title}]({url})")
                        # 处理 Anthropic SDK 对象
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
                            # 旧版 Pydantic 对象
                            dumped = item.to_dict()
                            text_parts.append(str(dumped))
                        else:
                            # 其他类型，尝试字符串化
                            text_parts.append(str(item))
                    content_str = "\n".join(text_parts) if text_parts else "[服务端工具结果]"
                else:
                    content_str = str(content)
                
                # 使用 ContentHandler 发送 tool_result（非流式）
                yield await content_handler.emit_block(
                    session_id=session_id,
                    block_type="tool_result",
                    content={
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": content_str,
                        "is_error": False
                    }
                )
                logger.debug(f"🌐 发送服务端工具结果事件（统一为 tool_result）: {block_type}")
    
    async def _execute_tools(
        self,
        tool_calls: List[Dict],
        session_id: str,
        ctx  # RuntimeContext
    ) -> List[Dict]:
        """
        执行工具调用（非流式模式，返回结果列表）
        
        使用 ContentHandler 发送 tool_use 和 tool_result 事件。
        支持并行执行（与 _execute_tools_stream 共享 _execute_tools_core）。
        
        Args:
            tool_calls: 工具调用列表
            session_id: 会话ID
            ctx: RuntimeContext（用于管理 block 索引）
            
        Returns:
            工具结果列表
        """
        # 创建 ContentHandler
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        results = []
        
        # 追踪工具调用
        for tc in tool_calls:
            if self._tracer:
                self._tracer.log_tool_call(tc['name'])
        
        # 发送所有 tool_use 事件（非流式模式需要显式发送）
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
        
        # 执行所有工具（支持并行）
        execution_results = await self._execute_tools_core(tool_calls, session_id, ctx)
        
        # 按原始顺序发送 tool_result 事件
        for tool_call in tool_calls:
            tool_id = tool_call['id']
            result_info = execution_results.get(tool_id, {})
            result = result_info.get("result", {})
            result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            is_error = result_info.get("is_error", False)
            
            # 使用 ContentHandler 发送 tool_result（非流式）
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
    
    # ==================== Agent 池化支持 ====================
    
    def clone(
        self,
        event_manager,
        conversation_service = None
    ) -> "SimpleAgent":
        """
        克隆 Agent（复用重组件，重置会话状态）
        
        用于 Agent 池化优化：预创建 Agent 原型，每次请求时克隆而非重新创建，
        避免重复初始化带来的 50-100ms 延迟。
        
        复用（避免重复初始化）：
        - llm: LLM Service（HTTP 客户端）
        - capability_registry: 工具注册表
        - tool_selector, tool_executor: 工具组件
        - plan_todo_tool, invocation_selector
        - _instance_registry, _mcp_clients, _mcp_tools
        
        重置（每次请求独立）：
        - _plan_cache, _last_intent_result, _tracer
        - usage_tracker, context_engineering
        - event_manager, broadcaster
        
        Args:
            event_manager: 事件管理器（必需，每次请求独立）
            conversation_service: 会话服务
            
        Returns:
            克隆后的 Agent 实例
        """
        cloned = object.__new__(SimpleAgent)
        
        # 复用静态配置
        cloned.model = self.model
        cloned.max_turns = self.max_turns
        cloned.schema = self.schema
        cloned.system_prompt = self.system_prompt
        cloned.prompt_schema = self.prompt_schema
        cloned.prompt_cache = self.prompt_cache
        cloned.apis_config = self.apis_config
        cloned.context_strategy = self.context_strategy
        cloned.allow_parallel_tools = self.allow_parallel_tools
        cloned.max_parallel_tools = self.max_parallel_tools
        cloned._serial_only_tools = self._serial_only_tools
        cloned.enable_tracing = self.enable_tracing
        
        # 复用重组件（核心优化点，避免重复创建）
        cloned.capability_registry = self.capability_registry
        cloned.tool_selector = self.tool_selector
        cloned.tool_executor = self.tool_executor
        cloned.plan_todo_tool = self.plan_todo_tool
        cloned.invocation_selector = self.invocation_selector
        cloned.llm = self.llm
        cloned._instance_registry = getattr(self, '_instance_registry', None)
        cloned._mcp_clients = getattr(self, '_mcp_clients', [])
        cloned._mcp_tools = getattr(self, '_mcp_tools', [])
        
        # 注入会话级依赖
        cloned.event_manager = event_manager
        cloned.broadcaster = EventBroadcaster(
            event_manager,
            conversation_service=conversation_service
        )
        
        # 重置会话状态
        cloned._reset_session_state()
        
        logger.debug(f"Agent 克隆完成: model={cloned.model}, schema={cloned.schema.name}")
        
        return cloned
    
    def _reset_session_state(self):
        """
        重置会话级状态（每次请求独立）
        
        在 clone() 时调用，确保每次请求的状态隔离
        """
        self._plan_cache = {"plan": None, "todo": None, "tool_calls": []}
        self._last_intent_result = None
        self._tracer = None
        self.usage_tracker = create_usage_tracker()
        self.context_engineering = create_context_engineering_manager()
        self.invocation_stats = {
            "direct": 0, 
            "code_execution": 0, 
            "programmatic": 0, 
            "streaming": 0
        }


def create_simple_agent(
    model: str = "claude-sonnet-4-5-20250929",
    event_manager=None,
    conversation_service=None
) -> SimpleAgent:
    """
    创建 SimpleAgent
    
    Args:
        model: 模型名称
        event_manager: EventManager 实例（必需）
        conversation_service: ConversationService 实例（用于消息持久化）
        
    Returns:
        SimpleAgent 实例
    """
    if event_manager is None:
        raise ValueError("event_manager 是必需参数")
    
    return SimpleAgent(
        model=model,
        event_manager=event_manager,
        conversation_service=conversation_service
    )

