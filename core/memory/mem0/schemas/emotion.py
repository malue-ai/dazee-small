"""
情绪状态数据结构

追踪用户的情绪变化和心理状态
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class EmotionSignal:
    """单次情绪信号"""

    timestamp: datetime
    message_snippet: str  # 消息片段
    detected_emotion: str  # 检测到的情绪：neutral/positive/fatigue/frustration/stressed
    keywords: List[str] = field(default_factory=list)  # 情绪关键词
    stress_delta: float = 0.0  # 压力变化量


@dataclass
class EmotionTrend:
    """情绪趋势"""

    period: str  # 时间段：7_days/14_days/30_days
    average_stress: float  # 平均压力水平
    trend_direction: str  # 趋势：increasing/decreasing/stable
    peak_stress_day: Optional[date] = None  # 压力最高日
    main_stressors: List[str] = field(default_factory=list)  # 主要压力源


@dataclass
class EmotionState:
    """
    情绪状态

    追踪用户的情绪和心理状态变化
    """

    user_id: str
    date: date

    # 当前状态
    current_mood: str = "neutral"  # neutral/positive/slightly_stressed/stressed/frustrated
    stress_level: float = 0.0  # 0.0-1.0
    energy_level: float = 0.5  # 0.0-1.0
    last_updated: datetime = field(default_factory=datetime.now)

    # 检测到的信号
    signals: List[EmotionSignal] = field(default_factory=list)

    # 趋势分析
    trend: Optional[EmotionTrend] = None

    # 支持需求
    support_needed: bool = False
    support_reason: Optional[str] = None
    suggested_action: str = "none"  # none/proactive_care/resource_recommendation

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "user_id": self.user_id,
            "date": self.date.isoformat(),
            "current": {
                "mood": self.current_mood,
                "stress_level": self.stress_level,
                "energy_level": self.energy_level,
                "last_updated": self.last_updated.isoformat(),
            },
            "signals": [
                {
                    "timestamp": signal.timestamp.isoformat(),
                    "message_snippet": signal.message_snippet,
                    "detected_emotion": signal.detected_emotion,
                    "keywords": signal.keywords,
                    "stress_delta": signal.stress_delta,
                }
                for signal in self.signals
            ],
            "trend": (
                {
                    "period": self.trend.period,
                    "average_stress": self.trend.average_stress,
                    "trend_direction": self.trend.trend_direction,
                    "peak_stress_day": (
                        self.trend.peak_stress_day.isoformat()
                        if self.trend.peak_stress_day
                        else None
                    ),
                    "main_stressors": self.trend.main_stressors,
                }
                if self.trend
                else None
            ),
            "support_needed": {
                "flag": self.support_needed,
                "reason": self.support_reason,
                "suggested_action": self.suggested_action,
            },
        }
