"""
缓存模块

提供 Redis 缓存服务，用于：
- Session 状态缓存
- 分布式锁
- Pub/Sub 消息
- 计数器/限流
"""

from infra.cache.redis import (
    RedisClient,
    create_redis_client,
    get_redis_client,
    get_redis_client_sync,
)

__all__ = [
    "RedisClient",
    "create_redis_client",
    "get_redis_client",
    "get_redis_client_sync",
]
