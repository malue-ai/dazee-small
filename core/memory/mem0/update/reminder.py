"""
Dazee 智能提醒调度器

基于用户计划和行为模式，生成智能提醒
支持定时提醒、截止日期提醒、习惯性提醒
"""

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from logger import get_logger

from ..schemas import ReminderItem, ReminderType, WorkPlan

logger = get_logger("dazee.reminder")


class Reminder:
    """
    智能提醒调度器

    根据用户计划和行为模式生成提醒
    """

    def __init__(self) -> None:
        """初始化提醒调度器"""
        # 用户提醒存储（user_id -> List[ReminderItem]）
        self._user_reminders: Dict[str, List[ReminderItem]] = {}

        # 提醒回调（可注册外部通知服务）
        self._callbacks: List[Callable[[str, ReminderItem], None]] = []

        logger.info("[Reminder] 初始化完成")

    # ==================== 提醒管理 ====================

    def create_reminder(
        self,
        user_id: str,
        content: str,
        reminder_type: ReminderType,
        time: datetime,
        related_plan_id: Optional[str] = None,
        repeat: Optional[str] = None,
        priority: str = "medium",
    ) -> ReminderItem:
        """
        创建提醒

        Args:
            user_id: 用户 ID
            content: 提醒内容
            reminder_type: 提醒类型
            time: 提醒时间
            related_plan_id: 关联的计划 ID（可选）
            repeat: 重复规则（daily/weekly/monthly）
            priority: 优先级

        Returns:
            ReminderItem
        """
        reminder = ReminderItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            content=content,
            reminder_type=reminder_type,
            time=time,
            related_plan_id=related_plan_id,
            repeat=repeat,
            priority=priority,
            status="pending",
            created_at=datetime.now(),
        )

        self._add_reminder(user_id, reminder)

        logger.info(f"[Reminder] 创建提醒: user={user_id}, content={content[:30]}...")
        return reminder

    def create_deadline_reminder(
        self, user_id: str, plan: WorkPlan, advance_hours: int = 24
    ) -> Optional[ReminderItem]:
        """
        为计划创建截止日期提醒

        Args:
            user_id: 用户 ID
            plan: 工作计划
            advance_hours: 提前多少小时提醒

        Returns:
            ReminderItem 或 None（如果计划没有截止日期）
        """
        if not plan.deadline:
            return None

        reminder_time = plan.deadline - timedelta(hours=advance_hours)

        # 如果提醒时间已过，调整到当前时间后
        if reminder_time < datetime.now():
            reminder_time = datetime.now() + timedelta(minutes=30)

        content = (
            f"⏰ 「{plan.title}」即将到期，截止时间: {plan.deadline.strftime('%m月%d日 %H:%M')}"
        )

        return self.create_reminder(
            user_id=user_id,
            content=content,
            reminder_type=ReminderType.DEADLINE,
            time=reminder_time,
            related_plan_id=plan.id,
            priority="high" if advance_hours <= 24 else "medium",
        )

    def create_progress_reminder(
        self, user_id: str, plan: WorkPlan, check_interval_hours: int = 48
    ) -> ReminderItem:
        """
        为计划创建进度检查提醒

        Args:
            user_id: 用户 ID
            plan: 工作计划
            check_interval_hours: 检查间隔小时数

        Returns:
            ReminderItem
        """
        reminder_time = datetime.now() + timedelta(hours=check_interval_hours)

        content = f"📊 「{plan.title}」进度检查 - 当前进度 {int(plan.progress * 100)}%"

        return self.create_reminder(
            user_id=user_id,
            content=content,
            reminder_type=ReminderType.PROGRESS_CHECK,
            time=reminder_time,
            related_plan_id=plan.id,
            priority="medium",
        )

    def create_habit_reminder(
        self, user_id: str, content: str, time: datetime, repeat: str = "daily"
    ) -> ReminderItem:
        """
        创建习惯性提醒（如每日站会、周报等）

        Args:
            user_id: 用户 ID
            content: 提醒内容
            time: 提醒时间
            repeat: 重复规则（daily/weekly/monthly）

        Returns:
            ReminderItem
        """
        return self.create_reminder(
            user_id=user_id,
            content=content,
            reminder_type=ReminderType.HABIT,
            time=time,
            repeat=repeat,
            priority="low",
        )

    # ==================== 提醒触发 ====================

    def get_due_reminders(self, user_id: str, window_minutes: int = 5) -> List[ReminderItem]:
        """
        获取即将到期的提醒

        Args:
            user_id: 用户 ID
            window_minutes: 时间窗口（分钟）

        Returns:
            到期的 ReminderItem 列表
        """
        reminders = self._user_reminders.get(user_id, [])
        now = datetime.now()
        window = timedelta(minutes=window_minutes)

        due = [r for r in reminders if r.status == "pending" and r.time <= now + window]

        return sorted(due, key=lambda r: r.time)

    def trigger_reminder(self, user_id: str, reminder_id: str) -> Optional[ReminderItem]:
        """
        触发提醒

        Args:
            user_id: 用户 ID
            reminder_id: 提醒 ID

        Returns:
            触发的 ReminderItem
        """
        reminder = self._get_reminder(user_id, reminder_id)
        if not reminder:
            return None

        reminder.status = "triggered"
        reminder.triggered_at = datetime.now()

        # 调用回调
        for callback in self._callbacks:
            try:
                callback(user_id, reminder)
            except Exception as e:
                logger.error(f"[Reminder] 回调执行失败: {e}")

        # 处理重复提醒
        if reminder.repeat:
            self._schedule_next_repeat(user_id, reminder)

        logger.info(f"[Reminder] 触发提醒: user={user_id}, content={reminder.content[:30]}...")
        return reminder

    def dismiss_reminder(self, user_id: str, reminder_id: str) -> Optional[ReminderItem]:
        """
        关闭提醒

        Args:
            user_id: 用户 ID
            reminder_id: 提醒 ID

        Returns:
            关闭的 ReminderItem
        """
        reminder = self._get_reminder(user_id, reminder_id)
        if not reminder:
            return None

        reminder.status = "dismissed"

        logger.info(f"[Reminder] 关闭提醒: user={user_id}, id={reminder_id}")
        return reminder

    def snooze_reminder(
        self, user_id: str, reminder_id: str, snooze_minutes: int = 30
    ) -> Optional[ReminderItem]:
        """
        延后提醒

        Args:
            user_id: 用户 ID
            reminder_id: 提醒 ID
            snooze_minutes: 延后分钟数

        Returns:
            延后的 ReminderItem
        """
        reminder = self._get_reminder(user_id, reminder_id)
        if not reminder:
            return None

        reminder.time = datetime.now() + timedelta(minutes=snooze_minutes)
        reminder.status = "pending"
        reminder.snooze_count = getattr(reminder, "snooze_count", 0) + 1

        logger.info(
            f"[Reminder] 延后提醒: user={user_id}, id={reminder_id}, minutes={snooze_minutes}"
        )
        return reminder

    # ==================== 查询接口 ====================

    def get_user_reminders(
        self, user_id: str, status: Optional[str] = None, limit: int = 20
    ) -> List[ReminderItem]:
        """
        获取用户的提醒列表

        Args:
            user_id: 用户 ID
            status: 过滤状态（pending/triggered/dismissed）
            limit: 最大数量

        Returns:
            ReminderItem 列表
        """
        reminders = self._user_reminders.get(user_id, [])

        if status:
            reminders = [r for r in reminders if r.status == status]

        reminders.sort(key=lambda r: r.time)
        return reminders[:limit]

    def get_upcoming_reminders(self, user_id: str, hours: int = 24) -> List[ReminderItem]:
        """
        获取即将到来的提醒

        Args:
            user_id: 用户 ID
            hours: 未来多少小时内

        Returns:
            ReminderItem 列表
        """
        reminders = self._user_reminders.get(user_id, [])
        cutoff = datetime.now() + timedelta(hours=hours)

        upcoming = [r for r in reminders if r.status == "pending" and r.time <= cutoff]

        return sorted(upcoming, key=lambda r: r.time)

    # ==================== 回调注册 ====================

    def register_callback(self, callback: Callable[[str, ReminderItem], None]) -> None:
        """
        注册提醒回调

        当提醒触发时，会调用注册的回调函数

        Args:
            callback: 回调函数，接收 (user_id, reminder) 参数
        """
        self._callbacks.append(callback)
        logger.info(
            f"[Reminder] 注册回调: {callback.__name__ if hasattr(callback, '__name__') else 'anonymous'}"
        )

    # ==================== 内部方法 ====================

    def _add_reminder(self, user_id: str, reminder: ReminderItem) -> None:
        """添加提醒到存储"""
        if user_id not in self._user_reminders:
            self._user_reminders[user_id] = []
        self._user_reminders[user_id].append(reminder)

    def _get_reminder(self, user_id: str, reminder_id: str) -> Optional[ReminderItem]:
        """获取指定提醒"""
        reminders = self._user_reminders.get(user_id, [])
        for reminder in reminders:
            if reminder.id == reminder_id:
                return reminder
        return None

    def _schedule_next_repeat(self, user_id: str, reminder: ReminderItem) -> None:
        """安排下一次重复提醒"""
        if not reminder.repeat:
            return

        # 计算下一次时间
        if reminder.repeat == "daily":
            next_time = reminder.time + timedelta(days=1)
        elif reminder.repeat == "weekly":
            next_time = reminder.time + timedelta(weeks=1)
        elif reminder.repeat == "monthly":
            # 简单处理：加30天
            next_time = reminder.time + timedelta(days=30)
        else:
            return

        # 创建新提醒
        new_reminder = ReminderItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            content=reminder.content,
            reminder_type=reminder.reminder_type,
            time=next_time,
            related_plan_id=reminder.related_plan_id,
            repeat=reminder.repeat,
            priority=reminder.priority,
            status="pending",
            created_at=datetime.now(),
        )

        self._add_reminder(user_id, new_reminder)
        logger.debug(f"[Reminder] 安排重复提醒: next_time={next_time}")


# ==================== 工厂函数 ====================

_reminder_instance: Optional[Reminder] = None


def get_reminder() -> Reminder:
    """获取提醒调度器单例"""
    global _reminder_instance
    if _reminder_instance is None:
        _reminder_instance = Reminder()
    return _reminder_instance


def reset_reminder() -> None:
    """重置提醒调度器（用于测试）"""
    global _reminder_instance
    _reminder_instance = None
