"""
Dazee Mem0 增强数据结构

导出所有 Schema 定义，支持碎片记忆、行为模式、PDCA 计划、情绪状态和用户画像
"""

# 行为模式（5W1H）
from .behavior import (
    BehaviorPattern,
    Collaborator,
    ConflictDetection,
    DateRange,
    Motivation,
    PeriodicityAnalysis,
    PreferenceStability,
    RoutineTask,
    TimePattern,
    WorkContext,
    WorkStyle,
)

# 情绪状态
from .emotion import (
    EmotionSignal,
    EmotionState,
    EmotionTrend,
)

# 显式记忆
from .explicit_memory import (
    MemoryCard,
    MemoryCardCategory,
)

# 碎片记忆
from .fragment import (
    ConstraintHint,
    DayOfWeek,
    EmotionHint,
    FragmentMemory,
    GoalHint,
    IdentityHint,
    MemorySource,
    MemoryType,
    MemoryVisibility,
    PreferenceHint,
    RelationHint,
    TaskHint,
    TimeHint,
    TimeSlot,
    TodoHint,
    ToolHint,
    TopicHint,
)

# 用户画像
from .persona import (
    PlanSummary,
    ReminderSummary,
    UserPersona,
)

# PDCA 工作计划
from .plan import (
    ActionItem,
    Blocker,
    Checkpoint,
    CheckResult,
    PDCAPhase,
    PlanStatus,
    Priority,
    ReminderItem,
    ReminderType,
    TodoItem,
    TodoStatus,
    WorkPlan,
)

__all__ = [
    # Fragment
    "FragmentMemory",
    "IdentityHint",
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
    "IdentityHint",
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
