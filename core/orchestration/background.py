"""
后台异步任务管理器

设计理念：
- 长任务异步化：用户发起任务后可离开，Agent 后台运行，完成后通知
- 进度追踪：通过 EventBroadcaster 推送实时进度
- 通知交付：完成/失败后通过系统通知 + 前端事件告知用户

使用场景：
    用户: "帮我做 5 家公司的竞品分析报告"
    Agent: "好的，预计 8 分钟，完成后通知你"
    → 后台执行 Pipeline
    → 完成后推送通知

架构：
    ChatService → BackgroundTaskManager.submit() → asyncio.Task
                                                  → 进度事件 → 前端
                                                  → 完成通知 → 系统通知
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from logger import get_logger

logger = get_logger("background_task")


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTask:
    """后台任务记录"""

    task_id: str
    name: str
    description: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    progress: float = 0.0
    progress_message: str = ""
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    user_id: str = ""
    session_id: str = ""
    conversation_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)

    @property
    def elapsed_ms(self) -> int:
        if not self.started_at:
            return 0
        end = self.completed_at or time.time()
        return int((end - self.started_at) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "result_preview": str(self.result)[:500] if self.result else None,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
        }


# 回调类型
TaskFn = Callable[["BackgroundTask", "BackgroundTaskManager"], Awaitable[Any]]
NotifyFn = Callable[["BackgroundTask"], Awaitable[None]]
ProgressEventFn = Callable[[str, Dict[str, Any]], Awaitable[None]]


class BackgroundTaskManager:
    """
    后台任务管理器

    职责：
    1. 接受任务提交，在后台 asyncio.Task 中执行
    2. 追踪任务状态和进度
    3. 完成/失败时触发通知回调
    4. 提供任务查询接口（供前端轮询或 WebSocket 推送）
    """

    def __init__(
        self,
        on_notify: Optional[NotifyFn] = None,
        on_progress_event: Optional[ProgressEventFn] = None,
        max_concurrent: int = 5,
    ):
        self.on_notify = on_notify
        self.on_progress_event = on_progress_event
        self.max_concurrent = max_concurrent
        self._tasks: Dict[str, BackgroundTask] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ================================================================
    # 任务提交
    # ================================================================

    def submit(
        self,
        name: str,
        fn: TaskFn,
        user_id: str = "",
        session_id: str = "",
        conversation_id: str = "",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BackgroundTask:
        """
        提交后台任务

        Args:
            name: 任务名称（用户可见）
            fn: 异步任务函数，签名 (task, manager) -> result
            user_id: 用户 ID
            session_id: 会话 ID
            conversation_id: 对话 ID
            description: 任务描述
            metadata: 附加元数据

        Returns:
            BackgroundTask: 任务对象（含 task_id 供查询）
        """
        task = BackgroundTask(
            task_id=f"bg_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            metadata=metadata or {},
        )
        self._tasks[task.task_id] = task

        asyncio_task = asyncio.create_task(self._run_task(task, fn))
        task._asyncio_task = asyncio_task

        logger.info(f"📋 后台任务已提交: {task.task_id} [{name}]")
        return task

    async def _run_task(self, task: BackgroundTask, fn: TaskFn) -> None:
        """执行任务（并发控制 + 状态管理 + 通知）"""
        async with self._semaphore:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            await self._emit_progress(task, "任务开始执行")

            try:
                result = await fn(task, self)
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.progress = 1.0
                task.completed_at = time.time()
                task.progress_message = "完成"

                logger.info(
                    f"✓ 后台任务完成: {task.task_id} [{task.name}] "
                    f"({task.elapsed_ms}ms)"
                )

            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                task.completed_at = time.time()
                logger.info(f"⊘ 后台任务取消: {task.task_id}")

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = time.time()
                logger.error(
                    f"✗ 后台任务失败: {task.task_id} [{task.name}]: {e}",
                    exc_info=True,
                )

            await self._emit_progress(task, task.progress_message or task.status.value)

            if self.on_notify and task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                try:
                    await self.on_notify(task)
                except Exception as e:
                    logger.warning(f"通知回调异常: {e}")

    # ================================================================
    # 进度更新
    # ================================================================

    async def update_progress(
        self,
        task_id: str,
        progress: float,
        message: str = "",
    ) -> None:
        """
        更新任务进度（由任务函数内部调用）

        Args:
            task_id: 任务 ID
            progress: 进度 0.0 ~ 1.0
            message: 进度描述
        """
        task = self._tasks.get(task_id)
        if not task:
            return
        task.progress = min(max(progress, 0.0), 1.0)
        if message:
            task.progress_message = message
        await self._emit_progress(task, message)

    async def _emit_progress(self, task: BackgroundTask, message: str) -> None:
        if self.on_progress_event:
            try:
                await self.on_progress_event(
                    "background_task_progress",
                    {
                        "task_id": task.task_id,
                        "name": task.name,
                        "status": task.status.value,
                        "progress": task.progress,
                        "message": message,
                        "elapsed_ms": task.elapsed_ms,
                    },
                )
            except Exception as e:
                logger.debug(f"进度事件发送失败: {e}")

    # ================================================================
    # 查询 & 管理
    # ================================================================

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        return self._tasks.get(task_id)

    def get_user_tasks(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
    ) -> List[BackgroundTask]:
        tasks = [t for t in self._tasks.values() if t.user_id == user_id]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def get_active_tasks(self) -> List[BackgroundTask]:
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)
        ]

    async def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or not task._asyncio_task:
            return False
        if task.status not in (TaskStatus.QUEUED, TaskStatus.RUNNING):
            return False
        task._asyncio_task.cancel()
        return True

    def cleanup_completed(self, max_age_seconds: int = 3600) -> int:
        """清理已完成超过指定时间的任务"""
        now = time.time()
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            and t.completed_at
            and (now - t.completed_at) > max_age_seconds
        ]
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)


# ================================================================
# 便捷函数
# ================================================================


def create_background_task_manager(
    on_notify: Optional[NotifyFn] = None,
    on_progress_event: Optional[ProgressEventFn] = None,
    max_concurrent: int = 5,
) -> BackgroundTaskManager:
    """创建后台任务管理器"""
    return BackgroundTaskManager(
        on_notify=on_notify,
        on_progress_event=on_progress_event,
        max_concurrent=max_concurrent,
    )


# ================================================================
# 全局单例（供 core 层和 services 层统一获取）
# ================================================================

_global_manager: Optional[BackgroundTaskManager] = None


def get_global_bg_manager() -> Optional[BackgroundTaskManager]:
    """获取全局 BackgroundTaskManager 单例（未初始化时返回 None）"""
    return _global_manager


def init_global_bg_manager(
    on_notify: Optional[NotifyFn] = None,
    on_progress_event: Optional[ProgressEventFn] = None,
    max_concurrent: int = 5,
) -> BackgroundTaskManager:
    """初始化全局 BackgroundTaskManager 单例（幂等，重复调用返回已有实例）"""
    global _global_manager
    if _global_manager is None:
        _global_manager = create_background_task_manager(
            on_notify=on_notify,
            on_progress_event=on_progress_event,
            max_concurrent=max_concurrent,
        )
        logger.info("📋 全局 BackgroundTaskManager 已初始化")
    return _global_manager
