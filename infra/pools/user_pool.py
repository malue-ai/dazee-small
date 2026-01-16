"""
用户池 - UserPool

职责：
- 用户活跃 Session 追踪
- 用户统计（调用次数、Token 消耗等）
- 预留限流接口（未来扩展）

设计原则：
- 轻量级：现阶段只做追踪和统计，不做强制限流
- 纯 Redis：所有状态存储在 Redis，支持分布式部署
- 可扩展：预留 check_rate_limit 接口，方便未来加入限流

Redis Key 设计：
- zf:user:{user_id}:sessions    # Set: 用户活跃 Session 列表
- zf:user:{user_id}:stats       # Hash: 用户统计
- zf:user:{user_id}:context     # Hash: 用户上下文缓存
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from logger import get_logger

logger = get_logger("user_pool")


class UserPool:
    """
    用户池
    
    使用方式：
        pool = get_user_pool()
        
        # 添加 Session
        count = await pool.add_session("user_123", "sess_abc")
        
        # 获取用户活跃 Session
        sessions = await pool.get_active_sessions("user_123")
        
        # 统计
        await pool.increment_stat("user_123", "api_calls")
        stats = await pool.get_stats("user_123")
    """
    
    # Redis Key 前缀
    KEY_PREFIX = "zf:user"
    
    def __init__(self, redis_manager):
        """
        初始化用户池
        
        Args:
            redis_manager: RedisSessionManager 实例
        """
        self.redis = redis_manager
        
        # 配置
        self.max_concurrent_sessions = int(os.getenv("POOL_USER_MAX_CONCURRENT", "5"))
        self.context_ttl_seconds = int(os.getenv("POOL_USER_CONTEXT_TTL", "3600"))
        
        logger.info(
            f"✅ UserPool 初始化完成: "
            f"max_concurrent={self.max_concurrent_sessions}, "
            f"context_ttl={self.context_ttl_seconds}s"
        )
    
    # ==================== Session 追踪 ====================
    
    async def add_session(self, user_id: str, session_id: str) -> int:
        """
        添加用户的活跃 Session
        
        Args:
            user_id: 用户 ID
            session_id: Session ID
            
        Returns:
            当前活跃 Session 数量
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:sessions"
        
        # 添加到集合
        await client.sadd(key, session_id)
        
        # 设置过期时间（防止泄漏）
        await client.expire(key, 3600)  # 1 小时
        
        # 返回当前数量
        count = await client.scard(key)
        
        logger.debug(f"📥 用户 {user_id} 添加 Session: {session_id}, 当前活跃: {count}")
        
        return count
    
    async def remove_session(self, user_id: str, session_id: str) -> int:
        """
        移除用户的活跃 Session
        
        Args:
            user_id: 用户 ID
            session_id: Session ID
            
        Returns:
            当前活跃 Session 数量
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:sessions"
        
        # 从集合移除
        await client.srem(key, session_id)
        
        # 返回当前数量
        count = await client.scard(key)
        
        logger.debug(f"📤 用户 {user_id} 移除 Session: {session_id}, 当前活跃: {count}")
        
        return count
    
    async def get_active_sessions(self, user_id: str) -> List[str]:
        """
        获取用户的所有活跃 Session
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session ID 列表
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:sessions"
        
        sessions = await client.smembers(key)
        return list(sessions) if sessions else []
    
    async def get_active_session_count(self, user_id: str) -> int:
        """
        获取用户活跃 Session 数量
        
        Args:
            user_id: 用户 ID
            
        Returns:
            活跃 Session 数量
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:sessions"
        
        return await client.scard(key)
    
    # ==================== 限流检查（预留） ====================
    
    async def check_can_create_session(self, user_id: str) -> bool:
        """
        检查用户是否可以创建新 Session
        
        当前实现：只检查并发数量（软限制，只记录警告）
        未来扩展：可以加入更严格的限流逻辑
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否允许创建（当前始终返回 True，但会记录警告）
        """
        current_count = await self.get_active_session_count(user_id)
        
        if current_count >= self.max_concurrent_sessions:
            logger.warning(
                f"⚠️ 用户 {user_id} 并发 Session 数量超限: "
                f"{current_count}/{self.max_concurrent_sessions}"
            )
            # 当前只警告，不阻止（未来可改为 return False）
        
        return True
    
    async def check_rate_limit(self, user_id: str, action: str = "api_call") -> bool:
        """
        检查用户是否触发限流（预留接口）
        
        当前实现：始终返回 True（不限流）
        未来扩展：可以实现滑动窗口限流、令牌桶等算法
        
        Args:
            user_id: 用户 ID
            action: 操作类型
            
        Returns:
            是否允许操作（当前始终返回 True）
        """
        # TODO: 未来实现限流逻辑
        # 例如：滑动窗口限流
        # key = f"{self.KEY_PREFIX}:{user_id}:rate:{action}"
        # count = await client.incr(key)
        # if count == 1:
        #     await client.expire(key, 60)  # 1 分钟窗口
        # return count <= self.rate_limit_per_minute
        
        return True
    
    # ==================== 用户统计 ====================
    
    async def increment_stat(
        self, 
        user_id: str, 
        stat_name: str, 
        amount: int = 1
    ) -> int:
        """
        增加用户统计计数
        
        Args:
            user_id: 用户 ID
            stat_name: 统计项名称（如 api_calls, tokens_used）
            amount: 增加量
            
        Returns:
            增加后的值
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:stats"
        
        new_value = await client.hincrby(key, stat_name, amount)
        
        # 更新最后活跃时间
        await client.hset(key, "last_active", datetime.now().isoformat())
        
        return new_value
    
    async def get_stats(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户统计信息
        
        Args:
            user_id: 用户 ID
            
        Returns:
            统计信息字典
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:stats"
        
        stats = await client.hgetall(key)
        
        if not stats:
            return {
                "user_id": user_id,
                "api_calls": 0,
                "sessions_created": 0,
                "last_active": None
            }
        
        # 转换数字类型
        result = {"user_id": user_id}
        for k, v in stats.items():
            if k == "last_active":
                result[k] = v
            else:
                try:
                    result[k] = int(v)
                except (ValueError, TypeError):
                    result[k] = v
        
        return result
    
    async def reset_stats(self, user_id: str) -> None:
        """
        重置用户统计
        
        Args:
            user_id: 用户 ID
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:stats"
        
        await client.delete(key)
        logger.info(f"🔄 用户 {user_id} 统计已重置")
    
    # ==================== 用户上下文（可选） ====================
    
    async def get_context(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户上下文缓存
        
        Args:
            user_id: 用户 ID
            
        Returns:
            上下文字典
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:context"
        
        context = await client.hgetall(key)
        return context if context else {}
    
    async def set_context(self, user_id: str, **fields) -> None:
        """
        设置用户上下文缓存
        
        Args:
            user_id: 用户 ID
            **fields: 要设置的字段
        """
        if not fields:
            return
        
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{user_id}:context"
        
        # 转换为字符串
        str_fields = {k: str(v) for k, v in fields.items() if v is not None}
        
        await client.hset(key, mapping=str_fields)
        await client.expire(key, self.context_ttl_seconds)
    
    # ==================== 清理 ====================
    
    async def cleanup(self) -> None:
        """
        清理资源（关闭时调用）
        """
        logger.info("🧹 UserPool 清理完成")


# ==================== 单例 ====================

_user_pool: Optional[UserPool] = None


def get_user_pool() -> UserPool:
    """
    获取 UserPool 单例
    
    Returns:
        UserPool 实例
    """
    global _user_pool
    if _user_pool is None:
        from services.redis_manager import get_redis_manager
        _user_pool = UserPool(redis_manager=get_redis_manager())
    return _user_pool


def reset_user_pool() -> None:
    """
    重置单例（仅用于测试）
    """
    global _user_pool
    _user_pool = None
