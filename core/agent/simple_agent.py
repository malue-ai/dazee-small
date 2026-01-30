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
    ContextStrategy,
    trim_by_token_budget,
    trim_history_messages,
    estimate_tokens
)
from core.context.prompt_manager import get_prompt_manager, get_prompt_manager_async, PromptManager
from core.events.broadcaster import EventBroadcaster
from core.llm import Message, LLMResponse, ToolType, create_llm_service
from core.orchestration import create_pipeline_tracer, E2EPipelineTracer
from core.prompt import TaskComplexity
from core.schemas import DEFAULT_AGENT_SCHEMA
from core.tool import create_tool_executor, create_tool_selector
from core.tool.capability import create_capability_registry, create_invocation_selector
from core.tool.registry_config import get_sandbox_tools  # 🆕 从统一配置读取
from logger import get_logger
from prompts.universal_agent_prompt import get_universal_agent_prompt
from core.billing.tracker import create_enhanced_usage_tracker
from tools.plan_todo_tool import load_plan_for_session
from utils.message_utils import (
    dict_list_to_messages,
    append_assistant_message,
    append_user_message,
    extract_text_from_message
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
        apis_config: Optional[List[Dict[str, Any]]] = None,  # 🆕 预配置的 APIs（用于 api_calling 自动注入）
        usage_tracker=None  # 🆕 共享 Tracker 方案：支持外部注入 Tracker
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
            usage_tracker: EnhancedUsageTracker 实例（可选，用于共享计费追踪）
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
                # 🆕 纯 token 驱动的裁剪配置
                preserve_first_messages=base_strategy.preserve_first_messages,
                preserve_last_messages=base_strategy.preserve_last_messages,
                preserve_tool_results=base_strategy.preserve_tool_results,
                trim_threshold=base_strategy.trim_threshold,
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
        
        # ===== 状态 =====
        self.invocation_stats = {"direct": 0, "code_execution": 0, "programmatic": 0, "streaming": 0}
        
        # 🆕 V6.1: 上轮意图分析结果（用于追问场景优化）
        # 存储 session 级别的意图结果，追问时复用 task_type
        self._last_intent_result: Optional["IntentResult"] = None
        
        # ===== 🆕 上下文工程管理器 =====
        # 整合 KV-Cache 优化、Todo 重写、工具遮蔽、可恢复压缩、结构化变异、错误保留
        self.context_engineering = create_context_engineering_manager()
        
        # ===== # Usage 统计（使用增强版，支持工具调用计费） =====
        # 🆕 共享 Tracker 方案：优先使用注入的 Tracker，否则创建新的（向后兼容）
        self.usage_tracker = usage_tracker if usage_tracker is not None else create_enhanced_usage_tracker()
        if usage_tracker is not None:
            logger.debug(f"✅ Agent 使用共享 Tracker: {id(self.usage_tracker)}")
        
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
        - invocation_selector: 调用模式选择器
        - context_engineering: 上下文工程管理器
        - _instance_registry: 实例级工具注册表
        - _mcp_clients, _mcp_tools: MCP 相关
        
        🆕 V7.0: IntentAnalyzer 已移至路由层，不再在 SimpleAgent 中创建
        
        重置的状态（每个会话独立）：
        - event_manager, broadcaster: 事件管理
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
            clone.tool_executor.update_context(event_manager=event_manager)
        
        # 创建新的 EventBroadcaster
        clone.broadcaster = EventBroadcaster(
            event_manager,
            conversation_service=conversation_service
        )
        
        # ========== 重置会话级状态 ==========
        clone.invocation_stats = {"direct": 0, "code_execution": 0, "programmatic": 0, "streaming": 0}
        clone._last_intent_result = None
        clone._tracer = None
        clone.enable_tracing = True
        clone._current_message_id = None
        clone._current_conversation_id = None
        clone._current_user_id = None
        
        # 创建新的 EnhancedUsageTracker（支持工具调用计费）
        clone.usage_tracker = create_enhanced_usage_tracker()
        
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
        from core.tool.base import create_tool_context
        tool_context = create_tool_context(
            event_manager=self.event_manager,
            apis_config=self.apis_config,
        )
        self.tool_executor = create_tool_executor(
            self.capability_registry,
            tool_context=tool_context
        )
        
        # 5. 🆕 InvocationSelector（V4.4 条件激活）
        # 仅在无匹配 Skill 时生效，选择调用模式（DIRECT/PROGRAMMATIC/TOOL_SEARCH）
        self.invocation_selector = create_invocation_selector(
            enable_tool_search=True,  # 启用 Tool Search（工具数量 > 30 时使用）
            enable_code_execution=True,
            enable_programmatic=True
        )
        logger.debug("✓ InvocationSelector 已初始化（V4.4 条件激活）")
        
        # 7. 执行 LLM（Sonnet）
        # 🆕 V7.10: 从 LLM Profile 加载配置（支持多模型容灾）
        from config.llm_config import get_llm_profile
        
        # 加载 main_agent 的 LLM 配置（包括 fallbacks 和 policy）
        llm_config = get_llm_profile("main_agent")
        
        # 🆕 V7: 从 Schema 读取 LLM 超参数，覆盖 Profile 默认值
        if self.schema.enable_thinking is not None:
            llm_config["enable_thinking"] = self.schema.enable_thinking
        if self.schema.enable_caching is not None:
            llm_config["enable_caching"] = self.schema.enable_caching
        if self.schema.temperature is not None:
            llm_config["temperature"] = self.schema.temperature
        if self.schema.max_tokens is not None:
            llm_config["max_tokens"] = self.schema.max_tokens
        
        # 添加内置工具（Schema 中的 tools 配置会在后面注册）
        llm_config["tools"] = [ToolType.BASH, ToolType.TEXT_EDITOR]
        
        # 创建 LLM Service（可能是 ModelRouter 或单个 LLM Service）
        self.llm = create_llm_service(**llm_config)
        
        logger.debug(
            f"✓ 执行 LLM 初始化: profile=main_agent, "
            f"thinking={llm_config.get('enable_thinking')}, "
            f"caching={llm_config.get('enable_caching')}, "
            f"temperature={self.schema.temperature}, "
            f"max_tokens={self.schema.max_tokens}"
        )
        
        # 注册自定义工具到 LLM
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
            self.llm.add_custom_tool(
                name=schema['name'],
                description=schema['description'],
                input_schema=schema['input_schema']
            )
    
    def _enable_registered_skills(self):
        """
        🆕 启用已注册到 Claude 的 Skills
        
        Skills 来源优先级：
        1. 实例级 Skills（从 instance_loader 注入的 _instance_skills）- 优先使用
        2. Anthropic 预置 Skills（从 config.yaml 的 document_skills）
        3. 全局 Skills（从 capabilities.yaml）- 仅当没有实例级 Skills 时使用
        
        调用 LLM service 的 enable_skills 方法激活 Skills Container
        """
        skills_to_enable = []
        
        # 1. 优先使用实例级 Custom Skills
        if hasattr(self, '_instance_skills') and self._instance_skills:
            for skill in self._instance_skills:
                # skill 是 SkillConfig 数据类，检查是否已注册且启用
                if skill.enabled and skill.skill_id:
                    skills_to_enable.append({
                        "type": "custom",
                        "skill_id": skill.skill_id,
                        "version": "latest"
                    })
            if skills_to_enable:
                logger.info(f"🎯 加载实例级 Custom Skills: {len(skills_to_enable)} 个")
        
        # 2. 检查是否启用 Anthropic 预置 Skills（document_skills）
        if hasattr(self, 'schema') and hasattr(self.schema, 'enabled_capabilities'):
            enabled_caps = self.schema.enabled_capabilities or {}
            if enabled_caps.get('document_skills'):
                # 添加 Anthropic 预置的文档处理 Skills
                prebuilt_skills = [
                    {"type": "anthropic", "skill_id": "pptx", "version": "latest"},
                    {"type": "anthropic", "skill_id": "xlsx", "version": "latest"},
                    {"type": "anthropic", "skill_id": "docx", "version": "latest"},
                    {"type": "anthropic", "skill_id": "pdf", "version": "latest"},
                ]
                skills_to_enable.extend(prebuilt_skills)
                logger.info(f"🎯 加载 Anthropic 预置 Skills: {len(prebuilt_skills)} 个 (pptx, xlsx, docx, pdf)")
        
        # 3. 仅当没有任何 Skills 时，才使用全局 Skills（fallback）
        if not skills_to_enable:
            global_skills = self.capability_registry.get_registered_skills()
            if global_skills:
                skills_to_enable = global_skills
                logger.info(f"🎯 使用全局 Skills (fallback): {len(skills_to_enable)} 个")
        
        if skills_to_enable:
            self.llm.enable_skills(skills_to_enable)
            skill_ids = [s.get('skill_id', 'unknown')[:20] + '...' for s in skills_to_enable]
            logger.info(f"🎯 已启用 {len(skills_to_enable)} 个 Claude Skills: {skill_ids}")
        else:
            logger.debug("○ 没有已注册的 Claude Skills")
    
    async def chat(
        self,
        messages: List[Dict[str, str]] = None,
        session_id: str = None,
        conversation_id: str = None,
        message_id: str = None,
        enable_stream: bool = True,
        variables: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Agent 统一执行入口 - 核心执行流程
        
        🆕 V8.0: 前置处理层重构
        阶段 2 (Intent 事件) 和 阶段 2.5 (Preface 生成) 已移至 ChatService._run_agent()
        本方法专注于核心推理和执行（阶段 3-7）
        
        完整流程：
        阶段 1: Session/Agent 初始化 (在 SessionService 中完成)
        阶段 2: Intent 事件发送 (在 ChatService 中完成)
        阶段 2.5: Preface 生成 (在 ChatService 中完成)
        阶段 3: Tool Selection (Schema 驱动优先)
        阶段 4: System Prompt 组装 + LLM 调用准备
        阶段 5: Plan Creation (System Prompt 约束 + Claude 自主触发)
        阶段 6: RVR Loop (核心执行)
        阶段 7: Final Output & Tracing Report
        
        Args:
            messages: 完整的消息列表（已包含 preface 消息）
            session_id: 会话ID
            conversation_id: 对话ID
            message_id: 消息ID（用于事件关联）
            enable_stream: 是否流式输出
            variables: 前端上下文变量（如位置、时区等），直接注入到 Prompt
            
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
        conversation_id = session_context.get("conversation_id", conversation_id)
        user_id = session_context.get("user_id")  # 用于 System Prompt 注入
        # 🆕 前端变量直接从参数传入（不再从 Redis 读取），用于注入 System Prompt
        # 存储为实例变量，供后续使用
        self._current_conversation_id = conversation_id
        self._current_user_id = user_id
        
        # 🆕 更新工具执行器的上下文（确保沙盒工具使用正确的 conversation_id）
        if self.tool_executor and hasattr(self.tool_executor, 'update_context'):
            self.tool_executor.update_context(
                session_id=session_id,
                conversation_id=conversation_id,
                user_id=user_id
            )
        
        # ===== 🆕 加载现有计划=====
        # 如果会话有未完成的计划，加载它并注入到 prompt 中
        self._current_plan = None
        if conversation_id:
            self._current_plan = await load_plan_for_session(conversation_id)
            if self._current_plan:
                logger.info(f"📋 检测到现有计划: {self._current_plan.get('name', 'Unknown')}")
        
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
        # 阶段 2 & 2.5: 已移至服务层 (ChatService._run_agent)
        # =====================================================================
        # 🆕 V8.0: 意图事件发送和 Preface 生成由 ChatService 在调用 chat() 前完成
        # Agent 使用默认 intent 配置进行工具选择等后续阶段
        # =====================================================================
        
        intent = IntentResult(
            task_type=TaskType.OTHER,
            complexity=Complexity.MEDIUM,
            needs_plan=self.schema.plan_manager.enabled,
            intent_id=3,
            intent_name="综合咨询",
            confidence=1.0
        )
        
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
        plan = self._current_plan
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
        # 兼容旧逻辑：直接添加 _mcp_tools（已废弃，建议使用 _instance_registry）
        elif hasattr(self, '_mcp_tools') and self._mcp_tools:
            for mcp_tool in self._mcp_tools:
                # 🔧 使用工具自带的 input_schema，不再使用写死的 prompt 默认值
                # 如果没有 schema，使用空 schema（允许任意参数）
                input_schema = mcp_tool.get("input_schema")
                if not input_schema or not isinstance(input_schema, dict):
                    input_schema = {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                    logger.warning(f"⚠️ MCP 工具 {mcp_tool['name']} 没有 input_schema，使用空 schema")
                
                mcp_tool_def = {
                    "name": mcp_tool["name"],
                    "description": mcp_tool.get("description", ""),
                    "input_schema": input_schema
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
        # 阶段 3.5: 沙盒环境预创建（真正的后台执行，不阻塞主流程）
        # =====================================================================
        # 检查是否需要沙盒（选择了 sandbox_* 工具）
        # 🆕 移除 bash/text_editor，统一使用 sandbox_run_command/sandbox_write_file
        sandbox_tools = set(t for t in selection.tool_names if t.startswith("sandbox_"))
        needs_sandbox = bool(sandbox_tools)
        
        if needs_sandbox:
            try:
                from infra.sandbox import get_sandbox_provider
                sandbox = get_sandbox_provider()
                
                if sandbox.is_available:
                    # 🆕 真正的后台创建：使用 create_task，不阻塞主流程
                    # 工具执行时会通过 ensure_sandbox() 等待后台任务完成
                    from tools.sandbox_tools import start_sandbox_creation_background
                    start_sandbox_creation_background(conversation_id, user_id)
                    logger.info(f"🚀 沙盒后台创建已启动: conversation_id={conversation_id}")
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
        # 从最后一条消息中提取文本（content 可能是 list 或 string）
        if messages:
            last_content = messages[-1]["content"]
            if isinstance(last_content, list):
                # Claude API 格式：[{"type": "text", "text": "..."}, ...]
                user_query = extract_text_from_message(last_content)
            else:
                user_query = str(last_content)
        else:
            user_query = ""
        skip_memory = getattr(intent, 'skip_memory_retrieval', False)
        
        # 4.1 选择 System Prompt（🆕 V6.3: 支持多层缓存）
        # 优先级：prompt_cache 多层缓存 > 用户自定义 > 框架默认
        
        # 🆕 V5.1: 获取任务复杂度用于动态路由
        task_complexity = self._get_task_complexity(intent)
        
        # 🆕 V6.3: 使用多层缓存（prompt_cache 可用时）
        # 🆕 V7.10: 兼容 ModelRouter（检查 config 是否存在）
        llm_config = getattr(self.llm, 'config', None)
        use_multi_layer_cache = (
            self.prompt_cache and 
            self.prompt_cache.is_loaded and 
            self.prompt_cache.system_prompt_simple and
            llm_config and llm_config.enable_caching  # 确保 LLM 配置启用了缓存
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
            system_prompt = self.prompt_cache.get_full_system_prompt(task_complexity)
            
            cached_size = len(self.prompt_cache.get_system_prompt(task_complexity))
            full_size = len(system_prompt)
            logger.info(f"✅ 单层缓存路由: complexity={task_complexity.value}, "
                       f"缓存={cached_size}字符 + 运行时={full_size - cached_size}字符 = {full_size}字符")
        elif self.system_prompt:
            # 使用用户定义的 System Prompt
            system_prompt = self.system_prompt
            
            # 🆕 追加 Memory Guidance Prompt（L1 策略，可配置）
            if self.context_strategy.enable_memory_guidance:
                memory_guidance = get_memory_guidance_prompt()
                system_prompt = f"{self.system_prompt}\n\n{memory_guidance}"
            
            logger.info(f"✅ 使用用户定义的 System Prompt "
                       f"({len(self.system_prompt)}字符, L1={self.context_strategy.enable_memory_guidance})")
        else:
            # 使用框架默认 Prompt（根据意图识别结果决定是否检索 Mem0）
            system_prompt = get_universal_agent_prompt(
                user_id=user_id,
                user_query=user_query,
                skip_memory_retrieval=skip_memory  # 🆕 V4.6: 传递意图识别结果
            )
            if skip_memory:
                logger.info("✅ 使用框架默认 System Prompt（跳过 Mem0 检索）")
            else:
                logger.info("✅ 使用框架默认 System Prompt（已检索 Mem0 画像）")
        
        # 🆕 V8.0: PromptManager 追加内容现在追加到用户消息，不再追加到 System Prompt
        # 在 RVR 循环中通过 prompt_manager.append_to_user_message() 追加
        
        # 4.2 Plan 注入（消息末尾，对抗 Lost-in-the-Middle）
        if self._current_plan:
            messages = self.context_engineering.prepare_messages_for_llm(
                messages=messages,
                plan=self._current_plan,
                inject_plan=True,
                inject_errors=False  # 错误单独处理
            )
            logger.info(f"📋 已将计划注入消息末尾: {self._current_plan.get('name', 'Unknown')}")
        
        # 4.3 构建 LLM Messages
        llm_messages = dict_list_to_messages(messages)
        
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
        # 阶段 5.5: 上下文长度检查与自动裁剪（防止 Token 溢出）
        # =====================================================================
        # 在进入 RVR 循环之前，检查当前上下文的 token 估算值
        # 如果超过安全阈值（token_budget - 20000 buffer），自动裁剪历史消息
        # 这可以防止 Claude API 返回 "prompt is too long" 错误
        
        # 计算 system_prompt 的长度（支持多层缓存格式）
        system_prompt_text = ""
        if isinstance(system_prompt, list):
            for block in system_prompt:
                if isinstance(block, dict) and block.get("type") == "text":
                    system_prompt_text += block.get("text", "")
                elif isinstance(block, str):
                    system_prompt_text += block
        else:
            system_prompt_text = system_prompt or ""
        
        # 转换消息为字典格式用于 token 估算
        messages_for_estimate = [
            {"role": m.role, "content": m.content} if hasattr(m, 'role') else m 
            for m in llm_messages
        ]
        
        # 估算当前 token 数
        estimated_tokens = estimate_tokens(messages_for_estimate, system_prompt_text)
        
        # 计算安全阈值（token_budget - 20000 用于输出和工具结果）
        # Claude API 限制：200K tokens（输入），所以留出足够空间
        safe_threshold = self.context_strategy.token_budget - 20000
        
        if estimated_tokens > safe_threshold:
            logger.warning(
                f"⚠️ 上下文长度警告: 估算 {estimated_tokens:,} tokens > 安全阈值 {safe_threshold:,} tokens"
            )
            
            # 🆕 使用纯 token 驱动的裁剪
            trimmed_messages, trim_stats = trim_by_token_budget(
                messages=messages_for_estimate,
                token_budget=safe_threshold,
                preserve_first_messages=self.context_strategy.preserve_first_messages,
                preserve_last_messages=self.context_strategy.preserve_last_messages,
                preserve_tool_results=self.context_strategy.preserve_tool_results,
                system_prompt=system_prompt_text
            )
            trimmed_tokens = trim_stats.estimated_tokens
            
            logger.info(
                f"✂️ 历史消息已裁剪: {len(messages_for_estimate)} → {len(trimmed_messages)} 条消息, "
                f"token 估算: {estimated_tokens:,} → {trimmed_tokens:,}"
            )
            
            # 更新 llm_messages
            llm_messages = dict_list_to_messages(trimmed_messages)
            
            # 如果裁剪后仍然超过阈值，进行更激进的裁剪
            if trimmed_tokens > safe_threshold:
                logger.warning(f"⚠️ 裁剪后仍超过阈值，进行激进裁剪...")
                
                # 激进策略：更小的 token 预算，只保留最少消息
                aggressive_budget = int(safe_threshold * 0.6)  # 60% 的安全阈值
                aggressively_trimmed, aggressive_stats = trim_by_token_budget(
                    messages=trimmed_messages,
                    token_budget=aggressive_budget,
                    preserve_first_messages=2,
                    preserve_last_messages=6,
                    preserve_tool_results=False,  # 不保留中间的 tool_result
                    system_prompt=system_prompt_text
                )
                aggressive_tokens = aggressive_stats.estimated_tokens
                
                logger.info(
                    f"✂️ 激进裁剪: {len(trimmed_messages)} → {len(aggressively_trimmed)} 条消息, "
                    f"token 估算: {trimmed_tokens:,} → {aggressive_tokens:,}"
                )
                
                llm_messages = dict_list_to_messages(aggressively_trimmed)
        else:
            logger.debug(f"📊 上下文长度正常: 估算 {estimated_tokens:,} tokens < 安全阈值 {safe_threshold:,}")
        
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
        
        # 🆕 V8.0: PromptManager 上下文追加到用户消息（初始追加）
        # 后续工具执行产生的新上下文会在工具执行后追加
        prompt_manager.append_to_user_message(ctx, messages)
        
        # 🆕 记录是否已生成模拟思考（确保只在第一轮生成一次）
        simulated_thinking_generated = False
        
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
            
            # 🆕 V8.0: 每轮开始时，将 PromptManager 新增的上下文追加到用户消息
            # （工具执行后产生的 RAG 上下文等）
            if turn > 0:
                # 将新的上下文追加到原始 messages（会传递到下一轮 LLM 调用）
                prompt_manager.append_to_user_message(ctx, messages)
            
            # 🆕 每轮开始时检查上下文长度（工具结果可能导致累积溢出）
            if turn > 0:  # 第一轮已在阶段 5.5 检查过
                messages_for_check = [
                    {"role": m.role, "content": m.content} if hasattr(m, 'role') else m 
                    for m in llm_messages
                ]
                current_tokens = estimate_tokens(messages_for_check, system_prompt_text)
                
                if current_tokens > safe_threshold:
                    logger.warning(
                        f"⚠️ Turn {turn + 1}: 上下文累积溢出 ({current_tokens:,} > {safe_threshold:,})，执行裁剪..."
                    )
                    
                    # 🆕 使用纯 token 驱动的裁剪
                    trimmed, trim_stats = trim_by_token_budget(
                        messages=messages_for_check,
                        token_budget=safe_threshold,
                        preserve_first_messages=self.context_strategy.preserve_first_messages,
                        preserve_last_messages=self.context_strategy.preserve_last_messages,
                        preserve_tool_results=self.context_strategy.preserve_tool_results,
                        system_prompt=system_prompt_text
                    )
                    trimmed_tokens = trim_stats.estimated_tokens
                    
                    logger.info(
                        f"✂️ Turn {turn + 1} 裁剪: {len(messages_for_check)} → {len(trimmed)} 条消息, "
                        f"{current_tokens:,} → {trimmed_tokens:,} tokens"
                    )
                    
                    llm_messages = dict_list_to_messages(trimmed)
            
            # 调用 LLM（Extended Thinking 由 System Prompt 和 Claude 自主决定）
            if enable_stream:
                # 流式处理 LLM 响应
                # 🔑 只在第一轮传递模拟思考标记,后续轮次不再生成
                async for event in self._process_stream(
                    llm_messages, system_prompt, tools_for_llm, ctx, session_id,
                    is_first_turn=(turn == 0 and not simulated_thinking_generated)
                ):
                    yield event
                
                # 标记已生成模拟思考
                if turn == 0:
                    simulated_thinking_generated = True
                    
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
                    # 支持多种 stop_reason 格式：
                    # - Claude: "tool_use"
                    # - OpenAI/Qwen: "tool_calls"
                    # 🔍 调试日志
                    logger.info(f"🔍 [DEBUG] stop_reason={response.stop_reason}, tool_calls={len(response.tool_calls) if response.tool_calls else 0}")
                    if response.tool_calls:
                        logger.info(f"🔍 [DEBUG] tool_calls 内容: {[{'type': tc.get('type'), 'name': tc.get('name') or tc.get('function', {}).get('name')} for tc in response.tool_calls[:3]]}")
                    
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
                            # 🔑 最后一轮强制回复不生成模拟思考
                            async for event in self._process_stream(
                                llm_messages, system_prompt, [], ctx, session_id,
                                is_first_turn=False  # 不是第一轮，不生成模拟思考
                            ):
                                yield event
                            # 标记完成
                            final_response = ctx.last_llm_response
                            if final_response:
                                ctx.set_completed(final_response.content, "max_turns_reached")
                            break
                        
                        # 🆕 区分客户端工具和服务端工具
                        # - 客户端工具（tool_use）：需要本地执行（统一格式）
                        # - 服务端工具（server_tool_use）：Anthropic 服务器已执行，结果在 raw_content 中
                        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
                        server_tools = [tc for tc in response.tool_calls if tc.get("type") == "server_tool_use"]
                        
                        # 🔍 调试日志
                        logger.info(f"🔍 [DEBUG] 过滤后: client_tools={len(client_tools)}, server_tools={len(server_tools)}")
                        if client_tools:
                            logger.info(f"🔍 [DEBUG] client_tools 详情: {[{'type': tc.get('type'), 'name': tc.get('name') or tc.get('function', {}).get('name')} for tc in client_tools[:3]]}")
                        
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
                        # 🔒 V7.8: 添加去重检查，避免与消息历史中的 tool_result 重复
                        tool_results = []
                        if client_tools:
                            accumulator = self.broadcaster.get_accumulator(session_id)
                            if accumulator:
                                client_tool_ids = {tc.get("id") for tc in client_tools}
                                
                                # 🆕 收集消息历史中已有的 tool_result IDs（用于去重）
                                existing_tool_result_ids = set()
                                for msg in llm_messages:
                                    msg_content = msg.content if hasattr(msg, 'content') else msg.get('content', [])
                                    if isinstance(msg_content, list):
                                        for block in msg_content:
                                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                                existing_tool_result_ids.add(block.get("tool_use_id"))
                                
                                for block in accumulator.all_blocks:
                                    if block.get("type") == "tool_result" and block.get("tool_use_id") in client_tool_ids:
                                        tool_use_id = block.get("tool_use_id")
                                        # 🔒 跳过已经在消息历史中的 tool_result
                                        if tool_use_id in existing_tool_result_ids:
                                            logger.debug(f"🧹 跳过重复的 tool_result: {tool_use_id}")
                                            continue
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
                # ✅ 使用 LLMResponse 中的 model 字段进行计费
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
                    # ✅ 使用 LLMResponse 中的 model 字段进行计费
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
        
        # 🆕 V7.5: 生成完整的 billing 信息
        from models.usage import UsageResponse
        usage_response = UsageResponse.from_usage_tracker(
            tracker=self.usage_tracker,
            model=self.model,
            latency=0  # Agent 内部不计算总延迟（由 ChatService 计算）
        )
        
        # 累积 usage 到内存（供 _finalize_message 保存到数据库）
        # 注意：如果通过 ChatService 调用，此数据会被 ChatService 的完整数据覆盖（包含总延迟）
        # 如果 Agent 独立使用，此数据确保 usage 信息被正确保存
        await self.broadcaster.accumulate_usage(
            session_id=session_id,
            usage=usage_response.model_dump(mode='json')
        )
        
        # 发送 billing 事件到前端（作为最后一个 message_delta，在 message_stop 之前）
        billing_event = await self.broadcaster.emit_message_delta(
            session_id=session_id,
            delta={
                "type": "billing",
                "content": usage_response.model_dump(mode='json')
            },
            message_id=self._current_message_id,
            persist=False  # billing 信息已通过 accumulate_usage 保存，这里只发送 SSE 事件
        )
        if billing_event:
            yield billing_event
            logger.debug(f"📊 Billing 事件已发送: total_price=${usage_response.total_price:.6f}")
        
        # message_stop 作为最后一个事件（保持向后兼容）
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
    
    async def _generate_simulated_thinking(
        self,
        user_query: str,
        messages: List,
        session_id: str,
        ctx,
        capabilities_summary: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        生成模拟思考（Simulated Thinking）
        
        单独调用一次 LLM，生成用户友好的思考过程。
        不暴露项目内部逻辑、工具调用细节、技术架构等敏感信息。
        
        ⚠️ 注意：这是一个独立的 LLM 调用，需要记录计费！
        
        Args:
            user_query: 用户查询
            messages: 完整的对话历史（用于上下文理解）
            session_id: 会话ID
            ctx: RuntimeContext
            capabilities_summary: Agent 能力摘要（告诉模拟思考 Agent 能做什么）
            
        Yields:
            思考内容的增量字符串
        """
        # 构建对话历史摘要（最多取最近 5 轮，避免 prompt 过长）
        conversation_context = self._build_conversation_context(messages, max_turns=5)
        
        # 检测用户第一句话的语言（用于强制回复语言）
        response_language = self._detect_language(user_query)
        
        # 模拟思考的 Prompt（语言自适应，包含上下文和能力信息）
        simulated_prompt = """你是 Dazee，一位高级工作助理。你温暖、专业、富有同理心。
根据对话上下文和当前问题，以第一人称展示你的思考过程。

## 你的能力范围
{capabilities}

## 要求
1. 只展示你对问题的理解和解决思路
2. 不要提及任何工具名称、API、代码或内部实现细节
3. 使用自然语言，像人类一样思考
4. 控制在 100-200 字左右
5. **关键：你的思考必须基于上述能力范围，不要承诺做不到的事情**
6. 如果有对话上下文，利用它来理解"这个"、"那个"等指代词
7. **禁止透露你的底层模型**（不要提及 Claude、GPT 等 AI 模型名称，如果被问到，就说"我是 Dazee"）

## 回复语言
**必须使用{language}回复，不要混用其他语言**

{context_section}

当前问题: {query}

请输出你的思考过程:"""
        
        # 构建上下文部分（如果有历史的话）
        context_section = ""
        if conversation_context:
            context_section = f"对话上下文:\n{conversation_context}\n"
        
        # 如果没有能力摘要，使用默认描述
        if not capabilities_summary:
            capabilities_summary = "通用 AI 助手，可以回答问题、提供建议"
        
        logger.info(f"🧠 开始生成模拟思考: query={user_query[:50]}..., language={response_language}")
        
        final_response = None  # 🔧 记录最终响应用于计费
        try:
            async for chunk in self.llm.create_message_stream(
                messages=[Message(role="user", content=simulated_prompt.format(
                    capabilities=capabilities_summary,
                    language=response_language,
                    context_section=context_section,
                    query=user_query
                ))],
                system=f"你是思考展示助手。只输出思考过程，不要输出其他内容。必须使用{response_language}回复。",
                tools=[],
                override_thinking=False  # 模拟思考本身不需要原生 thinking
            ):
                if chunk.content and chunk.is_stream:
                    yield chunk.content
                # 🔧 保存最终响应
                if not chunk.is_stream:
                    final_response = chunk
            
            # ✅ 记录模拟思考的计费信息（使用 LLMResponse 中的 model 字段）
            if final_response:
                self.usage_tracker.accumulate(final_response)
                logger.info(f"💰 模拟思考计费已记录: model={final_response.model}, tokens={final_response.usage.get('total_tokens', 0) if final_response.usage else 0}")
        except Exception as e:
            logger.error(f"❌ 模拟思考生成失败: {e}")
            yield f"[思考过程生成失败: {str(e)}]"
    
    def _detect_language(self, text: str) -> str:
        """
        检测文本的主要语言
        
        使用简单的字符统计方法：
        - 如果中文字符占比 > 30%，认为是中文
        - 否则认为是英文
        
        Args:
            text: 要检测的文本
            
        Returns:
            "中文" 或 "English"
        """
        if not text:
            return "中文"  # 默认中文
        
        # 统计中文字符数量
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        total_chars = len(text.replace(" ", ""))  # 不计空格
        
        if total_chars == 0:
            return "中文"
        
        chinese_ratio = chinese_chars / total_chars
        
        # 中文字符占比超过 30% 认为是中文
        if chinese_ratio > 0.3:
            return "中文"
        else:
            return "English"
    
    def _build_capabilities_summary(self) -> str:
        """
        构建 Agent 能力摘要（用于模拟思考）
        
        从多个来源收集能力信息：
        1. Schema 中定义的工具列表
        2. 实例级注册的 MCP 工具
        3. prompt_cache 中的能力描述（如果有）
        
        Returns:
            用户友好的能力描述字符串
        """
        capabilities = []
        
        # 1. 从 Schema 获取工具列表
        if self.schema and self.schema.tools:
            tool_names = self.schema.tools[:10]  # 最多取 10 个，避免太长
            capabilities.append(f"可用工具: {', '.join(tool_names)}")
        
        # 2. 从实例级工具注册表获取 MCP 工具
        if hasattr(self, '_instance_registry') and self._instance_registry:
            mcp_tools = self._instance_registry.get_tools_for_claude()
            if mcp_tools:
                mcp_names = [t.get('name', '') for t in mcp_tools[:5]]  # 最多 5 个
                capabilities.append(f"扩展能力: {', '.join(mcp_names)}")
        elif hasattr(self, '_mcp_tools') and self._mcp_tools:
            mcp_names = [t.get('name', '') for t in self._mcp_tools[:5]]
            capabilities.append(f"扩展能力: {', '.join(mcp_names)}")
        
        # 3. 从 prompt_cache 获取能力描述（如果有定义）
        if self.prompt_cache and hasattr(self.prompt_cache, 'capabilities_description'):
            desc = getattr(self.prompt_cache, 'capabilities_description', '')
            if desc:
                capabilities.append(desc)
        
        # 4. 如果没有收集到任何能力，使用 Schema 的 description
        if not capabilities and self.schema and hasattr(self.schema, 'description'):
            desc = getattr(self.schema, 'description', '')
            if desc:
                capabilities.append(desc)
        
        # 组合能力描述
        if capabilities:
            return "\n".join(capabilities)
        else:
            return "通用 AI 助手，可以回答问题、搜索信息、执行任务"
    
    def _build_conversation_context(self, messages: List, max_turns: int = 5) -> str:
        """
        构建对话历史摘要（用于模拟思考的上下文）
        
        Args:
            messages: 消息列表
            max_turns: 最多保留的对话轮数
            
        Returns:
            格式化的对话历史字符串
        """
        if not messages:
            return ""
        
        # 收集最近的对话（排除最后一条用户消息，因为它会单独作为 current question）
        context_parts = []
        turn_count = 0
        
        # 倒序遍历，跳过最后一条用户消息
        skipped_last_user = False
        for msg in reversed(messages):
            # 获取角色和内容
            if hasattr(msg, 'role'):
                role = msg.role
                content = msg.content
            elif isinstance(msg, dict):
                role = msg.get('role', '')
                content = msg.get('content', '')
            else:
                continue
            
            # 跳过最后一条用户消息
            if role == 'user' and not skipped_last_user:
                skipped_last_user = True
                continue
            
            # 跳过系统消息和工具结果
            if role in ('system', 'tool'):
                continue
            
            # 提取文本内容
            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        text_content = block.get('text', '')
                        break
            
            if not text_content:
                continue
            
            # 清理内容（移除系统注入的上下文信息）
            clean_content = text_content
            for marker in ["[用户上下文]", "[提取的文档信息]", "[图片url列表信息]", "[文档url列表信息]"]:
                if marker in clean_content:
                    idx = clean_content.find(marker)
                    clean_content = clean_content[:idx].strip()
            
            # 截断过长的内容
            if len(clean_content) > 200:
                clean_content = clean_content[:200] + "..."
            
            if clean_content:
                role_label = "User" if role == "user" else "Assistant"
                context_parts.insert(0, f"{role_label}: {clean_content}")
                
                if role == "user":
                    turn_count += 1
                    if turn_count >= max_turns:
                        break
        
        return "\n".join(context_parts)
    
    def _extract_user_query(self, messages: List) -> str:
        """
        从消息列表中提取最后一条用户消息（纯净版本）
        
        Args:
            messages: 消息列表（Message 对象或字典）
            
        Returns:
            用户查询字符串（限制 500 字符，不含系统注入的上下文信息）
        """
        raw_content = ""
        
        for msg in reversed(messages):
            # 处理 Message 对象
            if hasattr(msg, 'role') and msg.role == 'user':
                content = msg.content
                if isinstance(content, str):
                    raw_content = content
                    break
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            raw_content = block.get('text', '')
                            break
                    if raw_content:
                        break
            # 处理字典格式
            elif isinstance(msg, dict) and msg.get('role') == 'user':
                content = msg.get('content', '')
                if isinstance(content, str):
                    raw_content = content
                    break
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            raw_content = block.get('text', '')
                            break
                    if raw_content:
                        break
        
        if not raw_content:
            return ""
        
        # 过滤掉系统注入的上下文信息（如 [用户上下文]、[提取的文档信息] 等）
        # 这些信息不应该暴露给模拟思考，避免泄露 locale、timezone 等内部信息
        clean_content = raw_content
        
        # 移除 [用户上下文] 部分
        if "[用户上下文]" in clean_content:
            # 找到 [用户上下文] 的位置，截取之前的内容
            idx = clean_content.find("[用户上下文]")
            clean_content = clean_content[:idx].strip()
        
        # 移除 [提取的文档信息] 部分
        if "[提取的文档信息]" in clean_content:
            idx = clean_content.find("[提取的文档信息]")
            clean_content = clean_content[:idx].strip()
        
        # 移除其他可能的系统注入标记
        for marker in ["[图片url列表信息]", "[文档url列表信息]"]:
            if marker in clean_content:
                idx = clean_content.find(marker)
                clean_content = clean_content[:idx].strip()
        
        return clean_content[:500] if clean_content else ""
    
    async def _process_stream(
        self,
        messages: List,
        system_prompt,
        tools: List,
        ctx,
        session_id: str,
        is_first_turn: bool = False  # 🆕 标识是否是第一轮
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理流式 LLM 响应
        
        使用 ContentHandler 的手动控制模式（start_block, send_delta, stop_block）
        处理 LLM 的流式输出（thinking, text, tool_use）
        
        支持三种 thinking 模式：
        - native: 原生 Extended Thinking（默认）
        - simulated: 模拟思考（单独调用 LLM 生成用户友好的思考过程，仅第一轮）
        - none: 不展示思考
        
        Args:
            messages: 消息列表
            system_prompt: 系统提示词
            tools: 工具列表
            ctx: RuntimeContext
            session_id: 会话ID
            is_first_turn: 是否是第一轮（用于控制模拟思考生成）
        """
        # 创建 ContentHandler（手动控制模式）
        content_handler = create_content_handler(self.broadcaster, ctx.block, self._current_message_id)
        
        # 获取 thinking_mode 配置（默认 native 保持向后兼容）
        thinking_mode = getattr(self.schema, 'thinking_mode', 'native')
        logger.debug(f"🧠 Thinking 模式: {thinking_mode}")
        
        # ===== 模拟思考：只在第一轮且配置为 simulated 时生成 =====
        if thinking_mode == "simulated" and is_first_turn:
            user_query = self._extract_user_query(messages)
            if user_query:
                # 构建能力摘要（告诉模拟思考 Agent 能做什么）
                capabilities_summary = self._build_capabilities_summary()
                
                # 开始 thinking block
                yield await content_handler.start_block(
                    session_id=session_id,
                    block_type="thinking",
                    initial={"thinking": ""}
                )
                
                # 流式输出模拟思考内容（传入对话历史和能力摘要）
                async for delta in self._generate_simulated_thinking(
                    user_query, messages, session_id, ctx,
                    capabilities_summary=capabilities_summary
                ):
                    yield await content_handler.send_delta(
                        session_id=session_id,
                        delta=delta
                    )
                
                # 关闭 thinking block
                yield await content_handler.stop_block(session_id=session_id)
                logger.info("✅ 模拟思考生成完成")
        
        # ===== 正式调用 LLM =====
        # simulated/none 模式关闭原生 thinking，native 模式使用默认配置
        override_thinking = None if thinking_mode == "native" else False
        
        stream_generator = self.llm.create_message_stream(
            messages=messages,
            system=system_prompt,
            tools=tools,
            override_thinking=override_thinking
        )
        
        final_response = None
        
        async for llm_response in stream_generator:
            # ===== 处理 thinking（仅 native 模式） =====
            if llm_response.thinking and llm_response.is_stream and thinking_mode == "native":
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
            # ✅ 使用 LLMResponse 中的 model 字段进行计费
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
            # 🛡️ 仅对沙盒相关工具注入上下文（user_id, session_id, conversation_id）
            # ⚠️ 不要对所有工具注入，否则 MCP 工具会收到错误参数
            # 🆕 从 config/tool_registry.yaml 统一配置读取
            # 🔧 使用强制赋值而非 setdefault，确保 LLM 生成的错误值被系统值覆盖
            SANDBOX_TOOLS = get_sandbox_tools()
            if tool_name in SANDBOX_TOOLS:
                session_context = await self.event_manager.storage.get_session_context(session_id)
                tool_input["session_id"] = session_id  # 强制覆盖
                if session_context.get("user_id"):
                    tool_input["user_id"] = session_context.get("user_id")  # 强制覆盖
                conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
                tool_input["conversation_id"] = conv_id  # 强制覆盖，防止 LLM 编造
            
            # 🆕 V7.9: 为 api_calling 工具注入上下文（用于替换 body 中的占位符）
            # 这些值不会直接传入工具参数，而是通过 **kwargs 供工具内部使用
            if tool_name == "api_calling":
                session_context = await self.event_manager.storage.get_session_context(session_id)
                injected_user_id = session_context.get("user_id") or getattr(self, '_current_user_id', None)
                injected_conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
                tool_input["user_id"] = injected_user_id
                tool_input["session_id"] = session_id
                tool_input["conversation_id"] = injected_conv_id
                logger.info(f"🔑 [api_calling 上下文注入] user_id={injected_user_id}, session_id={session_id}, conversation_id={injected_conv_id}")
            
            # ===== 通用工具执行 =====
            result = await self.tool_executor.execute(tool_name, tool_input)
            
            # 触发 PromptManager（如 RAG 上下文追加）
            if ctx:
                (await get_prompt_manager_async()).on_tool_result(ctx, tool_name=tool_name, result=result)
            
            # 🆕 V7.5.1: 工具调用成功，记录计费
            # 注意：usage_tracker 由 SimpleAgent 提供（EnhancedUsageTracker）
            if hasattr(self, 'usage_tracker'):
                self.usage_tracker.record_tool_call(
                    tool_name=tool_name,
                    success=True,
                    params=tool_input  # 传递参数用于 api_calling 等通用工具的价格查询
                )
                logger.debug(f"💰 工具计费已记录: {tool_name}")
            
            # 🆕 Plan 刷新：如果是 plan_todo 的修改操作，刷新 _current_plan
            # 确保下一轮注入的 plan 上下文是最新的
            if tool_name == "plan_todo":
                operation = tool_input.get("operation", "")
                if operation in ("create", "update_todo", "add_todo"):
                    await self._refresh_current_plan(ctx)
            
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
    
    async def _refresh_current_plan(self, ctx=None) -> None:
        """
        刷新当前计划（从数据库重新加载）
        
        用途：当 plan_todo 工具执行了修改操作（create/update_todo/add_todo）后，
        刷新 _current_plan，确保下一轮注入到上下文的 plan 是最新状态。
        
        Args:
            ctx: RuntimeContext（可选，用于获取 conversation_id）
        """
        conversation_id = None
        
        # 从 ctx 获取 conversation_id
        if ctx and hasattr(ctx, 'conversation_id'):
            conversation_id = ctx.conversation_id
        
        # 如果 ctx 没有 conversation_id，使用类属性
        if not conversation_id and hasattr(self, '_current_conversation_id'):
            conversation_id = self._current_conversation_id
        
        if not conversation_id:
            logger.debug("📋 无法刷新 plan：缺少 conversation_id")
            return
        
        try:
            self._current_plan = await load_plan_for_session(conversation_id)
            
            if self._current_plan:
                plan_name = self._current_plan.get('name', 'Unknown')
                todos = self._current_plan.get('todos', [])
                completed = sum(1 for t in todos if t.get('status') == 'completed')
                total = len(todos)
                logger.info(f"🔄 Plan 已刷新: {plan_name} (进度: {completed}/{total})")
            else:
                logger.debug("📋 Plan 刷新完成: 当前无计划")
                
        except Exception as e:
            logger.warning(f"⚠️ 刷新 plan 失败: {e}")
    
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
        content_handler = create_content_handler(self.broadcaster, ctx.block, self._current_message_id)
        
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
                
                # 🛡️ 仅对沙盒相关工具注入上下文
                # ⚠️ 不要对所有工具注入，否则 MCP 工具会收到错误参数
                # 🆕 从 config/tool_registry.yaml 统一配置读取
                # 🔧 使用强制赋值而非 setdefault，确保 LLM 生成的错误值被系统值覆盖
                SANDBOX_TOOLS = get_sandbox_tools()
                if tool_name in SANDBOX_TOOLS:
                    session_context = await self.event_manager.storage.get_session_context(session_id)
                    tool_input["session_id"] = session_id  # 强制覆盖
                    if session_context.get("user_id"):
                        tool_input["user_id"] = session_context.get("user_id")  # 强制覆盖
                    conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
                    tool_input["conversation_id"] = conv_id  # 强制覆盖，防止 LLM 编造
                
                # 🆕 V7.9.2: 为 api_calling 工具注入上下文（流式执行路径）
                if tool_name == "api_calling":
                    session_context = await self.event_manager.storage.get_session_context(session_id)
                    injected_user_id = session_context.get("user_id") or getattr(self, '_current_user_id', None)
                    injected_conv_id = session_context.get("conversation_id") or getattr(self, '_current_conversation_id', None) or session_id
                    tool_input["user_id"] = injected_user_id
                    tool_input["session_id"] = session_id
                    tool_input["conversation_id"] = injected_conv_id
                    logger.info(f"🔑 [api_calling 流式上下文注入] user_id={injected_user_id}, session_id={session_id}, conversation_id={injected_conv_id}")
                
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
        content_handler = create_content_handler(self.broadcaster, ctx.block, self._current_message_id)
        
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
        content_handler = create_content_handler(self.broadcaster, ctx.block, self._current_message_id)
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
        - invocation_selector
        - _instance_registry, _mcp_clients, _mcp_tools
        
        重置（每次请求独立）：
        - _last_intent_result, _tracer
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
        self._last_intent_result = None
        self._tracer = None
        self.usage_tracker = create_enhanced_usage_tracker()
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

