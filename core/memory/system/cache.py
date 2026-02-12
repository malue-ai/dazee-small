"""
Cache Memory - 系统缓存（预留）

职责：
- 存储系统级缓存数据
- 支持 TTL 过期
- 支持 LRU 淘汰

设计原则：
- 系统级：全局共享
- 高性能：内存优先
- 可配置：支持 TTL 和大小限制
"""

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from logger import get_logger

from ..base import BaseMemory, MemoryConfig, MemoryScope, StorageBackend

logger = get_logger("memory.system.cache")


class CacheMemory(BaseMemory):
    """
    系统缓存记忆（预留）

    特性：
    - TTL 过期：支持设置缓存过期时间
    - LRU 淘汰：超过最大容量时淘汰最少使用的
    """

    def __init__(self, max_size: int = 1000, default_ttl_seconds: int = 3600):
        """
        Args:
            max_size: 最大缓存条目数
            default_ttl_seconds: 默认 TTL（秒）
        """
        config = MemoryConfig(
            scope=MemoryScope.SYSTEM, backend=StorageBackend.MEMORY, ttl_seconds=default_ttl_seconds
        )
        super().__init__(config)

        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """
        设置缓存

        Args:
            key: 缓存 key
            value: 缓存值
            ttl_seconds: TTL（秒），None 则使用默认值
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = None
        if ttl > 0:
            expires_at = (datetime.now() + timedelta(seconds=ttl)).isoformat()

        # 如果 key 已存在，先删除（更新顺序）
        if key in self._cache:
            del self._cache[key]

        self._cache[key] = {
            "value": value,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at,
        }

        # LRU 淘汰
        while len(self._cache) > self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存

        Args:
            key: 缓存 key
            default: 默认值（缓存不存在或已过期时返回）
        """
        entry = self._cache.get(key)
        if not entry:
            return default

        # 检查是否过期
        expires_at = entry.get("expires_at")
        if expires_at and datetime.now().isoformat() > expires_at:
            del self._cache[key]
            return default

        # 更新访问顺序（LRU）
        self._cache.move_to_end(key)

        return entry.get("value", default)

    def delete(self, key: str) -> None:
        """删除缓存"""
        if key in self._cache:
            del self._cache[key]

    def has(self, key: str) -> bool:
        """检查缓存是否存在且未过期"""
        return self.get(key) is not None

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()

    def cleanup_expired(self) -> None:
        """清理过期缓存"""
        now = datetime.now().isoformat()
        expired_keys = [
            k for k, v in self._cache.items() if v.get("expires_at") and v["expires_at"] < now
        ]
        for key in expired_keys:
            del self._cache[key]

    def size(self) -> int:
        """获取当前缓存条目数"""
        return len(self._cache)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        base = super().to_dict()
        base.update(
            {
                "size": self.size(),
                "max_size": self.max_size,
                "default_ttl_seconds": self.default_ttl_seconds,
            }
        )
        return base


def create_cache_memory(max_size: int = 1000, default_ttl_seconds: int = 3600) -> CacheMemory:
    """
    创建 CacheMemory 实例

    Args:
        max_size: 最大缓存条目数
        default_ttl_seconds: 默认 TTL（秒）
    """
    return CacheMemory(max_size=max_size, default_ttl_seconds=default_ttl_seconds)
