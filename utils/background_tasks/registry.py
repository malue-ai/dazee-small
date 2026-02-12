"""
任务注册表 - 自动注册后台任务

设计原则：
- 使用装饰器 @background_task("task_name") 自动注册任务
- 任务函数签名统一为 async def task_func(ctx: TaskContext, service: BackgroundTaskService)
- 新增任务只需创建文件并使用装饰器，无需手动注册
"""

from typing import TYPE_CHECKING, Awaitable, Callable, Dict

from logger import get_logger

if TYPE_CHECKING:
    from .context import TaskContext
    from .service import BackgroundTaskService

logger = get_logger("background_tasks.registry")

# 全局任务注册表
_TASK_REGISTRY: Dict[str, Callable[["TaskContext", "BackgroundTaskService"], Awaitable[None]]] = {}


def background_task(name: str):
    """
    后台任务装饰器 - 自动注册任务

    使用方式：
        @background_task("title_generation")
        async def generate_title(ctx: TaskContext, service: BackgroundTaskService):
            ...

    Args:
        name: 任务名称（用于 dispatch_tasks 时指定）
    """

    def decorator(func: Callable[["TaskContext", "BackgroundTaskService"], Awaitable[None]]):
        if name in _TASK_REGISTRY:
            logger.warning(f"⚠️ 后台任务重复注册: {name}，将覆盖原有任务")

        _TASK_REGISTRY[name] = func
        logger.debug(f"✅ 后台任务已注册: {name}")
        return func

    return decorator


def get_task_registry() -> Dict[str, Callable]:
    """获取任务注册表"""
    return _TASK_REGISTRY


def get_registered_task_names() -> list:
    """获取所有已注册的任务名称"""
    return list(_TASK_REGISTRY.keys())
