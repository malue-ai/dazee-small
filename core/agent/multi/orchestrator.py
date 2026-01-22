"""
多智能体编排器（V7.9 - Agent 选择三级优化）

负责协调多个 Agent 的执行，支持串行、并行、层级三种模式。

设计原则：
1. 与 SimpleAgent 完全独立
2. 通过 AgentRouter 被调用，而非互相嵌套
3. 每个子 Agent 是独立的 LLM 调用单元

V7.1 新增特性（基于 Anthropic Multi-Agent System）：
- ✅ 检查点机制：每个 Agent 完成后自动保存，支持从故障点恢复
- ✅ Lead Agent：使用 Opus 进行任务分解和结果综合
- ✅ 增强追踪：记录每个决策、工具调用、状态转换
- ✅ 明确任务定义：为每个 Worker 提供清晰的目标、工具、边界

V7.2 新增特性：
- ✅ Critic Agent：评估执行质量，支持 pass/retry/replan/fail 决策
- ✅ Plan-Execute-Critique 循环：智能质量保证和计划调整

V7.7 新增特性：
- ✅ DAGScheduler 集成：真正的依赖感知并行执行
- ✅ 依赖结果自动注入
- ✅ 分层并行执行（组内并行，组间串行）

V7.8 新增特性：
- ✅ 数据结构统一：SubTask → PlanStep，移除冗余转换层
- ✅ DAG-Critic 协同：REPLAN 后自动重算并行组
- ✅ 死代码清理：删除 _spawn_subagent、_planstep_to_subtask、_subtask_to_plan_step

V7.9 新增特性（借鉴工具选择三级优化 V7.6）：
- ✅ Agent 选择三级优先级：Config > Task > Capability
- ✅ 有效性验证：自动检测无效 Agent 配置
- ✅ 覆盖透明化：记录选择来源和被覆盖候选
- ✅ Tracer 增强追踪：完整记录 Agent 选择决策过程
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from core.agent.multi.models import (
    ExecutionMode,
    AgentConfig,
    AgentRole,  # V7.7: 用于步骤到 Agent 的映射
    MultiAgentConfig,
    TaskAssignment,
    AgentResult,
    # SubagentResult,  # V7.8: 已废弃，_spawn_subagent 已删除
    OrchestratorState,
    CriticConfig,
    CriticAction,
    CriticConfidence,
    CriticResult,
    PlanAdjustmentHint,  # V7.2: 计划调整建议
    AgentSelectionResult,  # V7.9: Agent 选择结果
)
from core.agent.multi.checkpoint import CheckpointManager, Checkpoint
from core.agent.multi.lead_agent import LeadAgent, TaskDecompositionPlan
from core.agent.multi.critic import CriticAgent
from core.planning.protocol import Plan, PlanStep, StepStatus
from core.planning.dag_scheduler import DAGScheduler, DAGExecutionResult, StepResult
from core.routing import IntentResult

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    多智能体编排器
    
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
        if config:
            self.config = config
        else:
            # 从参数构建配置
            agent_configs = []
            for i, agent_dict in enumerate(agents or []):
                agent_configs.append(AgentConfig(
                    agent_id=agent_dict.get("agent_id", f"agent_{i}"),
                    role=agent_dict.get("role", "executor"),
                    model=agent_dict.get("model", "claude-sonnet-4-5-20250929"),
                    system_prompt=agent_dict.get("system_prompt"),
                    tools=agent_dict.get("tools", []),
                ))
            
            self.config = MultiAgentConfig(
                config_id=f"config_{uuid4().hex[:8]}",
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
                profile_name = self.config.orchestrator_config.llm_profile_name or "lead_agent"
                self.lead_agent = LeadAgent(
                    model=orchestrator_model,
                    thinking_budget=self.config.orchestrator_config.thinking_budget,
                    max_tokens=self.config.orchestrator_config.max_tokens,
                    llm_profile_name=profile_name,
                )
            else:
                self.lead_agent = LeadAgent(model=orchestrator_model)
        else:
            self.lead_agent = None
        self.worker_model = worker_model  # 用于 Worker Agents
        
        # V7.2: Critic Agent（评估执行质量）
        critic_config = self.config.critic_config
        if critic_config and critic_config.enabled:
            critic_profile = critic_config.llm_profile_name or "critic_agent"
            self.critic = CriticAgent(
                model=critic_config.model,
                enable_thinking=critic_config.enable_thinking,
                config=critic_config,
                llm_profile_name=critic_profile,
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
        self.tool_executor = None  # 🆕 V7.3: 工具执行器（用于 RVR 循环）
        self._working_memory = None  # 工作记忆
        self._mem0_client = None  # Mem0 客户端
        self.workspace_dir = './workspace'  # 默认工作目录
        
        # 🆕 V7.4: Token 使用统计
        from utils.usage_tracker import create_usage_tracker
        self.usage_tracker = create_usage_tracker()
        
        # 追踪信息（用于监控和调试）
        self._execution_trace = []
        
        logger.info(
            f"✅ MultiAgentOrchestrator 初始化: mode={self.config.mode.value}, "
            f"agents={len(self.config.agents)}, checkpoints={enable_checkpoints}, "
            f"lead_agent={enable_lead_agent}, "
            f"orchestrator_model={orchestrator_model}, worker_model={worker_model}"
        )
    
    def clone_for_session(
        self,
        event_manager=None,
        workspace_dir: str = None,
        conversation_service=None,
        **kwargs
    ) -> "MultiAgentOrchestrator":
        """
        V7.9: 从原型克隆 MultiAgentOrchestrator 实例（快速路径）
        
        复用原型中的重量级组件，仅重置会话级状态。
        性能：<10ms（vs 50-100ms 完整初始化）
        
        复用的重量级组件：
        - config: 多智能体配置
        - lead_agent: LeadAgent 实例（含 LLM Service）
        - critic: CriticAgent 实例（含 LLM Service）
        - worker_model: Worker 模型名称
        - checkpoint_manager: 检查点管理器
        
        重置的会话级状态：
        - _state: 编排状态
        - plan: 当前计划
        - workspace_dir: 工作目录
        - usage_tracker: Token 统计
        - _execution_trace: 执行追踪
        
        Args:
            event_manager: 事件管理器（会话级）
            workspace_dir: 工作目录（会话级）
            conversation_service: 会话服务（会话级）
            **kwargs: 其他参数
            
        Returns:
            克隆后的 MultiAgentOrchestrator 实例
        """
        # 创建新实例（绕过 __init__）
        clone = object.__new__(MultiAgentOrchestrator)
        
        # ========== 复用原型的重量级组件 ==========
        clone.config = self.config
        clone.enable_checkpoints = self.enable_checkpoints
        clone.enable_lead_agent = self.enable_lead_agent
        clone.worker_model = self.worker_model
        clone.critic_config = self.critic_config
        
        # 复用 LeadAgent（含 LLM Service，重量级）
        clone.lead_agent = self.lead_agent
        
        # 复用 CriticAgent（含 LLM Service，重量级）
        clone.critic = self.critic
        
        # 复用 CheckpointManager（可跨会话复用）
        clone.checkpoint_manager = self.checkpoint_manager
        
        # ========== 设置会话级参数 ==========
        clone.workspace_dir = workspace_dir or './workspace'
        
        # ========== 重置会话级状态 ==========
        clone._state = None
        clone.plan = None
        clone.plan_todo_tool = None
        
        # 工具和记忆系统（延迟初始化）
        clone._tool_loader = None
        clone.tool_executor = None
        clone._working_memory = None
        clone._mem0_client = None
        
        # 新建 Token 统计器
        from utils.usage_tracker import create_usage_tracker
        clone.usage_tracker = create_usage_tracker()
        
        # 清空追踪信息
        clone._execution_trace = []
        
        # 标记为克隆实例
        clone._is_prototype = False
        
        logger.debug(
            f"🚀 MultiAgentOrchestrator 浅克隆完成: "
            f"workspace_dir={workspace_dir}, "
            f"lead_agent={'复用' if clone.lead_agent else '无'}, "
            f"critic={'复用' if clone.critic else '无'}"
        )
        
        return clone
    
    @property
    def usage_stats(self) -> Dict[str, int]:
        """
        🆕 V7.4: 统一接口，返回 usage 统计
        
        与 SimpleAgent.usage_stats 保持一致的接口
        """
        return self.usage_tracker.get_stats()
    
    def _accumulate_subagent_usage(self, subagent) -> None:
        """
        🆕 V7.4: 累积子智能体的 usage
        
        Args:
            subagent: 子智能体实例（需要有 usage_tracker 或 usage_stats）
        """
        if hasattr(subagent, 'usage_tracker'):
            sub_stats = subagent.usage_tracker.get_stats()
            self.usage_tracker.accumulate_from_dict({
                "input_tokens": sub_stats.get("total_input_tokens", 0),
                "output_tokens": sub_stats.get("total_output_tokens", 0),
                "thinking_tokens": sub_stats.get("total_thinking_tokens", 0),
                "cache_read_tokens": sub_stats.get("total_cache_read_tokens", 0),
                "cache_creation_tokens": sub_stats.get("total_cache_creation_tokens", 0),
            })
            logger.debug(
                f"📊 累积子智能体 usage: "
                f"input={sub_stats.get('total_input_tokens', 0)}, "
                f"output={sub_stats.get('total_output_tokens', 0)}"
            )

    async def _probe_worker_llm(
        self,
        llm_service: Any,
        agent_id: str,
        role: str,
        step_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Worker LLM 存活探针（执行前）
        
        Args:
            llm_service: LLM 服务实例
            agent_id: 子智能体 ID
            role: 子智能体角色
            step_id: 步骤 ID（可选）
        
        Returns:
            探针结果（包含是否切换）
        """
        if not llm_service or not hasattr(llm_service, "probe"):
            return None
        
        result = await llm_service.probe(
            max_retries=3,
            include_unhealthy=True
        )
        if result and result.get("switched"):
            trace_data = {
                "agent_id": agent_id,
                "role": role,
                "from": result.get("primary"),
                "to": result.get("selected"),
                "errors": result.get("errors", [])
            }
            if step_id:
                trace_data["step_id"] = step_id
            self._trace("llm_switch", trace_data)
            logger.warning(
                f"🔁 Subagent 模型切换: agent_id={agent_id}, role={role}, "
                f"from={result.get('primary')}, to={result.get('selected')}"
            )
        return result
    
    async def execute(
        self,
        intent: Optional[IntentResult],
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
        resume_from_checkpoint: bool = True,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行多智能体协作
        
        V7.1 新增：
        - 支持从检查点恢复
        - 使用 Lead Agent 进行任务分解（如果启用）
        
        Args:
            intent: 意图分析结果（来自路由层）
            messages: 消息历史
            session_id: 会话 ID
            message_id: 消息 ID
            resume_from_checkpoint: 是否尝试从检查点恢复（默认 True）
            
        Yields:
            事件字典
        """
        start_time = time.time()
        
        # 🆕 V7.2: 初始化共享资源（工具、记忆）
        user_id = intent.user_id if intent and hasattr(intent, 'user_id') else None
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
                state_id=f"orch_{uuid4().hex[:8]}",
                session_id=session_id,
                config_id=self.config.config_id,
                mode=self.config.mode,
                status="running",
                pending_agents=[agent.agent_id for agent in self.config.agents],
                started_at=datetime.now(),
            )
            
            # 发送开始事件
            yield {
                "type": "orchestrator_start",
                "session_id": session_id,
                "mode": self.config.mode.value,
                "agent_count": len(self.config.agents),
                "lead_agent_enabled": self.enable_lead_agent,
            }
        
        try:
            # V7.1: 使用 Lead Agent 进行任务分解（如果启用且不是恢复状态）
            decomposition_plan = None
            if self.enable_lead_agent and not checkpoint and self.lead_agent:
                try:
                    user_query = messages[-1].get("content", "") if messages else ""
                    available_tools = list(set(
                        tool for agent in self.config.agents for tool in agent.tools
                    ))
                    
                    self._trace("lead_agent_decompose_start", {
                        "query": user_query,
                        "available_tools": available_tools,
                    })
                    
                    decomposition_plan = await self.lead_agent.decompose_task(
                        user_query=user_query,
                        conversation_history=messages,
                        available_tools=available_tools,
                        intent_info=intent.to_dict() if intent else None,
                    )
                    
                    # 🆕 V7.4: 累积 LeadAgent.decompose_task 的 usage
                    if hasattr(self.lead_agent, 'last_llm_response'):
                        self.usage_tracker.accumulate(self.lead_agent.last_llm_response)
                    
                    self._trace("lead_agent_decompose_done", {
                        "plan_id": decomposition_plan.plan_id,
                        "subtasks_count": len(decomposition_plan.subtasks),
                        "execution_mode": decomposition_plan.execution_mode.value,
                    })
                    
                    yield {
                        "type": "task_decomposition",
                        "session_id": session_id,
                        "plan_id": decomposition_plan.plan_id,
                        "subtasks_count": len(decomposition_plan.subtasks),
                        "execution_mode": decomposition_plan.execution_mode.value,
                        "reasoning": decomposition_plan.reasoning,
                    }
                    
                except Exception as e:
                    logger.warning(f"⚠️ Lead Agent 任务分解失败: {e}，使用默认配置")
                    self._trace("lead_agent_decompose_error", {"error": str(e)})
            
            # 根据模式执行
            if self.config.mode == ExecutionMode.SEQUENTIAL:
                async for event in self._execute_sequential(
                    messages, session_id, message_id, decomposition_plan
                ):
                    yield event
            
            elif self.config.mode == ExecutionMode.PARALLEL:
                # V7.7: 优先使用 DAGScheduler（真正的依赖感知并行执行）
                if decomposition_plan and len(decomposition_plan.subtasks) > 0:
                    async for event in self._execute_with_dag_scheduler(
                        decomposition_plan, messages, session_id, message_id
                    ):
                        yield event
                else:
                    # 降级到原有逻辑
                    async for event in self._execute_parallel(
                        messages, session_id, message_id, decomposition_plan
                    ):
                        yield event
            
            elif self.config.mode == ExecutionMode.HIERARCHICAL:
                async for event in self._execute_hierarchical(
                    intent, messages, session_id, message_id, decomposition_plan
                ):
                    yield event
            
            # V7.1: 使用 Lead Agent 生成最终汇总
            if self.config.enable_final_summary:
                if self.enable_lead_agent and self.lead_agent and len(self._state.agent_results) > 0:
                    # 使用 Lead Agent 进行专业的结果综合
                    user_query = messages[-1].get("content", "") if messages else ""
                    
                    subtask_results = [
                        {
                            "agent_id": result.agent_id,
                            "title": f"Agent {result.agent_id}",
                            "output": result.output,
                            "success": result.success,
                        }
                        for result in self._state.agent_results
                    ]
                    
                    self._trace("lead_agent_synthesize_start", {
                        "results_count": len(subtask_results),
                    })
                    
                    final_output = await self.lead_agent.synthesize_results(
                        subtask_results=subtask_results,
                        original_query=user_query,
                        synthesis_strategy=decomposition_plan.synthesis_strategy if decomposition_plan else None,
                    )
                    
                    # 🆕 V7.4: 累积 LeadAgent.synthesize_results 的 usage
                    if hasattr(self.lead_agent, 'last_llm_response'):
                        self.usage_tracker.accumulate(self.lead_agent.last_llm_response)
                    
                    self._trace("lead_agent_synthesize_done", {
                        "output_length": len(final_output),
                    })
                else:
                    # 降级：使用简单汇总
                    final_output = await self._generate_summary()
                
                self._state.final_output = final_output
                
                yield {
                    "type": "orchestrator_summary",
                    "session_id": session_id,
                    "content": final_output,
                    "synthesized_by_lead_agent": self.enable_lead_agent,
                }
            
            # 完成
            duration_ms = int((time.time() - start_time) * 1000)
            self._state.status = "completed"
            self._state.completed_at = datetime.now()
            self._state.total_duration_ms = duration_ms
            
            yield {
                "type": "orchestrator_end",
                "session_id": session_id,
                "status": "completed",
                "duration_ms": duration_ms,
                "agent_results": len(self._state.agent_results),
            }
            
        except Exception as e:
            logger.error(f"❌ 多智能体执行失败: {e}", exc_info=True)
            self._state.status = "failed"
            self._state.errors.append({
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
            
            # V7.1: 错误时保存检查点（关键！）
            if self.checkpoint_manager:
                try:
                    error_checkpoint = await self.checkpoint_manager.save_checkpoint_on_error(
                        state=self._state,
                        error=e
                    )
                    logger.info(f"💾 错误检查点已保存: {error_checkpoint.checkpoint_id}")
                except Exception as cp_err:
                    logger.error(f"保存错误检查点失败: {cp_err}")
            
            self._trace("orchestrator_error", {"error": str(e), "type": type(e).__name__})
            
            yield {
                "type": "orchestrator_error",
                "session_id": session_id,
                "error": str(e),
                "checkpoint_saved": self.checkpoint_manager is not None,
            }
    
    async def _execute_sequential(
        self,
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
        decomposition_plan: Optional[TaskDecompositionPlan] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        串行执行模式
        
        V7.1 改进：
        - 支持任务分解计划
        - 每个 Agent 完成后自动保存检查点
        
        每个 Agent 依次执行，前一个的输出作为后一个的输入
        """
        current_input = messages
        previous_output = None
        
        for agent_config in self.config.agents:
            agent_id = agent_config.agent_id
            
            # 跳过已完成的 Agent（恢复场景）
            if agent_id in self._state.completed_agents:
                logger.info(f"⏭️ 跳过已完成的 Agent: {agent_id}")
                # 恢复前一个输出
                if self._state.agent_results:
                    last_result = next(
                        (r for r in self._state.agent_results if r.agent_id == agent_id),
                        None
                    )
                    if last_result:
                        previous_output = last_result.output
                continue
            
            self._state.current_agent = agent_id
            
            # V7.8: 从分解计划中获取步骤信息（如果有）
            plan_step = None
            if decomposition_plan:
                plan_step = next(
                    (st for st in decomposition_plan.subtasks if st.id == agent_id),
                    None
                )
            
            # 发送 Agent 开始事件
            step_title = plan_step.metadata.get("title") if plan_step else None
            yield {
                "type": "agent_start",
                "session_id": session_id,
                "agent_id": agent_id,
                "role": agent_config.role.value,
                "step_title": step_title,
            }
            
            # 创建任务分配
            task = TaskAssignment(
                task_id=f"task_{uuid4().hex[:8]}",
                agent_id=agent_id,
                instruction=plan_step.description if plan_step else f"执行 {agent_config.role.value} 任务",
                source_agent=self._state.completed_agents[-1] if self._state.completed_agents else None,
                source_output=previous_output,
            )
            self._state.task_assignments.append(task)
            
            self._trace("agent_execution_start", {
                "agent_id": agent_id,
                "role": agent_config.role.value,
                "has_plan_step": plan_step is not None,
            })
            
            # V7.2: 执行 Agent（带 Critic 评估，内部已包含重试逻辑）
            try:
                result = await self._execute_step_with_critique(
                    agent_config,
                    plan_step,
                    current_input,
                    previous_output,
                    session_id,
                )
            except Exception as e:
                logger.error(f"❌ Agent {agent_id} 执行异常: {e}", exc_info=True)
                # 创建失败结果
                result = AgentResult(
                    result_id=f"result_{uuid4().hex[:8]}",
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
            
            # 更新前一个输出
            previous_output = result.output
            
            self._trace("agent_execution_done", {
                "agent_id": agent_id,
                "success": result.success,
                "turns_used": result.turns_used,
                "output_length": len(result.output) if result.output else 0,
            })
            
            # V7.1: 保存检查点（关键！）
            if self.checkpoint_manager:
                try:
                    checkpoint = await self.checkpoint_manager.save_checkpoint_on_agent_completion(
                        state=self._state,
                        agent_id=agent_id,
                        result=result
                    )
                    logger.info(f"💾 检查点已保存: {checkpoint.checkpoint_id}")
                except Exception as cp_err:
                    logger.error(f"保存检查点失败: {cp_err}")
            
            # 发送 Agent 完成事件
            yield {
                "type": "agent_end",
                "session_id": session_id,
                "agent_id": agent_id,
                "success": result.success,
                "output_preview": result.output[:200] if result.output else "",
                "checkpoint_saved": self.checkpoint_manager is not None,
            }
            
            # 检查是否失败
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
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        并行执行模式（带重试）
        
        所有 Agent 同时执行，失败时自动重试
        """
        # V7.8: 创建所有 Agent 的任务（带 Critic 评估）
        async def execute_with_critique(agent_config, plan_step=None):
            """并行执行单个 Agent（带 Critic 评估）"""
            try:
                result = await self._execute_step_with_critique(
                    agent_config=agent_config,
                    plan_step=plan_step,
                    messages=messages,
                    previous_output=None,
                    session_id=session_id,
                )
                return result
            except Exception as e:
                logger.error(f"❌ Agent {agent_config.agent_id} 执行异常: {e}", exc_info=True)
                return AgentResult(
                    result_id=f"result_{uuid4().hex[:8]}",
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
            # V7.8: 从分解计划获取步骤
            plan_step = None
            if decomposition_plan and i < len(decomposition_plan.subtasks):
                plan_step = decomposition_plan.subtasks[i]
            
            task = asyncio.create_task(execute_with_critique(agent_config, plan_step))
            tasks.append((agent_config, task))
        
        # 发送并行开始事件
        yield {
            "type": "parallel_start",
            "session_id": session_id,
            "agent_count": len(tasks),
        }
        
        # 等待所有任务完成
        for agent_config, task in tasks:
            try:
                result = await asyncio.wait_for(
                    task, 
                    timeout=agent_config.timeout_seconds
                )
            except asyncio.TimeoutError:
                result = AgentResult(
                    result_id=f"result_{uuid4().hex[:8]}",
                    agent_id=agent_config.agent_id,
                    success=False,
                    error="执行超时",
                )
            
            self._state.agent_results.append(result)
            self._state.completed_agents.append(agent_config.agent_id)
            
            yield {
                "type": "agent_end",
                "session_id": session_id,
                "agent_id": agent_config.agent_id,
                "success": result.success,
            }
        
        self._state.pending_agents = []
    
    # ===================
    # V7.7: DAGScheduler 集成
    # ===================
    
    async def _execute_with_dag_scheduler(
        self,
        decomposition_plan: TaskDecompositionPlan,
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        使用 DAGScheduler 执行 Plan（V7.7 新增，V7.8 增强 REPLAN 支持）
        
        真正的依赖感知并行执行：
        1. 将 TaskDecompositionPlan 转换为 Plan 对象
        2. 使用 DAGScheduler 计算并行组
        3. 分层执行（组内并行，组间串行）
        4. 依赖结果自动注入
        5. 🆕 V7.8: 支持 REPLAN 后重新计算并行组
        
        Args:
            decomposition_plan: LeadAgent 产出的任务分解计划
            messages: 消息历史
            session_id: 会话 ID
            message_id: 消息 ID
        """
        # 1. 转换为 Plan 对象
        plan = Plan.from_decomposition(decomposition_plan)
        self.plan = plan  # 🆕 V7.8: 保存到实例，供 _trigger_replan 使用
        
        # 🆕 V7.8: REPLAN 重试循环
        max_replan_attempts = 2  # 最多重规划 2 次
        replan_attempt = 0
        needs_replan = False
        
        self._trace("dag_scheduler_start", {
            "plan_id": plan.plan_id,
            "total_steps": len(plan.steps),
            "execution_mode": plan.execution_mode,
        })
        
        # 2. 创建 DAGScheduler
        scheduler = DAGScheduler(
            max_concurrency=len(self.config.agents) if self.config.agents else 5,
            enable_retry=self.config.retry_on_failure,
            max_retries=self.config.max_retries,
        )
        
        # 3. 计算并行组
        groups = scheduler.compute_parallel_groups(plan)
        
        yield {
            "type": "dag_execution_start",
            "session_id": session_id,
            "plan_id": plan.plan_id,
            "total_groups": len(groups),
            "total_steps": len(plan.steps),
            "groups_distribution": [len(g) for g in groups],
        }
        
        # 🆕 V7.8: REPLAN 标记（用于跨步骤通信）
        replan_triggered = False
        replan_step_id = None
        
        # 4. 定义步骤执行器
        async def step_executor(step: PlanStep, dep_results: Dict[str, StepResult]) -> StepResult:
            """单个步骤执行器"""
            nonlocal replan_triggered, replan_step_id
            
            start_time = time.time()
            
            try:
                # V7.9: 选择 Agent 配置（三级优先级策略）
                selection_result = self._select_agent_for_step(step)
                agent_config = selection_result.selected_agent
                
                # 执行（V7.8: 直接传递 PlanStep，移除冗余转换）
                result = await self._execute_step_with_critique(
                    agent_config=agent_config,
                    plan_step=step,
                    messages=messages,
                    previous_output=step.injected_context,
                    session_id=session_id,
                )
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                # 🆕 V7.8: 检测 REPLAN 标志
                if result.metadata and result.metadata.get("needs_replan"):
                    replan_triggered = True
                    replan_step_id = step.id
                    logger.info(f"🔄 检测到 REPLAN 请求: step_id={step.id}")
                
                return StepResult(
                    step_id=step.id,
                    success=result.success,
                    output=result.output,
                    error=result.error,
                    duration_ms=duration_ms,
                )
                
            except Exception as e:
                logger.error(f"❌ 步骤 {step.id} 执行异常: {e}", exc_info=True)
                return StepResult(
                    step_id=step.id,
                    success=False,
                    error=str(e),
                    duration_ms=int((time.time() - start_time) * 1000),
                )
        
        # 5. 定义回调
        def on_step_start(step: PlanStep):
            self._trace("dag_step_start", {"step_id": step.id, "description": step.description[:50]})
        
        def on_step_end(step: PlanStep, result: StepResult):
            self._trace("dag_step_end", {
                "step_id": step.id,
                "success": result.success,
                "duration_ms": result.duration_ms,
            })
            
            # 记录到 agent_results 以便后续汇总
            self._state.agent_results.append(AgentResult(
                result_id=f"result_{step.id}",
                agent_id=step.assigned_agent or f"agent_{step.id}",
                success=result.success,
                output=result.output,
                error=result.error,
                turns_used=1,
                duration_ms=result.duration_ms,
                started_at=step.started_at or datetime.now(),
                completed_at=step.completed_at or datetime.now(),
            ))
        
        def on_group_start(group_idx: int, steps: List[PlanStep]):
            yield_event = {
                "type": "dag_group_start",
                "session_id": session_id,
                "group_index": group_idx,
                "step_ids": [s.id for s in steps],
            }
            self._trace("dag_group_start", {"group_index": group_idx, "step_count": len(steps)})
        
        def on_group_end(group_idx: int, steps: List[PlanStep], results: List[StepResult]):
            success_count = sum(1 for r in results if r.success)
            self._trace("dag_group_end", {
                "group_index": group_idx,
                "success_count": success_count,
                "total_count": len(steps),
            })
        
        # 6. 执行 DAG（🆕 V7.8: 带 REPLAN 重试循环）
        while replan_attempt <= max_replan_attempts:
            # 重置 REPLAN 标记
            replan_triggered = False
            replan_step_id = None
            
            # 重新计算并行组（首次或 REPLAN 后）
            if replan_attempt > 0:
                groups = scheduler.compute_parallel_groups(plan)
                logger.info(
                    f"🔄 REPLAN 后重新计算并行组: attempt={replan_attempt}, "
                    f"groups={len(groups)}"
                )
                
                yield {
                    "type": "dag_replan_start",
                    "session_id": session_id,
                    "plan_id": plan.plan_id,
                    "replan_attempt": replan_attempt,
                    "new_groups": len(groups),
                }
            
            dag_result = await scheduler.execute(
                plan=plan,
                executor=step_executor,
                on_step_start=on_step_start,
                on_step_end=on_step_end,
            )
            
            # 🆕 V7.8: 检查是否需要 REPLAN
            if replan_triggered and replan_attempt < max_replan_attempts:
                replan_attempt += 1
                logger.info(
                    f"🔄 触发 REPLAN 重试: step_id={replan_step_id}, "
                    f"attempt={replan_attempt}/{max_replan_attempts}"
                )
                
                # 重置未完成步骤的状态
                for step in plan.steps:
                    if step.status not in (StepStatus.COMPLETED,):
                        step.status = StepStatus.PENDING
                        step.retry_count = 0
                
                continue  # 重新执行
            
            break  # 正常完成或达到最大重试次数
        
        # 7. 发送执行完成事件
        yield {
            "type": "dag_execution_end",
            "session_id": session_id,
            "plan_id": plan.plan_id,
            "success": dag_result.success,
            "completed_steps": dag_result.completed_steps,
            "failed_steps": dag_result.failed_steps,
            "skipped_steps": dag_result.skipped_steps,
            "total_duration_ms": dag_result.total_duration_ms,
            "execution_groups": dag_result.execution_groups,
            "replan_attempts": replan_attempt,  # 🆕 V7.8: 记录重规划次数
        }
        
        self._trace("dag_scheduler_complete", {
            **dag_result.to_dict(),
            "replan_attempts": replan_attempt,
        })
        
        logger.info(
            f"✅ DAG 执行完成: plan_id={plan.plan_id}, "
            f"success={dag_result.success}, "
            f"steps={dag_result.completed_steps}/{dag_result.total_steps}, "
            f"replan_attempts={replan_attempt}"
        )
    
    def _select_agent_for_step(self, step: PlanStep) -> AgentSelectionResult:
        """
        V7.9: Agent 选择 - 三级优先级策略
        
        优先级（互斥选择）:
        1. Config（显式指定）: step.assigned_agent - 最高优先级
        2. Task（角色匹配）: step.assigned_agent_role
        3. Capability（能力匹配）: step.tools_required
        4. Default: 第一个可用 Agent 或自动创建
        
        借鉴工具选择三级优化（V7.6）:
        - 有效性验证：检测无效 Agent 配置
        - 覆盖透明化：记录选择来源和被覆盖候选
        - Tracer 追踪：完整记录决策过程
        
        Args:
            step: 执行步骤
            
        Returns:
            AgentSelectionResult: 包含选择结果和决策链路
        """
        selection_source = "default"
        overridden_sources: List[str] = []
        
        # 三层候选者
        config_candidate: Optional[AgentConfig] = None
        task_candidate: Optional[AgentConfig] = None
        capability_candidate: Optional[AgentConfig] = None
        
        # ===== Layer 3: Capability 匹配（最低优先级）=====
        if step.tools_required:
            for agent in self.config.agents:
                matching_tools = [t for t in step.tools_required if t in agent.tools]
                if matching_tools:
                    capability_candidate = agent
                    logger.debug(
                        f"  └─ Capability 匹配: {agent.agent_id} "
                        f"(工具: {matching_tools[:3]})"
                    )
                    break
        
        # ===== Layer 2: Task 匹配（角色）=====
        if step.assigned_agent_role:
            for agent in self.config.agents:
                if agent.role.value == step.assigned_agent_role:
                    task_candidate = agent
                    logger.debug(
                        f"  └─ Task 匹配: {agent.agent_id} "
                        f"(角色: {step.assigned_agent_role})"
                    )
                    break
        
        # ===== Layer 1: Config 显式指定（最高优先级）=====
        if step.assigned_agent:
            for agent in self.config.agents:
                if agent.agent_id == step.assigned_agent:
                    config_candidate = agent
                    logger.debug(f"  └─ Config 匹配: {agent.agent_id}")
                    break
            
            # V7.9: 有效性验证 - 检查显式指定的 Agent 是否存在
            if not config_candidate:
                available_ids = [a.agent_id for a in self.config.agents]
                logger.warning(
                    f"⚠️ Step '{step.id}' 指定的 Agent '{step.assigned_agent}' 不存在，"
                    f"可用 Agent: {available_ids}"
                )
        
        # ===== 按优先级选择，记录覆盖 =====
        if config_candidate:
            selected = config_candidate
            selection_source = "config"
            # 记录被覆盖的候选
            if task_candidate and task_candidate.agent_id != selected.agent_id:
                overridden_sources.append(f"task:{task_candidate.agent_id}")
            if capability_candidate and capability_candidate.agent_id != selected.agent_id:
                overridden_sources.append(f"capability:{capability_candidate.agent_id}")
                
        elif task_candidate:
            selected = task_candidate
            selection_source = "task"
            # 记录被覆盖的候选
            if capability_candidate and capability_candidate.agent_id != selected.agent_id:
                overridden_sources.append(f"capability:{capability_candidate.agent_id}")
                
        elif capability_candidate:
            selected = capability_candidate
            selection_source = "capability"
            
        elif self.config.agents:
            selected = self.config.agents[0]
            selection_source = "default"
            logger.debug(f"  └─ 使用默认 Agent: {selected.agent_id}")
            
        else:
            # 自动创建 Agent 配置
            selected = AgentConfig(
                agent_id=f"auto_agent_{step.id}",
                role=AgentRole.EXECUTOR,
                model=self.worker_model,
                tools=step.tools_required or [],
            )
            selection_source = "auto_created"
            logger.info(f"🆕 自动创建 Agent: {selected.agent_id}")
        
        # ===== V7.9: 有效性验证 =====
        validation_passed, validation_issues = self._validate_agent_for_step(
            selected, step
        )
        
        # ===== V7.9: 覆盖透明化日志 =====
        if overridden_sources:
            logger.info(
                f"📋 Agent 选择 [{selection_source}]: {selected.agent_id}，"
                f"覆盖了 {overridden_sources}"
            )
        else:
            logger.info(f"✅ Agent 选择 [{selection_source}]: {selected.agent_id}")
        
        if not validation_passed:
            logger.warning(f"   └─ 验证问题: {validation_issues}")
        
        # 构建选择结果
        result = AgentSelectionResult(
            selected_agent=selected,
            selection_source=selection_source,
            overridden_sources=overridden_sources,
            validation_passed=validation_passed,
            validation_issues=validation_issues,
            config_candidate=config_candidate.agent_id if config_candidate else None,
            task_candidate=task_candidate.agent_id if task_candidate else None,
            capability_candidate=capability_candidate.agent_id if capability_candidate else None,
        )
        
        # ===== V7.9: Tracer 增强追踪 =====
        self._trace("agent_selection", {
            "step_id": step.id,
            "step_description": step.description[:50] if step.description else "",
            **result.to_trace_dict(),
        })
        
        return result
    
    def _validate_agent_for_step(
        self, agent: AgentConfig, step: PlanStep
    ) -> tuple:
        """
        V7.9: 验证 Agent 配置对步骤的适配性
        
        检查项:
        1. 工具覆盖：Agent 是否具备步骤所需的工具
        2. 角色匹配：Agent 角色是否与步骤要求一致
        
        Args:
            agent: 选中的 Agent 配置
            step: 执行步骤
            
        Returns:
            (is_valid, issues): 验证结果和问题列表
        """
        issues: List[str] = []
        
        # 检查工具覆盖
        if step.tools_required:
            missing_tools = [t for t in step.tools_required if t not in agent.tools]
            if missing_tools:
                issues.append(f"Agent 缺少工具: {missing_tools}")
        
        # 检查角色匹配（仅当步骤明确指定角色时）
        if step.assigned_agent_role and agent.role.value != step.assigned_agent_role:
            issues.append(
                f"角色不匹配: 需要 {step.assigned_agent_role}, "
                f"实际 {agent.role.value}"
            )
        
        return len(issues) == 0, issues
    
    async def _execute_hierarchical(
        self,
        intent: Optional[IntentResult],
        messages: List[Dict[str, str]],
        session_id: str,
        message_id: Optional[str] = None,
        decomposition_plan: Optional[TaskDecompositionPlan] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        层级执行模式
        
        主 Agent（Planner）分解任务，分配给子 Agent 执行
        """
        # 找到 Planner Agent
        planner = next(
            (a for a in self.config.agents if a.role.value == "planner"),
            self.config.agents[0] if self.config.agents else None
        )
        
        if not planner:
            yield {
                "type": "orchestrator_error",
                "session_id": session_id,
                "error": "层级模式需要至少一个 Planner Agent",
            }
            return
        
        # Step 1: Planner 分解任务
        yield {
            "type": "planner_start",
            "session_id": session_id,
            "agent_id": planner.agent_id,
        }
        
        # 这里是占位实现，实际需要 Planner 返回任务分解
        plan_result = await self._execute_single_agent(planner, messages, None, session_id)
        
        yield {
            "type": "planner_end",
            "session_id": session_id,
            "agent_id": planner.agent_id,
            "success": plan_result.success,
        }
        
        # Step 2: 分配任务给子 Agent（简化实现）
        sub_agents = [a for a in self.config.agents if a.agent_id != planner.agent_id]
        
        for sub_agent in sub_agents:
            yield {
                "type": "sub_agent_start",
                "session_id": session_id,
                "agent_id": sub_agent.agent_id,
            }
            
            result = await self._execute_single_agent(
                sub_agent, 
                messages, 
                plan_result.output,
                session_id
            )
            
            self._state.agent_results.append(result)
            self._state.completed_agents.append(sub_agent.agent_id)
            
            yield {
                "type": "sub_agent_end",
                "session_id": session_id,
                "agent_id": sub_agent.agent_id,
                "success": result.success,
            }
    
    async def _execute_single_agent(
        self,
        config: AgentConfig,
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
        plan_step: Optional[PlanStep] = None,
    ) -> AgentResult:
        """
        执行单个 Agent（真实实现）
        
        V7.1 改进：
        - 支持步骤定义（来自 Lead Agent 的分解）
        - 动态注入 Subagent 系统提示词（8 个核心要素）
        - 上下文隔离：只传递必要的摘要
        
        V7.8 重构：
        - 统一使用 PlanStep，移除 SubTask 冗余层
        
        Args:
            config: Agent 配置
            messages: 消息历史
            previous_output: 前一个 Agent 的输出（串行模式）
            session_id: 会话 ID
            plan_step: 步骤定义（来自 Lead Agent 或 DAGScheduler）
            
        Returns:
            AgentResult 执行结果
        """
        start_time = time.time()
        
        task_description = plan_step.description if plan_step else f"执行 {config.role.value} 任务"
        
        logger.info(
            f"🤖 执行 Subagent: {config.agent_id} ({config.role.value}), "
            f"model={config.model}, task={task_description[:50]}..."
        )
        
        # 如果有步骤定义，使用更详细的日志
        if plan_step:
            logger.debug(
                f"   📋 步骤详情:\n"
                f"      - 期望输出: {plan_step.expected_output}\n"
                f"      - 成功标准: {plan_step.success_criteria}\n"
                f"      - 需要工具: {plan_step.tools_required}\n"
                f"      - 约束条件: {plan_step.constraints}"
            )
        
        try:
            # 1. 构建 Subagent 系统提示词（核心！）
            system_prompt = self._build_subagent_system_prompt(
                config=config,
                plan_step=plan_step,
                orchestrator_context=self._build_orchestrator_summary()
            )
            
            # 2. 创建独立的 LLM 服务（上下文隔离）
            # V7.1: 使用配置的 Worker 模型（强弱配对）
            from core.llm import create_llm_service
            from config.llm_config import get_llm_profile
            
            worker_model = self.worker_model if hasattr(self, "worker_model") else config.model
            profile_name = (
                self.config.worker_config.llm_profile_name
                if self.config.worker_config else None
            ) or "worker_agent"
            
            worker_profile = get_llm_profile(profile_name)
            profile_provider = str(worker_profile.get("provider", "claude")).lower()
            if profile_provider == "claude":
                worker_profile["model"] = worker_model
            if self.config.worker_config:
                worker_profile.update({
                    "enable_thinking": self.config.worker_config.enable_thinking,
                    "max_tokens": self.config.worker_config.max_tokens,
                    "thinking_budget": self.config.worker_config.thinking_budget,
                })
            else:
                worker_profile.update({
                    "enable_thinking": True,
                    "max_tokens": 8192,
                    "thinking_budget": 5000,
                })
            
            llm = create_llm_service(**worker_profile)
            
            # 🆕 Worker 探针：执行前做存活检查（失败自动切换）
            role_name = config.role.value if hasattr(config.role, "value") else str(config.role)
            await self._probe_worker_llm(
                llm_service=llm,
                agent_id=config.agent_id,
                role=role_name,
                step_id=plan_step.id if plan_step else None
            )
            
            # 3. 构建用户消息（只传递必要信息）
            user_message_parts = []
            
            # 添加任务描述
            if plan_step:
                step_title = plan_step.metadata.get("title", plan_step.description[:50])
                user_message_parts.append(f"任务：{step_title}")
                user_message_parts.append(f"描述：{plan_step.description}")
                if plan_step.context:
                    user_message_parts.append(f"\n背景信息：\n{plan_step.context}")
            else:
                user_message_parts.append(f"任务：{task_description}")
            
            # 添加前置输出（如果有，生成摘要）
            if previous_output:
                summary = self._summarize_previous_output(previous_output)
                user_message_parts.append(f"\n前置任务输出摘要：\n{summary}")
            
            # 添加原始用户查询（从消息历史中提取）
            if messages and len(messages) > 0:
                last_user_msg = messages[-1].get("content", "")
                user_message_parts.append(f"\n原始用户查询：\n{last_user_msg}")
            
            user_message = "\n\n".join(user_message_parts)
            
            # 4. 🆕 动态加载工具（根据 PlanStep 需求）
            tools = await self._load_subagent_tools(config, plan_step)
            
            # 5. 调用 LLM 执行
            from core.llm.base import Message
            
            agent_messages = [Message(role="user", content=user_message)]
            
            logger.debug(f"📤 Subagent system_prompt 长度: {len(system_prompt)} 字符")
            logger.debug(f"📤 Subagent user_message 长度: {len(user_message)} 字符")
            logger.debug(f"🔧 Subagent 工具数量: {len(tools)}")
            
            # 🆕 V7.3: 实现完整的 RVR 工具执行循环（参考 SimpleAgent）
            import json
            max_tool_turns = 5  # 最大工具调用轮次（防止无限循环）
            turns_used = 0
            all_tool_results = []  # 收集所有工具执行结果
            final_response = ""
            
            for turn in range(max_tool_turns):
                turns_used += 1
                
                logger.info(f"   🔄 Subagent Turn {turn + 1}/{max_tool_turns}")
                
                llm_response = await llm.create_message_async(
                    messages=agent_messages,
                    system=system_prompt,
                    temperature=0.5,
                    tools=tools,
                )
                
                # 🆕 V7.4: 累积每次 LLM 调用的 usage
                self.usage_tracker.accumulate(llm_response)
                
                stop_reason = getattr(llm_response, 'stop_reason', 'end_turn')
                logger.info(f"   📡 LLM stop_reason: {stop_reason}")
                
                # 检查是否有**客户端**工具调用
                if stop_reason == "tool_use" and hasattr(llm_response, 'tool_calls') and llm_response.tool_calls:
                    tool_calls = llm_response.tool_calls
                    logger.info(f"   🔧 LLM 请求调用 {len(tool_calls)} 个工具")
                    
                    # 🔑 关键理解：
                    # - `tool_calls` 只包含**客户端工具**（type="tool_use"）
                    # - 服务端工具（如 web_search）已由 Anthropic 自动执行，不在 tool_calls 中
                    # - 所以我们只需要执行 tool_calls 中的工具
                    
                    # 添加 assistant 消息（包含 tool_use 块）
                    agent_messages.append(Message(role="assistant", content=llm_response.raw_content))
                    
                    # 执行客户端工具并添加 tool_result
                    if tool_calls:
                        tool_results = []
                        for tc in tool_calls:
                            tool_name = tc.get('name', '')
                            tool_input = tc.get('input', {})
                            tool_id = tc.get('id', '')
                            
                            logger.info(f"   🔨 执行客户端工具: {tool_name}")
                            
                            try:
                                result = await self.tool_executor.execute(tool_name, tool_input)
                                all_tool_results.append({
                                    "tool": tool_name,
                                    "input": tool_input,
                                    "result": result
                                })
                                
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": json.dumps(result, ensure_ascii=False)
                                })
                                
                                logger.info(f"   ✅ 工具 {tool_name} 执行完成: success={result.get('success', 'N/A')}")
                                
                            except Exception as e:
                                logger.error(f"   ❌ 工具 {tool_name} 执行失败: {e}")
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": json.dumps({"error": str(e), "success": False}),
                                    "is_error": True
                                })
                        
                        if tool_results:
                            agent_messages.append(Message(role="user", content=tool_results))
                    
                    # 继续下一轮
                    continue
                
                # 没有工具调用，提取最终响应
                final_response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                
                if stop_reason in ('end_turn', 'stop', 'max_tokens'):
                    logger.info(f"   ✅ Subagent 完成（{turns_used} 轮），stop_reason={stop_reason}")
                    break
            else:
                # 达到最大轮次
                logger.warning(f"   ⚠️ Subagent 达到最大工具调用轮次 ({max_tool_turns})")
                if not final_response:
                    final_response = llm_response.content if hasattr(llm_response, 'content') else "达到最大执行轮次"
            
            # 使用最终响应
            response = final_response
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"✅ Subagent 执行完成: {config.agent_id}, 耗时 {duration_ms}ms")
            
            return AgentResult(
                result_id=f"result_{uuid4().hex[:8]}",
                agent_id=config.agent_id,
                success=True,
                output=response,
                turns_used=turns_used,  # 🆕 记录实际轮次
                duration_ms=duration_ms,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                metadata={
                    "model": config.model,
                    "previous_output_length": len(previous_output) if previous_output else 0,
                    "has_plan_step": plan_step is not None,
                    "step_title": plan_step.metadata.get("title") if plan_step else None,
                    "system_prompt_length": len(system_prompt),
                    "user_message_length": len(user_message),
                    "tool_calls_count": len(all_tool_results),  # 🆕 工具调用统计
                    "tool_results": all_tool_results[:5] if all_tool_results else [],  # 🆕 保留前5个工具结果摘要
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Subagent 执行失败: {config.agent_id}, error={e}", exc_info=True)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return AgentResult(
                result_id=f"result_{uuid4().hex[:8]}",
                agent_id=config.agent_id,
                success=False,
                output="",
                error=str(e),
                turns_used=0,
                duration_ms=duration_ms,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                metadata={
                    "model": config.model,
                    "has_plan_step": plan_step is not None,
                }
            )
    
    def _build_subagent_system_prompt(
        self,
        config: AgentConfig,
        plan_step: Optional[PlanStep] = None,
        orchestrator_context: Optional[str] = None,
    ) -> str:
        """
        构建 Subagent 系统提示词（8 个核心要素）
        
        参考 Anthropic Multi-Agent System：
        "Each subagent needs an objective, an output format, guidance on the tools 
        and sources to use, and clear task boundaries."
        
        V7.8 重构：统一使用 PlanStep，移除 SubTask 冗余层
        
        Args:
            config: Agent 配置
            plan_step: 步骤定义
            orchestrator_context: Orchestrator 提供的上下文摘要
            
        Returns:
            str: 完整的系统提示词
        """
        # 1. 明确的目标（Objective）
        if plan_step:
            title = plan_step.metadata.get("title", plan_step.description[:50])
            objective = f"**你的目标**：{title}\n{plan_step.description}"
        else:
            objective = f"**你的目标**：执行 {config.role.value} 任务"
        
        # 2. 期望输出格式（Output Format）
        if plan_step and plan_step.expected_output:
            output_format = f"""
**输出格式要求**：
{plan_step.expected_output}

请严格遵循以上格式，使用结构化的 JSON 或 Markdown。
"""
        else:
            output_format = """
**输出格式要求**：
- 使用 Markdown 格式
- 包含清晰的标题和段落
- 如果有多个发现，使用列表或表格
"""
        
        # 3. 可用工具指导（Tools Guidance）- V7.2 强化工具使用
        if plan_step and plan_step.tools_required:
            tools_guidance = f"""
**可用工具**：
{chr(10).join(f"- {tool}" for tool in plan_step.tools_required)}

**⚠️ 重要：你必须主动使用工具获取信息！**
- 不要仅凭已有知识回答，必须调用工具搜索最新信息
- 每个步骤至少调用 1-2 次工具
- 如果任务涉及"研究"、"分析"、"搜索"，你**必须**使用 web_search 或相关工具

**工具选择启发式规则**：
- 优先使用最直接的工具
- 避免重复调用相同的工具
- 工具失败时，尝试替代方案
"""
        elif config.tools:
            tools_guidance = f"""
**可用工具**：
{chr(10).join(f"- {tool}" for tool in config.tools)}

**⚠️ 重要：你必须主动使用工具获取信息！**
- 不要仅凭已有知识回答，必须调用工具获取最新数据
- 研究任务必须使用搜索工具
- 你的输出必须包含工具调用获取的实际数据

**工具选择启发式规则**：
- 根据任务类型选择合适的工具
- 组合使用工具以提高效率
"""
        else:
            tools_guidance = "**可用工具**：无特定工具要求，使用你的知识和推理能力完成任务。"
        
        # 4. 任务边界（Task Boundaries）
        if plan_step and plan_step.constraints:
            boundaries = f"""
**任务边界与约束**：
{chr(10).join(f"- {constraint}" for constraint in plan_step.constraints)}

**不要**：
- 超出以上范围工作
- 重复其他 Subagent 的工作
- 提供与任务无关的信息
"""
        else:
            boundaries = """
**任务边界**：
- 专注于你的具体任务
- 不要尝试解决整个问题
- 提供简洁、针对性的结果
"""
        
        # 5. 成功标准（Success Criteria）
        if plan_step and plan_step.success_criteria:
            success_criteria = f"""
**成功标准**：
{chr(10).join(f"- {criterion}" for criterion in plan_step.success_criteria)}

完成任务后，请自我检查是否满足以上所有标准。
"""
        else:
            success_criteria = """
**成功标准**：
- 完整回答任务要求
- 信息准确可靠
- 表达清晰简洁
"""
        
        # 6. 上下文信息（Context）
        context_section = ""
        if orchestrator_context:
            context_section = f"""
**Orchestrator 上下文**：
{orchestrator_context}

（这是 Orchestrator 提供的背景信息，帮助你理解整体任务）
"""
        
        # 7. 搜索策略指导（Search Strategy）
        search_strategy = """
**搜索策略指导**：
1. **先广泛后缩小**：从宽泛的搜索开始，逐步聚焦到具体细节
2. **迭代优化**：如果首次搜索结果不理想，调整关键词再试
3. **交叉验证**：从多个来源验证关键信息
4. **停止条件**：找到足够的高质量信息后停止，避免过度搜索
"""
        
        # 8. Extended Thinking 使用指导（Thinking Guidance）
        thinking_guidance = """
**Extended Thinking 使用指导**：
- 在执行复杂推理时，启用 Extended Thinking
- 在 Thinking 中记录你的决策过程、工具选择理由
- 不要在 Thinking 中输出最终答案（最终答案放在正式回复中）
"""
        
        # 组装完整的系统提示词
        system_prompt = f"""你是一个专业的 Subagent（子智能体），在多智能体协作系统中负责执行特定的子任务。

{objective}

{output_format}

{tools_guidance}

{boundaries}

{success_criteria}

{context_section}

{search_strategy}

{thinking_guidance}

**重要提醒**：
- 你的输出将作为整体任务的一部分，与其他 Subagent 的结果一起被 Orchestrator 综合
- 请确保你的输出是**自包含的**（self-contained），即使脱离上下文也能理解
- 使用结构化的格式（JSON/Markdown），便于后续处理

现在开始执行你的任务！
"""
        
        return system_prompt
    
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
                summary_parts.append(f"- {result.agent_id}: {status}, 输出预览: {output_preview}...")
        
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
        🆕 V7.2: 初始化共享资源（工具、记忆）
        
        在 execute() 开始时调用一次，初始化：
        - 工具加载器（ToolLoader + CapabilityRegistry）
        - 工作记忆（WorkingMemory）
        - Mem0 客户端（如果启用）
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID（可选）
            tool_names: 需要加载的工具列表（可选，默认加载核心工具）
        """
        # 1. 初始化工具加载器
        if self._tool_loader is None:
            from core.tool.loader import ToolLoader
            from core.tool.capability.registry import CapabilityRegistry
            
            self._tool_loader = ToolLoader(
                global_registry=CapabilityRegistry(),
            )
            logger.info("✅ 工具加载器已初始化")
        
        # 🆕 V7.3: 初始化工具执行器（用于 Subagent RVR 循环）
        if self.tool_executor is None:
            from core.tool.executor import ToolExecutor
            from core.tool.capability.registry import CapabilityRegistry
            
            self.tool_executor = ToolExecutor(
                registry=CapabilityRegistry(),
                tool_context={
                    "workspace_dir": None,  # 多智能体不需要特定工作目录
                },
                enable_compaction=True
            )
            logger.info("✅ 工具执行器已初始化")
        
        # 2. 初始化工作记忆
        if self._working_memory is None:
            from core.memory.working import WorkingMemory
            
            self._working_memory = WorkingMemory()
            logger.info(f"✅ 工作记忆已初始化")
        
        # 3. 初始化 Mem0 客户端（可选）
        if self._mem0_client is None and user_id:
            try:
                from core.memory.mem0.client import get_mem0_client
                
                self._mem0_client = get_mem0_client()
                logger.info(f"✅ Mem0 客户端已初始化: user_id={user_id}")
            except Exception as e:
                logger.warning(f"⚠️ Mem0 客户端初始化失败: {e}，将跳过长期记忆功能")
                self._mem0_client = None
    
    async def _load_subagent_tools(
        self,
        config: AgentConfig,
        plan_step: Optional[PlanStep] = None,
    ) -> List[Dict[str, Any]]:
        """
        🆕 V7.2: 动态加载 Subagent 工具（参考 V4 工具分层设计）
        
        工具分层策略（参考 V4-ARCHITECTURE-HISTORY.md）：
        - Level 1: 核心工具 - 始终加载（plan_todo 等）
        - Level 2: 动态工具 - 按需加载（web_search, exa_search 等）
        
        V7.8 重构：统一使用 PlanStep，移除 SubTask 冗余层
        
        Args:
            config: Agent 配置
            plan_step: 步骤定义（包含 tools_required）
            
        Returns:
            List[Dict]: Anthropic 格式的工具定义列表
        """
        # 确保工具加载器已初始化
        if self._tool_loader is None:
            await self._initialize_shared_resources(session_id="temp")
        
        # 1. 确定需要加载的工具（分层策略）
        # Level 1: 核心工具（始终加载）
        core_tools = ["plan_todo"]
        
        # Level 2: 动态工具（根据 PlanStep 或默认配置）
        if plan_step and plan_step.tools_required:
            dynamic_tools = plan_step.tools_required
            logger.debug(f"📋 PlanStep 指定工具: {dynamic_tools}")
        else:
            # 默认研究工具
            dynamic_tools = ["web_search", "exa_search", "wikipedia"]
            logger.debug(f"📋 使用默认工具: {dynamic_tools}")
        
        # 合并所有需要的工具
        all_required_tools = list(set(core_tools + dynamic_tools))
        
        # 2. 转换为 enabled_capabilities 格式
        enabled_capabilities = {tool: True for tool in all_required_tools}
        
        # 3. 加载工具
        try:
            load_result = self._tool_loader.load_tools(
                enabled_capabilities=enabled_capabilities,
            )
            
            # 4. 转换为 Anthropic 工具格式（区分原生工具 vs 自定义工具）
            from core.llm.claude import ClaudeLLMService
            
            anthropic_tools = []
            for capability in load_result.generic_tools:
                tool_name = capability.name
                
                # 🔑 关键：检查是否是 Anthropic 原生工具（如 web_search）
                native_schema = ClaudeLLMService.NATIVE_TOOLS.get(tool_name)
                
                if native_schema:
                    # 原生工具：使用 Claude 的特殊格式
                    anthropic_tools.append(native_schema)
                    logger.debug(f"   📡 原生工具: {tool_name}, type={native_schema.get('type')}")
                else:
                    # 自定义工具：使用标准格式
                    tool_description = capability.metadata.get('description', f"{tool_name} 工具")
                    tool_schema = capability.input_schema or {"type": "object", "properties": {}}
                    
                    anthropic_tools.append({
                        "name": tool_name,
                        "description": tool_description,
                        "input_schema": tool_schema
                    })
                    logger.debug(f"   🔧 自定义工具: {tool_name}")
            
            tool_names = [t.get('name', t.get('type', 'unknown')) for t in anthropic_tools]
            logger.info(f"✅ 已加载 {len(anthropic_tools)} 个工具供 Subagent 使用: {tool_names}")
            return anthropic_tools
            
        except Exception as e:
            logger.error(f"❌ 工具加载失败: {e}", exc_info=True)
            # 返回空列表但不应该阻止 Agent 执行
            return []
    
    # V7.8: 删除 _spawn_subagent（死代码，功能已被 _execute_single_agent 替代）
    
    async def _compress_subagent_output(self, output: str, max_length: int = 500) -> str:
        """
        压缩 Subagent 输出为摘要
        
        目的：减少 Orchestrator 的上下文消耗
        
        Args:
            output: 原始输出
            max_length: 最大摘要长度
            
        Returns:
            str: 压缩后的摘要
        """
        # TODO: 未来可以使用 LLM 生成更智能的摘要
        # 当前使用简单截断
        if len(output) <= max_length:
            return output
        
        # 尝试提取关键部分（如果是结构化输出）
        if "##" in output or "**" in output:
            # 保留标题和前几段
            lines = output.split("\n")
            summary_lines = []
            char_count = 0
            
            for line in lines:
                if char_count + len(line) > max_length:
                    break
                summary_lines.append(line)
                char_count += len(line) + 1
            
            summary = "\n".join(summary_lines)
            return summary + f"\n\n（已压缩，原始长度: {len(output)} 字符）"
        
        # 降级：简单截断
        return output[:max_length] + f"\n\n（已截断，原始长度: {len(output)} 字符）"
    
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
        """
        生成最终汇总
        
        将所有 Agent 的输出整合为最终结果
        """
        if not self._state or not self._state.agent_results:
            return "没有可汇总的结果"
        
        # 简单汇总（实际可以用专门的 Summarizer Agent）
        summary_parts = []
        for result in self._state.agent_results:
            if result.success and result.output:
                summary_parts.append(f"【{result.agent_id}】\n{result.output}")
        
        return "\n\n".join(summary_parts) if summary_parts else "所有 Agent 执行失败"
    
    def get_state(self) -> Optional[OrchestratorState]:
        """获取当前状态"""
        return self._state
    
    # ===================
    # V7.2: Critic 集成
    # ===================
    
    async def _execute_step_with_critique(
        self,
        agent_config: AgentConfig,
        plan_step: Optional[PlanStep],
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
    ) -> AgentResult:
        """
        执行步骤（带 Critic 评估）
        
        V7.2 新增：在执行后自动调用 Critic 评估，根据结果决定下一步
        V7.8 重构：统一使用 PlanStep，移除 SubTask 冗余层
        
        Args:
            agent_config: Agent 配置
            plan_step: 步骤定义
            messages: 消息历史
            previous_output: 前一个 Agent 的输出
            session_id: 会话 ID
            
        Returns:
            AgentResult: 执行结果
        """
        # 如果未启用 Critic，直接执行
        if not self.critic or not self.critic_config:
            return await self._execute_single_agent(
                agent_config, messages, previous_output, session_id, plan_step
            )
        
        # 使用传入的 PlanStep 或创建临时的
        if plan_step is None:
            plan_step = PlanStep(
                id=f"step_{agent_config.agent_id}",
                description=f"执行 {agent_config.role.value} 任务",
                status=StepStatus.IN_PROGRESS,
            )
        else:
            plan_step.status = StepStatus.IN_PROGRESS
        
        max_retries = self.critic_config.max_retries
        retry_count = 0
        
        while retry_count <= max_retries:
            # 1. Execute
            result = await self._execute_single_agent(
                agent_config, messages, previous_output, session_id, plan_step
            )
            
            # 如果执行失败，直接返回
            if not result.success:
                plan_step.fail(result.error or "执行失败")
                return result
            
            # 2. Critique
            success_criteria = plan_step.success_criteria or []
            
            critic_result = await self.critic.critique(
                executor_output=result.output,
                plan_step=plan_step,
                success_criteria=success_criteria,
                retry_count=retry_count,
                max_retries=max_retries,
            )
            
            # 3. 记录 Critic 反馈到 PlanStep.metadata
            plan_step.metadata["critic"] = {
                "action": critic_result.recommended_action.value,
                "confidence": critic_result.confidence.value,
                "reasoning": critic_result.reasoning,
                "observations": critic_result.observations,
                "gaps": critic_result.gaps,
                "suggestions": critic_result.suggestions,
                "retry_count": retry_count,
            }
            
            # 4. 根据 confidence 和 action 决定是否自动执行
            can_auto_execute = self.critic.should_auto_execute(critic_result)
            
            # 5. 根据 recommended_action 处理
            if critic_result.recommended_action == CriticAction.PASS:
                plan_step.complete(result.output)
                logger.info(
                    f"✅ Critic PASS: step_id={step_id}, "
                    f"confidence={critic_result.confidence.value}"
                )
                return result
            
            elif critic_result.recommended_action == CriticAction.ASK_HUMAN:
                # 请求人工介入
                logger.info(
                    f"👤 Critic ASK_HUMAN: step_id={step_id}, "
                    f"reasoning={critic_result.reasoning[:100]}..."
                )
                # 返回结果，但标记需要人工审核
                result.metadata["needs_human_review"] = True
                result.metadata["critic_result"] = critic_result.model_dump()
                return result
            
            elif critic_result.recommended_action == CriticAction.RETRY:
                # 检查是否可以自动重试
                if not can_auto_execute and self.critic_config.require_human_on_low_confidence:
                    logger.info(
                        f"👤 Critic 建议重试但信心不足，需要人工确认: step_id={step_id}"
                    )
                    result.metadata["needs_human_review"] = True
                    result.metadata["critic_result"] = critic_result.model_dump()
                    return result
                
                retry_count += 1
                plan_step.metadata["retry_count"] = retry_count
                plan_step.metadata["suggestions"] = critic_result.suggestions
                
                logger.info(
                    f"🔄 Critic RETRY: step_id={step_id}, "
                    f"confidence={critic_result.confidence.value}, "
                    f"retry_count={retry_count}/{max_retries}, "
                    f"suggestions={critic_result.suggestions}"
                )
                
                # 将改进建议注入到下一次执行的上下文中
                if plan_step:
                    plan_step.context = (
                        f"{plan_step.context}\n\n"
                        f"【改进建议（重试 {retry_count}/{max_retries}）】\n"
                        + "\n".join(f"- {s}" for s in critic_result.suggestions)
                    )
                else:
                    # 如果没有 plan_step，将建议添加到消息中
                    messages.append({
                        "role": "system",
                        "content": f"改进建议：\n" + "\n".join(f"- {s}" for s in critic_result.suggestions)
                    })
                
                continue  # 重试
            
            elif critic_result.recommended_action == CriticAction.REPLAN:
                logger.warning(
                    f"⚠️ Critic REPLAN: step_id={step_id}, "
                    f"reason={critic_result.plan_adjustment.reason if critic_result.plan_adjustment else critic_result.reasoning}"
                )
                
                # 触发计划调整
                if critic_result.plan_adjustment:
                    await self._trigger_replan(plan_step, critic_result.plan_adjustment)
                
                plan_step.fail("需要调整计划")
                return AgentResult(
                    result_id=f"result_{uuid4().hex[:8]}",
                    agent_id=agent_config.agent_id,
                    success=False,
                    output=result.output,
                    error="Critic 建议调整计划",
                    metadata={"needs_replan": True, "critic_result": critic_result.model_dump()}
                )
        
        # 超过最大重试次数
        plan_step.fail(f"超过最大重试次数 ({max_retries})")
        return AgentResult(
            result_id=f"result_{uuid4().hex[:8]}",
            agent_id=agent_config.agent_id,
            success=False,
            output=result.output if 'result' in locals() else "",
            error=f"超过最大重试次数 ({max_retries})",
        )
    
    async def _trigger_replan(
        self,
        plan_step: PlanStep,
        adjustment: PlanAdjustmentHint,
    ) -> None:
        """
        触发计划调整（复用现有组件）
        
        V7.2 新增：根据 Critic 的建议调整 Plan
        
        Args:
            plan_step: 当前步骤
            adjustment: 调整建议
        """
        
        logger.info(f"🔄 触发计划调整: step_id={plan_step.id}, action={adjustment.action}")
        
        # 延迟初始化 plan_todo_tool（避免循环依赖）
        if self.plan_todo_tool is None:
            try:
                from tools.plan_todo_tool import PlanTodoTool
                self.plan_todo_tool = PlanTodoTool()
            except ImportError:
                logger.warning("⚠️ plan_todo_tool 未找到，跳过 replan")
                return
        
        # 如果 Plan 不存在，创建一个
        if self.plan is None:
            self.plan = Plan(
                goal="多智能体任务执行",
                execution_mode="dag",
            )
        
        # 根据 action 处理
        if adjustment.action == "skip":
            plan_step.status = StepStatus.SKIPPED
            logger.info(f"⏭️ 跳过步骤: {plan_step.id}")
        
        elif adjustment.action == "insert_before":
            if adjustment.new_step:
                new_step = self.plan.add_step(
                    description=adjustment.new_step,
                    dependencies=plan_step.dependencies,
                )
                plan_step.dependencies = [new_step.id]
                logger.info(f"➕ 插入新步骤: {new_step.id} -> {plan_step.id}")
        
        elif adjustment.action == "modify":
            # 复用 plan_todo_tool.replan()
            if adjustment.context_for_replan:
                try:
                    await self.plan_todo_tool.replan(
                        plan=self.plan,
                        context=adjustment.context_for_replan,
                        failed_step_id=plan_step.id,
                    )
                    logger.info(f"🔧 修改计划: step_id={plan_step.id}")
                except Exception as e:
                    logger.error(f"❌ replan 失败: {e}", exc_info=True)
        
        # 保存 Plan（如果有 PlanStorage）
        # 注意：这里暂时不保存，因为 Orchestrator 可能没有 PlanStorage
        # 如果需要持久化，可以在外部调用时处理
