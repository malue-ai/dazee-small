"""
User Task Scheduler - 用户定时任务调度器

基于 APScheduler 的事件驱动调度（替代轮询模式）。

职责：
- 启动时从数据库加载活跃任务，注册到 APScheduler
- 动态添加/移除任务（创建、取消时实时生效）
- 执行任务动作（发送消息、执行 Agent 任务等）
- 执行后更新数据库状态，自动重新调度 cron/interval 任务

与系统级 TaskScheduler 的区别：
- TaskScheduler: 系统级后台任务（如 Mem0 批量更新），配置来自 YAML
- UserTaskScheduler: 用户通过 AI 创建的定时任务，数据来自 SQLite
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("services.user_task_scheduler")


class UserTaskScheduler:
    """
    用户定时任务调度器（APScheduler 事件驱动）

    每个用户任务注册为一个独立的 APScheduler Job，
    到 next_run_at 时刻精准触发，无需轮询。

    使用方式:
        scheduler = UserTaskScheduler()
        await scheduler.start()
        # ... 应用运行 ...
        await scheduler.shutdown()
    """

    def __init__(self):
        self._running = False
        self._scheduler = None
        self._workspace = None

    async def start(self):
        """启动调度器：创建 APScheduler 实例并加载活跃任务"""
        if self._running:
            logger.warning("用户任务调度器已在运行")
            return

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError:
            logger.warning(
                "APScheduler 未安装，用户任务调度不可用。"
                "安装: pip install apscheduler"
            )
            return

        # 获取 Workspace（从环境变量读取当前实例名）
        import os
        from infra.local_store import get_workspace

        instance_name = os.getenv("AGENT_INSTANCE", "default")
        self._workspace = await get_workspace(instance_name)

        # 创建并启动调度器
        self._scheduler = AsyncIOScheduler()

        # 添加错误监听器：捕获 job 执行异常和 missed job
        from apscheduler.events import (
            EVENT_JOB_ERROR,
            EVENT_JOB_EXECUTED,
            EVENT_JOB_MISSED,
        )

        self._scheduler.add_listener(self._on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)

        self._scheduler.start()
        self._running = True

        # 从数据库加载活跃任务
        loaded = await self._load_active_tasks()
        logger.info(f"✅ 用户任务调度器已启动（{loaded} 个活跃任务, instance={instance_name}）")

    def _on_job_event(self, event):
        """APScheduler job 事件监听器"""
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED

        if event.code == EVENT_JOB_ERROR:
            logger.error(
                f"❌ [Scheduler] Job 执行异常: job_id={event.job_id}, "
                f"error={event.exception}",
                exc_info=event.traceback,
            )
        elif event.code == EVENT_JOB_MISSED:
            logger.warning(f"⚠️ [Scheduler] Job 被跳过（错过执行时间）: job_id={event.job_id}")
        else:
            logger.info(f"✅ [Scheduler] Job 执行完成: job_id={event.job_id}")

    async def shutdown(self):
        """关闭调度器"""
        if not self._running:
            return

        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

        self._running = False
        logger.info("用户任务调度器已关闭")

    def is_running(self) -> bool:
        """调度器是否在运行"""
        return self._running

    # ==================== 任务注册 ====================

    async def _load_active_tasks(self) -> int:
        """启动时从数据库加载所有活跃任务并注册到 APScheduler"""
        if not self._workspace or not self._workspace.is_running:
            return 0

        try:
            from sqlalchemy import select

            from infra.local_store.models import LocalScheduledTask

            async with self._workspace._session_factory() as session:
                result = await session.execute(
                    select(LocalScheduledTask).where(
                        LocalScheduledTask.status == "active",
                        LocalScheduledTask.next_run_at.isnot(None),
                    )
                )
                active_tasks = list(result.scalars().all())

                count = 0
                for task in active_tasks:
                    if self._register_job(task):
                        count += 1

                return count

        except Exception as e:
            logger.error(f"加载活跃任务失败: {e}", exc_info=True)
            return 0

    def _register_job(self, task) -> bool:
        """
        将一个任务注册到 APScheduler

        策略：统一使用 DateTrigger(next_run_at)，在执行后由
        _execute_and_reschedule 根据 trigger_type 重新调度。
        """
        if not self._scheduler:
            logger.warning(f"⚠️ [Scheduler] 调度器未初始化，无法注册任务: id={task.id}")
            return False

        if not self._scheduler.running:
            logger.warning(f"⚠️ [Scheduler] 调度器未运行，无法注册任务: id={task.id}")
            return False

        from apscheduler.triggers.date import DateTrigger

        job_id = f"user_task_{task.id}"

        try:
            # 移除已有的同 ID Job（避免重复）
            existing = self._scheduler.get_job(job_id)
            if existing:
                self._scheduler.remove_job(job_id)
                logger.info(f"♻️ [Scheduler] 移除旧 Job: {job_id}")

            # 计算触发时间
            now = datetime.now()
            run_at = task.next_run_at

            if not run_at:
                logger.warning(f"⚠️ [Scheduler] 任务无 next_run_at，跳过注册: id={task.id}")
                return False

            # 处理 timezone-aware datetime：统一转为 naive（本地时间）
            if hasattr(run_at, 'tzinfo') and run_at.tzinfo is not None:
                run_at = run_at.replace(tzinfo=None)
                logger.info(
                    f"🔄 [Scheduler] 时区转换: 原始={task.next_run_at} → naive={run_at}"
                )

            # 已过期的任务立即执行（延迟 2 秒避免调度竞争）
            if run_at <= now:
                from datetime import timedelta
                old_run_at = run_at
                run_at = now + timedelta(seconds=2)
                logger.info(
                    f"⏩ [Scheduler] 任务已过期，立即调度: id={task.id}, "
                    f"原定={old_run_at:%H:%M:%S} → 改为={run_at:%H:%M:%S}"
                )

            self._scheduler.add_job(
                self._execute_and_reschedule,
                trigger=DateTrigger(run_date=run_at),
                args=[task.id],
                id=job_id,
                name=task.title or task.id,
                replace_existing=True,
            )

            # 验证注册成功
            registered_job = self._scheduler.get_job(job_id)
            if registered_job:
                logger.info(
                    f"✅ [Scheduler] 任务已注册到 APScheduler: "
                    f"id={task.id}, title={task.title}, "
                    f"trigger={task.trigger_type}, "
                    f"fire_at={run_at:%Y-%m-%d %H:%M:%S}, "
                    f"job_id={job_id}"
                )
            else:
                logger.error(f"❌ [Scheduler] 注册后验证失败，Job 不存在: {job_id}")
                return False

            return True

        except Exception as e:
            logger.error(f"❌ [Scheduler] 注册任务失败: id={task.id}, error={e}", exc_info=True)
            return False

    async def register_task(self, task) -> bool:
        """
        动态注册新任务

        在 scheduled_task_tool 创建任务后调用，
        使新任务立即加入调度（无需等待轮询）。
        """
        if not self._running:
            logger.warning(
                f"⚠️ [Scheduler] 调度器未运行，无法注册任务: "
                f"id={task.id}, title={task.title}"
            )
            return False

        result = self._register_job(task)
        if result:
            self._log_scheduler_status()
        return result

    async def unregister_task(self, task_id: str) -> bool:
        """
        移除任务

        在取消/删除任务时调用，立即停止调度。
        """
        if not self._scheduler:
            return False

        job_id = f"user_task_{task_id}"
        try:
            if self._scheduler.get_job(job_id):
                self._scheduler.remove_job(job_id)
                logger.info(f"🗑️ [Scheduler] 已移除任务: id={task_id}")
            return True
        except Exception as e:
            logger.error(f"❌ [Scheduler] 移除任务失败: id={task_id}, error={e}", exc_info=True)
            return False

    def _log_scheduler_status(self):
        """Log current scheduler status for debugging."""
        if not self._scheduler:
            return
        jobs = self._scheduler.get_jobs()
        job_info = [f"{j.id}(next={j.next_run_time})" for j in jobs]
        logger.info(f"📊 [Scheduler] 当前 Jobs: {len(jobs)} 个 → {job_info}")

    # ==================== 任务执行 ====================

    async def _execute_and_reschedule(self, task_id: str):
        """执行任务，然后根据 trigger_type 决定是否重新调度"""
        logger.info(f"🔔 [Scheduler] 任务触发: task_id={task_id}")

        if not self._workspace or not self._workspace.is_running:
            logger.error(
                f"❌ [Scheduler] Workspace 不可用，无法执行任务: "
                f"task_id={task_id}, workspace={self._workspace}, "
                f"is_running={self._workspace.is_running if self._workspace else 'N/A'}"
            )
            return

        from infra.local_store.crud.scheduled_task import (
            get_scheduled_task,
            mark_task_executed,
        )

        async with self._workspace._session_factory() as session:
            task = await get_scheduled_task(session, task_id)

            if not task:
                logger.warning(f"⚠️ [Scheduler] 任务不存在: task_id={task_id}")
                return

            if task.status != "active":
                logger.info(f"⏭️ [Scheduler] 任务非活跃状态，跳过: task_id={task_id}, status={task.status}")
                return

            try:
                logger.info(
                    f"🚀 [Scheduler] 开始执行任务: id={task.id}, "
                    f"title={task.title}, trigger={task.trigger_type}"
                )

                await self._execute_task(task)

                # 更新数据库（run_count++, 计算 next_run_at, 单次任务标记完成）
                await mark_task_executed(session, task.id)

                # 刷新任务状态
                await session.refresh(task)

                logger.info(
                    f"✅ [Scheduler] 任务执行完成: id={task.id}, "
                    f"run_count={task.run_count}, status={task.status}"
                )

                # cron / interval 任务需要重新调度
                if task.status == "active" and task.next_run_at:
                    logger.info(f"🔄 [Scheduler] 重新调度: id={task.id}, next_run={task.next_run_at}")
                    self._register_job(task)

            except Exception as e:
                logger.error(
                    f"❌ [Scheduler] 执行任务失败: task_id={task_id}, error={e}",
                    exc_info=True,
                )

    async def _execute_task(self, task):
        """执行单个任务"""
        action = task.action
        action_type = action.get("type", "send_message")

        logger.info(f"执行用户任务: id={task.id}, title={task.title}, action={action_type}")

        if action_type == "send_message":
            await self._action_send_message(task, action)
        elif action_type == "agent_task":
            await self._action_agent_task(task, action)
        else:
            logger.warning(f"未知的动作类型: {action_type}")

    async def _action_send_message(self, task, action: Dict[str, Any]):
        """发送消息动作：将提醒消息存储到数据库"""
        content = action.get("content", "定时提醒")
        user_id = task.user_id
        conversation_id = task.conversation_id

        try:
            if conversation_id and self._workspace:
                await self._workspace.create_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=[
                        {
                            "type": "text",
                            "text": f"⏰ **定时提醒**\n\n{content}",
                        }
                    ],
                    metadata={
                        "type": "scheduled_reminder",
                        "task_id": task.id,
                        "task_title": task.title,
                    },
                )
                logger.info(f"提醒消息已存储: task_id={task.id}")
            elif self._workspace:
                # 没有关联会话，创建新会话
                conv = await self._workspace.create_conversation(
                    user_id=user_id,
                    title=f"定时提醒: {task.title}",
                    metadata={"source": "scheduled_task", "task_id": task.id},
                )
                await self._workspace.create_message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=[
                        {
                            "type": "text",
                            "text": f"⏰ **定时提醒**\n\n{content}",
                        }
                    ],
                    metadata={
                        "type": "scheduled_reminder",
                        "task_id": task.id,
                        "task_title": task.title,
                    },
                )
                logger.info(f"提醒消息已存储到新会话: task_id={task.id}, conv_id={conv.id}")

        except Exception as e:
            logger.warning(f"存储提醒消息失败: {e}")

    async def _action_agent_task(self, task, action: Dict[str, Any]):
        """执行 Agent 任务动作"""
        prompt = action.get("prompt", "")
        user_id = task.user_id
        conversation_id = task.conversation_id

        if not prompt:
            logger.warning(f"Agent 任务缺少 prompt: task_id={task.id}")
            return

        logger.info(f"执行 Agent 任务: task_id={task.id}, prompt={prompt[:50]}...")

        try:
            from services.chat_service import get_chat_service

            chat_service = get_chat_service()

            if not conversation_id and self._workspace:
                conv = await self._workspace.create_conversation(
                    user_id=user_id,
                    title=f"定时任务: {task.title}",
                    metadata={"source": "scheduled_task", "task_id": task.id},
                )
                conversation_id = conv.id

            await chat_service.process_scheduled_task(
                user_id=user_id,
                conversation_id=conversation_id,
                prompt=prompt,
                task_id=task.id,
            )

            logger.info(f"Agent 任务执行完成: task_id={task.id}")

        except Exception as e:
            logger.error(
                f"Agent 任务执行失败: task_id={task.id}, error={e}",
                exc_info=True,
            )


# ==================== 全局实例 ====================

_user_task_scheduler: Optional[UserTaskScheduler] = None


def get_user_task_scheduler() -> UserTaskScheduler:
    """获取用户任务调度器单例"""
    global _user_task_scheduler
    if _user_task_scheduler is None:
        _user_task_scheduler = UserTaskScheduler()
    return _user_task_scheduler


async def start_user_task_scheduler():
    """启动用户任务调度器"""
    scheduler = get_user_task_scheduler()
    await scheduler.start()
    return scheduler


async def stop_user_task_scheduler():
    """停止用户任务调度器"""
    scheduler = get_user_task_scheduler()
    await scheduler.shutdown()
