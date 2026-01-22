"""
DAG 调度器（DAGScheduler）

V7.7 新增模块

提供多智能体 DAG 调度能力：
1. 依赖分析和并行组计算
2. 分层执行（每层可并行，层间串行）
3. 失败重试和级联失败处理
4. 依赖结果注入

设计原则：
- 与 Plan 协议解耦，只关注调度逻辑
- 支持回调函数，方便集成事件系统
- 异步执行，充分利用并发能力
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from core.planning.protocol import Plan, PlanStep, StepStatus

logger = logging.getLogger(__name__)


# ===================
# 数据结构
# ===================

@dataclass
class StepResult:
    """步骤执行结果"""
    step_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "success": self.success,
            "output": self.output[:500] if self.output else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
        }


@dataclass
class DAGExecutionResult:
    """DAG 执行结果"""
    plan_id: str
    success: bool
    total_steps: int
    completed_steps: int
    failed_steps: int
    skipped_steps: int
    step_results: Dict[str, StepResult] = field(default_factory=dict)
    execution_groups: List[List[str]] = field(default_factory=list)
    total_duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "success": self.success,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "execution_groups": self.execution_groups,
            "total_duration_ms": self.total_duration_ms,
        }


# ===================
# 回调类型定义
# ===================

# 步骤执行器：(step, 依赖结果) -> StepResult
StepExecutor = Callable[[PlanStep, Dict[str, StepResult]], Awaitable[StepResult]]

# 事件回调
OnStepStart = Callable[[PlanStep], None]
OnStepEnd = Callable[[PlanStep, StepResult], None]
OnGroupStart = Callable[[int, List[PlanStep]], None]
OnGroupEnd = Callable[[int, List[PlanStep], List[StepResult]], None]


# ===================
# DAG 调度器
# ===================

class DAGScheduler:
    """
    DAG 调度器
    
    功能：
    1. 依赖分析和并行组计算（拓扑分层）
    2. 分层执行（每层可并行，层间串行）
    3. 失败重试和级联失败处理
    4. 依赖结果注入
    
    使用方式：
        scheduler = DAGScheduler(max_concurrency=5)
        
        # 计算并行组
        groups = scheduler.compute_parallel_groups(plan)
        
        # 执行 DAG
        result = await scheduler.execute(
            plan=plan,
            executor=my_step_executor,
            on_step_start=lambda step: print(f"开始: {step.id}"),
            on_step_end=lambda step, result: print(f"完成: {step.id}"),
        )
    """
    
    def __init__(
        self,
        max_concurrency: int = 5,
        enable_retry: bool = True,
        max_retries: int = 2,
        context_max_length: int = 2000,
    ):
        """
        初始化 DAG 调度器
        
        Args:
            max_concurrency: 最大并发数
            enable_retry: 是否启用失败重试
            max_retries: 最大重试次数
            context_max_length: 注入上下文的最大长度
        """
        self.max_concurrency = max_concurrency
        self.enable_retry = enable_retry
        self.max_retries = max_retries
        self.context_max_length = context_max_length
        
        logger.info(
            f"✅ DAGScheduler 初始化: "
            f"max_concurrency={max_concurrency}, "
            f"enable_retry={enable_retry}, "
            f"max_retries={max_retries}"
        )
    
    # ===================
    # 并行组计算
    # ===================
    
    def compute_parallel_groups(self, plan: Plan) -> List[List[PlanStep]]:
        """
        计算可并行执行的步骤组（拓扑分层）
        
        算法：
        1. 找出所有入度为 0 的节点作为第一层
        2. 移除第一层节点，更新入度
        3. 重复直到所有节点都被分配
        
        Args:
            plan: Plan 对象
            
        Returns:
            List[List[PlanStep]]: 并行组列表，每组内可同时执行
        """
        if not plan.steps:
            return []
        
        step_map = {step.id: step for step in plan.steps}
        completed: Set[str] = set()
        groups: List[List[PlanStep]] = []
        
        # 检测已完成/跳过/失败的步骤
        for step in plan.steps:
            if step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED, StepStatus.FAILED):
                completed.add(step.id)
        
        max_iterations = len(plan.steps) + 1  # 防止无限循环
        iteration = 0
        
        while len(completed) < len(plan.steps) and iteration < max_iterations:
            iteration += 1
            
            # 找出可执行的步骤（依赖都已完成且状态为 PENDING）
            ready = []
            for step in plan.steps:
                if step.id in completed:
                    continue
                
                if step.status != StepStatus.PENDING:
                    continue
                
                # 检查所有依赖是否已完成
                deps_satisfied = all(dep in completed for dep in step.dependencies)
                if deps_satisfied:
                    ready.append(step)
            
            if not ready:
                # 没有可执行的步骤，可能存在循环依赖或其他问题
                remaining = [s.id for s in plan.steps if s.id not in completed]
                logger.warning(f"⚠️ DAG 调度异常：无法继续，剩余步骤 {remaining}")
                break
            
            # 按优先级排序（优先级高的先执行）
            ready.sort(key=lambda s: s.priority, reverse=True)
            
            groups.append(ready)
            completed.update(step.id for step in ready)
        
        logger.info(f"📊 DAG 分层: {len(groups)} 组, 分布: {[len(g) for g in groups]}")
        return groups
    
    # ===================
    # 依赖上下文注入
    # ===================
    
    def inject_dependency_context(
        self,
        step: PlanStep,
        completed_results: Dict[str, StepResult],
    ) -> PlanStep:
        """
        将依赖步骤的结果注入到当前步骤的上下文
        
        Args:
            step: 待执行的步骤
            completed_results: 已完成步骤的结果
            
        Returns:
            PlanStep: 注入上下文后的步骤（修改原对象）
        """
        if not step.dependencies:
            return step
        
        context_parts = ["## 前置任务结果\n"]
        total_length = 0
        
        for dep_id in step.dependencies:
            if dep_id in completed_results:
                result = completed_results[dep_id]
                
                if result.success and result.output:
                    # 截断过长的输出
                    output = result.output
                    if len(output) > self.context_max_length // len(step.dependencies):
                        output = output[:self.context_max_length // len(step.dependencies)] + "...[截断]"
                    
                    context_parts.append(f"### 步骤 {dep_id} 结果\n{output}\n")
                    total_length += len(output)
                elif not result.success:
                    context_parts.append(f"### 步骤 {dep_id} 失败\n错误: {result.error}\n")
        
        if len(context_parts) > 1:  # 有实际内容
            step.injected_context = "\n".join(context_parts)
            logger.debug(f"📥 步骤 {step.id} 注入依赖上下文: {total_length} 字符")
        
        return step
    
    # ===================
    # DAG 执行
    # ===================
    
    async def execute(
        self,
        plan: Plan,
        executor: StepExecutor,
        on_step_start: Optional[OnStepStart] = None,
        on_step_end: Optional[OnStepEnd] = None,
        on_group_start: Optional[OnGroupStart] = None,
        on_group_end: Optional[OnGroupEnd] = None,
    ) -> DAGExecutionResult:
        """
        执行 Plan（分层并行）
        
        执行流程：
        1. 计算并行组
        2. 逐组执行，组内并行
        3. 每步执行前注入依赖上下文
        4. 处理失败重试和级联失败
        
        Args:
            plan: 待执行的 Plan
            executor: 步骤执行器函数
            on_step_start: 步骤开始回调
            on_step_end: 步骤结束回调
            on_group_start: 组开始回调
            on_group_end: 组结束回调
            
        Returns:
            DAGExecutionResult: 执行结果
        """
        start_time = time.time()
        
        # 计算并行组
        groups = self.compute_parallel_groups(plan)
        
        if not groups:
            return DAGExecutionResult(
                plan_id=plan.plan_id,
                success=True,
                total_steps=0,
                completed_steps=0,
                failed_steps=0,
                skipped_steps=0,
                execution_groups=[],
                total_duration_ms=0,
            )
        
        # 执行状态
        completed_results: Dict[str, StepResult] = {}
        failed_step_ids: Set[str] = set()
        skipped_step_ids: Set[str] = set()
        execution_groups: List[List[str]] = []
        
        logger.info(f"🚀 开始 DAG 执行: plan_id={plan.plan_id}, 共 {len(groups)} 组")
        
        # 逐组执行
        for group_idx, group in enumerate(groups):
            # 过滤掉需要跳过的步骤（依赖失败）
            executable_steps = []
            for step in group:
                # 检查是否有依赖失败
                deps_failed = any(dep in failed_step_ids for dep in step.dependencies)
                if deps_failed:
                    step.skip("依赖步骤失败")
                    skipped_step_ids.add(step.id)
                    completed_results[step.id] = StepResult(
                        step_id=step.id,
                        success=False,
                        error="依赖步骤失败，跳过执行",
                    )
                    logger.warning(f"⏭️ 跳过步骤 {step.id}：依赖失败")
                else:
                    executable_steps.append(step)
            
            if not executable_steps:
                continue
            
            execution_groups.append([s.id for s in executable_steps])
            
            # 触发组开始回调
            if on_group_start:
                try:
                    on_group_start(group_idx, executable_steps)
                except Exception as e:
                    logger.warning(f"⚠️ on_group_start 回调异常: {e}")
            
            # 并行执行组内步骤
            group_results = await self._execute_group(
                steps=executable_steps,
                executor=executor,
                completed_results=completed_results,
                on_step_start=on_step_start,
                on_step_end=on_step_end,
            )
            
            # 更新状态
            for step, result in zip(executable_steps, group_results):
                completed_results[step.id] = result
                if not result.success:
                    failed_step_ids.add(step.id)
            
            # 触发组结束回调
            if on_group_end:
                try:
                    on_group_end(group_idx, executable_steps, group_results)
                except Exception as e:
                    logger.warning(f"⚠️ on_group_end 回调异常: {e}")
        
        # 计算最终结果
        total_duration_ms = int((time.time() - start_time) * 1000)
        completed_count = sum(1 for r in completed_results.values() if r.success)
        failed_count = len(failed_step_ids)
        skipped_count = len(skipped_step_ids)
        
        success = failed_count == 0 and skipped_count == 0
        
        logger.info(
            f"✅ DAG 执行完成: "
            f"success={success}, "
            f"completed={completed_count}, "
            f"failed={failed_count}, "
            f"skipped={skipped_count}, "
            f"duration={total_duration_ms}ms"
        )
        
        return DAGExecutionResult(
            plan_id=plan.plan_id,
            success=success,
            total_steps=len(plan.steps),
            completed_steps=completed_count,
            failed_steps=failed_count,
            skipped_steps=skipped_count,
            step_results=completed_results,
            execution_groups=execution_groups,
            total_duration_ms=total_duration_ms,
        )
    
    async def _execute_group(
        self,
        steps: List[PlanStep],
        executor: StepExecutor,
        completed_results: Dict[str, StepResult],
        on_step_start: Optional[OnStepStart] = None,
        on_step_end: Optional[OnStepEnd] = None,
    ) -> List[StepResult]:
        """
        并行执行一组步骤
        
        Args:
            steps: 待执行的步骤列表
            executor: 步骤执行器
            completed_results: 已完成的结果（用于注入上下文）
            on_step_start: 步骤开始回调
            on_step_end: 步骤结束回调
            
        Returns:
            List[StepResult]: 执行结果列表
        """
        # 控制并发数
        semaphore = asyncio.Semaphore(self.max_concurrency)
        
        async def execute_with_semaphore(step: PlanStep) -> StepResult:
            async with semaphore:
                return await self._execute_single_step(
                    step=step,
                    executor=executor,
                    completed_results=completed_results,
                    on_step_start=on_step_start,
                    on_step_end=on_step_end,
                )
        
        # 并行执行
        tasks = [execute_with_semaphore(step) for step in steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        final_results = []
        for step, result in zip(steps, results):
            if isinstance(result, Exception):
                final_results.append(StepResult(
                    step_id=step.id,
                    success=False,
                    error=str(result),
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    async def _execute_single_step(
        self,
        step: PlanStep,
        executor: StepExecutor,
        completed_results: Dict[str, StepResult],
        on_step_start: Optional[OnStepStart] = None,
        on_step_end: Optional[OnStepEnd] = None,
    ) -> StepResult:
        """
        执行单个步骤（带重试）
        
        Args:
            step: 待执行的步骤
            executor: 步骤执行器
            completed_results: 已完成的结果
            on_step_start: 步骤开始回调
            on_step_end: 步骤结束回调
            
        Returns:
            StepResult: 执行结果
        """
        start_time = time.time()
        
        # 注入依赖上下文
        self.inject_dependency_context(step, completed_results)
        
        # 标记开始
        step.start()
        
        # 触发开始回调
        if on_step_start:
            try:
                on_step_start(step)
            except Exception as e:
                logger.warning(f"⚠️ on_step_start 回调异常: {e}")
        
        logger.info(f"🔄 执行步骤 {step.id}: {step.description[:50]}...")
        
        result: Optional[StepResult] = None
        last_error: Optional[str] = None
        
        # 执行（带重试）
        for attempt in range(1, self.max_retries + 2):  # +2 是因为包含首次尝试
            try:
                result = await asyncio.wait_for(
                    executor(step, completed_results),
                    timeout=step.max_time_seconds,
                )
                
                if result.success:
                    break
                else:
                    last_error = result.error
                    
            except asyncio.TimeoutError:
                last_error = f"执行超时（{step.max_time_seconds}秒）"
                result = StepResult(
                    step_id=step.id,
                    success=False,
                    error=last_error,
                )
            except Exception as e:
                last_error = str(e)
                result = StepResult(
                    step_id=step.id,
                    success=False,
                    error=last_error,
                )
            
            # 判断是否重试
            if not self.enable_retry or attempt > self.max_retries:
                break
            
            step.increment_retry()
            logger.warning(f"⚠️ 步骤 {step.id} 失败（尝试 {attempt}/{self.max_retries + 1}），重试中...")
            await asyncio.sleep(0.5 * attempt)  # 指数退避
        
        # 计算耗时
        duration_ms = int((time.time() - start_time) * 1000)
        
        if result is None:
            result = StepResult(
                step_id=step.id,
                success=False,
                error=last_error or "未知错误",
            )
        
        result.duration_ms = duration_ms
        result.retry_count = step.retry_count
        
        # 更新步骤状态
        if result.success:
            step.complete(result.output or "")
            logger.info(f"✅ 步骤 {step.id} 完成（{duration_ms}ms）")
        else:
            step.fail(result.error or "执行失败")
            logger.error(f"❌ 步骤 {step.id} 失败: {result.error}")
        
        # 触发结束回调
        if on_step_end:
            try:
                on_step_end(step, result)
            except Exception as e:
                logger.warning(f"⚠️ on_step_end 回调异常: {e}")
        
        return result
