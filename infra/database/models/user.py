"""
用户模型

使用 PostgreSQL JSONB 类型存储 metadata
"""

from datetime import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy import String, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base

if TYPE_CHECKING:
    from infra.database.models.file import File


class User(Base):
    """
    用户表（PostgreSQL JSONB 版本）
    
    存储用户基本信息
    
    metadata 存储：
    - preferences: 用户偏好设置
    - profile: 用户资料信息
    - custom_data: 自定义数据
    """
    __tablename__ = "users"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 基本信息
    username: Mapped[Optional[str]] = mapped_column(
        String(100), 
        nullable=True,
        index=True  # 添加索引，便于用户名查询
    )
    
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
    files: Mapped[list["File"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"

