"""
确定性工作流引擎（Pipeline DSL Executor）

设计理念：
- LLM 生成管道定义（一次调用），执行引擎确定性运行（零 LLM 调用）
- 支持审批卡点（Approval Gate），敏感步骤暂停等待用户确认
- 支持断点恢复（Checkpoint & Resume），中断后凭 token 从断点继续
- 与 RVR-B 循环互补：简单确定性管道走 Pipeline，复杂推理走 RVR-B

管道定义格式（YAML）：
    pipeline:
      name: "竞品分析全流程"
      steps:
        - id: "1"
          skill: "deep-research"
          params: { query: "搜索竞品信息" }
        - id: "2"
          skill: "competitive-intel"
          depends_on: ["1"]
          approval: true          # 审批卡点
        - id: "3"
          skill: "elegant-reports"
          depends_on: ["1", "2"]

架构位置：
    core/orchestration/pipeline.py  ← 本文件
    core/planning/protocol.py       ← 复用 Plan/PlanStep 数据结构
    core/planning/dag_scheduler.py  ← 复用 DAG 拓扑调度
"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from logger import get_logger

logger = get_logger("pipeline")


# ================================================================
# 管道定义模型
# ================================================================


class StepType(str, Enum):
    SKILL = "skill"
    TOOL = "tool"
    CODE = "code"


class ApprovalConfig(BaseModel):
    """审批卡点配置"""

    required: bool = False
    message: str = ""
    timeout_seconds: int = 3600


class PipelineStep(BaseModel):
    """管道步骤定义"""

    id: str
    name: str = ""
    step_type: StepType = StepType.SKILL
    skill: str = ""
    tool: str = ""
    code: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    timeout_seconds: int = 300
    retry_max: int = 1
    output_key: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.name:
            self.name = self.skill or self.tool or f"step-{self.id}"
        if not self.output_key:
            self.output_key = f"step_{self.id}_result"


class PipelineDefinition(BaseModel):
    """管道定义（从 YAML/JSON 解析）"""

    name: str
    description: str = ""
    steps: List[PipelineStep]
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "PipelineDefinition":
        import yaml
        data = yaml.safe_load(yaml_str)
        pipeline_data = data.get("pipeline", data)
        steps_raw = pipeline_data.get("steps", [])
        steps = []
        for s in steps_raw:
            if isinstance(s.get("approval"), bool):
                s["approval"] = ApprovalConfig(
                    required=s["approval"],
                    message=s.get("approval_message", ""),
                )
            steps.append(PipelineStep(**s))
        return cls(
            name=pipeline_data.get("name", "unnamed"),
            description=pipeline_data.get("description", ""),
            steps=steps,
            metadata=pipeline_data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "PipelineDefinition":
        data = json.loads(json_str)
        return cls.from_yaml(json.dumps(data))


# ================================================================
# 执行状态
# ================================================================


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepExecution(BaseModel):
    """单步骤执行记录"""

    step_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    retry_count: int = 0


class PipelineState(BaseModel):
    """管道执行状态（可序列化，用于断点恢复）"""

    pipeline_id: str = Field(default_factory=lambda: f"pipe_{uuid.uuid4().hex[:12]}")
    definition: PipelineDefinition
    status: ExecutionStatus = ExecutionStatus.PENDING
    step_executions: Dict[str, StepExecution] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    resume_token: str = Field(default_factory=lambda: uuid.uuid4().hex)

    def model_post_init(self, __context: Any) -> None:
        for step in self.definition.steps:
            if step.id not in self.step_executions:
                self.step_executions[step.id] = StepExecution(step_id=step.id)

    @property
    def progress(self) -> float:
        total = len(self.step_executions)
        if total == 0:
            return 0.0
        done = sum(
            1 for se in self.step_executions.values()
            if se.status == ExecutionStatus.COMPLETED
        )
        return done / total

    @property
    def is_resumable(self) -> bool:
        return self.status in (
            ExecutionStatus.WAITING_APPROVAL,
            ExecutionStatus.FAILED,
        )

    def get_ready_steps(self) -> List[PipelineStep]:
        completed_ids = {
            sid for sid, se in self.step_executions.items()
            if se.status == ExecutionStatus.COMPLETED
        }
        ready = []
        for step in self.definition.steps:
            se = self.step_executions[step.id]
            if se.status != ExecutionStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in step.depends_on):
                ready.append(step)
        return ready


# ================================================================
# 回调类型
# ================================================================

StepExecutorFn = Callable[
    [PipelineStep, Dict[str, Any]],
    Awaitable[Dict[str, Any]],
]

ApprovalFn = Callable[
    [PipelineStep, str],
    Awaitable[bool],
]

ProgressFn = Callable[
    [PipelineState, PipelineStep, ExecutionStatus],
    Awaitable[None],
]


# ================================================================
# Pipeline Executor
# ================================================================


class PipelineExecutor:
    """
    确定性管道执行器

    与 RVR-B 执行器的区别：
    - RVR-B：每步 LLM 推理 → 工具调用 → 验证 → 反思（灵活但 token 开销大）
    - Pipeline：一次性定义 → 确定性执行 → 审批卡点（高效但需预定义）

    使用方式：
        executor = PipelineExecutor(step_executor=run_skill)
        state = await executor.run(pipeline_def)
    """

    def __init__(
        self,
        step_executor: StepExecutorFn,
        approval_fn: Optional[ApprovalFn] = None,
        progress_fn: Optional[ProgressFn] = None,
        max_concurrency: int = 3,
        storage_dir: Optional[Path] = None,
    ):
        self.step_executor = step_executor
        self.approval_fn = approval_fn
        self.progress_fn = progress_fn
        self.max_concurrency = max_concurrency
        self.storage_dir = storage_dir or Path("storage/pipelines")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # 核心执行
    # ================================================================

    async def run(
        self,
        definition: PipelineDefinition,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> PipelineState:
        """
        执行管道定义

        Args:
            definition: 管道定义
            initial_context: 初始上下文（前置数据，如用户输入）

        Returns:
            PipelineState: 最终执行状态
        """
        state = PipelineState(definition=definition)
        if initial_context:
            state.context.update(initial_context)

        logger.info(f"▶ Pipeline 启动: {definition.name} ({len(definition.steps)} 步)")

        return await self._execute_loop(state)

    async def resume(self, resume_token: str) -> Optional[PipelineState]:
        """
        从断点恢复执行

        Args:
            resume_token: 恢复令牌

        Returns:
            恢复后的执行状态，或 None（令牌无效）
        """
        state = self._load_state(resume_token)
        if not state:
            logger.warning(f"无效的恢复令牌: {resume_token}")
            return None

        if not state.is_resumable:
            logger.warning(f"Pipeline 状态不可恢复: {state.status}")
            return None

        logger.info(f"▶ Pipeline 恢复: {state.definition.name} (进度 {state.progress:.0%})")

        waiting_steps = [
            sid for sid, se in state.step_executions.items()
            if se.status == ExecutionStatus.WAITING_APPROVAL
        ]
        for sid in waiting_steps:
            state.step_executions[sid].status = ExecutionStatus.COMPLETED

        failed_steps = [
            sid for sid, se in state.step_executions.items()
            if se.status == ExecutionStatus.FAILED
        ]
        for sid in failed_steps:
            state.step_executions[sid].status = ExecutionStatus.PENDING
            state.step_executions[sid].error = None
            state.step_executions[sid].retry_count = 0

        return await self._execute_loop(state)

    async def _execute_loop(self, state: PipelineState) -> PipelineState:
        """主执行循环：拓扑排序 → 分层并行执行"""
        state.status = ExecutionStatus.RUNNING
        state.updated_at = datetime.now()

        try:
            while True:
                ready_steps = state.get_ready_steps()
                if not ready_steps:
                    break

                semaphore = asyncio.Semaphore(self.max_concurrency)
                tasks = [
                    self._execute_step_with_semaphore(semaphore, step, state)
                    for step in ready_steps
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                should_pause = False
                for step, result in zip(ready_steps, results):
                    if isinstance(result, Exception):
                        se = state.step_executions[step.id]
                        se.status = ExecutionStatus.FAILED
                        se.error = str(result)
                        logger.error(f"✗ 步骤 {step.id} 异常: {result}")
                    elif result == "paused":
                        should_pause = True

                if should_pause:
                    state.status = ExecutionStatus.WAITING_APPROVAL
                    state.updated_at = datetime.now()
                    self._save_state(state)
                    logger.info(f"⏸ Pipeline 暂停等待审批 (token: {state.resume_token})")
                    return state

                all_done = all(
                    se.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)
                    for se in state.step_executions.values()
                )
                if all_done:
                    break

                has_failure = any(
                    se.status == ExecutionStatus.FAILED
                    for se in state.step_executions.values()
                )
                no_progress = not ready_steps
                if has_failure and no_progress:
                    break

            has_any_failure = any(
                se.status == ExecutionStatus.FAILED
                for se in state.step_executions.values()
            )
            state.status = (
                ExecutionStatus.FAILED if has_any_failure else ExecutionStatus.COMPLETED
            )

        except Exception as e:
            state.status = ExecutionStatus.FAILED
            logger.error(f"Pipeline 执行异常: {e}", exc_info=True)

        state.updated_at = datetime.now()
        self._save_state(state)

        completed = sum(
            1 for se in state.step_executions.values()
            if se.status == ExecutionStatus.COMPLETED
        )
        total = len(state.step_executions)
        logger.info(
            f"{'✓' if state.status == ExecutionStatus.COMPLETED else '✗'} "
            f"Pipeline 结束: {state.definition.name} "
            f"({completed}/{total} 完成, 状态={state.status.value})"
        )

        return state

    async def _execute_step_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        step: PipelineStep,
        state: PipelineState,
    ) -> Optional[str]:
        async with semaphore:
            return await self._execute_step(step, state)

    async def _execute_step(
        self,
        step: PipelineStep,
        state: PipelineState,
    ) -> Optional[str]:
        """执行单个步骤（含审批、重试、进度通知）"""
        se = state.step_executions[step.id]
        se.status = ExecutionStatus.RUNNING
        se.started_at = datetime.now()

        if self.progress_fn:
            await self.progress_fn(state, step, ExecutionStatus.RUNNING)

        # 审批卡点
        if step.approval.required:
            if self.approval_fn:
                message = step.approval.message or f"步骤 [{step.name}] 需要您的确认才能继续"
                approved = await self.approval_fn(step, message)
                if not approved:
                    se.status = ExecutionStatus.WAITING_APPROVAL
                    if self.progress_fn:
                        await self.progress_fn(state, step, ExecutionStatus.WAITING_APPROVAL)
                    return "paused"
            else:
                se.status = ExecutionStatus.WAITING_APPROVAL
                if self.progress_fn:
                    await self.progress_fn(state, step, ExecutionStatus.WAITING_APPROVAL)
                return "paused"

        # 收集依赖结果作为上下文
        step_context = dict(state.context)
        for dep_id in step.depends_on:
            dep_se = state.step_executions.get(dep_id)
            if dep_se and dep_se.result:
                step_context[f"step_{dep_id}_result"] = dep_se.result

        # 合并步骤参数
        exec_params = {**step.params, "_context": step_context, "_step": step.model_dump()}

        start = time.time()
        last_error = None

        for attempt in range(1, step.retry_max + 1):
            try:
                result = await asyncio.wait_for(
                    self.step_executor(step, exec_params),
                    timeout=step.timeout_seconds,
                )
                se.status = ExecutionStatus.COMPLETED
                se.result = json.dumps(result, ensure_ascii=False, default=str) if isinstance(result, dict) else str(result)
                se.duration_ms = int((time.time() - start) * 1000)
                se.completed_at = datetime.now()

                state.context[step.output_key] = result

                logger.info(f"  ✓ 步骤 {step.id} [{step.name}] 完成 ({se.duration_ms}ms)")

                if self.progress_fn:
                    await self.progress_fn(state, step, ExecutionStatus.COMPLETED)

                return None

            except asyncio.TimeoutError:
                last_error = f"超时 ({step.timeout_seconds}s)"
            except Exception as e:
                last_error = str(e)

            se.retry_count = attempt
            if attempt < step.retry_max:
                logger.warning(f"  ⟳ 步骤 {step.id} 重试 ({attempt}/{step.retry_max}): {last_error}")
                await asyncio.sleep(1.0 * attempt)

        se.status = ExecutionStatus.FAILED
        se.error = last_error
        se.duration_ms = int((time.time() - start) * 1000)
        se.completed_at = datetime.now()
        logger.error(f"  ✗ 步骤 {step.id} [{step.name}] 失败: {last_error}")

        if self.progress_fn:
            await self.progress_fn(state, step, ExecutionStatus.FAILED)

        return None

    # ================================================================
    # 状态持久化（断点恢复）
    # ================================================================

    def _save_state(self, state: PipelineState) -> None:
        path = self.storage_dir / f"{state.resume_token}.json"
        try:
            path.write_text(
                state.model_dump_json(indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"保存 Pipeline 状态失败: {e}")

    def _load_state(self, resume_token: str) -> Optional[PipelineState]:
        path = self.storage_dir / f"{resume_token}.json"
        if not path.exists():
            return None
        try:
            return PipelineState.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"加载 Pipeline 状态失败: {e}")
            return None


# ================================================================
# 便捷函数
# ================================================================


def create_pipeline_executor(
    step_executor: StepExecutorFn,
    approval_fn: Optional[ApprovalFn] = None,
    progress_fn: Optional[ProgressFn] = None,
    storage_dir: Optional[Path] = None,
) -> PipelineExecutor:
    """创建管道执行器实例"""
    return PipelineExecutor(
        step_executor=step_executor,
        approval_fn=approval_fn,
        progress_fn=progress_fn,
        storage_dir=storage_dir,
    )
