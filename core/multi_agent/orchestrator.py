"""
Multi-Agent Orchestrator

V6.0 核心编排器，管理多 Agent 协作的完整生命周期

架构位置：
- 与 SimpleAgent 平级
- 复用 EventManager、MemoryManager、FaultToleranceLayer
- 支持检查点恢复

执行流程：
1. 任务分解（TaskDecomposer）
2. FSM 状态管理
3. Worker 调度（WorkerScheduler）
4. 结果聚合（ResultAggregator）
"""

# 1. 标准库
import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

# 3. 本地模块
from core.llm.base import Message
from core.memory.working import WorkingMemory
from core.multi_agent.checkpoint import create_checkpoint_manager
from logger import get_logger

from .decomposition import TaskDecomposer
from .fault_tolerance import FaultToleranceLayer, create_fault_tolerance_layer
from .fsm import FSMEngine, SubTaskStatus, TaskState, TaskStatus
from .scheduling import ExecutionResult, ExecutionStrategy, ResultAggregator, WorkerScheduler

# 2. 第三方库（无）


logger = get_logger("multi_agent_orchestrator")


@dataclass
class OrchestratorConfig:
    """编排器配置"""

    max_parallel_workers: int = 5
    execution_strategy: ExecutionStrategy = ExecutionStrategy.AUTO
    enable_checkpointing: bool = True
    checkpoint_interval: int = 1
    max_retries: int = 3
    timeout_seconds: int = 3600  # 1 小时


@dataclass
class OrchestratorResult:
    """编排器执行结果"""

    task_id: str
    success: bool
    final_output: Any
    task_state: TaskState
    total_duration: float
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "final_output": self.final_output,
            "task_state": self.task_state.to_dict(),
            "total_duration": self.total_duration,
            "error": self.error,
        }


class MultiAgentOrchestrator:
    """
    Multi-Agent 编排器

    V6.0 核心组件，管理复杂任务的多 Agent 协作

    特性：
    - FSM 状态机管理任务生命周期
    - LLM 语义任务分解
    - 并行/串行调度
    - 生产级容错
    - 检查点恢复

    使用示例：
        orchestrator = MultiAgentOrchestrator(
            event_manager=event_manager,
            memory_manager=memory_manager,
            llm_service=claude_service
        )

        async for event in orchestrator.execute(
            user_query="研究 Top 5 云计算公司的 AI 战略",
            session_id="sess-123"
        ):
            print(event)
    """

    def __init__(
        self,
        event_manager=None,
        memory_manager=None,
        llm_service=None,
        config: OrchestratorConfig = None,
        prompt_cache=None,
        workers_config: List = None,  # 🆕 V6.0: Worker 配置列表
    ):
        """
        初始化编排器

        Args:
            event_manager: EventManager 实例
            memory_manager: MemoryManager 实例
            llm_service: LLM 服务实例
            config: 配置
            prompt_cache: 提示词缓存
            workers_config: 🆕 Worker 配置列表（从 instance 预加载）
        """
        self.event_manager = event_manager
        self.memory_manager = memory_manager
        self.llm_service = llm_service
        self.config = config or OrchestratorConfig()
        self.prompt_cache = prompt_cache
        self.workers_config = workers_config or []  # 🆕 V6.0: 存储 Worker 配置

        # 初始化子组件
        self._init_components()

        # 🆕 V7.1: 原型标记（由 AgentRegistry 设置）
        self._is_prototype = False

        logger.info(
            f"✅ MultiAgentOrchestrator 初始化完成 (预加载 {len(self.workers_config)} 个 Worker 配置)"
        )

    def clone_for_session(
        self, event_manager, conversation_service=None
    ) -> "MultiAgentOrchestrator":
        """
        🆕 V7.1: 从原型克隆多智能体编排器（快速路径）

        复用原型中的重量级组件，仅重置会话级状态

        复用的组件（不重新创建）：
        - llm_service: LLM Service
        - task_decomposer: 任务分解器
        - result_aggregator: 结果聚合器
        - workers_config: Worker 配置
        - config: 编排器配置
        - prompt_cache: 提示词缓存

        重置的状态（每个会话独立）：
        - event_manager: 事件管理器
        - memory_manager: 记忆管理器（会话级）
        - fsm_engine: FSM 引擎（会话级状态）
        - worker_scheduler: Worker 调度器（会话级）
        - fault_tolerance: 容错层（会话级）

        Args:
            event_manager: 事件管理器（必需）
            conversation_service: 会话服务

        Returns:
            就绪的编排器实例
        """
        # 创建新实例（绕过 __init__）
        clone = object.__new__(MultiAgentOrchestrator)

        # ========== 复用原型的重量级组件 ==========
        clone.llm_service = self.llm_service
        clone.config = self.config
        clone.prompt_cache = self.prompt_cache
        clone.workers_config = self.workers_config

        # 复用任务分解器和结果聚合器（无状态）
        clone.task_decomposer = self.task_decomposer
        clone.result_aggregator = self.result_aggregator

        # ========== 设置会话级参数 ==========
        clone.event_manager = event_manager

        # 创建新的会话级记忆管理器
        clone.memory_manager = WorkingMemory(event_manager=event_manager)

        # 重新初始化会话级组件（FSM、调度器、容错层）
        clone._init_components()

        # 附加元数据（如果原型有）
        if hasattr(self, "schema"):
            clone.schema = self.schema
        if hasattr(self, "system_prompt"):
            clone.system_prompt = self.system_prompt
        if hasattr(self, "model"):
            clone.model = self.model
        if hasattr(self, "max_turns"):
            clone.max_turns = self.max_turns

        clone.conversation_service = conversation_service

        # 标记为非原型
        clone._is_prototype = False

        logger.debug(f"🚀 MultiAgentOrchestrator 克隆完成 ({len(clone.workers_config)} workers)")

        return clone

    def _init_components(self):
        """初始化子组件"""
        # FSM 引擎
        state_store = self.memory_manager.plan if self.memory_manager else None
        self.fsm_engine = FSMEngine(
            state_store=state_store,
            event_manager=self.event_manager,
            auto_checkpoint=self.config.enable_checkpointing,
            checkpoint_interval=self.config.checkpoint_interval,
        )

        # 任务分解器
        self.task_decomposer = TaskDecomposer(llm_service=self.llm_service)

        # Worker 调度器
        self.worker_scheduler = WorkerScheduler(
            max_parallel_workers=self.config.max_parallel_workers,
            worker_executor=self._execute_worker_task,
        )

        # 结果聚合器
        self.result_aggregator = ResultAggregator(llm_service=self.llm_service)

        # 容错层
        self.fault_tolerance = create_fault_tolerance_layer()

        # 🆕 V7.1: 检查点管理器（P0 优化）
        self.checkpoint_manager = create_checkpoint_manager()

    def _find_worker_config(self, specialization: str):
        """
        🆕 V6.0: 查找预加载的 Worker 配置

        Args:
            specialization: Worker 专业类型

        Returns:
            匹配的 WorkerConfig 或 None
        """
        for worker_config in self.workers_config:
            if worker_config.specialization == specialization and worker_config.enabled:
                return worker_config
        return None

    async def resume_from_checkpoint(
        self, checkpoint_id: str, user_query: str, session_id: str, context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        🆕 V7.1: 从检查点恢复执行

        Args:
            checkpoint_id: 检查点 ID
            user_query: 用户请求
            session_id: 会话 ID
            context: 额外上下文

        Yields:
            事件字典
        """
        logger.info(f"🔄 从检查点恢复任务: checkpoint_id={checkpoint_id}")

        try:
            # 恢复检查点
            metadata, orchestrator_state, worker_results, ckpt_context = (
                await self.checkpoint_manager.restore_from_checkpoint(checkpoint_id)
            )

            task_id = metadata.task_id

            yield self._emit_event(
                "checkpoint_restored",
                {
                    "task_id": task_id,
                    "checkpoint_id": checkpoint_id,
                    "phase": metadata.phase,
                    "progress": metadata.progress,
                },
            )

            # 根据阶段继续执行
            # TODO: 实现阶段恢复逻辑
            # 当前简化实现：从头开始执行
            logger.warning("⚠️ 检查点恢复功能正在开发中，将从头开始执行")

            async for event in self.execute(user_query, session_id, context):
                yield event

        except Exception as e:
            logger.error(f"❌ 检查点恢复失败: {e}")
            yield self._emit_event(
                "error", {"checkpoint_id": checkpoint_id, "error": f"检查点恢复失败: {str(e)}"}
            )

    async def execute(
        self, user_query: str, session_id: str, context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Multi-Agent 任务（流式返回）

        🆕 V7.1: 支持检查点保存，失败时可从检查点恢复

        Args:
            user_query: 用户请求
            session_id: 会话 ID
            context: 额外上下文

        Yields:
            事件字典
        """
        task_id = f"ma-task-{uuid.uuid4()}"
        start_time = datetime.now()

        logger.info(f"开始 Multi-Agent 任务: task_id={task_id}")

        try:
            # ==================== Phase 1: 创建任务 ====================
            yield self._emit_event("task_created", {"task_id": task_id, "user_query": user_query})

            task_state = await self.fsm_engine.create_task(
                task_id=task_id, session_id=session_id, user_query=user_query
            )

            # ==================== Phase 2: 任务分解 ====================
            yield self._emit_event("phase_start", {"phase": "decomposing", "task_id": task_id})

            await self.fsm_engine.transition(task_id, "start")

            decomposition_result = await self.task_decomposer.decompose(
                user_query=user_query, context=context
            )

            if not decomposition_result.success:
                yield self._emit_event(
                    "error",
                    {"task_id": task_id, "error": decomposition_result.error or "任务分解失败"},
                )
                await self.fsm_engine.transition(
                    task_id, "decompose_error", {"error": decomposition_result.error}
                )
                return

            # 添加子任务到 FSM
            await self.fsm_engine.add_sub_tasks(task_id, decomposition_result.sub_tasks)

            yield self._emit_event(
                "decomposition_complete",
                {
                    "task_id": task_id,
                    "sub_tasks_count": len(decomposition_result.sub_tasks),
                    "reasoning": decomposition_result.reasoning,
                    "parallelizable_groups": decomposition_result.parallelizable_groups,
                },
            )

            # 🆕 V7.1: 保存检查点（任务分解完成）
            await self.checkpoint_manager.save_checkpoint(
                task_id=task_id,
                session_id=session_id,
                orchestrator_state=task_state.model_dump(),
                worker_results=[],
                checkpoint_type="phase",
                phase="decomposing_complete",
                progress=0.25,
                description="任务分解完成",
                context={"sub_tasks_count": len(decomposition_result.sub_tasks)},
            )

            await self.fsm_engine.transition(
                task_id,
                "decompose_complete",
                {
                    "reasoning": decomposition_result.reasoning,
                    "parallelizable_groups": decomposition_result.parallelizable_groups,
                },
            )

            # ==================== Phase 3: 规划 ====================
            yield self._emit_event("phase_start", {"phase": "planning", "task_id": task_id})

            # 🆕 V6.0: 为每个子任务分配 Worker 提示词（优先使用预加载配置）
            for sub_task in decomposition_result.sub_tasks:
                # 1. 优先使用预加载的 Worker 配置（从 instance）
                worker_config = self._find_worker_config(sub_task.specialization)

                if worker_config and worker_config.system_prompt:
                    # 使用预加载的系统提示词
                    sub_task.worker_prompt = worker_config.system_prompt
                    logger.info(
                        f"✅ Worker '{sub_task.id}' 使用预加载提示词: "
                        f"{worker_config.name} ({len(worker_config.system_prompt)} 字符)"
                    )
                else:
                    # 2. Fallback: 动态生成 Worker 提示词（如果没有预加载配置）
                    logger.info(f"⚠️ Worker '{sub_task.id}' 未找到预加载配置，使用 LLM 动态生成")
                    prompt_result = await self.task_decomposer.generate_worker_prompt(sub_task)
                    if prompt_result.success:
                        sub_task.worker_prompt = prompt_result.system_prompt

            await self.fsm_engine.transition(task_id, "plan_ready")

            # ==================== Phase 4: 分配 Worker ====================
            yield self._emit_event("phase_start", {"phase": "dispatching", "task_id": task_id})

            await self.fsm_engine.transition(task_id, "workers_assigned")

            # ==================== Phase 5: 执行 ====================
            yield self._emit_event("phase_start", {"phase": "executing", "task_id": task_id})

            scheduler_result = await self.worker_scheduler.execute(
                sub_tasks=decomposition_result.sub_tasks, strategy=self.config.execution_strategy
            )

            # 发送执行进度事件
            for task_result in scheduler_result.results.values():
                yield self._emit_event(
                    "sub_task_complete",
                    {
                        "task_id": task_id,
                        "sub_task_id": task_result.task_id,
                        "success": task_result.success,
                        "duration": task_result.duration,
                    },
                )

            if scheduler_result.failed_tasks > 0:
                await self.fsm_engine.transition(task_id, "partial_complete")
            else:
                await self.fsm_engine.transition(task_id, "all_complete")

            # 🆕 V7.1: 保存检查点（Worker 执行完成）
            worker_results_dump = [
                {
                    "task_id": r.task_id,
                    "success": r.success,
                    "output": r.output[:500] if r.output else "",  # 截断输出
                    "duration": r.duration,
                }
                for r in scheduler_result.results.values()
            ]
            await self.checkpoint_manager.save_checkpoint(
                task_id=task_id,
                session_id=session_id,
                orchestrator_state=task_state.model_dump(),
                worker_results=worker_results_dump,
                checkpoint_type="phase",
                phase="executing_complete",
                progress=0.75,
                description=f"Worker 执行完成 ({scheduler_result.completed_tasks}/{scheduler_result.total_tasks})",
                context={
                    "completed": scheduler_result.completed_tasks,
                    "failed": scheduler_result.failed_tasks,
                },
            )

            # ==================== Phase 6: 观察 ====================
            yield self._emit_event("phase_start", {"phase": "observing", "task_id": task_id})

            await self.fsm_engine.transition(task_id, "observe_complete")

            # ==================== Phase 7: 验证 ====================
            yield self._emit_event("phase_start", {"phase": "validating", "task_id": task_id})

            # 简单验证：检查是否有足够的成功结果
            if scheduler_result.completed_tasks == 0:
                await self.fsm_engine.transition(
                    task_id, "validation_fail_final", {"error": "所有子任务都失败"}
                )
                yield self._emit_event("error", {"task_id": task_id, "error": "所有子任务都失败"})
                return

            await self.fsm_engine.transition(task_id, "validation_pass")

            # ==================== Phase 8: 聚合 ====================
            yield self._emit_event("phase_start", {"phase": "aggregating", "task_id": task_id})

            # 聚合结果
            worker_results = {
                task_id: result.to_dict() for task_id, result in scheduler_result.results.items()
            }

            aggregation_result = await self.result_aggregator.aggregate(
                user_query=user_query, worker_results=worker_results
            )

            await self.fsm_engine.transition(
                task_id, "aggregate_complete", {"result": aggregation_result.final_output}
            )

            # ==================== 完成 ====================
            total_duration = (datetime.now() - start_time).total_seconds()

            task_state = await self.fsm_engine.get_task(task_id)

            yield self._emit_event(
                "task_complete",
                {
                    "task_id": task_id,
                    "success": True,
                    "total_duration": total_duration,
                    "completed_tasks": scheduler_result.completed_tasks,
                    "failed_tasks": scheduler_result.failed_tasks,
                    "final_output": aggregation_result.final_output,
                },
            )

            logger.info(
                f"Multi-Agent 任务完成: task_id={task_id}, "
                f"耗时={total_duration:.1f}秒, "
                f"成功={scheduler_result.completed_tasks}/{scheduler_result.total_tasks}"
            )

        except Exception as e:
            logger.error(f"Multi-Agent 任务失败: {e}")

            yield self._emit_event("error", {"task_id": task_id, "error": str(e)})

            # 尝试转换到失败状态
            try:
                await self.fsm_engine.transition(task_id, "execution_error", {"error": str(e)})
            except Exception:
                pass

    async def _execute_worker_task(self, worker, sub_task):
        """
        执行单个 Worker 任务

        这是注入到 WorkerScheduler 的执行函数
        """
        logger.info(f"Worker {worker.id} 执行任务: {sub_task.id} ({sub_task.action})")

        try:
            # 使用容错层包装 LLM 调用
            if self.llm_service:
                result = await self.fault_tolerance.execute(
                    "claude_api", self._call_worker_llm, worker, sub_task
                )
            else:
                # 模拟执行
                await asyncio.sleep(1.0)
                result = {"message": f"任务 {sub_task.action} 模拟完成"}

            return ExecutionResult(
                task_id=sub_task.id, worker_id=worker.id, success=True, result=result
            )

        except Exception as e:
            logger.error(f"Worker {worker.id} 执行失败: {e}")
            return ExecutionResult(
                task_id=sub_task.id, worker_id=worker.id, success=False, error=str(e)
            )

    async def _call_worker_llm(self, worker, sub_task):
        """调用 Worker LLM"""
        response = await self.llm_service.create_message_async(
            model="claude-sonnet-4-5-20250929",
            max_tokens=16000,  # 增加以满足 extended thinking 要求
            system=worker.system_prompt,
            messages=[Message(role="user", content=sub_task.action)],
        )

        # 提取响应
        if hasattr(response, "content"):
            for block in response.content:
                if hasattr(block, "text"):
                    return {"content": block.text}

        return {"content": str(response)}

    def _emit_event(self, event_type: str, data: Dict) -> Dict:
        """生成事件"""
        return {
            "type": f"multi_agent.{event_type}",
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

    async def resume_task(self, task_id: str) -> AsyncGenerator[Dict, None]:
        """
        恢复中断的任务

        从检查点恢复执行
        """
        logger.info(f"尝试恢复任务: {task_id}")

        task_state = await self.fsm_engine.restore_from_checkpoint(task_id)

        if not task_state:
            yield self._emit_event("error", {"task_id": task_id, "error": "无法找到任务检查点"})
            return

        logger.info(
            f"任务恢复: task_id={task_id}, "
            f"status={task_state.status.value}, "
            f"checkpoint_version={task_state.checkpoint_version}"
        )

        yield self._emit_event(
            "task_resumed",
            {
                "task_id": task_id,
                "status": task_state.status.value,
                "checkpoint_version": task_state.checkpoint_version,
            },
        )

        # TODO: 根据当前状态继续执行
        # 这需要更复杂的逻辑来处理各种恢复场景

    def get_status(self) -> Dict:
        """获取编排器状态"""
        return {
            "config": {
                "max_parallel_workers": self.config.max_parallel_workers,
                "execution_strategy": self.config.execution_strategy.value,
                "enable_checkpointing": self.config.enable_checkpointing,
            },
            "fault_tolerance": self.fault_tolerance.get_status(),
            "scheduler": self.worker_scheduler.get_status(),
        }


def create_multi_agent_orchestrator(
    event_manager=None, memory_manager=None, llm_service=None, **kwargs
) -> MultiAgentOrchestrator:
    """
    创建 Multi-Agent 编排器

    工厂函数
    """
    return MultiAgentOrchestrator(
        event_manager=event_manager,
        memory_manager=memory_manager,
        llm_service=llm_service,
        **kwargs,
    )
