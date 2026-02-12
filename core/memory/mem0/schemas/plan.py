"""
PDCA 工作计划数据结构

支持从对话中识别待办，并进行 Plan-Do-Check-Act 循环管理
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class Priority(str, Enum):
    """优先级"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TodoStatus(str, Enum):
    """待办状态"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PlanStatus(str, Enum):
    """计划状态"""

    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"
    BLOCKED = "blocked"
    AT_RISK = "at_risk"


class PDCAPhase(str, Enum):
    """PDCA 阶段"""

    PLAN = "plan"
    DO = "do"
    CHECK = "check"
    ACT = "act"


class ReminderType(str, Enum):
    """提醒类型"""

    DEADLINE = "deadline"  # 截止日期提醒
    PROGRESS_CHECK = "progress"  # 进度检查提醒
    HABIT = "habit"  # 习惯性提醒
    BLOCKER_FOLLOWUP = "blocker"  # 阻碍跟进提醒
    CUSTOM = "custom"  # 自定义提醒


@dataclass
class TodoItem:
    """待办事项"""

    id: str
    title: str
    status: TodoStatus = TodoStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    depends_on: List[str] = field(default_factory=list)  # 依赖的其他 todo id


@dataclass
class Checkpoint:
    """检查点"""

    date: datetime
    expected_progress: float  # 预期进度 0.0-1.0
    actual_progress: Optional[float] = None
    status: str = "pending"  # pending/passed/failed


@dataclass
class Blocker:
    """阻碍项"""

    id: str
    description: str
    owner: Optional[str] = None  # 负责人
    status: str = "waiting"  # waiting/resolved/escalated
    reported_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None


@dataclass
class ReminderItem:
    """
    提醒项

    支持多种提醒类型：截止日期、进度检查、习惯性提醒等
    """

    id: str
    user_id: str
    content: str
    reminder_type: ReminderType = ReminderType.CUSTOM
    time: datetime = field(default_factory=datetime.now)
    related_plan_id: Optional[str] = None
    repeat: Optional[str] = None  # daily/weekly/monthly
    priority: str = "medium"
    status: str = "pending"  # pending/triggered/dismissed
    created_at: datetime = field(default_factory=datetime.now)
    triggered_at: Optional[datetime] = None
    snooze_count: int = 0


@dataclass
class CheckResult:
    """Check 阶段检查结果"""

    plan_id: str
    checked_at: datetime
    completion_rate: float
    actual_result: str
    gaps: List[str] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)


@dataclass
class ActionItem:
    """Act 阶段行动项"""

    plan_id: str
    decision: str  # continue/adjust/close/restart
    action_taken: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class WorkPlan:
    """
    PDCA 工作计划

    从对话中自动识别并管理用户的工作计划
    """

    id: str
    user_id: str
    created_from: str = "conversation"  # conversation/manual

    # Plan - 计划
    title: str = ""
    description: str = ""
    deadline: Optional[datetime] = None
    priority: str = "medium"  # low/medium/high/urgent
    source_message: str = ""  # 来源对话
    source_timestamp: Optional[datetime] = None
    category: str = "general"  # 类别：report/ppt/code/meeting/general
    tags: List[str] = field(default_factory=list)
    estimated_hours: Optional[float] = None

    # Do - 执行
    todos: List[TodoItem] = field(default_factory=list)
    sub_tasks: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    progress: float = 0.0  # 0.0-1.0
    current_step: Optional[str] = None
    phase: PDCAPhase = PDCAPhase.PLAN
    started_at: Optional[datetime] = None

    # Check - 检查
    checkpoints: List[Checkpoint] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)  # 简化为字符串列表
    blocker_items: List[Blocker] = field(default_factory=list)
    risks: List[dict] = field(default_factory=list)  # {description, probability, impact}
    check_results: List[CheckResult] = field(default_factory=list)

    # Act - 行动
    reminders: List[ReminderItem] = field(default_factory=list)
    actions_taken: List[dict] = field(default_factory=list)  # {action, timestamp, result}
    action_history: List[ActionItem] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)

    # 元数据
    status: str = "active"  # active/completed/blocked/at_risk/cancelled
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_from": self.created_from,
            "plan": {
                "title": self.title,
                "description": self.description,
                "deadline": self.deadline.isoformat() if self.deadline else None,
                "priority": self.priority.value,
                "source_message": self.source_message,
                "source_timestamp": (
                    self.source_timestamp.isoformat() if self.source_timestamp else None
                ),
                "category": self.category,
                "tags": self.tags,
            },
            "do": {
                "todos": [
                    {
                        "id": todo.id,
                        "title": todo.title,
                        "status": todo.status.value,
                        "started_at": todo.started_at.isoformat() if todo.started_at else None,
                        "completed_at": (
                            todo.completed_at.isoformat() if todo.completed_at else None
                        ),
                        "depends_on": todo.depends_on,
                    }
                    for todo in self.todos
                ],
                "progress": self.progress,
                "current_step": self.current_step,
            },
            "check": {
                "checkpoints": [
                    {
                        "date": cp.date.isoformat(),
                        "expected_progress": cp.expected_progress,
                        "actual_progress": cp.actual_progress,
                        "status": cp.status,
                    }
                    for cp in self.checkpoints
                ],
                "blockers": [
                    {
                        "id": blocker.id,
                        "description": blocker.description,
                        "owner": blocker.owner,
                        "status": blocker.status,
                        "reported_at": blocker.reported_at.isoformat(),
                        "resolved_at": (
                            blocker.resolved_at.isoformat() if blocker.resolved_at else None
                        ),
                    }
                    for blocker in self.blockers
                ],
                "risks": self.risks,
            },
            "act": {
                "reminders": [
                    {
                        "id": reminder.id,
                        "type": reminder.type,
                        "trigger_time": reminder.trigger_time.isoformat(),
                        "message": reminder.message,
                        "status": reminder.status,
                        "sent_at": reminder.sent_at.isoformat() if reminder.sent_at else None,
                    }
                    for reminder in self.reminders
                ],
                "actions_taken": self.actions_taken,
                "lessons_learned": self.lessons_learned,
            },
            "metadata": {
                "status": self.status.value,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            },
        }
