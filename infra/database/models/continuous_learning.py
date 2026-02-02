"""
持续学习数据库模型

V9.4 新增

包含：
- SessionReward: 会话级奖励记录
- StepReward: 步骤级奖励记录
- Playbook: 策略库
- IntentCache: 意图缓存（可选持久化）
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from enum import Enum as PyEnum

from sqlalchemy import (
    String, DateTime, Text, Integer, Float, 
    ForeignKey, Enum as SQLEnum, Boolean, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from infra.database.base import Base


# ============================================================
# 枚举类型
# ============================================================

class PlaybookStatus(str, PyEnum):
    """策略状态"""
    DRAFT = "draft"              # 草稿（自动生成）
    PENDING_REVIEW = "pending"   # 待审核
    APPROVED = "approved"        # 已发布
    REJECTED = "rejected"        # 已拒绝
    DEPRECATED = "deprecated"    # 已废弃


class RewardSignal(str, PyEnum):
    """奖励信号类型"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AttributionMethod(str, PyEnum):
    """归因方法"""
    UNIFORM = "uniform"
    DECAY = "decay"
    LLM_JUDGE = "llm_judge"
    ADVANTAGE = "advantage"


# ============================================================
# 会话奖励表
# ============================================================

class SessionRewardRecord(Base):
    """
    会话级奖励记录表
    
    存储每个会话的整体奖励评估结果
    """
    __tablename__ = "session_rewards"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 关联
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    
    # 奖励信息
    total_reward: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    outcome_success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # 归因方法
    attribution_method: Mapped[str] = mapped_column(
        SQLEnum(AttributionMethod, name="attribution_method_enum", create_constraint=False),
        default=AttributionMethod.DECAY,
        nullable=False
    )
    
    # 统计信息
    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # 时间信息
    session_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    session_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # 任务信息
    task_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    complexity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    execution_strategy: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # 评估来源
    evaluated_by: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    evaluator_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    
    # 元数据（JSONB）
    _metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default={},
        nullable=False
    )
    
    # 关系
    step_rewards: Mapped[List["StepRewardRecord"]] = relationship(
        back_populates="session_reward",
        cascade="all, delete-orphan",
        order_by="StepRewardRecord.step_index"
    )
    
    # 索引
    __table_args__ = (
        Index("ix_session_rewards_created_at", "created_at"),
        Index("ix_session_rewards_total_reward", "total_reward"),
        Index("ix_session_rewards_task_type_reward", "task_type", "total_reward"),
    )
    
    def __repr__(self) -> str:
        return f"<SessionReward(id={self.id}, reward={self.total_reward:.2f})>"


# ============================================================
# 步骤奖励表
# ============================================================

class StepRewardRecord(Base):
    """
    步骤级奖励记录表
    
    存储每个执行步骤的奖励归因结果
    """
    __tablename__ = "step_rewards"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 外键
    session_reward_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("session_rewards.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # 步骤信息
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)  # tool_call, llm_response, plan_step
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # 奖励信号
    signal: Mapped[str] = mapped_column(
        SQLEnum(RewardSignal, name="reward_signal_enum", create_constraint=False),
        default=RewardSignal.NEUTRAL,
        nullable=False
    )
    reward_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # 归因信息
    contribution_weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    
    # 执行信息
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 关键性评估
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    impact_on_outcome: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # 内容摘要
    input_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    
    # 关系
    session_reward: Mapped["SessionRewardRecord"] = relationship(back_populates="step_rewards")
    
    # 索引
    __table_args__ = (
        Index("ix_step_rewards_action_type", "action_type"),
        Index("ix_step_rewards_is_critical", "is_critical"),
        Index("ix_step_rewards_session_step", "session_reward_id", "step_index"),  # 复合索引：步骤排序
    )
    
    def __repr__(self) -> str:
        return f"<StepReward(id={self.id}, action={self.action_name}, reward={self.reward_value:.2f})>"


# ============================================================
# 策略库表
# ============================================================

class PlaybookRecord(Base):
    """
    策略库表
    
    存储从高质量会话中提取的执行策略
    """
    __tablename__ = "playbooks"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 基本信息
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 触发条件（JSONB）
    # {"task_types": [], "keywords": [], "complexity_range": [], "patterns": []}
    trigger: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False)
    
    # 执行策略（JSONB）
    # {"execution_strategy": "", "suggested_tools": [], "max_turns": 0, "planning_depth": ""}
    strategy: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False)
    
    # 工具序列（JSONB）
    # [{"tool": "", "purpose": "", "reward": 0.0}]
    tool_sequence: Mapped[list] = mapped_column(JSONB, default=[], nullable=False)
    
    # 质量指标（JSONB）
    # {"avg_reward": 0.0, "success_rate": 0.0, "avg_turns": 0.0}
    quality_metrics: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False)
    
    # 状态
    status: Mapped[str] = mapped_column(
        SQLEnum(PlaybookStatus, name="playbook_status_enum", create_constraint=False),
        default=PlaybookStatus.DRAFT,
        nullable=False,
        index=True
    )
    
    # 来源
    source: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)  # auto, manual, import
    source_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    
    # 审核信息
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 使用统计
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    
    # 索引
    __table_args__ = (
        Index("ix_playbooks_status_created", "status", "created_at"),
        Index("ix_playbooks_source", "source"),
        Index("ix_playbooks_usage_count", "usage_count"),
    )
    
    def __repr__(self) -> str:
        return f"<Playbook(id={self.id}, name={self.name}, status={self.status})>"


# ============================================================
# 意图缓存表（可选持久化）
# ============================================================

class IntentCacheRecord(Base):
    """
    意图缓存表
    
    持久化语义缓存，支持跨实例共享
    """
    __tablename__ = "intent_cache"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 查询信息
    query_hash: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 向量（存储为 JSON 数组）
    embedding: Mapped[list] = mapped_column(JSONB, nullable=False)
    
    # 意图结果（JSONB）
    intent_result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # 统计
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    
    # 索引
    __table_args__ = (
        Index("ix_intent_cache_hit_count", "hit_count"),
    )
    
    def __repr__(self) -> str:
        return f"<IntentCache(id={self.id}, query_hash={self.query_hash[:8]}...)>"
