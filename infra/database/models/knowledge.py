"""
知识库模型
"""

from datetime import datetime
from typing import Optional
import json
from enum import Enum

from sqlalchemy import String, DateTime, Text, Integer, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base


class KnowledgeType(str, Enum):
    """知识类型"""
    DOCUMENT = "document"        # 文档
    WEBPAGE = "webpage"          # 网页
    NOTE = "note"                # 笔记
    FAQ = "faq"                  # FAQ
    CODE = "code"                # 代码


class KnowledgeStatus(str, Enum):
    """知识状态"""
    PENDING = "pending"          # 待处理
    INDEXING = "indexing"        # 索引中
    READY = "ready"              # 就绪
    FAILED = "failed"            # 失败


class Knowledge(Base):
    """
    知识库表
    
    存储知识库条目（用于 RAG）
    """
    __tablename__ = "knowledge"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 外键
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # 来源文件（可选）
    file_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # 知识信息
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 类型和状态
    type: Mapped[KnowledgeType] = mapped_column(
        SQLEnum(KnowledgeType),
        default=KnowledgeType.DOCUMENT,
        nullable=False
    )
    status: Mapped[KnowledgeStatus] = mapped_column(
        SQLEnum(KnowledgeStatus),
        default=KnowledgeStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # 向量索引信息（用于 Milvus 等）
    vector_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # 分块信息
    chunk_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunk_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 原始文档 ID
    
    # 来源信息
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # 统计信息
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
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
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # 元数据
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
        return f"<Knowledge(id={self.id}, title={self.title}, status={self.status})>"

