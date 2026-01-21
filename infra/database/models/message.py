"""
消息模型

使用 PostgreSQL JSONB 类型存储 content 和 metadata
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base
from infra.database.models.conversation import Conversation


class Message(Base):
    """
    消息表（PostgreSQL JSONB 版本）
    
    存储对话中的消息（用户消息和 AI 回复）
    
    content 格式（Claude API 标准）：
    - 用户消息: [{"type": "text", "text": "..."}]
    - AI 回复: [{"type": "thinking", ...}, {"type": "text", "text": "..."}, {"type": "tool_use", ...}]
    
    metadata 存储：
    - session_id: 会话 ID
    - model: 使用的模型
    - usage: token 使用量和计费信息
    - files: 附件文件信息
    - plan: Agent 规划信息
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
    
    # ✅ 使用 JSONB 存储 content blocks（直接存取 list）
    content: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list
    )
    
    # 状态（用于流式更新）
    status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        index=True  # 添加索引，便于查询 streaming 状态的消息
    )  # processing/completed/stopped/failed
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
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
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    
    # 复合索引：conversation_id + created_at（常用查询模式）
    __table_args__ = (
        Index('idx_messages_conv_created', 'conversation_id', 'created_at'),
    )
    
    def get_text_content(self) -> str:
        """
        提取纯文本内容
        
        从 content blocks 中提取所有 text 类型的内容
        """
        blocks = self.content or []
        text_parts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(text_parts) if text_parts else ""
    
    def __repr__(self) -> str:
        preview = self.get_text_content()[:50]
        return f"<Message(id={self.id}, role={self.role}, content={preview}...)>"

