"""
Dazee Mem0 增强数据结构

导出所有 Schema 定义，支持碎片记忆、行为模式、PDCA 计划、情绪状态和用户画像
"""

# 碎片记忆
from .fragment import (
    FragmentMemory,
    TaskHint,
    TimeHint,
    EmotionHint,
    RelationHint,
    TodoHint,
    PreferenceHint,
    TopicHint,
    ConstraintHint,
    ToolHint,
    GoalHint,
    TimeSlot,
    DayOfWeek,
    MemoryType,
    MemorySource,
    MemoryVisibility,
)

# 行为模式（5W1H）
from .behavior import (
    BehaviorPattern,
    DateRange,
    RoutineTask,
    TimePattern,
    WorkContext,
    Collaborator,
    Motivation,
    WorkStyle,
    PreferenceStability,
    PeriodicityAnalysis,
    ConflictDetection,
)

# PDCA 工作计划
from .plan import (
    WorkPlan,
    TodoItem,
    Checkpoint,
    Blocker,
    Reminder,
    ReminderItem,
    ReminderType,
    CheckResult,
    ActionItem,
    Priority,
    TodoStatus,
    PlanStatus,
    PDCAPhase,
)

# 情绪状态
from .emotion import (
    EmotionState,
    EmotionSignal,
    EmotionTrend,
)

# 用户画像
from .persona import (
    UserPersona,
    PlanSummary,
    ReminderSummary,
)

# 显式记忆
from .explicit_memory import (
    MemoryCard,
    MemoryCardCategory,
)


__all__ = [
    # Fragment
    "FragmentMemory",
    "TaskHint",
    "TimeHint",
    "EmotionHint",
    "RelationHint",
    "TodoHint",
    "PreferenceHint",
    "TopicHint",
    "ConstraintHint",
    "ToolHint",
    "GoalHint",
    "TimeSlot",
    "DayOfWeek",
    "MemoryType",
    "MemorySource",
    "MemoryVisibility",
    # Behavior
    "BehaviorPattern",
    "DateRange",
    "RoutineTask",
    "TimePattern",
    "WorkContext",
    "Collaborator",
    "Motivation",
    "WorkStyle",
    "PreferenceStability",
    "PeriodicityAnalysis",
    "ConflictDetection",
    # Plan
    "WorkPlan",
    "TodoItem",
    "Checkpoint",
    "Blocker",
    "Reminder",
    "ReminderItem",
    "ReminderType",
    "CheckResult",
    "ActionItem",
    "Priority",
    "TodoStatus",
    "PlanStatus",
    "PDCAPhase",
    # Emotion
    "EmotionState",
    "EmotionSignal",
    "EmotionTrend",
    # Persona
    "UserPersona",
    "PlanSummary",
    "ReminderSummary",
    # Explicit Memory
    "MemoryCard",
    "MemoryCardCategory",
]
