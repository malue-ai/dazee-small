"""
行为模式数据结构 - 5W1H

从碎片记忆中聚合推断的用户行为模式
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class DateRange:
    """日期范围"""
    start: datetime
    end: datetime


@dataclass
class RoutineTask:
    """常规任务 - What"""
    name: str                        # 任务名称，如"客户反馈处理"
    category: str = "general"        # 类别
    frequency: str = "ad_hoc"        # 频率：daily/weekly/monthly/ad_hoc
    avg_duration_hours: Optional[float] = None  # 平均耗时
    confidence: float = 0.5          # 置信度


@dataclass
class TimePattern:
    """时间模式 - When"""
    work_start: Optional[str] = None          # 通常开始工作时间，如"09:00"
    work_end: Optional[str] = None            # 通常结束工作时间，如"18:00"
    peak_hours: List[str] = field(default_factory=list)         # 高效工作时段
    meeting_slots: List[str] = field(default_factory=list)      # 常见会议时段
    preferred_deep_work_time: Optional[str] = None              # 偏好的深度工作时间


@dataclass
class WorkContext:
    """工作场景 - Where"""
    primary_context: str = "unknown"  # 主要场景：office/remote/hybrid/unknown
    tools_mentioned: List[str] = field(default_factory=list)    # 提到的工具/平台


@dataclass
class Collaborator:
    """协作者 - Who"""
    name: str                        # 名称或称呼，如"老板"、"客户A"
    relationship: str = "colleague"  # 关系：supervisor/colleague/client/external
    interaction_frequency: str = "occasionally"  # 互动频率：daily/weekly/occasionally


@dataclass
class Motivation:
    """动机/目标 - Why"""
    primary_goals: List[str] = field(default_factory=list)      # 主要工作目标
    motivations: List[str] = field(default_factory=list)        # 工作动力/驱动因素
    pain_points: List[str] = field(default_factory=list)        # 工作痛点/困扰


@dataclass
class WorkStyle:
    """工作风格 - How"""
    work_style: str = "flexible"              # 工作风格：structured/flexible/deadline_driven
    communication_preference: str = "mixed"    # 沟通偏好：async/sync/mixed
    decision_style: str = "collaborative"      # 决策风格：data_driven/intuitive/collaborative
    response_format_preference: str = "concise"  # 响应格式偏好：detailed/concise/structured


@dataclass
class BehaviorPattern:
    """
    5W1H 行为模式
    
    从多次碎片对话中聚合推断的行为规律
    """
    id: str
    user_id: str
    analysis_period: DateRange
    fragment_count: int = 0  # 基于多少碎片推断
    
    # What - 做什么
    routine_tasks: List[RoutineTask] = field(default_factory=list)
    main_work_focus: str = ""
    
    # When - 何时做
    time_pattern: Optional[TimePattern] = None
    
    # Where - 在哪做
    work_context: Optional[WorkContext] = None
    
    # Who - 与谁做
    collaborators: List[Collaborator] = field(default_factory=list)
    reporting_to: Optional[str] = None
    
    # Why - 为何做
    motivation: Optional[Motivation] = None
    
    # How - 如何做
    work_style: Optional[WorkStyle] = None
    
    # 推断角色
    inferred_role: str = "unknown"  # product_manager/developer/sales/operations/designer/analyst/unknown
    role_confidence: float = 0.0
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "analysis_period": {
                "start": self.analysis_period.start.isoformat(),
                "end": self.analysis_period.end.isoformat()
            },
            "fragment_count": self.fragment_count,
            "what": {
                "routine_tasks": [
                    {
                        "name": task.name,
                        "category": task.category,
                        "frequency": task.frequency,
                        "avg_duration_hours": task.avg_duration_hours,
                        "confidence": task.confidence
                    }
                    for task in self.routine_tasks
                ],
                "main_work_focus": self.main_work_focus
            },
            "when": {
                "work_start": self.time_pattern.work_start if self.time_pattern else None,
                "work_end": self.time_pattern.work_end if self.time_pattern else None,
                "peak_hours": self.time_pattern.peak_hours if self.time_pattern else [],
                "meeting_slots": self.time_pattern.meeting_slots if self.time_pattern else [],
                "preferred_deep_work_time": self.time_pattern.preferred_deep_work_time if self.time_pattern else None
            },
            "where": {
                "primary_context": self.work_context.primary_context if self.work_context else "unknown",
                "tools_mentioned": self.work_context.tools_mentioned if self.work_context else []
            },
            "who": {
                "collaborators": [
                    {
                        "name": collab.name,
                        "relationship": collab.relationship,
                        "interaction_frequency": collab.interaction_frequency
                    }
                    for collab in self.collaborators
                ],
                "reporting_to": self.reporting_to
            },
            "why": {
                "primary_goals": self.motivation.primary_goals if self.motivation else [],
                "motivations": self.motivation.motivations if self.motivation else [],
                "pain_points": self.motivation.pain_points if self.motivation else []
            },
            "how": {
                "work_style": self.work_style.work_style if self.work_style else "flexible",
                "communication_preference": self.work_style.communication_preference if self.work_style else "mixed",
                "decision_style": self.work_style.decision_style if self.work_style else "collaborative",
                "response_format_preference": self.work_style.response_format_preference if self.work_style else "concise"
            } if self.work_style else None,
            "inferred_role": self.inferred_role,
            "role_confidence": self.role_confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
