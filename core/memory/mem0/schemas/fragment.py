"""
碎片记忆数据结构

从单次对话中提取的碎片级记忆，包含任务、时间、情绪、关系等线索
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryType(str, Enum):
    """记忆类型枚举"""

    EXPLICIT = "explicit"  # 显式记忆：用户主动上传的记忆卡片
    IMPLICIT = "implicit"  # 隐式记忆：从对话中自动提取
    BEHAVIOR = "behavior"  # 行为模式：5W1H 分析结果
    EMOTION = "emotion"  # 情绪状态
    PREFERENCE = "preference"  # 用户偏好


class MemorySource(str, Enum):
    """记忆来源枚举"""

    USER_CARD = "user_card"  # 用户记忆卡片
    CONVERSATION = "conversation"  # 对话提取
    BEHAVIOR_ANALYSIS = "behavior_analysis"  # 行为分析
    EMOTION_ANALYSIS = "emotion_analysis"  # 情绪分析
    SYSTEM_INFERENCE = "system_inference"  # 系统推断
    INSTANCE_REMEMBER = "instance_remember"  # InstanceMemoryManager.remember() 写入


class MemoryVisibility(str, Enum):
    """记忆可见性枚举"""

    PUBLIC = "public"  # 完全可见（用于 Prompt 注入）
    PRIVATE = "private"  # 私有（不注入 Prompt，仅存储）
    FILTERED = "filtered"  # 过滤后可见（敏感信息已处理）


class TimeSlot(str, Enum):
    """时间段枚举"""

    MORNING = "morning"  # 06:00-12:00
    AFTERNOON = "afternoon"  # 12:00-18:00
    EVENING = "evening"  # 18:00-22:00
    NIGHT = "night"  # 22:00-06:00


class DayOfWeek(str, Enum):
    """星期枚举"""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


@dataclass
class TaskHint:
    """任务线索"""

    content: str  # 任务内容，如"客户反馈处理"
    category: str  # 任务类别，如"customer_support"
    confidence: float = 0.0  # 推断置信度 0.0-1.0


@dataclass
class TimeHint:
    """时间规律线索"""

    pattern: str  # 时间模式，如"early_morning_routine"
    inferred_schedule: Optional[str] = None  # 推断的时间段，如"09:00-10:00"
    confidence: float = 0.0


@dataclass
class EmotionHint:
    """情绪线索"""

    signal: str  # 情绪信号：neutral/positive/stressed/frustrated
    stress_level: float = 0.0  # 压力水平 0.0-1.0
    keywords_detected: List[str] = field(default_factory=list)  # 检测到的情绪关键词


@dataclass
class RelationHint:
    """关系线索"""

    mentioned: List[str] = field(default_factory=list)  # 提到的人，如["客户A", "老板"]
    relationship_type: Optional[str] = None  # 关系类型：colleague/supervisor/client


@dataclass
class TodoHint:
    """待办线索"""

    content: str  # 待办内容
    deadline: Optional[datetime] = None  # 截止时间
    priority: str = "medium"  # 优先级：low/medium/high
    confidence: float = 0.0


@dataclass
class PreferenceHint:
    """偏好线索"""

    response_format: Optional[str] = None  # 响应格式偏好：structured/concise/detailed
    communication_style: Optional[str] = None  # 沟通风格：formal/casual/professional
    preferred_tools: List[str] = field(default_factory=list)  # 偏好的工具/平台
    work_preferences: Dict[str, Any] = field(default_factory=dict)  # 其他工作偏好
    verbatim_preferences: List[str] = field(default_factory=list)  # 用户原话偏好摘录
    confidence: float = 0.0


@dataclass
class TopicHint:
    """主题与项目线索（新增）"""

    topics: List[str] = field(default_factory=list)  # 讨论的主题
    projects: List[str] = field(default_factory=list)  # 涉及的项目
    keywords: List[str] = field(default_factory=list)  # 关键词
    confidence: float = 0.0


@dataclass
class ConstraintHint:
    """约束与禁忌线索（新增）"""

    constraints: List[str] = field(default_factory=list)  # 约束条件（如：不能使用某个工具）
    taboos: List[str] = field(default_factory=list)  # 禁忌事项（如：不要提及某个话题）
    limitations: List[str] = field(default_factory=list)  # 限制条件
    confidence: float = 0.0


@dataclass
class ToolHint:
    """工具与平台线索（新增）"""

    tools_mentioned: List[str] = field(default_factory=list)  # 提到的工具
    platforms_mentioned: List[str] = field(default_factory=list)  # 提到的平台
    preferred_workflow: Optional[str] = None  # 偏好的工作流程
    confidence: float = 0.0


@dataclass
class GoalHint:
    """目标与风险信号线索（新增）"""

    goals: List[str] = field(default_factory=list)  # 提到的目标
    risks: List[str] = field(default_factory=list)  # 风险信号
    blockers: List[str] = field(default_factory=list)  # 阻碍因素
    achievements: List[str] = field(default_factory=list)  # 成就/成果
    confidence: float = 0.0


@dataclass
class FragmentMemory:
    """
    碎片记忆

    从单次对话中提取的原始碎片，包含各种隐性线索
    """

    id: str
    user_id: str
    session_id: str

    # 原始信息
    message: str
    timestamp: datetime
    time_slot: TimeSlot
    day_of_week: DayOfWeek

    # 提取的线索
    task_hint: Optional[TaskHint] = None
    time_hint: Optional[TimeHint] = None
    emotion_hint: Optional[EmotionHint] = None
    relation_hint: Optional[RelationHint] = None
    todo_hint: Optional[TodoHint] = None

    # 新增线索维度
    preference_hint: Optional[PreferenceHint] = None
    topic_hint: Optional[TopicHint] = None
    constraint_hint: Optional[ConstraintHint] = None
    tool_hint: Optional[ToolHint] = None
    goal_hint: Optional[GoalHint] = None

    # 记忆元数据（新增）
    memory_type: MemoryType = MemoryType.IMPLICIT  # 记忆类型
    source: MemorySource = MemorySource.CONVERSATION  # 记忆来源
    confidence: float = 0.0  # 整体提取置信度
    visibility: MemoryVisibility = MemoryVisibility.PUBLIC  # 可见性
    ttl_minutes: Optional[int] = None  # 过期时间（分钟），None 表示永不过期
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # 过期时间（自动计算）

    def __post_init__(self):
        """初始化后处理：计算过期时间"""
        if self.ttl_minutes is not None and self.ttl_minutes > 0:
            self.expires_at = self.created_at + timedelta(minutes=self.ttl_minutes)

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "time_slot": self.time_slot.value,
            "day_of_week": self.day_of_week.value,
            "task_hint": (
                {
                    "content": self.task_hint.content,
                    "category": self.task_hint.category,
                    "confidence": self.task_hint.confidence,
                }
                if self.task_hint
                else None
            ),
            "time_hint": (
                {
                    "pattern": self.time_hint.pattern,
                    "inferred_schedule": self.time_hint.inferred_schedule,
                    "confidence": self.time_hint.confidence,
                }
                if self.time_hint
                else None
            ),
            "emotion_hint": (
                {
                    "signal": self.emotion_hint.signal,
                    "stress_level": self.emotion_hint.stress_level,
                    "keywords_detected": self.emotion_hint.keywords_detected,
                }
                if self.emotion_hint
                else None
            ),
            "relation_hint": (
                {
                    "mentioned": self.relation_hint.mentioned,
                    "relationship_type": self.relation_hint.relationship_type,
                }
                if self.relation_hint
                else None
            ),
            "todo_hint": (
                {
                    "content": self.todo_hint.content,
                    "deadline": (
                        self.todo_hint.deadline.isoformat() if self.todo_hint.deadline else None
                    ),
                    "priority": self.todo_hint.priority,
                    "confidence": self.todo_hint.confidence,
                }
                if self.todo_hint
                else None
            ),
            "preference_hint": (
                {
                    "response_format": self.preference_hint.response_format,
                    "communication_style": self.preference_hint.communication_style,
                    "preferred_tools": self.preference_hint.preferred_tools,
                    "work_preferences": self.preference_hint.work_preferences,
                    "confidence": self.preference_hint.confidence,
                }
                if self.preference_hint
                else None
            ),
            "topic_hint": (
                {
                    "topics": self.topic_hint.topics,
                    "projects": self.topic_hint.projects,
                    "keywords": self.topic_hint.keywords,
                    "confidence": self.topic_hint.confidence,
                }
                if self.topic_hint
                else None
            ),
            "constraint_hint": (
                {
                    "constraints": self.constraint_hint.constraints,
                    "taboos": self.constraint_hint.taboos,
                    "limitations": self.constraint_hint.limitations,
                    "confidence": self.constraint_hint.confidence,
                }
                if self.constraint_hint
                else None
            ),
            "tool_hint": (
                {
                    "tools_mentioned": self.tool_hint.tools_mentioned,
                    "platforms_mentioned": self.tool_hint.platforms_mentioned,
                    "preferred_workflow": self.tool_hint.preferred_workflow,
                    "confidence": self.tool_hint.confidence,
                }
                if self.tool_hint
                else None
            ),
            "goal_hint": (
                {
                    "goals": self.goal_hint.goals,
                    "risks": self.goal_hint.risks,
                    "blockers": self.goal_hint.blockers,
                    "achievements": self.goal_hint.achievements,
                    "confidence": self.goal_hint.confidence,
                }
                if self.goal_hint
                else None
            ),
            # 记忆元数据
            "memory_type": self.memory_type.value,
            "source": self.source.value,
            "confidence": self.confidence,
            "visibility": self.visibility.value,
            "ttl_minutes": self.ttl_minutes,
            "metadata": self.metadata,
            # 时间戳
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
