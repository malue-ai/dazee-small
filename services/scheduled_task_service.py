"""
Scheduled Task Service

Business logic for scheduled task management (REST API layer).
Orchestrates CRUD operations and APScheduler synchronization.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from logger import get_logger

logger = get_logger(__name__)


def _get_instance_name() -> str:
    """Get current instance name from environment variable."""
    return os.getenv("AGENT_INSTANCE", "default")


async def list_tasks(
    user_id: str,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict], int]:
    """
    List user's scheduled tasks with pagination.

    Returns:
        (task_dicts, total_count)
    """
    from infra.local_store import get_workspace
    from infra.local_store.crud.scheduled_task import count_user_tasks, list_user_tasks

    workspace = await get_workspace(_get_instance_name())
    offset = (page - 1) * page_size

    async with workspace.session() as session:
        tasks = await list_user_tasks(
            session, user_id, status=status, limit=page_size, offset=offset
        )
        total = await count_user_tasks(session, user_id, status=status)

        # Convert ORM objects to dicts inside session scope
        task_dicts = [_task_to_dict(t) for t in tasks]

    return task_dicts, total


async def get_task(task_id: str, user_id: str) -> Optional[Dict]:
    """
    Get a single task by ID (with ownership check).

    Returns:
        Task dict or None if not found / not owned.
    """
    from infra.local_store import get_workspace
    from infra.local_store.crud.scheduled_task import get_scheduled_task

    workspace = await get_workspace(_get_instance_name())

    async with workspace.session() as session:
        task = await get_scheduled_task(session, task_id)
        if not task or task.user_id != user_id:
            return None
        return _task_to_dict(task)


async def pause_task(task_id: str, user_id: str) -> Optional[Dict]:
    """
    Pause an active task: DB status -> paused, remove from APScheduler.

    Returns:
        Updated task dict, or None on failure.
    """
    from infra.local_store import get_workspace
    from infra.local_store.crud.scheduled_task import get_scheduled_task

    workspace = await get_workspace(_get_instance_name())

    async with workspace.session() as session:
        task = await get_scheduled_task(session, task_id)
        if not task:
            return None
        if task.user_id != user_id:
            logger.warning(f"Unauthorized pause attempt: task_id={task_id}, user_id={user_id}")
            return None
        if task.status != "active":
            logger.warning(f"Cannot pause non-active task: task_id={task_id}, status={task.status}")
            return None

        task.status = "paused"
        task.updated_at = datetime.now()
        await session.commit()
        await session.refresh(task)
        result = _task_to_dict(task)

    # Remove from APScheduler
    await _unregister_from_scheduler(task_id)
    logger.info(f"Task paused: task_id={task_id}")

    return result


async def resume_task(task_id: str, user_id: str) -> Optional[Dict]:
    """
    Resume a paused task: DB status -> active, re-register in APScheduler.

    Returns:
        Updated task dict, or None on failure.
    """
    from infra.local_store import get_workspace
    from infra.local_store.crud.scheduled_task import get_scheduled_task

    workspace = await get_workspace(_get_instance_name())

    async with workspace.session() as session:
        task = await get_scheduled_task(session, task_id)
        if not task:
            return None
        if task.user_id != user_id:
            logger.warning(f"Unauthorized resume attempt: task_id={task_id}, user_id={user_id}")
            return None
        if task.status != "paused":
            logger.warning(f"Cannot resume non-paused task: task_id={task_id}, status={task.status}")
            return None

        # Recalculate next_run_at for cron/interval tasks
        from infra.local_store.crud.scheduled_task import _calculate_next_run

        next_run = _calculate_next_run(
            task.trigger_type, task.run_at, task.cron_expr, task.interval_seconds
        )

        task.status = "active"
        task.next_run_at = next_run
        task.updated_at = datetime.now()
        await session.commit()
        await session.refresh(task)
        result = _task_to_dict(task)

    # Re-register in APScheduler
    await _register_to_scheduler(task_id)
    logger.info(f"Task resumed: task_id={task_id}")

    return result


async def cancel_task(task_id: str, user_id: str) -> bool:
    """
    Cancel a task (soft delete): DB status -> cancelled, remove from APScheduler.
    """
    from infra.local_store import get_workspace
    from infra.local_store.crud.scheduled_task import cancel_task as crud_cancel

    workspace = await get_workspace(_get_instance_name())

    async with workspace.session() as session:
        success = await crud_cancel(session, task_id, user_id)

    if success:
        await _unregister_from_scheduler(task_id)
        logger.info(f"Task cancelled: task_id={task_id}")

    return success


async def delete_task(task_id: str, user_id: str) -> bool:
    """
    Delete a task (hard delete): remove from DB and APScheduler.
    """
    from infra.local_store import get_workspace
    from infra.local_store.crud.scheduled_task import delete_task as crud_delete

    workspace = await get_workspace(_get_instance_name())

    # Remove from scheduler first (before DB delete)
    await _unregister_from_scheduler(task_id)

    async with workspace.session() as session:
        success = await crud_delete(session, task_id, user_id)

    if success:
        logger.info(f"Task deleted: task_id={task_id}")

    return success


# ==================== Helper functions ====================


def _task_to_dict(task) -> Dict:
    """Convert ORM task object to a plain dict (safe outside session)."""
    return {
        "id": task.id,
        "user_id": task.user_id,
        "title": task.title,
        "description": task.description,
        "trigger_type": task.trigger_type,
        "run_at": task.run_at,
        "cron_expr": task.cron_expr,
        "interval_seconds": task.interval_seconds,
        "action": task.action,  # uses @property, JSON deserialized
        "status": task.status,
        "next_run_at": task.next_run_at,
        "last_run_at": task.last_run_at,
        "run_count": task.run_count,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "conversation_id": task.conversation_id,
    }


async def _unregister_from_scheduler(task_id: str) -> None:
    """Remove a task from the APScheduler (if running)."""
    try:
        from services.user_task_scheduler import get_user_task_scheduler

        scheduler = get_user_task_scheduler()
        if scheduler.is_running():
            await scheduler.unregister_task(task_id)
    except Exception as e:
        logger.warning(f"Failed to unregister task from scheduler: task_id={task_id}, error={e}")


async def _register_to_scheduler(task_id: str) -> None:
    """Register a task in the APScheduler (if running)."""
    try:
        from services.user_task_scheduler import get_user_task_scheduler

        scheduler = get_user_task_scheduler()
        if scheduler.is_running():
            await scheduler.register_task_by_id(task_id)
    except Exception as e:
        logger.warning(f"Failed to register task to scheduler: task_id={task_id}, error={e}")
