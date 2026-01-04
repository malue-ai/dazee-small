"""
消息模型
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
import json

from sqlalchemy import String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base

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
    )  # JSON 格式: {"index": 0, "action": "generating", ...}
    
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
    
    # 元数据
    _metadata: Mapped[str] = mapped_column(
        "metadata",
        Text,
        default="{}",
        nullable=False
    )
    
    # 关系
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    
    @property
    def extra_data(self) -> dict:
        """获取元数据（自动解析 JSON）"""
        return json.loads(self._metadata) if self._metadata else {}
    
    @extra_data.setter
    def extra_data(self, value: dict):
        """设置元数据（自动序列化为 JSON）"""
        self._metadata = json.dumps(value, ensure_ascii=False)
    
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

