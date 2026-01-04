"""
文件模型
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
import json
from enum import Enum

from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base

if TYPE_CHECKING:
    from infra.database.models.user import User


class FileStatus(str, Enum):
    """文件状态"""
    PENDING = "pending"          # 待处理
    UPLOADING = "uploading"      # 上传中
    PROCESSING = "processing"    # 处理中
    READY = "ready"              # 就绪
    FAILED = "failed"            # 失败
    DELETED = "deleted"          # 已删除


class StorageType(str, Enum):
    """存储类型"""
    LOCAL = "local"              # 本地存储
    S3 = "s3"                    # S3 / MinIO
    OSS = "oss"                  # 阿里云 OSS


class File(Base):
    """
    文件表
    
    存储用户上传的文件信息
    """
    __tablename__ = "files"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 外键
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # 文件信息
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # 存储信息
    storage_type: Mapped[StorageType] = mapped_column(
        SQLEnum(StorageType),
        default=StorageType.LOCAL,
        nullable=False
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)  # 存储路径或 S3 Key
    storage_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # 访问 URL
    
    # 状态
    status: Mapped[FileStatus] = mapped_column(
        SQLEnum(FileStatus),
        default=FileStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # 关联（可选）
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )
    message_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )
    
    # 处理结果（如 RAG 提取的文本）
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
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
    
    # 元数据
    _metadata: Mapped[str] = mapped_column(
        "metadata",
        Text,
        default="{}",
        nullable=False
    )
    
    # 关系
    user: Mapped["User"] = relationship(back_populates="files")
    
    @property
    def extra_data(self) -> dict:
        """获取元数据（自动解析 JSON）"""
        return json.loads(self._metadata) if self._metadata else {}
    
    @extra_data.setter
    def extra_data(self, value: dict):
        """设置元数据（自动序列化为 JSON）"""
        self._metadata = json.dumps(value, ensure_ascii=False)
    
    def __repr__(self) -> str:
        return f"<File(id={self.id}, filename={self.filename}, status={self.status})>"

