"""
Worker 调度器

负责 Worker 的分配和任务执行调度

功能：
- Worker 池管理
- 任务分配策略
- 并行/串行执行控制
- 结果收集
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Awaitable
from enum import Enum

from logger import get_logger
from ..fsm.states import SubTaskState, SubTaskStatus
from .dependency_graph import DependencyGraph
from .conflict_resolver import ConflictResolver

logger = get_logger("worker_scheduler")


class ExecutionStrategy(str, Enum):
    """执行策略"""
    AUTO = "auto"           # 自动选择（根据依赖关系）
    PARALLEL = "parallel"   # 并行执行（无依赖任务）
    SEQUENTIAL = "sequential"  # 串行执行


@dataclass
class WorkerInstance:
    """Worker 实例"""
    id: str
    specialization: str
    system_prompt: str
    status: str = "idle"  # idle | running | completed | failed
    current_task: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionResult:
    """执行结果"""
    task_id: str
    worker_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration": self.duration
        }


@dataclass
class SchedulerResult:
    """调度器执行结果"""
    success: bool
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    results: Dict[str, ExecutionResult]  # task_id -> result
    total_duration: float
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "total_duration": self.total_duration
        }


class WorkerScheduler:
    """
    Worker 调度器
    
    负责任务的分配和执行调度
    
    使用示例：
        scheduler = WorkerScheduler(
            max_parallel_workers=5,
            worker_factory=create_worker
        )
        
        result = await scheduler.execute(
            sub_tasks=decomposition_result.sub_tasks,
            strategy=ExecutionStrategy.AUTO
        )
    """
    
    def __init__(
        self,
        max_parallel_workers: int = 5,
        worker_factory: Callable[[SubTaskState], Awaitable[WorkerInstance]] = None,
        worker_executor: Callable[[WorkerInstance, SubTaskState], Awaitable[ExecutionResult]] = None
    ):
        """
        初始化调度器
        
        Args:
            max_parallel_workers: 最大并行 Worker 数
            worker_factory: Worker 工厂函数
            worker_executor: Worker 执行函数
        """
        self.max_parallel_workers = max_parallel_workers
        self._worker_factory = worker_factory
        self._worker_executor = worker_executor
        
        # Worker 池
        self._workers: Dict[str, WorkerInstance] = {}
        
        # 依赖图
        self._dependency_graph: Optional[DependencyGraph] = None
        
        # 执行结果
        self._results: Dict[str, ExecutionResult] = {}
        
        # 并发控制
        self._semaphore = asyncio.Semaphore(max_parallel_workers)
        
        # 冲突解决器
        self.conflict_resolver = ConflictResolver(default_lock_timeout=300)
        
        logger.info(f"WorkerScheduler 初始化完成 (max_parallel={max_parallel_workers})")
    
    async def execute(
        self,
        sub_tasks: List[SubTaskState],
        strategy: ExecutionStrategy = ExecutionStrategy.AUTO
    ) -> SchedulerResult:
        """
        执行任务调度
        
        Args:
            sub_tasks: 子任务列表
            strategy: 执行策略
            
        Returns:
            SchedulerResult
        """
        start_time = datetime.now()
        
        logger.info(
            f"开始任务调度: {len(sub_tasks)} 个任务, "
            f"策略={strategy.value}"
        )
        
        # 1. 构建依赖图
        self._dependency_graph = DependencyGraph()
        self._dependency_graph.add_tasks(sub_tasks)
        
        # 1.5. 🆕 冲突检测与解决
        conflicts = self.conflict_resolver.detect_conflicts(sub_tasks)
        if conflicts:
            logger.warning(f"检测到 {len(conflicts)} 个冲突，应用解决策略")
            # 应用串行化策略
            new_dependencies = self.conflict_resolver.resolve_conflicts(conflicts)
            # 更新依赖图
            for task_id, deps in new_dependencies.items():
                for dep_id in deps:
                    self._dependency_graph.add_edge(dep_id, task_id)
            logger.info(f"已添加 {sum(len(deps) for deps in new_dependencies.values())} 个依赖关系")
        
        # 2. 确定执行策略
        if strategy == ExecutionStrategy.AUTO:
            # 检查是否有依赖
            has_dependencies = any(st.dependencies for st in sub_tasks)
            strategy = ExecutionStrategy.SEQUENTIAL if has_dependencies else ExecutionStrategy.PARALLEL
            logger.info(f"自动选择策略: {strategy.value}")
        
        # 3. 执行
        try:
            if strategy == ExecutionStrategy.PARALLEL:
                await self._execute_parallel()
            else:
                await self._execute_sequential()
            
            # 4. 汇总结果
            total_duration = (datetime.now() - start_time).total_seconds()
            
            completed = sum(1 for r in self._results.values() if r.success)
            failed = sum(1 for r in self._results.values() if not r.success)
            
            result = SchedulerResult(
                success=failed == 0,
                total_tasks=len(sub_tasks),
                completed_tasks=completed,
                failed_tasks=failed,
                results=self._results.copy(),
                total_duration=total_duration
            )
            
            logger.info(
                f"任务调度完成: {completed}/{len(sub_tasks)} 成功, "
                f"耗时 {total_duration:.1f}秒"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"任务调度失败: {e}")
            total_duration = (datetime.now() - start_time).total_seconds()
            
            return SchedulerResult(
                success=False,
                total_tasks=len(sub_tasks),
                completed_tasks=0,
                failed_tasks=len(sub_tasks),
                results=self._results.copy(),
                total_duration=total_duration
            )
    
    async def _execute_parallel(self):
        """并行执行（所有无依赖任务同时执行）"""
        runnable_tasks = self._dependency_graph.get_runnable_tasks()
        
        if not runnable_tasks:
            logger.warning("没有可执行的任务")
            return
        
        # 并行执行所有任务
        tasks = [
            self._execute_task(st)
            for st in runnable_tasks
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_sequential(self):
        """
        串行执行（基于依赖关系）
        
        使用拓扑排序确定执行顺序，
        同一层级的任务可以并行执行
        """
        while True:
            # 获取可执行的任务
            runnable_tasks = self._dependency_graph.get_runnable_tasks()
            
            if not runnable_tasks:
                # 检查是否全部完成
                if self._dependency_graph.is_all_completed():
                    logger.info("所有任务执行完成")
                    break
                
                # 检查是否有失败阻塞
                if self._dependency_graph.has_failed():
                    logger.warning("存在失败任务，部分任务被阻塞")
                    break
                
                # 没有可执行任务也没有完成，可能是死锁
                logger.error("调度死锁：没有可执行任务")
                break
            
            logger.info(f"本轮执行 {len(runnable_tasks)} 个任务")
            
            # 并行执行本轮任务（受 semaphore 限制）
            tasks = [
                self._execute_task(st)
                for st in runnable_tasks
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_task(self, sub_task: SubTaskState) -> ExecutionResult:
        """
        执行单个任务
        
        Args:
            sub_task: 子任务
            
        Returns:
            ExecutionResult
        """
        async with self._semaphore:
            start_time = datetime.now()
            
            logger.info(f"开始执行任务: {sub_task.id} ({sub_task.action})")
            
            # 更新状态
            sub_task.status = SubTaskStatus.RUNNING
            sub_task.started_at = datetime.now()
            
            try:
                # 1. 创建 Worker
                worker = await self._create_worker(sub_task)
                sub_task.worker_id = worker.id
                
                # 2. 执行任务
                result = await self._run_worker(worker, sub_task)
                
                # 3. 更新状态
                duration = (datetime.now() - start_time).total_seconds()
                result.duration = duration
                
                if result.success:
                    sub_task.status = SubTaskStatus.COMPLETED
                    sub_task.result = result.result
                    self._dependency_graph.mark_completed(sub_task.id)
                    logger.info(f"任务完成: {sub_task.id} (耗时 {duration:.1f}秒)")
                else:
                    sub_task.status = SubTaskStatus.FAILED
                    sub_task.error = result.error
                    self._dependency_graph.mark_failed(sub_task.id)
                    logger.warning(f"任务失败: {sub_task.id} - {result.error}")
                
                sub_task.completed_at = datetime.now()
                self._results[sub_task.id] = result
                
                return result
                
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                
                sub_task.status = SubTaskStatus.FAILED
                sub_task.error = str(e)
                sub_task.completed_at = datetime.now()
                
                self._dependency_graph.mark_failed(sub_task.id)
                
                result = ExecutionResult(
                    task_id=sub_task.id,
                    worker_id=sub_task.worker_id or "unknown",
                    success=False,
                    error=str(e),
                    duration=duration
                )
                self._results[sub_task.id] = result
                
                logger.error(f"任务执行异常: {sub_task.id} - {e}")
                return result
    
    async def _create_worker(self, sub_task: SubTaskState) -> WorkerInstance:
        """创建 Worker"""
        if self._worker_factory:
            return await self._worker_factory(sub_task)
        
        # 默认创建简单 Worker
        worker = WorkerInstance(
            id=f"worker-{sub_task.specialization}-{len(self._workers) + 1}",
            specialization=sub_task.specialization,
            system_prompt=sub_task.worker_prompt or ""
        )
        
        self._workers[worker.id] = worker
        return worker
    
    async def _run_worker(
        self,
        worker: WorkerInstance,
        sub_task: SubTaskState
    ) -> ExecutionResult:
        """执行 Worker"""
        if self._worker_executor:
            return await self._worker_executor(worker, sub_task)
        
        # 默认模拟执行
        logger.info(f"Worker {worker.id} 执行任务: {sub_task.action}")
        
        # 模拟执行时间
        await asyncio.sleep(1.0)
        
        return ExecutionResult(
            task_id=sub_task.id,
            worker_id=worker.id,
            success=True,
            result={"message": f"任务 {sub_task.action} 模拟完成"},
            duration=1.0
        )
    
    def get_status(self) -> Dict:
        """获取调度器状态"""
        graph_status = self._dependency_graph.get_status() if self._dependency_graph else {}
        
        return {
            "max_parallel_workers": self.max_parallel_workers,
            "active_workers": len([w for w in self._workers.values() if w.status == "running"]),
            "total_workers": len(self._workers),
            "dependency_graph": graph_status,
            "results_count": len(self._results)
        }


def create_worker_scheduler(
    max_parallel_workers: int = 5,
    **kwargs
) -> WorkerScheduler:
    """创建调度器"""
    return WorkerScheduler(
        max_parallel_workers=max_parallel_workers,
        **kwargs
    )
