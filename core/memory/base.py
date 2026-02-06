"""
Memory 基础模块 - 通用类型和抽象基类

设计原则：
- 定义 Memory 的通用接口和类型
- 支持按 scope 划分（user / system / org）
- 可扩展的存储后端抽象
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryScope(Enum):
    """
    记忆作用域

    - USER: 用户级别（按 user_id 隔离）
    - SYSTEM: 系统级别（全局共享）
    - ORG: 组织级别（按 org_id 隔离，预留）
    """

    USER = "user"
    SYSTEM = "system"
    ORG = "org"  # 预留


class StorageBackend(Enum):
    """
    存储后端类型

    - MEMORY: 内存存储（默认，会话结束即清除）
    - FILE: 文件存储（JSON 文件）
    - DATABASE: 数据库存储（SQLite）
    """

    MEMORY = "memory"
    FILE = "file"
    DATABASE = "database"


@dataclass
class MemoryConfig:
    """
    Memory 配置

    Attributes:
        scope: 作用域（user/system/org）
        backend: 存储后端
        storage_path: 存储路径（file 后端使用）
        ttl_seconds: 过期时间（秒，0 表示不过期）
    """

    scope: MemoryScope = MemoryScope.USER
    backend: StorageBackend = StorageBackend.MEMORY
    storage_path: Optional[str] = None
    ttl_seconds: int = 0  # 0 = 不过期


class BaseMemory(ABC):
    """
    Memory 抽象基类

    所有 Memory 实现都应该继承此类
    """

    def __init__(self, config: Optional[MemoryConfig] = None) -> None:
        self.config = config or MemoryConfig()
        self._created_at = datetime.now()

    @property
    def scope(self) -> MemoryScope:
        """获取作用域"""
        return self.config.scope

    @property
    def backend(self) -> StorageBackend:
        """获取存储后端"""
        return self.config.backend

    @abstractmethod
    def clear(self) -> None:
        """清空记忆"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（子类可覆盖）"""
        return {
            "scope": self.scope.value,
            "backend": self.backend.value,
            "created_at": self._created_at.isoformat(),
        }


class BaseScopedMemory(BaseMemory):
    """
    带作用域的 Memory 基类

    支持按 user_id / org_id 隔离数据
    """

    def __init__(self, scope_id: Optional[str] = None, config: Optional[MemoryConfig] = None):
        """
        Args:
            scope_id: 作用域 ID（user_id 或 org_id）
            config: Memory 配置
        """
        super().__init__(config)
        self.scope_id = scope_id

    def get_storage_key(self, key: str) -> str:
        """
        获取存储 key（带作用域前缀）

        格式：{scope}:{scope_id}:{key}
        """
        if self.scope_id:
            return f"{self.scope.value}:{self.scope_id}:{key}"
        return f"{self.scope.value}:{key}"


# ==================== 通用数据结构 ====================


@dataclass
class MemoryEntry:
    """
    通用记忆条目

    用于存储任意类型的记忆数据
    """

    key: str
    value: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None

    def is_expired(self) -> bool:
        """检查是否过期"""
        if not self.expires_at:
            return False
        return datetime.now().isoformat() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "key": self.key,
            "value": self.value,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """从字典反序列化"""
        return cls(
            key=data["key"],
            value=data["value"],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at"),
        )
