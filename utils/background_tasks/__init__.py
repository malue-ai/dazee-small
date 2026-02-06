"""
后台任务模块 - Background Tasks

提供统一的后台任务管理：
- 自动注册任务（使用 @background_task 装饰器）
- 统一调度（dispatch_tasks）
- 任务上下文（TaskContext）

使用方式：
    from utils.background_tasks import (
        BackgroundTaskService,
        get_background_task_service,
        TaskContext,
        background_task,
    )

    # 统一调度
    service = get_background_task_service()
    await service.dispatch_tasks(
        task_names=["title_generation", "recommended_questions"],
        context=TaskContext(...)
    )

新增任务只需：
1. 在 tasks/ 目录下创建新文件
2. 使用 @background_task("task_name") 装饰器标记任务函数
"""

# 再导入 tasks（触发自动注册）
from . import tasks

# 最后导入 service 和 context
from .context import (
    Mem0BatchUpdateResult,
    Mem0UpdateResult,
    TaskContext,
)

# 先导入 registry（装饰器）
from .registry import (
    background_task,
    get_registered_task_names,
    get_task_registry,
)
from .scheduler import (
    ScheduledTaskConfig,
    TaskScheduler,
    get_scheduler,
)
from .service import (
    BackgroundTaskService,
    get_background_task_service,
)

# 导出任务函数（供外部直接调用）
from .tasks.mem0_update import (
    batch_update_all_memories,
    update_user_memories,
)

__all__ = [
    # Service
    "BackgroundTaskService",
    "get_background_task_service",
    # Context
    "TaskContext",
    "Mem0UpdateResult",
    "Mem0BatchUpdateResult",
    # Registry
    "background_task",
    "get_task_registry",
    "get_registered_task_names",
    # Scheduler
    "TaskScheduler",
    "get_scheduler",
    "ScheduledTaskConfig",
    # Task Functions（直接调用）
    "update_user_memories",
    "batch_update_all_memories",
]
