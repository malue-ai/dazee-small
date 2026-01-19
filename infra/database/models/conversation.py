"""
对话模型
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
import json

from sqlalchemy import String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from infra.database.base import Base
from infra.database.engine import IS_SQLITE

if TYPE_CHECKING:
    from infra.database.models.user import User
    from infra.database.models.message import Message


class Conversation(Base):
    """
    对话表
    
    存储对话（会话）信息
    """
    __tablename__ = "conversations"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 外键
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # 基本信息
    title: Mapped[str] = mapped_column(String(255), default="新对话", nullable=False)
    
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
        nullable=False,
        index=True
    )
    
    # 元数据（使用 JSONB 类型，PostgreSQL 自动优化）
    # 注意：SQLAlchemy 的 metadata 是保留字，使用 _metadata 作为字段名
    # 应用层通过 extra_data 属性访问（直接读写 dict，无需序列化）
    _metadata: Mapped[dict] = mapped_column(
        "metadata",  # 数据库字段名仍然是 metadata
        JSONB if not IS_SQLITE else JSON,  # PostgreSQL 使用 JSONB，SQLite 使用 JSON
        default={},
        nullable=False
    )
    
    # 关系
    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )
    
    @property
    def extra_data(self) -> dict:
        """获取元数据（直接返回 dict，无需序列化）"""
        return self._metadata if isinstance(self._metadata, dict) else {}
    
    @extra_data.setter
    def extra_data(self, value: dict):
        """设置元数据（直接设置 dict，自动序列化为 JSONB）"""
        self._metadata = value if isinstance(value, dict) else {}
    
    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"

