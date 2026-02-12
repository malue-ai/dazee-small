"""
显式记忆数据结构

用户主动上传的记忆卡片，用于保存用户的明确偏好和事实
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from .fragment import MemorySource, MemoryType, MemoryVisibility


class MemoryCardCategory(str, Enum):
    """记忆卡片分类"""

    PREFERENCE = "preference"  # 偏好设置
    FACT = "fact"  # 事实信息
    CONTEXT = "context"  # 上下文信息
    CONSTRAINT = "constraint"  # 约束条件
    RELATION = "relation"  # 关系信息
    GOAL = "goal"  # 目标信息
    OTHER = "other"  # 其他


@dataclass
class MemoryCard:
    """
    记忆卡片

    用户主动上传的显式记忆，包含明确的偏好、事实或上下文信息
    """

    id: str
    user_id: str
    content: str  # 记忆内容
    category: MemoryCardCategory = MemoryCardCategory.OTHER

    # 记忆元数据
    memory_type: MemoryType = MemoryType.EXPLICIT  # 固定为显式记忆
    source: MemorySource = MemorySource.USER_CARD  # 固定为用户卡片
    visibility: MemoryVisibility = MemoryVisibility.PUBLIC  # 默认公开
    ttl_minutes: Optional[int] = None  # 过期时间（分钟），None 表示永不过期

    # 额外信息
    title: Optional[str] = None  # 标题（可选）
    tags: List[str] = field(default_factory=list)  # 标签
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # 过期时间（自动计算）

    def __post_init__(self):
        """初始化后处理：计算过期时间"""
        if self.ttl_minutes is not None and self.ttl_minutes > 0:
            self.expires_at = self.created_at + timedelta(minutes=self.ttl_minutes)

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content": self.content,
            "category": self.category.value,
            "title": self.title,
            "tags": self.tags,
            "memory_type": self.memory_type.value,
            "source": self.source.value,
            "visibility": self.visibility.value,
            "ttl_minutes": self.ttl_minutes,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryCard":
        """从字典创建记忆卡片"""
        # 解析时间
        created_at = (
            datetime.fromisoformat(data["created_at"])
            if isinstance(data.get("created_at"), str)
            else data.get("created_at", datetime.now())
        )
        updated_at = (
            datetime.fromisoformat(data["updated_at"])
            if isinstance(data.get("updated_at"), str)
            else data.get("updated_at", created_at)
        )
        expires_at = None
        if data.get("expires_at"):
            expires_at = (
                datetime.fromisoformat(data["expires_at"])
                if isinstance(data["expires_at"], str)
                else data["expires_at"]
            )

        # 解析枚举
        category = MemoryCardCategory(data.get("category", "other"))
        memory_type = MemoryType(data.get("memory_type", "explicit"))
        source = MemorySource(data.get("source", "user_card"))
        visibility = MemoryVisibility(data.get("visibility", "public"))

        card = cls(
            id=data["id"],
            user_id=data["user_id"],
            content=data["content"],
            category=category,
            memory_type=memory_type,
            source=source,
            visibility=visibility,
            ttl_minutes=data.get("ttl_minutes"),
            title=data.get("title"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at,
        )
        return card

    def to_mem0_message(self) -> Dict[str, str]:
        """
        转换为 Mem0 消息格式

        Returns:
            用于 Mem0.add() 的消息字典
        """
        # 构建消息内容
        message_parts = []
        if self.title:
            message_parts.append(f"标题: {self.title}")
        message_parts.append(f"内容: {self.content}")
        if self.tags:
            message_parts.append(f"标签: {', '.join(self.tags)}")

        return {"role": "user", "content": "\n".join(message_parts)}

    def to_mem0_metadata(self) -> Dict[str, Any]:
        """
        转换为 Mem0 元数据格式

        Returns:
            用于 Mem0.add() 的元数据字典
        """
        return {
            "card_id": self.id,
            "memory_type": self.memory_type.value,
            "source": self.source.value,
            "visibility": self.visibility.value,
            "category": self.category.value,
            "title": self.title,
            "tags": self.tags,
            "ttl_minutes": self.ttl_minutes,
            **self.metadata,
        }
