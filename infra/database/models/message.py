"""
消息模型
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
import json

from sqlalchemy import String, DateTime, Text, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from infra.database.base import Base
from infra.database.engine import IS_SQLITE

if TYPE_CHECKING:
    from infra.database.models.conversation import Conversation


class Message(Base):
    """
    消息表
    
    存储对话中的消息（用户消息和 AI 回复）
    
    content 格式（Claude API 标准）：
    - 用户消息: [{"type": "text", "text": "..."}]
    - AI 回复: [{"type": "thinking", ...}, {"type": "text", "text": "..."}, {"type": "tool_use", ...}]
    """
    __tablename__ = "messages"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # 外键
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # 消息内容
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )  # user, assistant, system
    
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )  # JSON 格式的 content blocks
    
    # 状态（用于流式更新）
    status: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )  # 字符串: processing/completed/stopped/failed
    
    # 评分（用于用户反馈）
    score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
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
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    
    @property
    def extra_data(self) -> dict:
        """获取元数据（直接返回 dict，无需序列化）"""
        return self._metadata if isinstance(self._metadata, dict) else {}
    
    @extra_data.setter
    def extra_data(self, value: dict):
        """设置元数据（直接设置 dict，自动序列化为 JSONB）"""
        self._metadata = value if isinstance(value, dict) else {}
    
    @property
    def content_blocks(self) -> list:
        """获取 content blocks（自动解析 JSON）"""
        try:
            return json.loads(self.content) if self.content else []
        except json.JSONDecodeError:
            # 兼容旧格式（纯文本）
            return [{"type": "text", "text": self.content}]
    
    @content_blocks.setter
    def content_blocks(self, value: list):
        """设置 content blocks（自动序列化为 JSON）"""
        self.content = json.dumps(value, ensure_ascii=False)
    
    def get_text_content(self) -> str:
        """
        提取纯文本内容
        
        从 content blocks 中提取所有 text 类型的内容
        """
        blocks = self.content_blocks
        text_parts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(text_parts) if text_parts else ""
    
    def __repr__(self) -> str:
        preview = self.get_text_content()[:50]
        return f"<Message(id={self.id}, role={self.role}, content={preview}...)>"

