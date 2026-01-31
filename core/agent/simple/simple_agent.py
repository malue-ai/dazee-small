"""
SimpleAgent - 精简版核心 Agent

职责：
- 只做编排（Orchestrator）
- 协调各个独立模块完成任务
- 实现 RVR（React-Validation-Reflectio）循环

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
from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING

# 2. 第三方库（无）

# 3. 本地模块
# 🆕 V9.0: IntentAnalyzer 已移至路由层 (core/routing/intent_analyzer.py)
# SimpleAgent 不再内部做意图识别，由 AgentRouter 统一处理
from core.context.runtime import create_runtime_context
from core.context.failure_summary import (
    FailureSummaryGenerator,
    get_failure_summary_config
)
from core.context.context_engineering import (
    ContextEngineeringManager, 
    AgentState, 
    create_context_engineering_manager
)
from core.context.prompt_manager import get_prompt_manager, PromptManager
from core.events.broadcaster import EventBroadcaster
from core.llm import Message, LLMResponse, ToolType, create_llm_service
from core.tool import create_tool_executor, create_tool_selector, create_unified_tool_caller
from core.tool.capability import create_capability_registry, create_invocation_selector
from core.orchestration import create_pipeline_tracer, E2EPipelineTracer
from core.confirmation_manager import get_confirmation_manager, ConfirmationType
from core.agent.types import IntentResult

if TYPE_CHECKING:
    from core.llm.base import LLMConfig
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
        self.conversation_service = conversation_service
        
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

        # 失败经验总结（MVP）
        self.failure_summary_config = get_failure_summary_config()
        self.failure_summary_generator: Optional[FailureSummaryGenerator] = None
        
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
        🆕 V10.0: 从原型克隆 Agent 实例（委托给 AgentFactory）
        
        克隆逻辑已移至 AgentFactory.clone_for_session()，
        保持 Factory 作为唯一创建/克隆入口。
        """
        from core.agent.factory import AgentFactory
        return AgentFactory.clone_for_session(
            prototype=self,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service
        )
    
    def _init_modules(self):
        """根据 Schema 动态初始化各独立模块"""
        # 1. 能力注册表
        self.capability_registry = create_capability_registry()
        
        # 2. 🆕 V9.0: IntentAnalyzer 已移至路由层
        # 意图识别由 AgentRouter 统一完成，结果通过 chat(intent=...) 传入
        # 见 core/routing/intent_analyzer.py
        
        # 3. 工具选择器
        if self.schema.tool_selector.enabled:
            self.tool_selector = create_tool_selector(registry=self.capability_registry)
            logger.debug(f"✓ ToolSelector 已启用 (strategy={self.schema.tool_selector.selection_strategy})")
        else:
            self.tool_selector = None
            logger.debug("○ ToolSelector 未启用")
        
        # 3.1 🆕 统一工具调用协调器
        self.unified_tool_caller = create_unified_tool_caller(self.capability_registry)
        
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
            "enable_thinking": llm_enable_thinking,
            "enable_caching": llm_enable_caching,
            "tools": [ToolType.BASH, ToolType.TEXT_EDITOR, ToolType.WEB_SEARCH],
        }
        
        if self.schema.temperature is not None:
            llm_kwargs["temperature"] = self.schema.temperature
        if self.schema.max_tokens is not None:
            llm_kwargs["max_tokens"] = self.schema.max_tokens

        from config.llm_config import get_llm_profile
        main_profile = get_llm_profile("main_agent")
        profile_provider = str(main_profile.get("provider", "claude")).lower()
        if profile_provider == "claude":
            main_profile["model"] = self.model
        main_profile.update(llm_kwargs)
        self.llm = create_llm_service(**main_profile)
        
        logger.debug(f"✓ 执行 LLM 初始化: thinking={llm_enable_thinking}, caching={llm_enable_caching}")
        
        # 注册自定义工具到 LLM
        if self.plan_todo_tool:
            self._register_tools_to_llm()
        
        # 🔧 Skills 启用由 instance_loader 处理，SimpleAgent 不负责
        
        # 8. 并行工具执行配置
        self.allow_parallel_tools = self.schema.allow_parallel_tools
        self.max_parallel_tools = self.schema.tool_selector.max_parallel_tools
        # 🆕 V10.0: 从 ToolSelector 获取串行工具列表（配置驱动）
        self._serial_only_tools = getattr(self.tool_selector, 'SERIAL_ONLY_TOOLS', {"plan_todo", "request_human_confirmation"})
        logger.debug(f"✓ 并行工具配置: allow={self.allow_parallel_tools}, max={self.max_parallel_tools}, serial_only={self._serial_only_tools}")
        
        # 🆕 V10.0: Session context 注入点（由 ChatService 设置）
        self._injected_session_context = None
    
    def inject_session_context(self, session_context: Dict[str, Any]) -> None:
        """
        🆕 V10.0: 从 Service 层注入 session context
        
        分层解耦：Agent 层不应直接访问存储，由 Service 层获取后注入。
        
        Args:
            session_context: 包含 conversation_id, user_id 等的上下文字典
        """
        self._injected_session_context = session_context
        logger.debug(f"📦 Session context 已注入: {list(session_context.keys())}")
    
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
        # 分层解耦：session_context 必须由 ChatService 注入
        if not hasattr(self, '_injected_session_context') or self._injected_session_context is None:
            raise ValueError(
                "session_context 未注入。Agent 不应直接访问存储，"
                "请通过 agent.inject_session_context() 注入会话上下文。"
            )
        
        session_context = self._injected_session_context
        self._injected_session_context = None  # 清理，避免跨调用污染
        
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
        # 🆕 V10.0: 简化意图处理，删除 _process_intent() 方法
        # - 默认值创建保留在此（过渡期），后续由 ChatService 强制传入
        # - 直接调用 _handle_intent_transition() 管理 plan_cache 状态
        if intent is None:
            logger.warning("⚠️ 未提供意图结果，使用默认配置（建议 ChatService 强制传入）")
            from core.agent.types import IntentResult, TaskType, Complexity
            intent = IntentResult(
                task_type=TaskType.OTHER,
                complexity=Complexity.MEDIUM,
                needs_plan=self.schema.plan_manager.enabled,
                confidence=1.0
            )
        else:
            self._handle_intent_transition(intent)
        
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
        # 🆕 V10.0: 委托给 SandboxService（从 SimpleAgent 解耦）
        from services.sandbox_service import get_sandbox_service
        sandbox_service = get_sandbox_service()
        await sandbox_service.ensure_for_tools(selection.tool_names, conversation_id, user_id)
        
        # ===== 阶段 4: System Prompt 组装 =====
        user_query = messages[-1]["content"] if messages else ""
        llm_config = self._get_llm_config()
        system_prompt = build_system_prompt(
            intent=intent,
            prompt_cache=self.prompt_cache,
            prompt_manager=prompt_manager,
            context_strategy=self.context_strategy,
            system_prompt=self.system_prompt,
            llm_enable_caching=llm_config.enable_caching if llm_config else False,
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
        
        # 🆕 V7.5: 发送 billing 信息（作为最后一个 message_delta，在 message_stop 之前）
        from models.usage import UsageResponse
        usage_response = UsageResponse.from_tracker(
            tracker=self.usage_tracker,
            latency=0  # Agent 内部不计算总延迟（由 ChatService 计算）
        )
        
        yield {
            "type": "message_delta",
            "data": {
                "type": "billing",
                "content": usage_response.model_dump()
            }
        }
        logger.debug(f"📊 Billing 事件已发送: total_price=${usage_response.total_price:.6f}")
        
        # message_stop 作为最后一个事件
        yield await self.broadcaster.emit_message_stop(
            session_id=session_id,
            message_id=self._current_message_id
        )

        # 🆕 V10.0: 失败经验总结（委托给 FailureSummaryManager）
        if self.conversation_service and self.failure_summary_config.enabled:
            from core.context.failure_summary import FailureSummaryManager
            failure_manager = FailureSummaryManager(
                conversation_service=self.conversation_service,
                llm_service=self.llm,
                config=self.failure_summary_config,
                context_strategy=self.context_strategy
            )
            await failure_manager.maybe_generate(
                conversation_id=conversation_id,
                stop_reason=ctx.stop_reason,
                session_id=session_id,
                user_id=user_id,
                message_id=self._current_message_id
            )

        logger.info(f"✅ Agent 执行完成: turns={ctx.current_turn}")
    
    def _handle_intent_transition(self, new_intent: "IntentResult") -> None:
        """
        🆕 V9.0: 处理意图状态转换（轻量，< 0.1ms）
        
        追问：复用 plan_cache，继承 task_type
        新意图：重置 plan_cache
        
        Args:
            new_intent: 新的意图分析结果
        """
        previous_intent = self._last_intent_result
        
        if new_intent.is_follow_up and previous_intent is not None:
            # 追问模式：保留 plan_cache，继承 task_type
            logger.info(
                f"🔄 追问模式: 复用 plan_cache, "
                f"继承 task_type={previous_intent.task_type.value}"
            )
            new_intent.task_type = previous_intent.task_type
            # plan_cache 保持不变，不重置
        else:
            # 新意图：重置状态
            if self._plan_cache.get("plan") is not None:
                logger.info("🆕 新意图: 重置 plan_cache")
            self._plan_cache = {"plan": None, "todo": None, "tool_calls": []}
        
        # 更新最后一次意图结果
        self._last_intent_result = new_intent

    def _get_llm_config(self) -> Optional["LLMConfig"]:
        """
        获取 LLM 配置（兼容 ModelRouter）
        
        Returns:
            LLMConfig 或 None
        """
        if hasattr(self.llm, "config"):
            return self.llm.config
        if hasattr(self.llm, "primary") and hasattr(self.llm.primary, "service"):
            service = self.llm.primary.service
            if hasattr(service, "config"):
                return service.config
        return None

    async def _select_tools(self, intent: "IntentResult", ctx):
        """
        工具选择 - 三级优先级策略
        
        优先级（互斥选择）：
        1. Schema 配置（schema.tools）- 运营显式配置，最高优先级
        2. Plan 推荐（plan.required_capabilities）- 任务规划推荐
        3. Intent 推断（intent → task_type → capabilities）- 意图分析兜底
        
        V7.6 改进：
        - ✅ Schema 工具有效性验证（过滤无效工具）
        - ✅ 覆盖透明化日志（记录被忽略的 Plan/Intent 建议）
        - ✅ 增强 Tracer 追踪（完整记录选择决策链路）
        
        Args:
            intent: 意图分析结果
            ctx: Agent 上下文
            
        Returns:
            (tools_for_llm, selection): LLM 工具列表和选择结果
        """
        if self._tracer:
            tool_stage = self._tracer.create_stage("tool_selection")
            tool_stage.start()
        
        logger.info("🔧 开始工具选择...")
        
        plan = self._plan_cache.get("plan")
        use_skill_path = False
        invocation_strategy = None
        
        # V4.4: Skill 路径（仅当当前 LLM 支持 Skills）
        if plan and plan.get('recommended_skill'):
            if hasattr(self.llm, "supports_skills") and self.llm.supports_skills():
                use_skill_path = True
                skill_info = plan.get('recommended_skill')
                skill_name = skill_info.get('name', 'unknown') if isinstance(skill_info, dict) else skill_info
                logger.info(f"🎯 V4.4 Skill 路径: 使用 Claude Skill '{skill_name}'")
                
                invocation_strategy = self.invocation_selector.select_strategy(
                    task_type=intent.task_type.value,
                    selected_tools=[],
                    plan_result=plan
                )
            else:
                logger.info("ℹ️ 当前模型不支持 Claude Skills，忽略推荐 Skill 路径")
        
        # 🆕 V10.0: 使用 ToolSelector.resolve_capabilities() 处理三级优先级
        # 将工具选择策略从 SimpleAgent 提取到 ToolSelector
        required_capabilities, selection_source, overridden_sources = self.tool_selector.resolve_capabilities(
            schema_tools=self.schema.tools if self.schema.tools else None,
            plan=plan,
            intent_task_type=intent.task_type.value if intent else None
        )
        
        # Skill 路径时覆盖 selection_source
        if use_skill_path:
            selection_source = "skill"

        # 🆕 Skills 不可用时，尝试注入 fallback 工具
        if plan and plan.get('recommended_skill'):
            required_capabilities = self.unified_tool_caller.ensure_skill_fallback(
                required_capabilities=required_capabilities,
                recommended_skill=plan.get('recommended_skill'),
                llm_service=self.llm
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
        
        # 🆕 V7.6: 增强的选择总结日志
        logger.info(
            f"✅ 工具选择完成 [{selection_source}]: "
            f"共 {len(selection.tool_names)} 个工具 - {selection.tool_names}"
        )
        if overridden_sources:
            logger.info(f"   └─ 覆盖了来源: {', '.join(overridden_sources)}")
        
        # 🆕 V10.0: 简化的 Tracer 记录（三级策略已由 ToolSelector 处理）
        if self._tracer:
            tool_stage.set_input({
                "schema_tools": self.schema.tools if self.schema.tools else [],
                "required_capabilities": required_capabilities[:5] if required_capabilities else [],
                "selection_source": selection_source,
                "use_skill_path": use_skill_path
            })
            tool_stage.complete({
                "tool_count": len(selection.tool_names),
                "tools": selection.tool_names[:8],
                "base_tools": selection.base_tools,
                "dynamic_tools": selection.dynamic_tools[:5],
                "overridden_sources": overridden_sources,
                "invocation_type": invocation_strategy.type.value if invocation_strategy else "skill",
                "final_source": selection_source
            })
        
        return tools_for_llm, selection
    
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
