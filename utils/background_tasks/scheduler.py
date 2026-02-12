"""
定时任务调度器 - Task Scheduler

基于 APScheduler 实现的轻量级定时任务调度器

特点：
- 内置在应用中，无需外部依赖（如 Celery）
- 支持 cron 表达式和间隔执行
- 与 FastAPI lifespan 集成
- 任务配置从 YAML 文件读取

使用方式：
    from utils.background_tasks.scheduler import get_scheduler

    scheduler = get_scheduler()
    await scheduler.start()
    # ... 应用运行 ...
    await scheduler.shutdown()
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml

from logger import get_logger

from .context import TaskContext
from .registry import get_registered_task_names, get_task_registry
from .service import BackgroundTaskService, get_background_task_service
from .tasks.mem0_update import batch_update_all_memories

logger = get_logger("background_tasks.scheduler")


@dataclass
class ScheduledTaskConfig:
    """定时任务配置"""

    task_name: str
    enabled: bool = True
    trigger_type: str = "cron"  # cron / interval

    # cron 触发配置
    cron: Optional[str] = None  # cron 表达式，如 "0 2 * * *"

    # interval 触发配置（秒）
    interval_seconds: Optional[int] = None

    # 任务参数
    params: Dict[str, Any] = field(default_factory=dict)

    # 描述
    description: str = ""


class TaskScheduler:
    """
    定时任务调度器

    支持两种触发方式：
    - cron: 基于 cron 表达式（如 "0 2 * * *" 表示每天凌晨 2 点）
    - interval: 固定间隔（如每 3600 秒）
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化调度器

        Args:
            config_path: 配置文件路径，默认为 config/scheduled_tasks.yaml
        """
        from utils.app_paths import get_bundle_dir
        self.config_path = config_path or str(
            get_bundle_dir() / "config" / "scheduled_tasks.yaml"
        )
        self.background_service = get_background_task_service()
        self._scheduler = None
        self._running = False
        self._tasks: Dict[str, ScheduledTaskConfig] = {}

    async def _load_config_async(self) -> List[ScheduledTaskConfig]:
        """异步加载配置文件"""
        config_path = Path(self.config_path)

        if not config_path.exists():
            logger.debug(f"定时任务配置文件不存在: {self.config_path}")
            return []

        try:
            async with aiofiles.open(config_path, "r", encoding="utf-8") as f:
                content = await f.read()
                config = yaml.safe_load(content) or {}

            tasks = []
            for task_config in config.get("scheduled_tasks", []):
                tasks.append(
                    ScheduledTaskConfig(
                        task_name=task_config.get("task_name"),
                        enabled=task_config.get("enabled", True),
                        trigger_type=task_config.get("trigger_type", "cron"),
                        cron=task_config.get("cron"),
                        interval_seconds=task_config.get("interval_seconds"),
                        params=task_config.get("params", {}),
                        description=task_config.get("description", ""),
                    )
                )

            return tasks

        except Exception as e:
            logger.error(f"加载定时任务配置失败: {e}", exc_info=True)
            return []

    async def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("调度器已在运行")
            return

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            logger.warning(
                "APScheduler 未安装，定时任务功能不可用。"
                "安装: pip install apscheduler"
            )
            return

        # 加载配置
        task_configs = await self._load_config_async()
        enabled_configs = [c for c in task_configs if c.enabled]

        if not enabled_configs:
            logger.info(f"系统定时任务调度器未启动（{len(task_configs)} 个配置均已禁用）")
            return

        # 创建调度器
        self._scheduler = AsyncIOScheduler()
        registered_names = get_registered_task_names()

        for config in enabled_configs:
            if config.task_name not in registered_names:
                logger.warning(f"定时任务未注册: {config.task_name}，跳过")
                continue

            # 创建触发器
            if config.trigger_type == "cron" and config.cron:
                trigger = CronTrigger.from_crontab(config.cron)
            elif config.trigger_type == "interval" and config.interval_seconds:
                trigger = IntervalTrigger(seconds=config.interval_seconds)
            else:
                logger.warning(f"定时任务配置无效: {config.task_name}，跳过")
                continue

            self._scheduler.add_job(
                self._run_scheduled_task,
                trigger=trigger,
                args=[config],
                id=config.task_name,
                name=config.description or config.task_name,
                replace_existing=True,
            )
            self._tasks[config.task_name] = config

        if self._tasks:
            self._scheduler.start()
            self._running = True
            task_names = ", ".join(self._tasks.keys())
            logger.info(f"系统定时任务调度器已启动（{len(self._tasks)} 个任务: {task_names}）")
        else:
            logger.info("系统定时任务调度器未启动（无有效任务）")

    async def shutdown(self, wait: bool = True):
        """关闭调度器"""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=wait)
            self._running = False
            logger.info("系统定时任务调度器已关闭")

    async def _run_scheduled_task(self, config: ScheduledTaskConfig):
        """执行定时任务"""
        task_name = config.task_name
        started_at = datetime.now()

        logger.info(f"执行系统定时任务: {task_name}")

        try:
            # 检查是否是批量任务
            if config.params.get("batch", False):
                # 批量任务（如 mem0_update 批量更新所有用户）
                result = await batch_update_all_memories(
                    since_hours=config.params.get("since_hours", 24),
                    max_concurrent=config.params.get("max_concurrent", 5),
                    service=self.background_service,
                )

                duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                logger.info(
                    f"系统定时任务完成: {task_name}, "
                    f"耗时={duration_ms}ms, "
                    f"成功={result.successful}, 失败={result.failed}"
                )
            else:
                # 单次任务
                context = TaskContext(
                    session_id=f"scheduled_{task_name}_{started_at.timestamp()}",
                    conversation_id="",
                    user_id=config.params.get("user_id", ""),
                    message_id="",
                    user_message="",
                    assistant_response="",
                    is_new_conversation=False,
                    metadata={
                        "trigger": "scheduled",
                        "scheduled_at": started_at.isoformat(),
                        **config.params,
                    },
                )

                registry = get_task_registry()
                task_func = registry[task_name]
                await task_func(context, self.background_service)

                duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                logger.info(f"系统定时任务完成: {task_name}, 耗时={duration_ms}ms")

        except Exception as e:
            logger.error(f"系统定时任务失败: {task_name}, error={e}", exc_info=True)

    def get_jobs(self) -> List[Dict[str, Any]]:
        """获取所有定时任务"""
        if not self._scheduler:
            return []

        jobs = []
        for job in self._scheduler.get_jobs():
            config = self._tasks.get(job.id)
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger_type": config.trigger_type if config else "unknown",
                    "cron": config.cron if config else None,
                    "interval_seconds": config.interval_seconds if config else None,
                }
            )

        return jobs

    def is_running(self) -> bool:
        """调度器是否在运行"""
        return self._running


# ==================== 便捷函数 ====================

_default_scheduler: Optional[TaskScheduler] = None


def get_scheduler(config_path: Optional[str] = None) -> TaskScheduler:
    """获取默认调度器单例"""
    global _default_scheduler
    if _default_scheduler is None:
        _default_scheduler = TaskScheduler(config_path)
    return _default_scheduler
