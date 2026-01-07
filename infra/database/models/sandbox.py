"""
沙盒模型

存储 E2B 沙盒与 conversation 的映射关系，
支持沙盒生命周期管理（pause/resume）
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
import json

from sqlalchemy import String, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base

if TYPE_CHECKING:
    pass


class Sandbox(Base):
    """
    沙盒表
    
    存储 E2B 沙盒与 conversation 的映射关系
    一个 conversation 最多对应一个活跃的沙盒
    """
    __tablename__ = "sandboxes"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 关联关系
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True
    )
    
    # E2B 沙盒信息
    e2b_sandbox_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="creating",
        nullable=False,
        index=True
    )
    stack: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True
    )
    preview_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True
    )
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=True
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # 元数据（JSON 存储）
    _metadata: Mapped[str] = mapped_column(
        "metadata",
        Text,
        default="{}",
        nullable=False
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
        return f"<Sandbox(id={self.id}, conversation_id={self.conversation_id}, status={self.status})>"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "e2b_sandbox_id": self.e2b_sandbox_id,
            "status": self.status,
            "stack": self.stack,
            "preview_url": self.preview_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "metadata": self.extra_data
        }

