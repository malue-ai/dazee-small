"""
Agent - 统一智能体实现

V10.0 破坏性重构：
- 唯一的 Agent 类，执行策略通过 Executor 注入
- 执行策略通过注入 Executor 实现（Strategy 模式）
- 新增策略：只需新增 execution/*.py + 注册
- 新增特殊工具：只需新增 handler
- 新增注入源：只需新增 injector
- 新增 agent 类型：Factory 查表

架构：
┌─────────────────────────────────────────┐
│                Agent                     │
│  ┌─────────────────────────────────┐    │
│  │     Executor (Strategy)          │    │
│  │  - RVRExecutor                   │    │
│  │  - RVRBExecutor                  │    │
│  │  - SequentialExecutor            │    │
│  │  - ParallelExecutor              │    │
│  │  - HierarchicalExecutor          │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘

设计原则：
1. Agent 只做编排，不包含执行逻辑
2. 执行策略由 Executor 实现
3. Factory 负责组装依赖
"""

from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Union,
)

from core.agent.execution.protocol import ExecutionContext, ExecutorConfig
from core.context import stable_json_dumps
from models.usage import UsageResponse, create_usage_tracker
from logger import get_logger

if TYPE_CHECKING:
    from core.agent.execution.protocol import ExecutorProtocol
    from core.events.broadcaster import EventBroadcaster
    from core.llm.base import BaseLLMService, LLMResponse
    from core.routing.types import IntentResult
    from core.tool.executor import ToolExecutor
    from models.usage import UsageTracker

logger = get_logger(__name__)


class AgentState(Enum):
    """Agent 执行状态"""

    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


# 需要注入上下文的工具
CONTEXT_INJECTION_TOOLS = {"api_calling"}


class Agent:
    """
    统一智能体实现

    通过注入 Executor 实现不同的执行策略：
    - RVRExecutor: 标准 RVR 循环
    - RVRBExecutor: 带回溯的 RVR-B 循环
    - SequentialExecutor: 多智能体顺序执行
    - ParallelExecutor: 多智能体并行执行
    - HierarchicalExecutor: 多智能体层级执行

    使用方式（由 Factory 创建）：
        agent = AgentFactory.create(
            strategy="rvr",
            event_manager=em,
            schema=schema
        )

        async for event in agent.execute(messages, session_id):
            yield event
    """

    def __init__(
        self,
        executor: "ExecutorProtocol" = None,
        llm: "BaseLLMService" = None,
        tool_executor: "ToolExecutor" = None,
        broadcaster: "EventBroadcaster" = None,
        schema=None,
        prompt_cache=None,
        context_strategy=None,
        max_steps: int = 30,
    ):
        """
        初始化 Agent

        Args:
            executor: 执行策略（通过 Factory 创建时必需，子类可不传）
            llm: LLM 服务
            tool_executor: 工具执行器
            broadcaster: 事件广播器
            schema: AgentSchema 配置
            prompt_cache: PromptCache 实例
            context_strategy: 上下文策略
            max_steps: 最大执行步数
        """
        # 核心依赖（允许 None，支持子类延迟初始化）
        self._executor = executor
        self._llm = llm
        self._tool_executor = tool_executor
        self._broadcaster = broadcaster

        # 配置
        self._schema = schema
        self._prompt_cache = prompt_cache
        self._context_strategy = context_strategy
        self._max_steps = max_steps

        # Usage 统计
        self._usage_tracker = create_usage_tracker()

        # 上下文
        self._current_session_id: Optional[str] = None
        self._current_user_id: Optional[str] = None
        self._current_conversation_id: Optional[str] = None
        self._injected_session_context: Optional[Dict] = None

        # 状态
        self._state: AgentState = AgentState.IDLE
        self._current_step: int = 0

        # Plan 缓存
        self._plan_cache: Dict[str, Any] = {"plan": None, "todo": None, "tool_calls": []}

        # E2E Tracer（由 Service 层通过 session_context 传入）
        self._tracer = None

        # 工具配置
        self.allow_parallel_tools = (
            getattr(schema, "allow_parallel_tools", True) if schema else True
        )
        self.max_parallel_tools = (
            getattr(schema.tool_selector, "max_parallel_tools", 5)
            if schema and hasattr(schema, "tool_selector")
            else 5
        )
        # plan 工具会写入 Conversation.metadata.plan，必须串行执行
        self._serial_only_tools = {"plan", "request_human_confirmation"}

        # 兼容属性（外部代码可能直接设置）
        self.model: Optional[str] = None
        self.system_prompt: Optional[str] = None
        self.event_manager = None
        self.apis_config: List = []
        self.workspace_dir: Optional[str] = None
        self.conversation_service = None

        # 工具/能力相关
        self.capability_registry = None
        self.tool_selector = None
        self._instance_registry = None

        # 原型/实例标记
        self._is_prototype: bool = False

        # 实例级配置（instance_loader 设置）
        self._instance_skills: List = []
        self.workers_config: List = []

        # MCP 相关
        self._mcp_clients: List = []
        self._mcp_tools: List = []

        executor_name = executor.name if executor else "None"
        logger.info(f"✅ Agent 初始化完成: executor={executor_name}")

    # ==================== 属性 ====================

    @property
    def executor(self) -> "ExecutorProtocol":
        return self._executor

    @property
    def llm(self) -> "BaseLLMService":
        return self._llm

    @property
    def tool_executor(self) -> "ToolExecutor":
        return self._tool_executor

    @property
    def broadcaster(self) -> "EventBroadcaster":
        return self._broadcaster

    @property
    def schema(self):
        return self._schema

    @property
    def prompt_cache(self):
        return self._prompt_cache

    @property
    def context_strategy(self):
        return self._context_strategy

    @property
    def usage_tracker(self) -> "UsageTracker":
        return self._usage_tracker

    @property
    def usage_stats(self) -> Dict[str, int]:
        if self._usage_tracker:
            return self._usage_tracker.get_stats()
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
        }

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def max_turns(self) -> int:
        """兼容属性"""
        return self._max_steps

    @max_turns.setter
    def max_turns(self, value: int) -> None:
        """设置最大执行步数"""
        self._max_steps = value

    # ==================== Session Context ====================

    def inject_session_context(self, session_context: Dict[str, Any]) -> None:
        """
        注入 session context（由 Service 层调用）

        Args:
            session_context: {conversation_id, user_id, ...}
        """
        self._injected_session_context = session_context
        logger.debug(f"📦 Session context 已注入: {list(session_context.keys())}")

    def set_context(
        self, session_id: str = None, user_id: str = None, conversation_id: str = None
    ) -> None:
        """设置执行上下文"""
        if session_id is not None:
            self._current_session_id = session_id
        if user_id is not None:
            self._current_user_id = user_id
        if conversation_id is not None:
            self._current_conversation_id = conversation_id

    # ==================== 状态管理 ====================

    @asynccontextmanager
    async def state_context(self, new_state: AgentState):
        """状态转换上下文管理器"""
        previous_state = self._state
        self._state = new_state
        logger.debug(f"🔄 状态: {previous_state.value} → {new_state.value}")

        try:
            yield
        except Exception as e:
            self._state = AgentState.ERROR
            logger.error(f"❌ 执行出错: {e}")
            raise
        finally:
            if self._state not in (AgentState.ERROR, AgentState.FINISHED):
                self._state = previous_state

    def reset_state(self) -> None:
        """重置状态"""
        self._state = AgentState.IDLE
        self._current_step = 0

    # ==================== 执行入口 ====================

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        session_id: str,
        intent: Optional["IntentResult"] = None,
        enable_stream: bool = True,
        message_id: str = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        统一执行入口

        Args:
            messages: 消息列表
            session_id: 会话 ID
            intent: 意图分析结果
            enable_stream: 是否启用流式
            message_id: 消息 ID
            **kwargs: 其他参数

        Yields:
            SSE 事件流
        """
        from core.agent.context.prompt_builder import build_system_blocks_with_injector
        from core.agent.execution import ExecutionContext
        from core.context.runtime import create_runtime_context

        # 验证必需参数
        if self._injected_session_context is None:
            raise ValueError("session_context 未注入，请先调用 inject_session_context()")
        if intent is None:
            raise ValueError("intent 未传入，Service 层必须提供 intent")

        session_context = self._injected_session_context
        self._injected_session_context = None

        conversation_id = session_context.get("conversation_id", "default")
        user_id = session_context.get("user_id")
        self._current_conversation_id = conversation_id
        self._current_user_id = user_id
        self._current_session_id = session_id

        # 从 session_context 获取 tracer（由 Service 层创建）
        self._tracer = session_context.get("tracer")

        # 从 session_context 获取 plan（由 Service 层加载）
        if session_context.get("plan"):
            self._plan_cache["plan"] = session_context["plan"]

        # 初始化运行时上下文
        ctx = create_runtime_context(session_id=session_id, max_turns=self._max_steps)

        # 工具选择
        tools_for_llm, selection = await self._select_tools(intent, ctx)

        # System Prompt 组装
        user_query = self._extract_user_query(messages)
        system_prompt = await build_system_blocks_with_injector(
            intent=intent,
            prompt_cache=self._prompt_cache,
            context_strategy=self._context_strategy,
            user_id=user_id,
            user_query=user_query,
            available_tools=tools_for_llm,
        )

        # 执行配置
        executor_config = ExecutorConfig(
            max_turns=self._max_steps,
            enable_stream=enable_stream,
            enable_backtrack=self._executor.supports_backtrack(),
        )

        # 执行上下文（V10.1: 传递所有依赖，不再依赖 agent 引用）
        execution_context = ExecutionContext(
            llm=self._llm,
            session_id=session_id,
            conversation_id=conversation_id,
            tool_executor=self._tool_executor,
            tools_for_llm=tools_for_llm,
            broadcaster=self._broadcaster,
            system_prompt=system_prompt,
            intent=intent,
            runtime_ctx=ctx,
            context_strategy=self._context_strategy,
            plan_cache=self._plan_cache,
            extra={
                "usage_tracker": self.usage_tracker,
                "context_engineering": getattr(self, "context_engineering", None),
                "tracer": self._tracer,
            },
        )

        # 委托给 Executor 执行
        if self._executor is None:
            raise ValueError("executor 未初始化，无法执行。请通过 Factory 创建 Agent。")

        async for event in self._executor.execute(
            messages=messages,
            context=execution_context,
            config=executor_config,
        ):
            yield event

        # Final Output
        if self._tracer:
            final_response = (
                ctx.accumulator.get_text_content() if hasattr(ctx, "accumulator") else ""
            )
            self._tracer.set_final_response(final_response[:500] if final_response else "")
            self._tracer.finish()

        # Usage
        stats = self.usage_stats
        await self._broadcaster.accumulate_usage(
            session_id,
            {
                "input_tokens": stats.get("total_input_tokens", 0),
                "output_tokens": stats.get("total_output_tokens", 0),
                "cache_read_tokens": stats.get("total_cache_read_tokens", 0),
                "cache_creation_tokens": stats.get("total_cache_creation_tokens", 0),
            },
        )

        # Usage
        usage_response = UsageResponse.from_tracker(tracker=self._usage_tracker, latency=0)

        yield {
            "type": "message_delta",
            "data": {"type": "billing", "content": usage_response.model_dump()},
        }

        # Stop
        yield await self._broadcaster.emit_message_stop(
            session_id=session_id, message_id=message_id
        )

        logger.info(f"✅ Agent 执行完成: executor={self._executor.name}")

    # ==================== chat() 兼容方法 ====================

    async def chat(
        self,
        messages: List[Dict[str, str]] = None,
        session_id: str = None,
        message_id: str = None,
        enable_stream: bool = True,
        intent: Optional["IntentResult"] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """chat() 方法 - 委托给 execute()"""
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        async for event in self.execute(
            messages=messages or [],
            session_id=session_id,
            intent=intent,
            enable_stream=enable_stream,
            message_id=message_id,
        ):
            yield event

    # ==================== 工具选择 ====================

    async def _select_tools(self, intent: "IntentResult", ctx) -> tuple:
        """工具选择"""
        from core.tool import create_tool_selector
        from core.tool.registry import create_capability_registry

        if not hasattr(self, "tool_selector") or self.tool_selector is None:
            if not hasattr(self, "capability_registry"):
                self.capability_registry = create_capability_registry()
            self.tool_selector = create_tool_selector(registry=self.capability_registry)

        plan = self._plan_cache.get("plan")

        required_capabilities, selection_source, overridden_sources, allowed_tools = (
            await self.tool_selector.resolve_capabilities(
                schema_tools=self._schema.tools if self._schema and self._schema.tools else None,
                plan=plan,
                intent_task_type=intent.agent_type if intent else None,
            )
        )

        available_apis = self.tool_selector.get_available_apis(self._tool_executor)
        selection = await self.tool_selector.select(
            required_capabilities=required_capabilities,
            context={
                "plan": plan,
                "agent_type": intent.agent_type if intent else None,
                "available_apis": available_apis,
            },
            allowed_tools=allowed_tools,
        )

        tools_for_llm = self.tool_selector.get_tools_for_llm(selection, self._llm)

        logger.info(f"✅ 工具选择完成 [{selection_source}]: {len(selection.tool_names)} 个")

        return tools_for_llm, selection

    # ==================== 辅助方法 ====================

    def _extract_user_query(self, messages: List[Dict[str, Any]]) -> str:
        """提取用户查询"""
        if not messages:
            return ""

        content = messages[-1].get("content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            return " ".join(text_parts)

        return ""

    def _inject_tool_context(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """工具上下文注入"""
        if self._tool_executor is None:
            return tool_input

        session_id = self._current_session_id or None
        user_id = self._current_user_id or None
        conversation_id = self._current_conversation_id or None

        if session_id or user_id or conversation_id:
            self._tool_executor.update_context(
                session_id=session_id,
                user_id=user_id,
                conversation_id=conversation_id,
            )

        if tool_name in CONTEXT_INJECTION_TOOLS:
            tool_input.pop("session_id", None)
            tool_input.pop("user_id", None)
            tool_input.pop("conversation_id", None)

        return tool_input

    def _register_tools_to_llm(self) -> None:
        """
        工具注册到 LLM（兼容方法）

        V10.0 架构中工具通过 ToolSelector 动态选择，
        此方法保留用于兼容外部代码调用。
        """
        if self.tool_selector and self._tool_executor:
            logger.debug("🔧 工具已通过 ToolSelector 管理，跳过手动注册")

    def get_plan(self) -> Optional[Dict]:
        """获取当前计划"""
        return self._plan_cache.get("plan")

    def get_progress(self) -> Dict[str, Any]:
        """获取进度"""
        plan = self._plan_cache.get("plan")
        if not plan:
            return {"total": 0, "completed": 0, "progress": 0.0}

        total = len(plan.get("steps", []))
        completed = sum(1 for s in plan.get("steps", []) if s.get("status") == "completed")
        return {
            "total": total,
            "completed": completed,
            "progress": completed / total if total > 0 else 0.0,
        }

    # ==================== 克隆 ====================

    def clone_for_session(
        self, event_manager, workspace_dir: str = None, conversation_service=None
    ) -> "Agent":
        """
        从原型克隆实例

        复用重量级组件，重置会话级状态。
        """
        from core.events.broadcaster import EventBroadcaster
        from core.tool import create_tool_context, create_tool_executor

        # 创建新 broadcaster
        broadcaster = EventBroadcaster(event_manager, conversation_service=conversation_service)

        # 创建独立的 ToolExecutor（并发安全）
        tool_context = create_tool_context(
            event_manager=event_manager,
            workspace_dir=workspace_dir or getattr(self, "workspace_dir", None),
            apis_config=getattr(self, "apis_config", []),
        )
        tool_executor = create_tool_executor(
            registry=getattr(self, "capability_registry", None),
            tool_context=tool_context,
            enable_compaction=True,
        )

        # 复用 tool_instances
        if self._tool_executor:
            tool_executor._tool_instances = self._tool_executor._tool_instances
            tool_executor._tool_handlers = getattr(self._tool_executor, "_tool_handlers", {})

        # 创建克隆
        clone = Agent(
            executor=self._executor,
            llm=self._llm,
            tool_executor=tool_executor,
            broadcaster=broadcaster,
            schema=self._schema,
            prompt_cache=self._prompt_cache,
            context_strategy=self._context_strategy,
            max_steps=self._max_steps,
        )

        # 复制配置
        clone.capability_registry = getattr(self, "capability_registry", None)
        clone.tool_selector = getattr(self, "tool_selector", None)
        clone.allow_parallel_tools = self.allow_parallel_tools
        clone.max_parallel_tools = self.max_parallel_tools
        clone._serial_only_tools = self._serial_only_tools

        # 复制兼容属性
        clone.model = self.model
        clone.system_prompt = self.system_prompt
        clone.event_manager = event_manager
        clone.apis_config = self.apis_config
        clone.workspace_dir = workspace_dir or self.workspace_dir
        clone.conversation_service = conversation_service

        # 复制实例级配置
        clone._instance_registry = self._instance_registry
        clone._instance_skills = self._instance_skills.copy() if self._instance_skills else []
        clone.workers_config = self.workers_config.copy() if self.workers_config else []
        clone._mcp_clients = self._mcp_clients.copy() if self._mcp_clients else []
        clone._mcp_tools = self._mcp_tools.copy() if self._mcp_tools else []

        logger.debug(f"🚀 Agent 克隆完成: executor={self._executor.name}")

        return clone


# V10.3: BaseAgent 别名已删除，统一使用 Agent
