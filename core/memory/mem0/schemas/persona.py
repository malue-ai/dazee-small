"""
用户画像数据结构

汇总所有分析结果，生成综合用户画像，用于 Prompt 注入
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class PlanSummary:
    """计划摘要"""
    title: str
    deadline: Optional[datetime]
    progress: float
    status: str  # active/at_risk/completed
    blockers: List[str] = field(default_factory=list)


@dataclass
class ReminderSummary:
    """提醒摘要"""
    time: datetime
    content: str
    type: str  # deadline/blocker/checkpoint


@dataclass
class UserPersona:
    """
    用户画像
    
    汇总所有层的分析结果，用于 Prompt 注入和个性化响应
    """
    user_id: str
    generated_at: datetime = field(default_factory=datetime.now)
    
    # 身份推断
    inferred_role: str = "unknown"  # product_manager/developer/sales/operations
    role_confidence: float = 0.0
    work_domain: str = "general"  # 工作领域
    
    # 行为摘要
    routine_overview: str = ""  # 工作规律概述
    work_style: str = ""  # 工作风格
    time_management: str = ""  # 时间管理方式
    
    # 当前状态
    mood: str = "neutral"
    stress_level: float = 0.0
    main_concerns: List[str] = field(default_factory=list)  # 主要关注点
    support_flag: bool = False  # 是否需要关怀
    
    # 活跃计划
    active_plans: List[PlanSummary] = field(default_factory=list)
    upcoming_reminders: List[ReminderSummary] = field(default_factory=list)
    
    # 个性化配置
    greeting_style: str = "professional"  # professional/casual/warm
    response_format: str = "structured"  # structured/concise/detailed
    proactive_level: str = "medium"  # low/medium/high
    emotional_support: bool = True
    
    # Prompt 注入配置
    prompt_injection_enabled: bool = True
    prompt_sections: List[str] = field(default_factory=lambda: [
        "identity", "current_state", "active_plans", "personalization"
    ])
    max_prompt_tokens: int = 500
    
    # 元数据
    source_fragments: int = 0  # 基于多少碎片
    last_behavior_analysis: Optional[datetime] = None
    last_emotion_analysis: Optional[datetime] = None
    ttl_minutes: int = 60  # 缓存 TTL
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "user_id": self.user_id,
            "generated_at": self.generated_at.isoformat(),
            "identity": {
                "inferred_role": self.inferred_role,
                "role_confidence": self.role_confidence,
                "work_domain": self.work_domain
            },
            "behavior_summary": {
                "routine_overview": self.routine_overview,
                "work_style": self.work_style,
                "time_management": self.time_management
            },
            "current_state": {
                "mood": self.mood,
                "stress_level": self.stress_level,
                "main_concerns": self.main_concerns,
                "support_flag": self.support_flag
            },
            "active_plans": [
                {
                    "title": plan.title,
                    "deadline": plan.deadline.isoformat() if plan.deadline else None,
                    "progress": plan.progress,
                    "status": plan.status,
                    "blockers": plan.blockers
                }
                for plan in self.active_plans
            ],
            "upcoming_reminders": [
                {
                    "time": reminder.time.isoformat(),
                    "content": reminder.content,
                    "type": reminder.type
                }
                for reminder in self.upcoming_reminders
            ],
            "personalization": {
                "greeting_style": self.greeting_style,
                "response_format": self.response_format,
                "proactive_level": self.proactive_level,
                "emotional_support": self.emotional_support
            },
            "prompt_injection": {
                "enabled": self.prompt_injection_enabled,
                "sections": self.prompt_sections,
                "max_tokens": self.max_prompt_tokens
            },
            "metadata": {
                "source_fragments": self.source_fragments,
                "last_behavior_analysis": self.last_behavior_analysis.isoformat() if self.last_behavior_analysis else None,
                "last_emotion_analysis": self.last_emotion_analysis.isoformat() if self.last_emotion_analysis else None,
                "ttl_minutes": self.ttl_minutes
            }
        }
    
    def to_prompt_text(self) -> str:
        """
        转换为 Prompt 注入文本
        
        Returns:
            格式化的 Prompt 文本
        """
        sections = []
        
        sections.append("## Dazee 用户洞察\n")
        
        # 身份
        if "identity" in self.prompt_sections and self.inferred_role != "unknown":
            sections.append(f"**身份**: {self._role_to_chinese(self.inferred_role)}（置信度: {int(self.role_confidence * 100)}%）\n")
        
        # 工作规律
        if "behavior_summary" in self.prompt_sections and self.routine_overview:
            sections.append(f"**工作规律**:\n{self.routine_overview}\n")
        
        # 当前状态
        if "current_state" in self.prompt_sections:
            state_lines = []
            if self.mood != "neutral":
                state_lines.append(f"- 情绪: {self._mood_to_chinese(self.mood)}")
            if self.main_concerns:
                state_lines.append(f"- 关注: {', '.join(self.main_concerns[:2])}")
            if state_lines:
                sections.append("**当前状态**:\n" + "\n".join(state_lines) + "\n")
        
        # 活跃计划
        if "active_plans" in self.prompt_sections and self.active_plans:
            sections.append("**活跃计划**:")
            for plan in self.active_plans[:2]:  # 最多显示2个
                deadline_str = plan.deadline.strftime("%m月%d日") if plan.deadline else "无截止"
                status_emoji = "⚠️" if plan.status == "at_risk" else "🔄"
                sections.append(f"- {plan.title}（{status_emoji} {deadline_str}，进度 {int(plan.progress * 100)}%）")
                if plan.blockers:
                    sections.append(f"  - 阻碍: {plan.blockers[0]}")
            sections.append("")
        
        # 注意事项
        if "personalization" in self.prompt_sections:
            notes = []
            if self.response_format == "structured":
                notes.append("响应格式: 结构化 + 摘要优先")
            if self.emotional_support and self.support_flag:
                notes.append("用户近期压力较大，适时关怀")
            if notes:
                sections.append("**注意事项**:\n- " + "\n- ".join(notes) + "\n")
        
        return "\n".join(sections)
    
    def _role_to_chinese(self, role: str) -> str:
        """角色英文转中文"""
        mapping = {
            "product_manager": "产品经理",
            "developer": "开发工程师",
            "sales": "销售",
            "operations": "运营",
            "unknown": "未知"
        }
        return mapping.get(role, role)
    
    def _mood_to_chinese(self, mood: str) -> str:
        """情绪英文转中文"""
        mapping = {
            "neutral": "平和",
            "positive": "积极",
            "slightly_stressed": "略有压力",
            "stressed": "压力较大",
            "frustrated": "沮丧"
        }
        return mapping.get(mood, mood)
