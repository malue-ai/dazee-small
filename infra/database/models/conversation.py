"""
对话模型

使用 PostgreSQL JSONB 类型存储 metadata
"""

from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy import String, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base

if TYPE_CHECKING:
    from infra.database.models.message import Message


class Conversation(Base):
    """
    对话表（PostgreSQL JSONB 版本）
    
    存储对话（会话）信息
    
    metadata 存储：
    - compaction_info: 上下文压缩信息
    - agent_config: Agent 配置信息
    - custom_data: 用户自定义数据
    """
    __tablename__ = "conversations"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 创建者 ID（不再使用外键约束，支持多用户访问同一对话）
    user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True
    )
    
    # 基本信息
    title: Mapped[str] = mapped_column(String(255), default="新对话", nullable=False)

    # 状态
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False
    )
    
    # ✅ 使用 JSONB 存储 extra_data（数据库列名: metadata）
    extra_data: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict
    )
    
    # 关系
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )
    
    # 复合索引：user_id + updated_at（按更新时间倒序查询用户对话列表）
    __table_args__ = (
        Index('idx_conversations_user_updated', 'user_id', 'updated_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"

