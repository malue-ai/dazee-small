"""
多智能体编排器（V7.1 - Anthropic 启发版）

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
"""

# 1. 标准库
import asyncio
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

# 2. 第三方库（无）

# 3. 本地模块
from core.billing.tracker import create_enhanced_usage_tracker
from core.agent.multi.models import (
    ExecutionMode,
    AgentConfig,
    MultiAgentConfig,
    TaskAssignment,
    AgentResult,
    SubagentResult,
    OrchestratorState,
    CriticConfig,
    CriticAction,
    CriticConfidence,
    CriticResult,
    PlanAdjustmentHint,  # 🆕 V7.2: 计划调整建议
)
from core.agent.multi.checkpoint import CheckpointManager, Checkpoint
from core.agent.multi.lead_agent import LeadAgent, TaskDecompositionPlan, SubTask
from core.agent.multi.critic import CriticAgent
from core.planning.protocol import Plan, PlanStep, StepStatus
from core.routing import IntentResult
from logger import get_logger

logger = get_logger(__name__)


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
        self.tool_executor = None  # 🆕 V7.3: 工具执行器（用于 RVR 循环）
        self._working_memory = None  # 工作记忆
        self._mem0_client = None  # Mem0 客户端
        
        # 🆕 V7.4: Token 使用统计
        self.usage_tracker = create_enhanced_usage_tracker()
        
        # 追踪信息（用于监控和调试）
        self._execution_trace = []
        
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
                state_id=f"orch_{uuid4()}",
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
            
            # 从分解计划中获取子任务信息（如果有）
            subtask = None
            if decomposition_plan:
                subtask = next(
                    (st for st in decomposition_plan.subtasks if st.subtask_id == agent_id),
                    None
                )
            
            # 发送 Agent 开始事件
            yield {
                "type": "agent_start",
                "session_id": session_id,
                "agent_id": agent_id,
                "role": agent_config.role.value,
                "subtask_title": subtask.title if subtask else None,
            }
            
            # 创建任务分配
            task = TaskAssignment(
                task_id=f"task_{uuid4()}",
                agent_id=agent_id,
                instruction=subtask.description if subtask else f"执行 {agent_config.role.value} 任务",
                source_agent=self._state.completed_agents[-1] if self._state.completed_agents else None,
                source_output=previous_output,
            )
            self._state.task_assignments.append(task)
            
            self._trace("agent_execution_start", {
                "agent_id": agent_id,
                "role": agent_config.role.value,
                "has_subtask": subtask is not None,
            })
            
            # V7.2: 执行 Agent（带 Critic 评估，内部已包含重试逻辑）
            try:
                result = await self._execute_step_with_critique(
                    agent_config,
                    subtask,
                    current_input,
                    previous_output,
                    session_id,
                )
            except Exception as e:
                logger.error(f"❌ Agent {agent_id} 执行异常: {e}", exc_info=True)
                # 创建失败结果
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
                    result_id=f"result_{uuid4()}",
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
        subtask: Optional[SubTask] = None,
    ) -> AgentResult:
        """
        执行单个 Agent（真实实现）
        
        V7.1 改进：
        - 支持子任务定义（来自 Lead Agent 的分解）
        - 动态注入 Subagent 系统提示词（8 个核心要素）
        - 上下文隔离：只传递必要的摘要
        
        Args:
            config: Agent 配置
            messages: 消息历史
            previous_output: 前一个 Agent 的输出（串行模式）
            session_id: 会话 ID
            subtask: 子任务定义（来自 Lead Agent）
            
        Returns:
            AgentResult 执行结果
        """
        start_time = time.time()
        
        task_description = subtask.description if subtask else f"执行 {config.role.value} 任务"
        
        logger.info(
            f"🤖 执行 Subagent: {config.agent_id} ({config.role.value}), "
            f"model={config.model}, task={task_description[:50]}..."
        )
        
        # 如果有子任务定义，使用更详细的日志
        if subtask:
            logger.debug(
                f"   📋 子任务详情:\n"
                f"      - 期望输出: {subtask.expected_output}\n"
                f"      - 成功标准: {subtask.success_criteria}\n"
                f"      - 需要工具: {subtask.tools_required}\n"
                f"      - 约束条件: {subtask.constraints}"
            )
        
        try:
            # 1. 构建 Subagent 系统提示词（核心！）
            system_prompt = self._build_subagent_system_prompt(
                config=config,
                subtask=subtask,
                orchestrator_context=self._build_orchestrator_summary()
            )
            
            # 2. 创建独立的 LLM 服务（上下文隔离）
            # V7.1: 使用配置的 Worker 模型（强弱配对）
            from core.llm import create_claude_service
            
            worker_model = self.worker_model if hasattr(self, 'worker_model') else config.model
            
            if self.config.worker_config:
                llm = create_claude_service(
                    model=worker_model,
                    enable_thinking=self.config.worker_config.enable_thinking,
                    max_tokens=self.config.worker_config.max_tokens,
                    thinking_budget=self.config.worker_config.thinking_budget,
                )
            else:
                llm = create_claude_service(
                    model=worker_model,
                    enable_thinking=True,
                    max_tokens=8192,
                    thinking_budget=5000,  # 默认值，确保小于 max_tokens
                )
            
            # 3. 构建用户消息（只传递必要信息）
            user_message_parts = []
            
            # 添加任务描述
            if subtask:
                user_message_parts.append(f"任务：{subtask.title}")
                user_message_parts.append(f"描述：{subtask.description}")
                if subtask.context:
                    user_message_parts.append(f"\n背景信息：\n{subtask.context}")
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
            
            # 4. 🆕 动态加载工具（根据 SubTask 需求）
            tools = await self._load_subagent_tools(config, subtask)
            
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
                            
                            # 🆕 V7.10: 为 api_calling 工具注入上下文（用于替换 body 中的占位符）
                            if tool_name == "api_calling":
                                tool_input["user_id"] = getattr(self, '_current_user_id', None)
                                tool_input["session_id"] = getattr(self, '_current_session_id', None) or session_id
                                tool_input["conversation_id"] = getattr(self, '_current_session_id', None) or session_id
                                logger.info(
                                    f"   🔑 [api_calling 上下文注入] user_id={tool_input.get('user_id')}, "
                                    f"session_id={tool_input.get('session_id')}, conversation_id={tool_input.get('conversation_id')}"
                                )
                            
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
                result_id=f"result_{uuid4()}",
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
                    "has_subtask": subtask is not None,
                    "subtask_title": subtask.title if subtask else None,
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
                result_id=f"result_{uuid4()}",
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
                    "has_subtask": subtask is not None,
                }
            )
    
    def _build_subagent_system_prompt(
        self,
        config: AgentConfig,
        subtask: Optional[SubTask] = None,
        orchestrator_context: Optional[str] = None,
    ) -> str:
        """
        构建 Subagent 系统提示词（8 个核心要素）
        
        参考 Anthropic Multi-Agent System：
        "Each subagent needs an objective, an output format, guidance on the tools 
        and sources to use, and clear task boundaries."
        
        Args:
            config: Agent 配置
            subtask: 子任务定义
            orchestrator_context: Orchestrator 提供的上下文摘要
            
        Returns:
            str: 完整的系统提示词
        """
        # 1. 明确的目标（Objective）
        if subtask:
            objective = f"**你的目标**：{subtask.title}\n{subtask.description}"
        else:
            objective = f"**你的目标**：执行 {config.role.value} 任务"
        
        # 2. 期望输出格式（Output Format）
        if subtask and subtask.expected_output:
            output_format = f"""
**输出格式要求**：
{subtask.expected_output}

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
        if subtask and subtask.tools_required:
            tools_guidance = f"""
**可用工具**：
{chr(10).join(f"- {tool}" for tool in subtask.tools_required)}

**⚠️ 重要：你必须主动使用工具获取信息！**
- 不要仅凭已有知识回答，必须调用工具搜索最新信息
- 每个子任务至少调用 1-2 次工具
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
        if subtask and subtask.constraints:
            boundaries = f"""
**任务边界与约束**：
{chr(10).join(f"- {constraint}" for constraint in subtask.constraints)}

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
        if subtask and subtask.success_criteria:
            success_criteria = f"""
**成功标准**：
{chr(10).join(f"- {criterion}" for criterion in subtask.success_criteria)}

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
        # 🆕 V7.10: 保存上下文信息，供工具执行时注入使用
        self._current_session_id = session_id
        self._current_user_id = user_id
        
        # 1. 初始化工具加载器
        if self._tool_loader is None:
            from core.tool.loader import ToolLoader
            from core.tool.capability.registry import CapabilityRegistry
            
            self._tool_loader = ToolLoader(
                global_registry=CapabilityRegistry(),
            )
            logger.info("✅ 工具加载器已初始化")
        
        # 初始化工具执行器（用于 Subagent RVR 循环）
        if self.tool_executor is None:
            from core.tool.executor import ToolExecutor
            from core.tool.base import create_tool_context
            from core.tool.capability.registry import CapabilityRegistry
            
            self.tool_executor = ToolExecutor(
                registry=CapabilityRegistry(),
                tool_context=create_tool_context(),
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
        subtask: Optional[SubTask] = None,
    ) -> List[Dict[str, Any]]:
        """
        🆕 V7.2: 动态加载 Subagent 工具（参考 V4 工具分层设计）
        
        工具分层策略（参考 V4-ARCHITECTURE-HISTORY.md）：
        - Level 1: 核心工具 - 始终加载（plan_todo 等）
        - Level 2: 动态工具 - 按需加载（web_search, exa_search 等）
        
        Args:
            config: Agent 配置
            subtask: 子任务定义（包含 tools_required）
            
        Returns:
            List[Dict]: Anthropic 格式的工具定义列表
        """
        # 确保工具加载器已初始化
        if self._tool_loader is None:
            await self._initialize_shared_resources(session_id="temp")
        
        # 1. 确定需要加载的工具（分层策略）
        # Level 1: 核心工具（始终加载）
        core_tools = ["plan_todo"]
        
        # Level 2: 动态工具（根据 SubTask 或默认配置）
        if subtask and subtask.tools_required:
            dynamic_tools = subtask.tools_required
            logger.debug(f"📋 SubTask 指定工具: {dynamic_tools}")
        else:
            # 默认研究工具
            # 🆕 web_search 已移除，改用 tavily_search
            dynamic_tools = ["tavily_search", "exa_search", "wikipedia"]
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
    
    async def _spawn_subagent(
        self,
        config: AgentConfig,
        subtask: SubTask,
        orchestrator_summary: str,
        previous_output_summary: Optional[str] = None,
    ) -> SubagentResult:
        """
        生成并执行 Subagent（上下文隔离版本）
        
        V7.1 核心特性：
        - Subagent 在独立的上下文中执行
        - 只接收压缩的摘要（< 500 tokens）
        - 返回压缩的摘要给 Orchestrator
        
        参考 Anthropic Multi-Agent System：
        "The orchestrator maintains a clean context with summaries, 
        while subagents work in isolation."
        
        Args:
            config: Agent 配置
            subtask: 子任务定义
            orchestrator_summary: Orchestrator 提供的摘要
            previous_output_summary: 前置输出摘要（如果有）
            
        Returns:
            SubagentResult: 执行结果（包含摘要）
        """
        start_time = time.time()
        
        logger.info(f"🚀 Spawn Subagent: {config.agent_id} for task '{subtask.title}'")
        
        try:
            # 1. 构建系统提示词
            system_prompt = self._build_subagent_system_prompt(
                config=config,
                subtask=subtask,
                orchestrator_context=orchestrator_summary
            )
            
            # 2. 创建独立的 LLM 服务
            # V7.1: 使用配置的 Worker 模型（强弱配对）
            from core.llm import create_claude_service
            
            worker_model = self.worker_model if hasattr(self, 'worker_model') else config.model
            
            if self.config.worker_config:
                llm = create_claude_service(
                    model=worker_model,
                    enable_thinking=self.config.worker_config.enable_thinking,
                    max_tokens=self.config.worker_config.max_tokens,
                    thinking_budget=self.config.worker_config.thinking_budget,
                )
            else:
                llm = create_claude_service(
                    model=worker_model,
                    enable_thinking=True,
                    max_tokens=8192,
                    thinking_budget=5000,  # 默认值，确保小于 max_tokens
                )
            
            # 3. 构建用户消息（只传递摘要，不传完整历史）
            user_message_parts = [
                f"**任务**：{subtask.title}",
                f"**描述**：{subtask.description}",
            ]
            
            if subtask.context:
                user_message_parts.append(f"\n**背景信息**：\n{subtask.context}")
            
            if previous_output_summary:
                user_message_parts.append(f"\n**前置任务输出摘要**：\n{previous_output_summary}")
            
            user_message = "\n\n".join(user_message_parts)
            
            # 4. 🆕 动态加载工具
            tools = await self._load_subagent_tools(config, subtask)
            
            # 5. 执行 Subagent
            context_length = len(system_prompt) + len(user_message)
            
            logger.info(
                f"📊 Subagent 上下文: system={len(system_prompt)}, "
                f"user={len(user_message)}, total={context_length}, tools={len(tools)}"
            )
            
            # V7.2 调试：显示第一个工具的完整结构
            if tools:
                first_tool = tools[0]
                logger.info(
                    f"   🔧 第一个工具示例: name={first_tool.get('name')}, "
                    f"has_schema={bool(first_tool.get('input_schema'))}, "
                    f"schema_type={first_tool.get('input_schema', {}).get('type')}"
                )
            
            from core.llm.base import Message
            import json
            
            # 🆕 V7.3: 实现完整的 RVR 工具执行循环
            # 参考 SimpleAgent 的工具调用逻辑 + V4-ARCHITECTURE-HISTORY 分层设计
            
            messages = [Message(role="user", content=user_message)]
            max_tool_turns = 5  # 最大工具调用轮次（防止无限循环）
            turns_used = 0
            all_tool_results = []  # 收集所有工具执行结果
            final_response = ""
            
            for turn in range(max_tool_turns):
                turns_used += 1
                
                logger.info(f"   🔄 Subagent Turn {turn + 1}/{max_tool_turns}")
                
                llm_response = await llm.create_message_async(
                    messages=messages,
                    system=system_prompt,
                    temperature=0.5,
                    tools=tools,
                )
                
                stop_reason = getattr(llm_response, 'stop_reason', 'end_turn')
                logger.info(f"   📡 LLM stop_reason: {stop_reason}")
                
                # 检查是否有工具调用
                if stop_reason == "tool_use" and hasattr(llm_response, 'tool_calls') and llm_response.tool_calls:
                    tool_calls = llm_response.tool_calls
                    logger.info(f"   🔧 LLM 请求调用 {len(tool_calls)} 个工具")
                    
                    # 🆕 V7.3: 区分客户端工具和服务端工具（参考 SimpleAgent）
                    # - 客户端工具（tool_use）：需要我们执行并返回 tool_result
                    # - 服务端工具（server_tool_use）：Anthropic 服务器已执行，结果在 raw_content 中
                    client_tools = [tc for tc in tool_calls if tc.get("type") == "tool_use"]
                    server_tools = [tc for tc in tool_calls if tc.get("type") == "server_tool_use"]
                    
                    if server_tools:
                        server_tool_names = [t.get('name') for t in server_tools]
                        logger.info(f"   🌐 服务端工具已执行: {server_tool_names}")
                        # 记录服务端工具调用
                        for st in server_tools:
                            all_tool_results.append({
                                "tool": st.get('name'),
                                "input": st.get('input', {}),
                                "result": {"handled_by": "anthropic_server"}
                            })
                    
                    # 添加 assistant 消息（包含 tool_use 和 server_tool_use）
                    messages.append(Message(role="assistant", content=llm_response.raw_content))
                    
                    # 只有客户端工具需要我们执行
                    if client_tools:
                        tool_results = []
                        for tc in client_tools:
                            tool_name = tc.get('name', '')
                            tool_input = tc.get('input', {})
                            tool_id = tc.get('id', '')
                            
                            logger.info(f"   🔨 执行客户端工具: {tool_name}")
                            
                            # 🆕 V7.10: 为 api_calling 工具注入上下文（用于替换 body 中的占位符）
                            if tool_name == "api_calling":
                                tool_input["user_id"] = getattr(self, '_current_user_id', None)
                                tool_input["session_id"] = getattr(self, '_current_session_id', None)
                                tool_input["conversation_id"] = getattr(self, '_current_session_id', None)
                                logger.info(
                                    f"   🔑 [api_calling 上下文注入] user_id={tool_input.get('user_id')}, "
                                    f"session_id={tool_input.get('session_id')}, conversation_id={tool_input.get('conversation_id')}"
                                )
                            
                            try:
                                # 使用 ToolExecutor 执行工具
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
                        
                        # 只有客户端工具需要添加 tool_result 到 user message
                        if tool_results:
                            messages.append(Message(role="user", content=tool_results))
                    # 如果只有服务端工具，不需要添加 user message，直接进入下一轮
                    
                    # 继续下一轮
                    continue
                
                # 没有工具调用，提取最终响应
                final_response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                
                # 如果是文本响应，跳出循环
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
            
            # 6. 生成摘要（压缩输出）
            summary = await self._compress_subagent_output(response)
            
            compression_ratio = len(summary) / len(response) if len(response) > 0 else 1.0
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"✅ Subagent 完成: {config.agent_id}, "
                f"耗时 {duration_ms}ms, 压缩比 {compression_ratio:.2f}"
            )
            
            return SubagentResult(
                result_id=f"subresult_{uuid4()}",
                agent_id=config.agent_id,
                subtask_id=subtask.subtask_id,
                success=True,
                summary=summary,
                full_output=response,
                turns_used=turns_used,  # 🆕 记录实际轮次
                duration_ms=duration_ms,
                context_length=context_length,
                summary_compression_ratio=compression_ratio,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                metadata={
                    "model": config.model,
                    "subtask_title": subtask.title,
                    "system_prompt_length": len(system_prompt),
                    "user_message_length": len(user_message),
                    "full_output_length": len(response),
                    "summary_length": len(summary),
                    "tool_calls_count": len(all_tool_results),  # 🆕 工具调用统计
                    "tool_results": all_tool_results[:5] if all_tool_results else [],  # 🆕 保留前5个工具结果摘要
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Subagent 执行失败: {config.agent_id}, error={e}", exc_info=True)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return SubagentResult(
                result_id=f"subresult_{uuid4()}",
                agent_id=config.agent_id,
                subtask_id=subtask.subtask_id,
                success=False,
                summary=f"执行失败: {str(e)}",
                full_output="",
                error=str(e),
                turns_used=0,
                duration_ms=duration_ms,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                metadata={
                    "model": config.model,
                    "subtask_title": subtask.title,
                }
            )
    
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
            }
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
        执行步骤（带 Critic 评估）
        
        V7.2 新增：在执行后自动调用 Critic 评估，根据结果决定下一步
        
        Args:
            agent_config: Agent 配置
            subtask: 子任务定义
            messages: 消息历史
            previous_output: 前一个 Agent 的输出
            session_id: 会话 ID
            
        Returns:
            AgentResult: 执行结果
        """
        # 如果未启用 Critic，直接执行
        if not self.critic or not self.critic_config:
            return await self._execute_single_agent(
                agent_config, messages, previous_output, session_id, subtask
            )
        
        # 创建 PlanStep（用于 Critic）
        step_id = subtask.subtask_id if subtask else f"step_{agent_config.agent_id}"
        plan_step = self._subtask_to_plan_step(subtask, step_id) if subtask else PlanStep(
            id=step_id,
            description=f"执行 {agent_config.role.value} 任务",
            status=StepStatus.IN_PROGRESS,
        )
        
        max_retries = self.critic_config.max_retries
        retry_count = 0
        
        while retry_count <= max_retries:
            # 1. Execute
            result = await self._execute_single_agent(
                agent_config, messages, previous_output, session_id, subtask
            )
            
            # 如果执行失败，直接返回
            if not result.success:
                plan_step.fail(result.error or "执行失败")
                return result
            
            # 2. Critique
            success_criteria = (
                subtask.success_criteria 
                if subtask and subtask.success_criteria 
                else plan_step.metadata.get("success_criteria", [])
            )
            
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
                if subtask:
                    subtask.context = (
                        f"{subtask.context}\n\n"
                        f"【改进建议（重试 {retry_count}/{max_retries}）】\n"
                        + "\n".join(f"- {s}" for s in critic_result.suggestions)
                    )
                else:
                    # 如果没有 subtask，将建议添加到消息中
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
                    result_id=f"result_{uuid4()}",
                    agent_id=agent_config.agent_id,
                    success=False,
                    output=result.output,
                    error="Critic 建议调整计划",
                    metadata={"needs_replan": True, "critic_result": critic_result.model_dump()}
                )
        
        # 超过最大重试次数
        plan_step.fail(f"超过最大重试次数 ({max_retries})")
        return AgentResult(
            result_id=f"result_{uuid4()}",
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
