"""
多智能体编排器

负责协调多个 Agent 的执行，支持串行、并行、层级三种模式。

架构（V10.3 组合模式）：
    MultiAgentOrchestrator 通过组合以下子模块实现功能：
    - TaskDecomposer: 调用 LeadAgent 进行任务分解
    - WorkerRunner: 复用 RVRExecutor 执行单个 Worker
    - CriticEvaluator: 执行 → 评估循环（pass/retry/replan）
    - ResultAggregator: 多 Worker 结果聚合和最终摘要
    - EventEmitter: SSE 事件发送

设计原则：
    1. 不继承 Agent/BaseAgent，自行管理状态
    2. Worker 复用 RVRExecutor（统一执行路径，V10.4）
    3. 通过 Factory.create_multi_agent() 创建，通过 MultiAgentExecutor 适配

核心能力：
    - 检查点机制：每个 Agent 完成后自动保存，支持从故障点恢复
    - Lead Agent（Opus）：任务分解和结果综合
    - Critic Agent：评估执行质量，支持 pass/retry/replan/fail 决策
    - 依赖注入（V10.4）：inject_dependencies() 统一注入 broadcaster/tool_executor/llm

调用入口：
    1. ChatService → AgentFactory.create_multi_agent() → orchestrator.execute()
    2. MultiAgentExecutor.execute() → orchestrator.execute()（策略模式适配）
"""

# 1. 标准库
import asyncio
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

# V10.3: 不再继承 BaseAgent，自行管理状态
from core.agent.components.checkpoint import Checkpoint, CheckpointManager
from core.agent.components.critic import CriticAgent
from core.agent.components.lead_agent import (
    ContextDependency,
    LeadAgent,
    SubTask,
    TaskDecompositionPlan,
)
from core.agent.execution._multi.critic_evaluator import CriticEvaluator
from core.agent.execution._multi.events import EventEmitter


from core.agent.execution._multi.result_aggregator import ResultAggregator
from core.agent.execution._multi.task_decomposer import TaskDecomposer
from core.agent.execution._multi.worker_runner import WorkerRunner
from core.agent.models import (
    AgentConfig,
    AgentResult,
    CriticAction,
    CriticConfidence,
    CriticConfig,
    CriticResult,
    ExecutionMode,
    MultiAgentConfig,
    OrchestratorState,
    PlanAdjustmentHint,
    SubagentResult,
    TaskAssignment,
)

# 3. 本地模块
from core.planning.protocol import Plan, PlanStep, StepStatus
from core.routing import IntentResult
from logger import get_logger

# 2. 第三方库（无）


logger = get_logger(__name__)


class MultiAgentOrchestrator:
    """
    多智能体编排器

    V10.3: 不再继承 Agent/BaseAgent，自行管理状态。
    通过组合（TaskDecomposer, WorkerRunner, CriticEvaluator, ResultAggregator）实现功能。

    负责协调多个 Agent 的执行：
    - SEQUENTIAL: 依次执行，前一个输出作为后一个输入
    - PARALLEL: 同时执行，结果汇总
    - HIERARCHICAL: 主 Agent 分配任务给子 Agent

    使用方式：
        orchestrator = MultiAgentOrchestrator(config)
        async for event in orchestrator.execute(intent, messages, session_id):
            # 处理事件
            pass
    """

    def __init__(
        self,
        config: Optional[MultiAgentConfig] = None,
        mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
        agents: Optional[List[Dict[str, Any]]] = None,
        enable_checkpoints: bool = True,
        enable_lead_agent: bool = True,
    ):
        """
        初始化编排器

        Args:
            config: 完整的多智能体配置（优先使用）
            mode: 执行模式（当 config 为 None 时使用）
            agents: 智能体配置列表（当 config 为 None 时使用）
            enable_checkpoints: 是否启用检查点（默认 True）
            enable_lead_agent: 是否启用 Lead Agent 进行任务分解（默认 True）
        """
        # V10.3: 自行管理状态（不再继承 Agent）
        self._broadcaster = None
        self._tool_executor = None
        self._current_session_id: Optional[str] = None
        self._current_user_id: Optional[str] = None
        self._current_conversation_id: Optional[str] = None
        self.schema = None
        self.model = None
        self.max_turns = 30

        # 内部状态记录
        self.decomposition_plan: Optional[TaskDecompositionPlan] = None

        if config:
            self.config = config
        else:
            # 从参数构建配置
            agent_configs = []
            for i, agent_dict in enumerate(agents or []):
                agent_configs.append(
                    AgentConfig(
                        agent_id=agent_dict.get("agent_id", f"agent_{i}"),
                        role=agent_dict.get("role", "executor"),
                        model=agent_dict.get("model", "claude-sonnet-4-5-20250929"),
                        system_prompt=agent_dict.get("system_prompt"),
                        tools=agent_dict.get("tools", []),
                    )
                )

            self.config = MultiAgentConfig(
                config_id=f"config_{uuid4()}",
                mode=mode,
                agents=agent_configs,
            )

        self._state: Optional[OrchestratorState] = None

        # V7.1: 检查点管理器
        self.enable_checkpoints = enable_checkpoints
        self.checkpoint_manager = CheckpointManager() if enable_checkpoints else None

        # V7.1: Lead Agent（用于任务分解和结果综合）
        self.enable_lead_agent = enable_lead_agent

        # V7.1: 强弱配对策略
        # Orchestrator (Lead Agent) 使用 Opus，Worker 使用 Sonnet
        orchestrator_model = (
            self.config.orchestrator_config.model
            if self.config.orchestrator_config
            else "claude-opus-4-5-20251101"
        )

        worker_model = (
            self.config.worker_config.model
            if self.config.worker_config
            else "claude-sonnet-4-5-20250929"
        )

        # V7.1: 传递配置给 LeadAgent
        if enable_lead_agent:
            if self.config.orchestrator_config:
                self.lead_agent = LeadAgent(
                    model=orchestrator_model,
                    thinking_budget=self.config.orchestrator_config.thinking_budget,
                    max_tokens=self.config.orchestrator_config.max_tokens,
                )
            else:
                self.lead_agent = LeadAgent(model=orchestrator_model)
        else:
            self.lead_agent = None
        self.worker_model = worker_model  # 用于 Worker Agents

        # V7.2: Critic Agent（评估执行质量）
        critic_config = self.config.critic_config
        if critic_config and critic_config.enabled:
            self.critic = CriticAgent(
                model=critic_config.model,
                enable_thinking=critic_config.enable_thinking,
                config=critic_config,
            )
            self.critic_config = critic_config
            logger.info(
                f"✅ Critic Agent 已启用: model={critic_config.model}, "
                f"max_retries={critic_config.max_retries}, "
                f"auto_pass={critic_config.auto_pass_on_high_confidence}"
            )
        else:
            self.critic = None
            self.critic_config = None
            logger.info("ℹ️ Critic Agent 未启用")

        # V7.2: Plan 存储（用于 replan）
        self.plan: Optional[Plan] = None
        self.plan_todo_tool = None  # 延迟初始化，避免循环依赖

        # 🆕 V7.2: 工具和记忆系统（延迟初始化）
        self._tool_loader = None  # 工具加载器
        self._tool_executor = None  # 🆕 V7.3: 工具执行器（用于 RVR 循环）
        self._working_memory = None  # 工作记忆
        self._mem0_client = None  # Mem0 客户端

        # 🆕 V7.4: Token 使用统计
        from models.usage import UsageTracker

        self._usage_tracker = UsageTracker()

        # 追踪信息（用于监控和调试）
        self._execution_trace = []

        # 🆕 V10.3: 组合模块（职责委托）
        self.task_decomposer = TaskDecomposer(
            lead_agent=self.lead_agent,
            usage_tracker=self.usage_tracker,
        )
        self.worker_runner = WorkerRunner(
            worker_model=self.worker_model,
            config=self.config,
            usage_tracker=self.usage_tracker,
            prompt_builder=self,
        )
        self.critic_evaluator = CriticEvaluator(
            critic=self.critic,
            critic_config=self.critic_config,
        )
        self.result_aggregator = ResultAggregator(
            lead_agent=self.lead_agent,
            usage_tracker=self.usage_tracker,
        )
        self.event_emitter = EventEmitter(broadcaster=None)

        # 初始化标记
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        异步初始化：加载需要异步初始化的组件

        使用方式：
            orchestrator = MultiAgentOrchestrator(...)
            await orchestrator.initialize()
        """
        if self._initialized:
            return

        # 初始化 Critic Agent
        if self.critic:
            await self.critic.initialize()

        self._initialized = True
        logger.debug("[MultiAgentOrchestrator] 初始化完成")

    # ==================== 依赖注入（V10.4） ====================

    def inject_dependencies(
        self,
        broadcaster=None,
        tool_executor=None,
        llm=None,
    ) -> None:
        """
        正规的依赖注入（替代外部直接设置私有属性）

        V10.4: 统一的依赖注入入口，确保所有子组件同步更新。

        Args:
            broadcaster: 事件广播器
            tool_executor: 工具执行器
            llm: LLM 服务
        """
        if broadcaster:
            self._broadcaster = broadcaster
            self.event_emitter.broadcaster = broadcaster
            self.worker_runner.broadcaster = broadcaster
        if tool_executor:
            self._tool_executor = tool_executor
            self.worker_runner.tool_executor = tool_executor
        if llm:
            self._llm = llm

    # ==================== 属性（V10.3: 自行管理） ====================

    @property
    def broadcaster(self):
        """事件广播器"""
        return self._broadcaster

    @broadcaster.setter
    def broadcaster(self, value):
        self._broadcaster = value

    @property
    def tool_executor(self):
        """工具执行器"""
        return self._tool_executor

    @tool_executor.setter
    def tool_executor(self, value):
        self._tool_executor = value

    @property
    def usage_tracker(self):
        """Token 使用追踪器"""
        return self._usage_tracker

    @property
    def usage_stats(self) -> Dict[str, int]:
        """Token 使用统计"""
        if self._usage_tracker:
            return self._usage_tracker.get_stats()
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
        }

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

    def clone_for_session(
        self,
        event_manager: Any = None,
        workspace_dir: Optional[str] = None,
        conversation_service: Optional[Any] = None,
        **kwargs,
    ) -> "MultiAgentOrchestrator":
        """
        从原型克隆实例

        MultiAgentOrchestrator 是有状态的编排器，克隆时需要：
        - 复用配置（config, critic_config）
        - 重置状态（_state, plan, _execution_trace）
        - 创建新的 usage_tracker

        Args:
            event_manager: 事件管理器（MultiAgent 不使用，保持接口一致）
            workspace_dir: 工作目录
            conversation_service: 会话服务（MultiAgent 不使用，保持接口一致）
            **kwargs: 其他参数

        Returns:
            克隆后的 MultiAgentOrchestrator 实例
        """
        clone = MultiAgentOrchestrator(
            config=self.config,
            enable_checkpoints=self.enable_checkpoints,
            enable_lead_agent=self.enable_lead_agent,
        )

        # 重置状态
        clone._state = None
        clone.plan = None
        clone._execution_trace = []
        clone._initialized = False

        # 复用已初始化的组件（如果有）
        if self.tool_executor:
            clone.tool_executor = self.tool_executor
        if self._tool_loader:
            clone._tool_loader = self._tool_loader

        # 复用 worker_runner 的共享资源
        if self.worker_runner._initialized:
            clone.worker_runner._tool_loader = self.worker_runner._tool_loader
            clone.worker_runner._tool_executor = self.worker_runner._tool_executor

        logger.debug("🚀 MultiAgentOrchestrator 克隆完成")
        return clone

    def _accumulate_subagent_usage(self, subagent) -> None:
        """
        🆕 V7.4: 累积子智能体的 usage

        Args:
            subagent: 子智能体实例（需要有 usage_tracker 或 usage_stats）
        """
        if hasattr(subagent, "usage_tracker"):
            sub_stats = subagent.usage_tracker.get_stats()
            self.usage_tracker.accumulate_from_dict(
                {
                    "input_tokens": sub_stats.get("total_input_tokens", 0),
                    "output_tokens": sub_stats.get("total_output_tokens", 0),
                    "thinking_tokens": sub_stats.get("total_thinking_tokens", 0),
                    "cache_read_tokens": sub_stats.get("total_cache_read_tokens", 0),
                    "cache_creation_tokens": sub_stats.get("total_cache_creation_tokens", 0),
                }
            )
            logger.debug(
                f"📊 累积子智能体 usage: "
                f"input={sub_stats.get('total_input_tokens', 0)}, "
                f"output={sub_stats.get('total_output_tokens', 0)}"
            )

    # ==================== 执行方法 ====================

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        session_id: str,
        intent: Optional[IntentResult] = None,
        enable_stream: bool = True,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行多智能体协作

        V7.1 新增：
        - 支持从检查点恢复
        - 使用 Lead Agent 进行任务分解（如果启用）

        Args:
            messages: 消息历史
            session_id: 会话 ID
            intent: 意图分析结果（来自路由层）
            enable_stream: 是否启用流式输出（未使用，保持接口一致）
            **kwargs: 其他参数
                - message_id: 消息 ID
                - resume_from_checkpoint: 是否尝试从检查点恢复（默认 True）

        Yields:
            事件字典
        """
        # 从 kwargs 提取参数
        message_id = kwargs.get("message_id")
        resume_from_checkpoint = kwargs.get("resume_from_checkpoint", True)

        start_time = time.time()

        # 🆕 V7.2: 初始化共享资源（工具、记忆）
        user_id = intent.user_id if intent and hasattr(intent, "user_id") else None
        await self._initialize_shared_resources(
            session_id=session_id,
            user_id=user_id,
        )

        # V7.1: 尝试从检查点恢复
        checkpoint = None
        if resume_from_checkpoint and self.checkpoint_manager:
            checkpoint = await self.checkpoint_manager.load_latest_checkpoint(session_id)
            if checkpoint and self.checkpoint_manager.can_resume(checkpoint):
                logger.info(f"🔄 从检查点恢复: {checkpoint.checkpoint_id}")
                self._state = self.checkpoint_manager.restore_state(checkpoint)

                yield {
                    "type": "orchestrator_resumed",
                    "session_id": session_id,
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "completed_agents": len(self._state.completed_agents),
                    "pending_agents": len(self._state.pending_agents),
                }

        # 初始化状态（如果没有恢复）
        if not self._state:
            self._state = OrchestratorState(
                state_id=f"orch_{uuid4()}",
                session_id=session_id,
                config_id=self.config.config_id,
                mode=self.config.mode,
                status="running",
                pending_agents=[agent.agent_id for agent in self.config.agents],
                started_at=datetime.now(),
            )

            # 🆕 V10.1: 发送开始事件（通过 content_* 通道）
            await self.event_emitter.emit_orchestrator_start(
                session_id=session_id,
                mode=self.config.mode.value,
                agent_count=len(self.config.agents),
                lead_agent_enabled=self.enable_lead_agent,
            )

        try:
            # V7.1: 使用 Lead Agent 进行任务分解（如果启用且不是恢复状态）
            decomposition_plan = None
            if self.enable_lead_agent and not checkpoint and self.lead_agent:
                try:
                    # 🔧 修复：查找最后一条 role=user 的消息（而不是 messages[-1]，可能是 preface）
                    user_query = self._extract_user_query(messages)
                    available_tools = list(
                        set(tool for agent in self.config.agents for tool in agent.tools)
                    )

                    self._trace(
                        "lead_agent_decompose_start",
                        {
                            "query": user_query,
                            "available_tools": available_tools,
                        },
                    )

                    decomposition_plan = await self.lead_agent.decompose_task(
                        user_query=user_query,
                        conversation_history=messages,
                        available_tools=available_tools,
                        intent_info=intent.to_dict() if intent else None,
                    )

                    # 🆕 V7.4: 累积 LeadAgent.decompose_task 的 usage
                    if hasattr(self.lead_agent, "last_llm_response"):
                        self.usage_tracker.accumulate(self.lead_agent.last_llm_response)

                    self._trace(
                        "lead_agent_decompose_done",
                        {
                            "plan_id": decomposition_plan.plan_id,
                            "subtasks_count": len(decomposition_plan.subtasks),
                            "execution_mode": decomposition_plan.execution_mode.value,
                        },
                    )

                    # 保存计划到实例变量，以便后续构建 content_blocks
                    self.decomposition_plan = decomposition_plan

                    # 🆕 V10.1: 发送任务分解事件（通过 content_* 通道）
                    await self.event_emitter.emit_decomposition(
                        session_id=session_id,
                        plan_id=decomposition_plan.plan_id,
                        subtasks_count=len(decomposition_plan.subtasks),
                        execution_mode=decomposition_plan.execution_mode.value,
                        reasoning=decomposition_plan.reasoning,
                    )

                except Exception as e:
                    logger.warning(f"⚠️ Lead Agent 任务分解失败: {e}，使用默认配置")
                    self._trace("lead_agent_decompose_error", {"error": str(e)})

            # 根据模式执行（V10.4: 内部方法改为普通 async def）
            if self.config.mode == ExecutionMode.SEQUENTIAL:
                await self._execute_sequential(
                    messages, session_id, message_id, decomposition_plan
                )

            elif self.config.mode == ExecutionMode.PARALLEL:
                await self._execute_parallel(
                    messages, session_id, message_id, decomposition_plan
                )

            elif self.config.mode == ExecutionMode.HIERARCHICAL:
                await self._execute_hierarchical(
                    intent, messages, session_id, message_id, decomposition_plan
                )

            # V7.1: 使用 Lead Agent 生成最终汇总
            if self.config.enable_final_summary:
                if (
                    self.enable_lead_agent
                    and self.lead_agent
                    and len(self._state.agent_results) > 0
                ):
                    # 使用 Lead Agent 进行专业的结果综合
                    # 🔧 修复：查找最后一条 role=user 的消息
                    user_query = self._extract_user_query(messages)

                    subtask_results = [
                        {
                            "agent_id": result.agent_id,
                            "title": f"Agent {result.agent_id}",
                            "output": result.output,
                            "success": result.success,
                        }
                        for result in self._state.agent_results
                    ]

                    self._trace(
                        "lead_agent_synthesize_start",
                        {
                            "results_count": len(subtask_results),
                        },
                    )

                    final_output = await self.lead_agent.synthesize_results(
                        subtask_results=subtask_results,
                        original_query=user_query,
                        synthesis_strategy=(
                            decomposition_plan.synthesis_strategy if decomposition_plan else None
                        ),
                    )

                    # 🆕 V7.4: 累积 LeadAgent.synthesize_results 的 usage
                    if hasattr(self.lead_agent, "last_llm_response"):
                        self.usage_tracker.accumulate(self.lead_agent.last_llm_response)

                    self._trace(
                        "lead_agent_synthesize_done",
                        {
                            "output_length": len(final_output),
                        },
                    )
                else:
                    # 降级：使用简单汇总
                    final_output = await self._generate_summary()

                self._state.final_output = final_output

                # 🆕 V10.1: 发送汇总事件（通过 content_* 通道）
                await self.event_emitter.emit_orchestrator_summary(session_id=session_id, summary=final_output)

            # 完成
            duration_ms = int((time.time() - start_time) * 1000)
            self._state.status = "completed"
            self._state.completed_at = datetime.now()
            self._state.total_duration_ms = duration_ms

            # 🆕 V10.1: 发送结束事件（通过 content_* 通道）
            await self.event_emitter.emit_orchestrator_end(
                session_id=session_id,
                status="completed",
                duration_ms=duration_ms,
                agent_results_count=len(self._state.agent_results),
            )

        except Exception as e:
            logger.error(f"❌ 多智能体执行失败: {e}", exc_info=True)
            self._state.status = "failed"
            self._state.errors.append(
                {
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # V7.1: 错误时保存检查点（关键！）
            if self.checkpoint_manager:
                try:
                    error_checkpoint = await self.checkpoint_manager.save_checkpoint_on_error(
                        state=self._state, error=e
                    )
                    logger.info(f"💾 错误检查点已保存: {error_checkpoint.checkpoint_id}")
                except Exception as cp_err:
                    logger.error(f"保存错误检查点失败: {cp_err}")

            self._trace("orchestrator_error", {"error": str(e), "type": type(e).__name__})

            # 🆕 V10.1: 发送错误事件（通过 content_* 通道）
            await self.event_emitter.emit_orchestrator_error(
                session_id=session_id,
                error=str(e),
                checkpoint_saved=self.checkpoint_manager is not None,
            )

    async def _execute_sequential(
        self,
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
        decomposition_plan: Optional[TaskDecompositionPlan] = None,
    ) -> None:
        """
        串行执行模式

        V10.4: 改为普通 async def（事件通过 broadcaster 直接推送）

        V7.1 改进：
        - 支持任务分解计划
        - 每个 Agent 完成后自动保存检查点

        V7.11 改进：
        - 支持上下文关联性判断
        - 高关联性任务由主 Agent（Lead Agent）自己执行

        每个 Agent 依次执行，前一个的输出作为后一个的输入
        """
        current_input = messages
        previous_output = None

        # 🆕 V7.11: 如果有分解计划，按 subtask 执行（支持上下文关联性）
        if decomposition_plan and decomposition_plan.subtasks:
            for subtask in decomposition_plan.subtasks:
                subtask_id = subtask.subtask_id

                # 跳过已完成的任务（恢复场景）
                if subtask_id in self._state.completed_agents:
                    logger.info(f"⏭️ 跳过已完成的任务: {subtask_id}")
                    if self._state.agent_results:
                        last_result = next(
                            (r for r in self._state.agent_results if r.agent_id == subtask_id), None
                        )
                        if last_result:
                            previous_output = last_result.output
                    continue

                self._state.current_agent = subtask_id

                # 🆕 V7.11: 根据上下文关联性决定执行方式
                execute_by_lead = subtask.execute_by_lead
                context_dep = (
                    subtask.context_dependency.value if subtask.context_dependency else "low"
                )

                # 🆕 V10.1: 发送任务开始事件（通过 content_* 通道）
                await self.event_emitter.emit_subtask_start(
                    session_id=session_id,
                    subtask_id=subtask_id,
                    title=subtask.title,
                    role=subtask.assigned_agent_role.value,
                    execute_by_lead=execute_by_lead,
                    context_dependency=context_dep,
                )

                self._trace(
                    "agent_execution_start",
                    {
                        "agent_id": subtask_id,
                        "role": subtask.assigned_agent_role.value,
                        "execute_by_lead": execute_by_lead,
                        "context_dependency": context_dep,
                        "context_dependency_reason": subtask.context_dependency_reason,
                    },
                )

                try:
                    if execute_by_lead:
                        # 🆕 V7.11: 高关联性任务 - 由 Lead Agent 自己执行
                        logger.info(
                            f"🧠 主 Agent 执行高关联性任务: {subtask_id}, "
                            f"原因: {subtask.context_dependency_reason or '上下文依赖'}"
                        )
                        result = await self._execute_by_lead_agent(
                            subtask=subtask,
                            messages=messages,
                            previous_output=previous_output,
                            session_id=session_id,
                        )
                    else:
                        # 低/中关联性任务 - 派发给 Subagent
                        logger.info(f"🤖 派发给 Subagent: {subtask_id}")

                        # 为 subtask 创建临时 AgentConfig
                        agent_config = AgentConfig(
                            agent_id=subtask_id,
                            role=subtask.assigned_agent_role,
                            model=self.worker_model,
                            tools=subtask.tools_required,
                        )

                        result = await self._execute_step_with_critique(
                            agent_config,
                            subtask,
                            current_input,
                            previous_output,
                            session_id,
                        )
                except Exception as e:
                    logger.error(f"❌ 任务 {subtask_id} 执行异常: {e}", exc_info=True)
                    result = AgentResult(
                        result_id=f"result_{uuid4()}",
                        agent_id=subtask_id,
                        success=False,
                        error=str(e),
                        turns_used=0,
                        duration_ms=0,
                        started_at=datetime.now(),
                        completed_at=datetime.now(),
                    )

                self._state.agent_results.append(result)
                self._state.completed_agents.append(subtask_id)
                if subtask_id in self._state.pending_agents:
                    self._state.pending_agents.remove(subtask_id)
                self._state.total_turns += result.turns_used

                previous_output = result.output

                self._trace(
                    "agent_execution_done",
                    {
                        "agent_id": subtask_id,
                        "success": result.success,
                        "turns_used": result.turns_used,
                        "output_length": len(result.output) if result.output else 0,
                        "executed_by_lead": execute_by_lead,
                    },
                )

                # 保存检查点
                if self.checkpoint_manager:
                    try:
                        checkpoint = (
                            await self.checkpoint_manager.save_checkpoint_on_agent_completion(
                                state=self._state, agent_id=subtask_id, result=result
                            )
                        )
                        logger.info(f"💾 检查点已保存: {checkpoint.checkpoint_id}")
                    except Exception as cp_err:
                        logger.error(f"保存检查点失败: {cp_err}")

                # 🆕 V10.1: 发送任务结束事件（通过 content_* 通道）
                await self.event_emitter.emit_subtask_end(
                    session_id=session_id,
                    subtask_id=subtask_id,
                    output=result.output or "",
                    success=result.success,
                    executed_by_lead=execute_by_lead,
                )

                if not result.success and self.config.fail_fast:
                    logger.warning(f"⚠️ 任务 {subtask_id} 失败，fail_fast=True，停止执行")
                    break
        else:
            # 没有分解计划，按原有逻辑执行
            for agent_config in self.config.agents:
                agent_id = agent_config.agent_id

                if agent_id in self._state.completed_agents:
                    logger.info(f"⏭️ 跳过已完成的 Agent: {agent_id}")
                    if self._state.agent_results:
                        last_result = next(
                            (r for r in self._state.agent_results if r.agent_id == agent_id), None
                        )
                        if last_result:
                            previous_output = last_result.output
                    continue

                self._state.current_agent = agent_id

                # 🆕 V10.1: 发送任务开始事件（通过 content_* 通道）
                await self.event_emitter.emit_subtask_start(
                    session_id=session_id,
                    subtask_id=agent_id,
                    title=f"Agent {agent_id}",
                    role=agent_config.role.value,
                    execute_by_lead=False,
                    context_dependency="low",
                )

                task = TaskAssignment(
                    task_id=f"task_{uuid4()}",
                    agent_id=agent_id,
                    instruction=f"执行 {agent_config.role.value} 任务",
                    source_agent=(
                        self._state.completed_agents[-1] if self._state.completed_agents else None
                    ),
                    source_output=previous_output,
                )
                self._state.task_assignments.append(task)

                self._trace(
                    "agent_execution_start",
                    {
                        "agent_id": agent_id,
                        "role": agent_config.role.value,
                    },
                )

                try:
                    result = await self._execute_step_with_critique(
                        agent_config,
                        None,
                        current_input,
                        previous_output,
                        session_id,
                    )
                except Exception as e:
                    logger.error(f"❌ Agent {agent_id} 执行异常: {e}", exc_info=True)
                    result = AgentResult(
                        result_id=f"result_{uuid4()}",
                        agent_id=agent_config.agent_id,
                        success=False,
                        error=str(e),
                        turns_used=0,
                        duration_ms=0,
                        started_at=datetime.now(),
                        completed_at=datetime.now(),
                    )

                self._state.agent_results.append(result)
                self._state.completed_agents.append(agent_id)
                self._state.pending_agents.remove(agent_id)
                self._state.total_turns += result.turns_used

                previous_output = result.output

                self._trace(
                    "agent_execution_done",
                    {
                        "agent_id": agent_id,
                        "success": result.success,
                        "turns_used": result.turns_used,
                        "output_length": len(result.output) if result.output else 0,
                    },
                )

                if self.checkpoint_manager:
                    try:
                        checkpoint = (
                            await self.checkpoint_manager.save_checkpoint_on_agent_completion(
                                state=self._state, agent_id=agent_id, result=result
                            )
                        )
                        logger.info(f"💾 检查点已保存: {checkpoint.checkpoint_id}")
                    except Exception as cp_err:
                        logger.error(f"保存检查点失败: {cp_err}")

                # 🆕 V10.1: 发送任务结束事件（通过 content_* 通道）
                await self.event_emitter.emit_subtask_end(
                    session_id=session_id,
                    subtask_id=agent_id,
                    output=result.output or "",
                    success=result.success,
                    executed_by_lead=False,
                )

                if not result.success and self.config.fail_fast:
                    logger.warning(f"⚠️ Agent {agent_id} 失败，fail_fast=True，停止执行")
                    break

        self._state.current_agent = None

    async def _execute_parallel(
        self,
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
        decomposition_plan: Optional[TaskDecompositionPlan] = None,
    ) -> None:
        """
        并行执行模式（带重试）

        V10.4: 改为普通 async def（事件通过 broadcaster 直接推送）

        所有 Agent 同时执行，失败时自动重试
        """

        # 创建所有 Agent 的任务（V7.2: 带 Critic 评估）
        async def execute_with_critique(agent_config, subtask=None):
            """并行执行单个 Agent（带 Critic 评估）"""
            try:
                # V7.2: 使用带 Critic 的执行方法
                result = await self._execute_step_with_critique(
                    agent_config=agent_config,
                    subtask=subtask,
                    messages=messages,
                    previous_output=None,
                    session_id=session_id,
                )
                return result
            except Exception as e:
                logger.error(f"❌ Agent {agent_config.agent_id} 执行异常: {e}", exc_info=True)
                return AgentResult(
                    result_id=f"result_{uuid4()}",
                    agent_id=agent_config.agent_id,
                    success=False,
                    error=str(e),
                    turns_used=0,
                    duration_ms=0,
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                )

        # 创建所有任务
        tasks = []
        for i, agent_config in enumerate(self.config.agents):
            # 从分解计划获取子任务
            subtask = None
            if decomposition_plan and i < len(decomposition_plan.subtasks):
                subtask = decomposition_plan.subtasks[i]

            task = asyncio.create_task(execute_with_critique(agent_config, subtask))
            tasks.append((agent_config, task))

        # 🆕 V10.1: 并行开始事件（不单独发送，已由 orchestrator_start 覆盖）
        # parallel_start 信息已包含在 orchestrator_start 中

        # 等待所有任务完成
        for agent_config, task in tasks:
            try:
                result = await asyncio.wait_for(task, timeout=agent_config.timeout_seconds)
            except asyncio.TimeoutError:
                result = AgentResult(
                    result_id=f"result_{uuid4()}",
                    agent_id=agent_config.agent_id,
                    success=False,
                    output=f"Agent {agent_config.agent_id} 执行超时（超过 {agent_config.timeout_seconds} 秒）",
                    error="执行超时",
                )

            self._state.agent_results.append(result)
            self._state.completed_agents.append(agent_config.agent_id)

            # 🆕 V10.1: 发送任务结束事件（通过 content_* 通道）
            # 注意：并行模式下没有发送 agent_start，这里直接发送完整的 tool_use + tool_result
            await self.event_emitter.emit_subtask_start(
                session_id=session_id,
                subtask_id=agent_config.agent_id,
                title=f"Agent {agent_config.agent_id}",
                role=agent_config.role.value,
                execute_by_lead=False,
                context_dependency="low",
            )
            await self.event_emitter.emit_subtask_end(
                session_id=session_id,
                subtask_id=agent_config.agent_id,
                output=result.output or "",
                success=result.success,
                executed_by_lead=False,
            )

        self._state.pending_agents = []

    async def _execute_hierarchical(
        self,
        intent: Optional[IntentResult],
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
        decomposition_plan: Optional[TaskDecompositionPlan] = None,
    ) -> None:
        """
        层级执行模式

        V10.4: 改为普通 async def（事件通过 broadcaster 直接推送）

        主 Agent（Planner）分解任务，分配给子 Agent 执行
        """
        # 找到 Planner Agent
        planner = next(
            (a for a in self.config.agents if a.role.value == "planner"),
            self.config.agents[0] if self.config.agents else None,
        )

        if not planner:
            # 🆕 V10.1: 发送错误事件（通过 content_* 通道）
            await self.event_emitter.emit_orchestrator_error(
                session_id=session_id,
                error="层级模式需要至少一个 Planner Agent",
                checkpoint_saved=False,
            )
            return

        # Step 1: Planner 分解任务
        # 🆕 V10.1: 发送 Planner 开始事件（通过 content_* 通道）
        await self.event_emitter.emit_subtask_start(
            session_id=session_id,
            subtask_id=planner.agent_id,
            title=f"Planner: {planner.agent_id}",
            role="planner",
            execute_by_lead=True,
            context_dependency="high",
        )

        # 这里是占位实现，实际需要 Planner 返回任务分解
        plan_result = await self._execute_single_agent(planner, messages, None, session_id)

        # 🆕 V10.1: 发送 Planner 结束事件（通过 content_* 通道）
        await self.event_emitter.emit_subtask_end(
            session_id=session_id,
            subtask_id=planner.agent_id,
            output=plan_result.output or "",
            success=plan_result.success,
            executed_by_lead=True,
        )

        # Step 2: 分配任务给子 Agent（简化实现）
        sub_agents = [a for a in self.config.agents if a.agent_id != planner.agent_id]

        for sub_agent in sub_agents:
            # 🆕 V10.1: 发送子 Agent 开始事件（通过 content_* 通道）
            await self.event_emitter.emit_subtask_start(
                session_id=session_id,
                subtask_id=sub_agent.agent_id,
                title=f"SubAgent: {sub_agent.agent_id}",
                role=sub_agent.role.value,
                execute_by_lead=False,
                context_dependency="medium",
            )

            result = await self._execute_single_agent(
                sub_agent, messages, plan_result.output, session_id
            )

            self._state.agent_results.append(result)
            self._state.completed_agents.append(sub_agent.agent_id)

            # 🆕 V10.1: 发送子 Agent 结束事件（通过 content_* 通道）
            await self.event_emitter.emit_subtask_end(
                session_id=session_id,
                subtask_id=sub_agent.agent_id,
                output=result.output or "",
                success=result.success,
                executed_by_lead=False,
            )

    async def _execute_single_agent(
        self,
        config: AgentConfig,
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
        subtask: Optional[SubTask] = None,
    ) -> AgentResult:
        """
        执行单个 Agent — 委托给 WorkerRunner

        V10.3: 从内联 RVR 循环迁移到 WorkerRunner 模块
        """
        return await self.worker_runner.execute_worker(
            config=config,
            messages=messages,
            previous_output=previous_output,
            session_id=session_id,
            subtask=subtask,
            build_system_prompt=self._build_subagent_system_prompt,
            build_orchestrator_summary=self._build_orchestrator_summary,
            summarize_previous_output=self._summarize_previous_output,
        )

    async def _execute_by_lead_agent(
        self,
        subtask: SubTask,
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
    ) -> AgentResult:
        """
        由主 Agent（Lead Agent）执行高关联性任务 — 委托给 WorkerRunner

        V10.4: 复用 WorkerRunner.execute_by_lead_agent()（统一走 RVRExecutor）
        """
        orchestrator_model = (
            self.config.orchestrator_config.model
            if self.config.orchestrator_config
            else "claude-opus-4-5-20251101"
        )
        return await self.worker_runner.execute_by_lead_agent(
            subtask=subtask,
            messages=messages,
            previous_output=previous_output,
            session_id=session_id,
            lead_agent_model=orchestrator_model,
        )

    def _build_subagent_system_prompt(
        self,
        config: "AgentConfig",
        subtask: Optional["SubTask"] = None,
        orchestrator_context: Optional[str] = None,
    ) -> str:
        """
        构建 Subagent 系统提示词（8 个核心要素）

        从 prompts/multi_agent/subagent.md 加载模板，注入动态变量。
        """
        # 1. 明确的目标（Objective）
        if subtask:
            objective = f"**你的目标**：{subtask.title}\n{subtask.description}"
        else:
            objective = f"**你的目标**：执行 {config.role.value} 任务"

        # 2. 期望输出格式（Output Format）
        if subtask and subtask.expected_output:
            output_format = (
                f"**输出格式要求**：\n{subtask.expected_output}\n\n"
                "请严格遵循以上格式，使用结构化的 JSON 或 Markdown。"
            )
        else:
            output_format = (
                "**输出格式要求**：\n"
                "- 使用 Markdown 格式\n"
                "- 包含清晰的标题和段落\n"
                "- 如果有多个发现，使用列表或表格"
            )

        # 3. 可用工具指导（Tools Guidance）
        tools_list = (
            subtask.tools_required if subtask and subtask.tools_required else None
        ) or (config.tools if config.tools else None)
        if tools_list:
            tools_str = "\n".join(f"- {tool}" for tool in tools_list)
            tools_guidance = (
                f"**可用工具**：\n{tools_str}\n\n"
                "**重要：你必须主动使用工具获取信息！**\n"
                "- 不要仅凭已有知识回答，必须调用工具获取最新数据\n"
                "- 每个子任务至少调用 1-2 次工具\n"
                "- 工具失败时，尝试替代方案"
            )
        else:
            tools_guidance = (
                "**可用工具**：无特定工具要求，使用你的知识和推理能力完成任务。"
            )

        # 4. 任务边界（Task Boundaries）
        if subtask and subtask.constraints:
            constraints_str = "\n".join(f"- {c}" for c in subtask.constraints)
            boundaries = f"**任务边界与约束**：\n{constraints_str}"
        else:
            boundaries = (
                "**任务边界**：\n"
                "- 专注于你的具体任务\n"
                "- 不要尝试解决整个问题\n"
                "- 提供简洁、针对性的结果"
            )

        # 5. 成功标准（Success Criteria）
        if subtask and subtask.success_criteria:
            criteria_str = "\n".join(f"- {c}" for c in subtask.success_criteria)
            success_criteria = (
                f"**成功标准**：\n{criteria_str}\n\n"
                "完成任务后，请自我检查是否满足以上所有标准。"
            )
        else:
            success_criteria = (
                "**成功标准**：\n"
                "- 完整回答任务要求\n"
                "- 信息准确可靠\n"
                "- 表达清晰简洁"
            )

        # 6. 上下文信息（Context）
        context_section = ""
        if orchestrator_context:
            context_section = (
                f"**Orchestrator 上下文**：\n{orchestrator_context}\n\n"
                "（这是 Orchestrator 提供的背景信息，帮助你理解整体任务）"
            )

        # 从 .md 模板加载并注入变量
        from prompts import load_prompt

        try:
            return load_prompt(
                "multi_agent/subagent",
                objective=objective,
                output_format=output_format,
                tools_guidance=tools_guidance,
                boundaries=boundaries,
                success_criteria=success_criteria,
                context_section=context_section,
            )
        except FileNotFoundError:
            logger.warning("⚠️ Subagent Prompt 文件不存在，使用内联 fallback")
            return (
                f"你是一个 Subagent，负责执行特定子任务。\n\n"
                f"{objective}\n\n{output_format}\n\n{tools_guidance}\n\n"
                f"{boundaries}\n\n{success_criteria}\n\n{context_section}"
            )

    def _build_orchestrator_summary(self) -> str:
        """
        生成 Orchestrator 当前状态的摘要（传递给 Subagent）

        目的：提供必要的上下文，但不传递完整的历史记录（上下文隔离）

        Returns:
            str: 摘要文本（< 500 tokens）
        """
        if not self._state:
            return "这是第一个执行的子任务。"

        summary_parts = [
            f"当前执行模式: {self._state.mode.value}",
            f"已完成的 Agent 数量: {len(self._state.completed_agents)}",
        ]

        # 添加最近完成的任务摘要（最多 2 个）
        if self._state.agent_results:
            recent_results = self._state.agent_results[-2:]
            summary_parts.append("\n最近完成的任务：")
            for result in recent_results:
                status = "成功" if result.success else "失败"
                output_preview = result.output[:100] if result.output else "无输出"
                summary_parts.append(
                    f"- {result.agent_id}: {status}, 输出预览: {output_preview}..."
                )

        summary = "\n".join(summary_parts)

        # 确保不超过 500 tokens（约 2000 字符）
        if len(summary) > 2000:
            summary = summary[:2000] + "..."

        return summary

    def _summarize_previous_output(self, output: str, max_length: int = 500) -> str:
        """
        对前一个 Agent 的输出生成摘要

        目的：避免传递完整的历史记录，减少 token 消耗

        Args:
            output: 原始输出
            max_length: 最大摘要长度

        Returns:
            str: 摘要
        """
        if not output:
            return "（无前置输出）"

        # 简单截断（实际可以用 LLM 生成更智能的摘要）
        if len(output) <= max_length:
            return output

        return output[:max_length] + f"\n\n（已截断，原始长度: {len(output)} 字符）"

    async def _initialize_shared_resources(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        tool_names: Optional[List[str]] = None,
    ) -> None:
        """
        初始化共享资源 — 同时初始化 orchestrator 本地资源和 WorkerRunner 资源

        V10.3: WorkerRunner 管理工具加载和执行
        """
        self._current_session_id = session_id
        self._current_user_id = user_id

        # 初始化 WorkerRunner 的共享资源
        await self.worker_runner.initialize_shared_resources(
            session_id=session_id,
            user_id=user_id,
        )

        # 同步 tool_executor（兼容旧代码引用 self.tool_executor）
        if self.worker_runner.tool_executor and not self._tool_executor:
            self._tool_executor = self.worker_runner.tool_executor

        # 同步 tool_loader
        if self.worker_runner._tool_loader and not self._tool_loader:
            self._tool_loader = self.worker_runner._tool_loader

        # 初始化工作记忆
        if self._working_memory is None:
            from core.memory.working import WorkingMemory

            self._working_memory = WorkingMemory()

        # 初始化 Mem0 客户端（可选）
        if self._mem0_client is None and user_id:
            try:
                from core.memory.mem0.client import get_mem0_client

                self._mem0_client = get_mem0_client()
            except Exception as e:
                logger.warning(f"⚠️ Mem0 客户端初始化失败: {e}")
                self._mem0_client = None

    async def _load_subagent_tools(
        self,
        config: AgentConfig,
        subtask: Optional[SubTask] = None,
    ) -> List[Dict[str, Any]]:
        """动态加载 Subagent 工具 — 委托给 WorkerRunner"""
        return await self.worker_runner.load_subagent_tools(config, subtask)

    def _extract_user_query(self, messages: List[Dict[str, Any]]) -> str:
        """从消息历史中提取最后一条用户查询 — 委托给 WorkerRunner"""
        return WorkerRunner._extract_user_query(messages)

    def _trace(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        记录执行追踪（用于监控和调试）

        V7.1: 参考 Anthropic 的生产追踪系统
        记录每个决策、工具调用、状态转换

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        trace_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data,
        }

        self._execution_trace.append(trace_entry)

        # 记录到日志（可选）
        logger.debug(f"📊 [TRACE] {event_type}: {data}")

    def get_execution_trace(self) -> List[Dict[str, Any]]:
        """
        获取完整的执行追踪

        用于：
        - 调试问题
        - 分析 Agent 决策模式
        - 性能优化

        Returns:
            List[Dict]: 执行追踪列表
        """
        return self._execution_trace.copy()

    async def _generate_summary(self) -> str:
        """生成最终汇总 — 委托给 ResultAggregator"""
        return await self.result_aggregator.generate_summary(self._state)

    def build_content_blocks(
        self,
        decomposition_plan: Optional[TaskDecompositionPlan] = None,
        final_summary: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """构建 content_blocks — 委托给 ResultAggregator"""
        plan_to_use = decomposition_plan or self.decomposition_plan
        return ResultAggregator.build_content_blocks(
            state=self._state,
            decomposition_plan=plan_to_use,
            final_summary=final_summary,
        )

    def get_multi_agent_metadata(
        self, decomposition_plan: Optional[TaskDecompositionPlan] = None
    ) -> Dict[str, Any]:
        """获取多智能体 metadata — 委托给 ResultAggregator"""
        plan_to_use = decomposition_plan or self.decomposition_plan
        return ResultAggregator.build_metadata(
            state=self._state,
            config=self.config,
            decomposition_plan=plan_to_use,
            lead_agent=self.lead_agent,
            worker_model=self.worker_model if hasattr(self, "worker_model") else None,
            execution_trace=self.get_execution_trace(),
            checkpoint_manager=self.checkpoint_manager,
        )

    def get_state(self) -> Optional[OrchestratorState]:
        """获取当前状态"""
        return self._state

    # ===================
    # V7.2: Critic 集成
    # ===================

    def _subtask_to_plan_step(self, subtask: SubTask, step_id: str) -> PlanStep:
        """
        将 SubTask 转换为 PlanStep（用于 Critic 评估）

        Args:
            subtask: 子任务定义
            step_id: 步骤 ID

        Returns:
            PlanStep: Plan 步骤
        """
        return PlanStep(
            id=step_id,
            description=subtask.description,
            status=StepStatus.IN_PROGRESS,
            metadata={
                "subtask_id": subtask.subtask_id,
                "title": subtask.title,
                "expected_output": subtask.expected_output,
                "success_criteria": subtask.success_criteria,
                "tools_required": subtask.tools_required,
                "constraints": subtask.constraints,
            },
        )

    async def _execute_step_with_critique(
        self,
        agent_config: AgentConfig,
        subtask: Optional[SubTask],
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
    ) -> AgentResult:
        """
        执行步骤（带 Critic 评估）— 委托给 CriticEvaluator

        V10.3: 从内联评估循环迁移到 CriticEvaluator 模块
        """
        return await self.critic_evaluator.execute_with_critique(
            worker_runner=self.worker_runner,
            agent_config=agent_config,
            subtask=subtask,
            messages=messages,
            previous_output=previous_output,
            session_id=session_id,
            build_system_prompt=self._build_subagent_system_prompt,
            build_orchestrator_summary=self._build_orchestrator_summary,
            summarize_previous_output=self._summarize_previous_output,
        )