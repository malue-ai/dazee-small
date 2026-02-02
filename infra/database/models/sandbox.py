"""
沙盒模型

存储 E2B 沙盒与 conversation 的映射关系，
支持沙盒生命周期管理（pause/resume）
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
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
    
    # 当前运行的项目信息（用于暂停/恢复时自动管理项目）
    active_project_path: Mapped[Optional[str]] = mapped_column(
        String(256),
        nullable=True
    )
    active_project_stack: Mapped[Optional[str]] = mapped_column(
        String(32),
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
    
    # 元数据（JSONB 类型，PostgreSQL 原生支持）
    extra_data: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default={},
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<Sandbox(id={self.id}, conversation_id={self.conversation_id}, status={self.status})>"
    
    # 复合索引：清理过期沙盒
    __table_args__ = (
        Index('idx_sandboxes_status_last_active', 'status', 'last_active_at'),
    )
    
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
            "active_project_path": self.active_project_path,
            "active_project_stack": self.active_project_stack,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "metadata": self.extra_data
        }

