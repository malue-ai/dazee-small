"""
对话模型
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
import json

from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base

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
    
    # 元数据（JSON 存储，包含压缩信息等）
    _metadata: Mapped[str] = mapped_column(
        "metadata",
        Text,
        default="{}",
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
        """获取元数据（自动解析 JSON）"""
        return json.loads(self._metadata) if self._metadata else {}
    
    @extra_data.setter
    def extra_data(self, value: dict):
        """设置元数据（自动序列化为 JSON）"""
        self._metadata = json.dumps(value, ensure_ascii=False)
    
    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"

