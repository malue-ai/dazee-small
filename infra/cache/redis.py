"""
Redis 客户端 - 基础设施层

提供 Redis 连接和基础操作封装

职责：
- Redis 连接管理
- 基础操作封装（get/set/incr/hash/list 等）
- 连接池管理
- 自动降级（无 Redis 时）

使用示例：
    from infra.cache import get_redis_client, RedisClient
    
    # 获取客户端（单例）
    redis = await get_redis_client()
    
    # 基础操作
    await redis.set("key", "value", ttl=3600)
    value = await redis.get("key")
"""

import os
from typing import Optional, Any, Dict, List, Union
from datetime import datetime

from logger import get_logger

logger = get_logger("infra.cache.redis")


class RedisClient:
    """
    Redis 客户端封装
    
    提供统一的 Redis 操作接口，支持：
    - 自动连接管理
    - 操作封装
    - 无 Redis 时返回 None（不抛异常）
    """
    
    def __init__(self, client=None):
        """
        初始化 Redis 客户端
        
        Args:
            client: redis.asyncio.Redis 实例（可选）
        """
        self._client = client
        self._connected = client is not None
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self._client is not None
    
    # ==================== 基础操作 ====================
    
    async def get(self, key: str) -> Optional[str]:
        """获取值"""
        if not self._client:
            return None
        try:
            value = await self._client.get(key)
            if value and isinstance(value, bytes):
                return value.decode()
            return value
        except Exception as e:
            logger.error(f"Redis GET 失败: {key}, error={str(e)}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: str, 
        ttl: Optional[int] = None
    ) -> bool:
        """设置值"""
        if not self._client:
            return False
        try:
            if ttl:
                await self._client.set(key, value, ex=ttl)
            else:
                await self._client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Redis SET 失败: {key}, error={str(e)}")
            return False
    
    async def delete(self, *keys: str) -> int:
        """删除键"""
        if not self._client or not keys:
            return 0
        try:
            return await self._client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE 失败: {keys}, error={str(e)}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self._client:
            return False
        try:
            return await self._client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS 失败: {key}, error={str(e)}")
            return False
    
    async def expire(self, key: str, ttl: int) -> bool:
        """设置过期时间"""
        if not self._client:
            return False
        try:
            return await self._client.expire(key, ttl)
        except Exception as e:
            logger.error(f"Redis EXPIRE 失败: {key}, error={str(e)}")
            return False
    
    # ==================== 计数器操作 ====================
    
    async def incr(self, key: str) -> int:
        """递增（返回递增后的值）"""
        if not self._client:
            return 0
        try:
            return await self._client.incr(key)
        except Exception as e:
            logger.error(f"Redis INCR 失败: {key}, error={str(e)}")
            return 0
    
    async def decr(self, key: str) -> int:
        """递减"""
        if not self._client:
            return 0
        try:
            return await self._client.decr(key)
        except Exception as e:
            logger.error(f"Redis DECR 失败: {key}, error={str(e)}")
            return 0
    
    # ==================== Hash 操作 ====================
    
    async def hset(self, key: str, mapping: Dict[str, str]) -> bool:
        """设置 Hash 字段"""
        if not self._client or not mapping:
            return False
        try:
            await self._client.hset(key, mapping=mapping)
            return True
        except Exception as e:
            logger.error(f"Redis HSET 失败: {key}, error={str(e)}")
            return False
    
    async def hget(self, key: str, field: str) -> Optional[str]:
        """获取 Hash 字段"""
        if not self._client:
            return None
        try:
            value = await self._client.hget(key, field)
            if value and isinstance(value, bytes):
                return value.decode()
            return value
        except Exception as e:
            logger.error(f"Redis HGET 失败: {key}.{field}, error={str(e)}")
            return None
    
    async def hgetall(self, key: str) -> Dict[str, str]:
        """获取所有 Hash 字段"""
        if not self._client:
            return {}
        try:
            data = await self._client.hgetall(key)
            # 解码 bytes
            return {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()
            }
        except Exception as e:
            logger.error(f"Redis HGETALL 失败: {key}, error={str(e)}")
            return {}
    
    # ==================== List 操作 ====================
    
    async def rpush(self, key: str, *values: str) -> int:
        """从右侧推入列表"""
        if not self._client or not values:
            return 0
        try:
            return await self._client.rpush(key, *values)
        except Exception as e:
            logger.error(f"Redis RPUSH 失败: {key}, error={str(e)}")
            return 0
    
    async def lpush(self, key: str, *values: str) -> int:
        """从左侧推入列表"""
        if not self._client or not values:
            return 0
        try:
            return await self._client.lpush(key, *values)
        except Exception as e:
            logger.error(f"Redis LPUSH 失败: {key}, error={str(e)}")
            return 0
    
    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        """获取列表范围"""
        if not self._client:
            return []
        try:
            data = await self._client.lrange(key, start, end)
            return [
                v.decode() if isinstance(v, bytes) else v
                for v in data
            ]
        except Exception as e:
            logger.error(f"Redis LRANGE 失败: {key}, error={str(e)}")
            return []
    
    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """裁剪列表"""
        if not self._client:
            return False
        try:
            await self._client.ltrim(key, start, end)
            return True
        except Exception as e:
            logger.error(f"Redis LTRIM 失败: {key}, error={str(e)}")
            return False
    
    async def llen(self, key: str) -> int:
        """获取列表长度"""
        if not self._client:
            return 0
        try:
            return await self._client.llen(key)
        except Exception as e:
            logger.error(f"Redis LLEN 失败: {key}, error={str(e)}")
            return 0
    
    # ==================== Pub/Sub 操作 ====================
    
    async def publish(self, channel: str, message: str) -> int:
        """发布消息"""
        if not self._client:
            return 0
        try:
            return await self._client.publish(channel, message)
        except Exception as e:
            logger.error(f"Redis PUBLISH 失败: {channel}, error={str(e)}")
            return 0
    
    def pubsub(self):
        """获取 PubSub 对象"""
        if not self._client:
            return None
        return self._client.pubsub()
    
    # ==================== 连接管理 ====================
    
    async def ping(self) -> bool:
        """测试连接"""
        if not self._client:
            return False
        try:
            return await self._client.ping()
        except Exception:
            return False
    
    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.close()
            self._connected = False
            logger.info("✅ Redis 连接已关闭")


# ==================== 单例管理 ====================

_redis_client: Optional[RedisClient] = None


async def create_redis_client(redis_url: str = None) -> RedisClient:
    """
    创建 Redis 客户端
    
    Args:
        redis_url: Redis URL（可选，默认从环境变量读取）
        
    Returns:
        RedisClient 实例
    """
    redis_url = redis_url or os.getenv("REDIS_URL")
    
    if not redis_url:
        logger.warning("⚠️ 未配置 REDIS_URL，Redis 功能不可用")
        return RedisClient(None)
    
    try:
        import redis.asyncio as aioredis
        
        client = aioredis.from_url(redis_url, decode_responses=False)
        # 测试连接
        await client.ping()
        
        logger.info(f"✅ Redis 客户端已连接: {redis_url}")
        return RedisClient(client)
        
    except ImportError:
        logger.warning("⚠️ redis 包未安装，Redis 功能不可用")
        return RedisClient(None)
    except Exception as e:
        logger.warning(f"⚠️ Redis 连接失败: {str(e)}")
        return RedisClient(None)


async def get_redis_client() -> RedisClient:
    """
    获取 Redis 客户端（单例）
    
    Returns:
        RedisClient 实例
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = await create_redis_client()
    return _redis_client


def get_redis_client_sync() -> Optional[RedisClient]:
    """
    同步获取 Redis 客户端（如果已初始化）
    
    Returns:
        RedisClient 实例或 None
    """
    return _redis_client

