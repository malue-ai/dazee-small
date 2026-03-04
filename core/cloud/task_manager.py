"""
云端任务管理器

在本地 SQLite 中管理云端委托任务的生命周期。
不依赖云端提供 task 管理能力——所有状态在本地维护。
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cloud.models import LocalCloudTask
from logger import get_logger

logger = get_logger(__name__)

VALID_STATUSES = {"created", "streaming", "completed", "failed", "canceled"}
TERMINAL_STATUSES = {"completed", "failed", "canceled"}


class CloudTaskManager:
    """本地云端任务管理器"""

    async def create_task(
        self,
        session: AsyncSession,
        task_description: str,
        user_id: str = "local_agent",
    ) -> LocalCloudTask:
        task = LocalCloudTask(
            id=f"ct_{uuid.uuid4().hex[:24]}",
            user_id=user_id,
            status="created",
            task_description=task_description[:2000],
            created_at=datetime.utcnow(),
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        logger.info("云端任务已创建: %s", task.id)
        return task

    async def update_status(
        self,
        session: AsyncSession,
        task_id: str,
        status: str,
        *,
        result_summary: Optional[str] = None,
        error_message: Optional[str] = None,
        cloud_conversation_id: Optional[str] = None,
    ) -> Optional[LocalCloudTask]:
        if status not in VALID_STATUSES:
            logger.warning("无效的任务状态: %s", status)
            return None

        task = await session.get(LocalCloudTask, task_id)
        if not task:
            logger.warning("任务不存在: %s", task_id)
            return None

        if task.status in TERMINAL_STATUSES:
            logger.debug("任务已终态(%s)，忽略状态更新: %s -> %s", task.status, task.status, status)
            return task

        task.status = status
        if result_summary is not None:
            task.result_summary = result_summary[:5000]
        if error_message is not None:
            task.error_message = error_message[:2000]
        if cloud_conversation_id is not None:
            task.cloud_conversation_id = cloud_conversation_id
        if status in TERMINAL_STATUSES:
            task.completed_at = datetime.utcnow()

        await session.commit()
        await session.refresh(task)
        return task

    async def add_progress_step(
        self,
        session: AsyncSession,
        task_id: str,
        step: Dict[str, Any],
    ) -> Optional[LocalCloudTask]:
        task = await session.get(LocalCloudTask, task_id)
        if not task:
            return None

        task.add_progress_step(step)
        await session.commit()
        await session.refresh(task)
        return task

    async def get_task(
        self,
        session: AsyncSession,
        task_id: str,
    ) -> Optional[LocalCloudTask]:
        return await session.get(LocalCloudTask, task_id)

    async def list_active_tasks(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None,
    ) -> List[LocalCloudTask]:
        stmt = select(LocalCloudTask).where(
            LocalCloudTask.status.notin_(list(TERMINAL_STATUSES))
        ).order_by(LocalCloudTask.created_at.desc())

        if user_id:
            stmt = stmt.where(LocalCloudTask.user_id == user_id)

        result = await session.execute(stmt)
        return list(result.scalars().all())
