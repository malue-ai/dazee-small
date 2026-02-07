"""
SQLite 本地存储表模型

适配 SQLite 的 ORM 模型定义：
- 不使用 JSONB → 使用 TEXT + JSON 序列化
- 不使用 PostgreSQL 特有语法
- 支持 FTS5 全文索引（通过触发器同步）
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class LocalBase(DeclarativeBase):
    """SQLite 专用声明式基类"""
    pass


# ==================== JSON 辅助 ====================


def _to_json(value: Any) -> str:
    """Python 对象 → JSON 字符串"""
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _from_json(value: str, default: Any = None) -> Any:
    """JSON 字符串 → Python 对象"""
    if value is None:
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


# ==================== 会话表 ====================


class LocalConversation(LocalBase):
    """
    本地会话表

    SQLite 版本的 Conversation，使用 TEXT 存储 JSON 数据
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    # JSON 数据存储为 TEXT
    metadata_json: Mapped[str] = mapped_column(
        "metadata", Text, nullable=False, default="{}"
    )

    # 关系
    messages: Mapped[list["LocalMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="LocalMessage.created_at",
    )

    __table_args__ = (
        Index("idx_local_conv_user_updated", "user_id", "updated_at"),
    )

    @property
    def extra_data(self) -> Dict[str, Any]:
        return _from_json(self.metadata_json, {})

    @extra_data.setter
    def extra_data(self, value: Dict[str, Any]):
        self.metadata_json = _to_json(value)

    def __repr__(self) -> str:
        return f"<LocalConversation(id={self.id}, title={self.title})>"


# ==================== 消息表 ====================


class LocalMessage(LocalBase):
    """
    本地消息表

    SQLite 版本的 Message，content 和 metadata 存储为 TEXT (JSON)

    content 格式（Claude API 标准）：
    - 用户消息: [{"type": "text", "text": "..."}]
    - AI 回复: [{"type": "thinking", ...}, {"type": "text", "text": "..."}, ...]
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # JSON 数据存储为 TEXT
    content_json: Mapped[str] = mapped_column("content", Text, nullable=False, default="[]")
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )

    metadata_json: Mapped[str] = mapped_column(
        "metadata", Text, nullable=False, default="{}"
    )

    # 关系
    conversation: Mapped["LocalConversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_local_msg_conv_created", "conversation_id", "created_at"),
    )

    @property
    def content(self) -> List[Dict[str, Any]]:
        return _from_json(self.content_json, [])

    @content.setter
    def content(self, value: List[Dict[str, Any]]):
        self.content_json = _to_json(value)

    @property
    def extra_data(self) -> Dict[str, Any]:
        return _from_json(self.metadata_json, {})

    @extra_data.setter
    def extra_data(self, value: Dict[str, Any]):
        self.metadata_json = _to_json(value)

    def get_text_content(self) -> str:
        """提取纯文本内容"""
        blocks = self.content
        text_parts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(text_parts) if text_parts else ""

    def __repr__(self) -> str:
        preview = self.get_text_content()[:50]
        return f"<LocalMessage(id={self.id}, role={self.role}, content={preview}...)>"


# ==================== Skills 缓存表 ====================


# ==================== 定时任务表 ====================


class LocalScheduledTask(LocalBase):
    """
    用户定时任务表

    存储用户通过 AI 对话创建的定时任务：
    - 支持单次执行 (once)、Cron 表达式 (cron)、固定间隔 (interval)
    - 动作类型：发送消息、执行 Agent 任务等

    示例：
    - "每天早上 9 点提醒我开会" → trigger_type=cron, cron="0 9 * * *"
    - "明天下午 3 点提醒我打电话" → trigger_type=once, run_at="2026-02-07T15:00:00"
    - "每隔 2 小时提醒我喝水" → trigger_type=interval, interval_seconds=7200
    """

    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 任务基本信息
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="未命名任务")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 触发配置
    trigger_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="once"
    )  # once / cron / interval

    # 单次执行时间（trigger_type=once 时使用）
    run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Cron 表达式（trigger_type=cron 时使用）
    cron_expr: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 间隔秒数（trigger_type=interval 时使用）
    interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 动作配置（JSON）
    # 格式: {"type": "send_message", "content": "..."} 或 {"type": "agent_task", "prompt": "..."}
    action_json: Mapped[str] = mapped_column("action", Text, nullable=False, default="{}")

    # 任务状态
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # active / paused / completed / cancelled

    # 执行记录
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 元数据
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    # 关联的会话（创建任务时的对话）
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_scheduled_task_user_status", "user_id", "status"),
        Index("idx_scheduled_task_next_run", "next_run_at", "status"),
    )

    @property
    def action(self) -> Dict[str, Any]:
        return _from_json(self.action_json, {})

    @action.setter
    def action(self, value: Dict[str, Any]):
        self.action_json = _to_json(value)

    def __repr__(self) -> str:
        return f"<LocalScheduledTask(id={self.id}, title={self.title}, trigger={self.trigger_type})>"


class LocalSkillCache(LocalBase):
    """
    Skills 缓存表

    支持延迟加载：首次请求时从磁盘读取 SKILL.md 并缓存到 SQLite，
    后续请求直接从 SQLite 读取，避免重复的文件 I/O。

    缓存策略：
    - 按 instance_id + skill_name 唯一索引
    - 通过 file_mtime 判断是否需要刷新
    - TTL 过期后下次访问自动刷新
    """

    __tablename__ = "skills_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Skill 内容
    skill_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    skill_metadata_json: Mapped[str] = mapped_column(
        "skill_metadata", Text, nullable=False, default="{}"
    )

    # 缓存元数据
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_mtime: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    cached_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )

    __table_args__ = (
        Index("idx_skill_cache_unique", "instance_id", "skill_name", unique=True),
        Index("idx_skill_cache_accessed", "accessed_at"),
    )

    @property
    def skill_metadata(self) -> Dict[str, Any]:
        return _from_json(self.skill_metadata_json, {})

    @skill_metadata.setter
    def skill_metadata(self, value: Dict[str, Any]):
        self.skill_metadata_json = _to_json(value)

    def __repr__(self) -> str:
        return f"<LocalSkillCache(instance={self.instance_id}, skill={self.skill_name})>"


# ==================== 文件索引元数据 ====================


class LocalIndexedFile(LocalBase):
    """
    已索引文件元数据

    用于增量索引：通过 file_hash 判断文件是否变更。
    """

    __tablename__ = "indexed_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    file_mtime: Mapped[float] = mapped_column(Float, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )

    __table_args__ = (
        Index("idx_indexed_files_path", "file_path", unique=True),
        Index("idx_indexed_files_hash", "file_hash"),
    )

    def __repr__(self) -> str:
        return f"<LocalIndexedFile(path={self.file_path}, chunks={self.chunk_count})>"
