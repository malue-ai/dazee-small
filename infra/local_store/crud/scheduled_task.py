"""
定时任务 CRUD 操作

提供用户定时任务的增删改查功能：
- 创建任务
- 查询任务列表
- 更新任务状态
- 取消/删除任务
- 获取待执行任务
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from croniter import croniter
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from logger import get_logger

from ..models import LocalScheduledTask

logger = get_logger("local_store.crud.scheduled_task")


# ==================== 创建任务 ====================


async def create_scheduled_task(
    session: AsyncSession,
    user_id: str,
    title: str,
    trigger_type: str,
    action: Dict[str, Any],
    run_at: Optional[datetime] = None,
    cron_expr: Optional[str] = None,
    interval_seconds: Optional[int] = None,
    description: Optional[str] = None,
    conversation_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> LocalScheduledTask:
    """
    创建定时任务

    Args:
        session: 数据库会话
        user_id: 用户 ID
        title: 任务标题
        trigger_type: 触发类型 (once / cron / interval)
        action: 动作配置
        run_at: 单次执行时间（trigger_type=once 时必填）
        cron_expr: Cron 表达式（trigger_type=cron 时必填）
        interval_seconds: 间隔秒数（trigger_type=interval 时必填）
        description: 任务描述
        conversation_id: 关联的会话 ID
        task_id: 自定义任务 ID（可选）

    Returns:
        创建的任务对象
    """
    task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"

    # 计算下次执行时间
    next_run_at = _calculate_next_run(trigger_type, run_at, cron_expr, interval_seconds)

    task = LocalScheduledTask(
        id=task_id,
        user_id=user_id,
        title=title,
        description=description,
        trigger_type=trigger_type,
        run_at=run_at,
        cron_expr=cron_expr,
        interval_seconds=interval_seconds,
        action_json="{}",  # 先设置默认值
        status="active",
        next_run_at=next_run_at,
        conversation_id=conversation_id,
    )
    # 使用 property setter 设置 action
    task.action = action

    session.add(task)
    await session.commit()

    # 强制 WAL checkpoint，确保数据对后续新 session/连接立即可见
    # SQLite WAL 模式下，已提交的数据可能仍在 WAL 文件中，
    # 新连接在特定时序下可能看不到（pool_size=1 场景下的边界条件）
    try:
        from sqlalchemy import text
        await session.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
    except Exception as e:
        logger.warning(f"⚠️ WAL checkpoint 失败（非致命）: {e}")

    await session.refresh(task)

    logger.info(f"✅ 创建定时任务: id={task_id}, title={title}, trigger={trigger_type}")

    return task


def _calculate_next_run(
    trigger_type: str,
    run_at: Optional[datetime] = None,
    cron_expr: Optional[str] = None,
    interval_seconds: Optional[int] = None,
) -> Optional[datetime]:
    """计算下次执行时间"""
    now = datetime.now()

    if trigger_type == "once" and run_at:
        return run_at

    if trigger_type == "cron" and cron_expr:
        try:
            cron = croniter(cron_expr, now)
            return cron.get_next(datetime)
        except Exception as e:
            logger.warning(f"⚠️ 解析 Cron 表达式失败: {cron_expr}, error={e}")
            return None

    if trigger_type == "interval" and interval_seconds:
        return now + timedelta(seconds=interval_seconds)

    return None


# ==================== 查询任务 ====================


async def get_scheduled_task(
    session: AsyncSession, task_id: str
) -> Optional[LocalScheduledTask]:
    """获取单个任务"""
    result = await session.execute(
        select(LocalScheduledTask).where(LocalScheduledTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def list_user_tasks(
    session: AsyncSession,
    user_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[LocalScheduledTask]:
    """
    获取用户的任务列表

    Args:
        session: 数据库会话
        user_id: 用户 ID
        status: 状态过滤（可选）
        limit: 返回数量
        offset: 偏移量

    Returns:
        任务列表
    """
    query = select(LocalScheduledTask).where(LocalScheduledTask.user_id == user_id)

    if status:
        query = query.where(LocalScheduledTask.status == status)

    query = query.order_by(LocalScheduledTask.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_pending_tasks(
    session: AsyncSession, before: Optional[datetime] = None, limit: int = 100
) -> List[LocalScheduledTask]:
    """
    获取待执行的任务（用于调度器轮询）

    Args:
        session: 数据库会话
        before: 截止时间（默认当前时间）
        limit: 返回数量

    Returns:
        待执行的任务列表
    """
    before = before or datetime.now()

    result = await session.execute(
        select(LocalScheduledTask)
        .where(
            and_(
                LocalScheduledTask.status == "active",
                LocalScheduledTask.next_run_at <= before,
                LocalScheduledTask.next_run_at.isnot(None),
            )
        )
        .order_by(LocalScheduledTask.next_run_at)
        .limit(limit)
    )

    return list(result.scalars().all())


# ==================== 更新任务 ====================


async def update_task_status(
    session: AsyncSession, task_id: str, status: str
) -> Optional[LocalScheduledTask]:
    """更新任务状态"""
    task = await get_scheduled_task(session, task_id)
    if not task:
        return None

    task.status = status
    task.updated_at = datetime.now()

    await session.commit()
    await session.refresh(task)

    logger.info(f"📝 更新任务状态: id={task_id}, status={status}")

    return task


async def update_task(
    session: AsyncSession,
    task_id: str,
    title: Optional[str] = None,
    trigger_type: Optional[str] = None,
    run_at: Optional[datetime] = None,
    cron_expr: Optional[str] = None,
    interval_seconds: Optional[int] = None,
    action: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
) -> Optional[LocalScheduledTask]:
    """
    更新任务配置

    Args:
        session: 数据库会话
        task_id: 任务 ID
        其他参数: 要更新的字段

    Returns:
        更新后的任务对象
    """
    task = await get_scheduled_task(session, task_id)
    if not task:
        return None

    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if trigger_type is not None:
        task.trigger_type = trigger_type
    if run_at is not None:
        task.run_at = run_at
    if cron_expr is not None:
        task.cron_expr = cron_expr
    if interval_seconds is not None:
        task.interval_seconds = interval_seconds
    if action is not None:
        task.action = action

    # 重新计算下次执行时间
    task.next_run_at = _calculate_next_run(
        task.trigger_type, task.run_at, task.cron_expr, task.interval_seconds
    )
    task.updated_at = datetime.now()

    await session.commit()
    await session.refresh(task)

    logger.info(f"📝 更新任务配置: id={task_id}")

    return task


async def mark_task_executed(
    session: AsyncSession, task_id: str
) -> Optional[LocalScheduledTask]:
    """
    标记任务已执行（更新执行记录和下次执行时间）

    Args:
        session: 数据库会话
        task_id: 任务 ID

    Returns:
        更新后的任务对象
    """
    task = await get_scheduled_task(session, task_id)
    if not task:
        return None

    now = datetime.now()
    task.last_run_at = now
    task.run_count += 1
    task.updated_at = now

    # 计算下次执行时间
    if task.trigger_type == "once":
        # 单次任务执行后标记为完成
        task.status = "completed"
        task.next_run_at = None
    elif task.trigger_type == "cron" and task.cron_expr:
        try:
            cron = croniter(task.cron_expr, now)
            task.next_run_at = cron.get_next(datetime)
        except Exception:
            task.next_run_at = None
    elif task.trigger_type == "interval" and task.interval_seconds:
        task.next_run_at = now + timedelta(seconds=task.interval_seconds)

    await session.commit()
    await session.refresh(task)

    logger.debug(f"✓ 任务执行完成: id={task_id}, run_count={task.run_count}")

    return task


# ==================== 删除任务 ====================


async def cancel_task(
    session: AsyncSession, task_id: str, user_id: str
) -> bool:
    """
    取消任务（软删除，标记为 cancelled）

    Args:
        session: 数据库会话
        task_id: 任务 ID
        user_id: 用户 ID（用于权限校验）

    Returns:
        是否成功
    """
    task = await get_scheduled_task(session, task_id)
    if not task:
        return False

    # 权限校验
    if task.user_id != user_id:
        logger.warning(f"⚠️ 无权取消任务: task_id={task_id}, user_id={user_id}")
        return False

    task.status = "cancelled"
    task.next_run_at = None
    task.updated_at = datetime.now()

    await session.commit()

    logger.info(f"🛑 任务已取消: id={task_id}")

    return True


async def delete_task(
    session: AsyncSession, task_id: str, user_id: str
) -> bool:
    """
    删除任务（硬删除）

    Args:
        session: 数据库会话
        task_id: 任务 ID
        user_id: 用户 ID（用于权限校验）

    Returns:
        是否成功
    """
    task = await get_scheduled_task(session, task_id)
    if not task:
        return False

    # 权限校验
    if task.user_id != user_id:
        logger.warning(f"⚠️ 无权删除任务: task_id={task_id}, user_id={user_id}")
        return False

    await session.delete(task)
    await session.commit()

    logger.info(f"🗑️ 任务已删除: id={task_id}")

    return True


# ==================== 统计 ====================


async def count_user_tasks(
    session: AsyncSession, user_id: str, status: Optional[str] = None
) -> int:
    """统计用户任务数量"""
    from sqlalchemy import func

    query = select(func.count(LocalScheduledTask.id)).where(
        LocalScheduledTask.user_id == user_id
    )

    if status:
        query = query.where(LocalScheduledTask.status == status)

    result = await session.execute(query)
    return result.scalar() or 0
