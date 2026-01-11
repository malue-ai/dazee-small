"""
碎片记忆数据结构

从单次对话中提取的碎片级记忆，包含任务、时间、情绪、关系等线索
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class TimeSlot(str, Enum):
    """时间段枚举"""
    MORNING = "morning"      # 06:00-12:00
    AFTERNOON = "afternoon"  # 12:00-18:00
    EVENING = "evening"      # 18:00-22:00
    NIGHT = "night"          # 22:00-06:00


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
    content: str           # 任务内容，如"客户反馈处理"
    category: str          # 任务类别，如"customer_support"
    confidence: float = 0.0  # 推断置信度 0.0-1.0


@dataclass
class TimeHint:
    """时间规律线索"""
    pattern: str           # 时间模式，如"early_morning_routine"
    inferred_schedule: Optional[str] = None  # 推断的时间段，如"09:00-10:00"
    confidence: float = 0.0


@dataclass
class EmotionHint:
    """情绪线索"""
    signal: str            # 情绪信号：neutral/positive/stressed/frustrated
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
    content: str           # 待办内容
    deadline: Optional[datetime] = None  # 截止时间
    priority: str = "medium"  # 优先级：low/medium/high
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
    
    # 元数据
    confidence: float = 0.0  # 整体提取置信度
    created_at: datetime = field(default_factory=datetime.now)
    
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
            "task_hint": {
                "content": self.task_hint.content,
                "category": self.task_hint.category,
                "confidence": self.task_hint.confidence
            } if self.task_hint else None,
            "time_hint": {
                "pattern": self.time_hint.pattern,
                "inferred_schedule": self.time_hint.inferred_schedule,
                "confidence": self.time_hint.confidence
            } if self.time_hint else None,
            "emotion_hint": {
                "signal": self.emotion_hint.signal,
                "stress_level": self.emotion_hint.stress_level,
                "keywords_detected": self.emotion_hint.keywords_detected
            } if self.emotion_hint else None,
            "relation_hint": {
                "mentioned": self.relation_hint.mentioned,
                "relationship_type": self.relation_hint.relationship_type
            } if self.relation_hint else None,
            "todo_hint": {
                "content": self.todo_hint.content,
                "deadline": self.todo_hint.deadline.isoformat() if self.todo_hint.deadline else None,
                "priority": self.todo_hint.priority,
                "confidence": self.todo_hint.confidence
            } if self.todo_hint else None,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat()
        }
