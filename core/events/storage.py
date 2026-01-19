"""
事件存储 - EventStorage

实现 EventStorage Protocol，提供事件缓冲和断线重连支持

实现类：
1. RedisEventStorage - 生产环境，Redis 存储
2. InMemoryEventStorage - 开发环境，内存存储

Redis Key 设计：
- zenflux:session:{session_id}:seq       → 序号计数器
- zenflux:session:{session_id}:context   → Session 上下文
- zenflux:session:{session_id}:events    → 事件列表（支持断线重连）
- zenflux:session:{session_id}:heartbeat → 心跳时间戳
"""

# 1. 标准库
import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List, Optional

# 2. 第三方库（无）

# 3. 本地模块
from infra.cache import get_redis_client
from logger import get_logger

logger = get_logger("events.storage")


class RedisEventStorage:
    """
    Redis 事件存储
    
    实现 EventStorage 协议，使用 RedisClient 进行存储
    
    特性：
    - Session 内递增序号
    - 事件持久化缓冲
    - 支持断线重连
    - 自动过期清理
    """
    
    def __init__(
        self,
        redis_client,  # infra.cache.RedisClient
        key_prefix: str = "zenflux",
        event_ttl: int = 3600,  # 事件保留时间（秒）
        max_events: int = 1000  # 每个 Session 最大事件数
    ):
        """
        初始化事件存储
        
        Args:
            redis_client: RedisClient 实例
            key_prefix: Key 前缀
            event_ttl: 事件 TTL（秒）
            max_events: 每 Session 最大事件数
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.event_ttl = event_ttl
        self.max_events = max_events
    
    def _key(self, *parts: str) -> str:
        """生成 Redis Key"""
        return f"{self.key_prefix}:{':'.join(parts)}"
    
    @property
    def is_available(self) -> bool:
        """检查存储是否可用"""
        return self.redis is not None and self.redis.is_connected
    
    # ==================== EventStorage Protocol ====================
    
    async def generate_session_seq(self, session_id: str) -> int:
        """
        生成 Session 内的事件序号（从 1 开始递增）
        """
        if not self.is_available:
            return 0
        
        key = self._key("session", session_id, "seq")
        seq = await self.redis.incr(key)
        
        # 设置 TTL（如果是新创建的）
        if seq == 1:
            await self.redis.expire(key, self.event_ttl)
        
        return seq
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 Session 上下文"""
        if not self.is_available:
            return {}
        
        key = self._key("session", session_id, "context")
        return await self.redis.hgetall(key)
    
    async def set_session_context(
        self,
        session_id: str,
        conversation_id: str = None,
        user_id: str = None,
        **extra
    ) -> None:
        """设置 Session 上下文"""
        if not self.is_available:
            return
        
        key = self._key("session", session_id, "context")
        
        context = {}
        if conversation_id:
            context["conversation_id"] = conversation_id
        if user_id:
            context["user_id"] = user_id
        context.update(extra)
        
        if context:
            await self.redis.hset(key, context)
            await self.redis.expire(key, self.event_ttl)
    
    async def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any]
    ) -> None:
        """缓冲事件"""
        if not self.is_available:
            return
        
        key = self._key("session", session_id, "events")
        
        # 序列化事件
        event_json = json.dumps(event_data, ensure_ascii=False)
        
        # 添加到列表尾部
        await self.redis.rpush(key, event_json)
        
        # 限制列表长度
        await self.redis.ltrim(key, -self.max_events, -1)
        
        # 更新 TTL
        await self.redis.expire(key, self.event_ttl)
    
    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳时间戳"""
        if not self.is_available:
            return
        
        key = self._key("session", session_id, "heartbeat")
        await self.redis.set(key, datetime.now().isoformat(), ttl=self.event_ttl)
    
    # ==================== 扩展方法（断线重连支持）====================
    
    async def get_events_since(
        self,
        session_id: str,
        last_seq: int
    ) -> List[Dict[str, Any]]:
        """
        获取指定序号之后的所有事件（断线重连）
        
        Args:
            session_id: Session ID
            last_seq: 客户端收到的最后一个序号
            
        Returns:
            序号大于 last_seq 的事件列表
        """
        if not self.is_available:
            return []
        
        key = self._key("session", session_id, "events")
        events_raw = await self.redis.lrange(key, 0, -1)
        
        events = []
        for event_json in events_raw:
            try:
                event = json.loads(event_json)
                if event.get("seq", 0) > last_seq:
                    events.append(event)
            except json.JSONDecodeError:
                continue
        
        return events
    
    async def get_latest_events(
        self,
        session_id: str,
        count: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的 N 个事件"""
        if not self.is_available:
            return []
        
        key = self._key("session", session_id, "events")
        events_raw = await self.redis.lrange(key, -count, -1)
        
        events = []
        for event_json in events_raw:
            try:
                events.append(json.loads(event_json))
            except json.JSONDecodeError:
                continue
        
        return events
    
    async def get_current_seq(self, session_id: str) -> int:
        """获取当前序号（不递增）"""
        if not self.is_available:
            return 0
        
        key = self._key("session", session_id, "seq")
        seq = await self.redis.get(key)
        return int(seq) if seq else 0
    
    async def cleanup_session(self, session_id: str) -> None:
        """清理 Session 数据"""
        if not self.is_available:
            return
        
        keys = [
            self._key("session", session_id, "seq"),
            self._key("session", session_id, "context"),
            self._key("session", session_id, "events"),
            self._key("session", session_id, "heartbeat"),
        ]
        
        await self.redis.delete(*keys)
        logger.info(f"🧹 Session 数据已清理: session_id={session_id}")


class InMemoryEventStorage:
    """
    内存事件存储（无 Redis 时的降级方案）
    
    实现 EventStorage 协议，使用内存存储
    
    注意：
    - 不支持跨进程/跨实例
    - 不支持持久化
    - 适用于单实例开发环境
    """
    
    def __init__(self, max_events: int = 1000):
        """初始化内存存储"""
        self.max_events = max_events
        
        # 存储结构
        self._seq: Dict[str, int] = defaultdict(int)
        self._context: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._heartbeat: Dict[str, str] = {}
    
    @property
    def is_available(self) -> bool:
        """内存存储始终可用"""
        return True
    
    # ==================== EventStorage Protocol ====================
    
    async def generate_session_seq(self, session_id: str) -> int:
        """生成 Session 内的事件序号"""
        self._seq[session_id] += 1
        return self._seq[session_id]
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 Session 上下文"""
        return self._context.get(session_id, {})
    
    async def set_session_context(
        self,
        session_id: str,
        conversation_id: str = None,
        user_id: str = None,
        **extra
    ) -> None:
        """设置 Session 上下文"""
        context = self._context.get(session_id, {})
        if conversation_id:
            context["conversation_id"] = conversation_id
        if user_id:
            context["user_id"] = user_id
        context.update(extra)
        self._context[session_id] = context
    
    async def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any]
    ) -> None:
        """缓冲事件"""
        events = self._events[session_id]
        events.append(event_data)
        
        # 限制数量
        if len(events) > self.max_events:
            self._events[session_id] = events[-self.max_events:]
    
    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        self._heartbeat[session_id] = datetime.now().isoformat()
    
    # ==================== 扩展方法 ====================
    
    async def get_events_since(
        self,
        session_id: str,
        last_seq: int
    ) -> List[Dict[str, Any]]:
        """获取指定序号之后的所有事件"""
        events = self._events.get(session_id, [])
        return [e for e in events if e.get("seq", 0) > last_seq]
    
    async def get_latest_events(
        self,
        session_id: str,
        count: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的 N 个事件"""
        events = self._events.get(session_id, [])
        return events[-count:]
    
    async def get_current_seq(self, session_id: str) -> int:
        """获取当前序号"""
        return self._seq.get(session_id, 0)
    
    async def cleanup_session(self, session_id: str) -> None:
        """清理 Session 数据"""
        self._seq.pop(session_id, None)
        self._context.pop(session_id, None)
        self._events.pop(session_id, None)
        self._heartbeat.pop(session_id, None)
        logger.info(f"🧹 Session 内存数据已清理: session_id={session_id}")


# ==================== 工厂函数 ====================

_default_storage: Optional[InMemoryEventStorage] = None


async def create_event_storage(redis_client=None) -> RedisEventStorage:
    """
    创建事件存储
    
    Args:
        redis_client: RedisClient 实例（可选）
        
    Returns:
        EventStorage 实例（Redis 或内存）
    """
    global _default_storage
    
    # 如果提供了 Redis 客户端且已连接
    if redis_client and redis_client.is_connected:
        logger.info("✅ 使用 Redis 事件存储")
        return RedisEventStorage(redis_client=redis_client)
    
    # 尝试从 infra.cache 获取
    try:
        client = await get_redis_client()
        if client.is_connected:
            logger.info("✅ 使用 Redis 事件存储")
            return RedisEventStorage(redis_client=client)
    except Exception as e:
        logger.debug(f"无法获取 Redis 客户端: {str(e)}")
    
    # 降级到内存存储
    if _default_storage is None:
        _default_storage = InMemoryEventStorage()
        logger.info("📦 使用内存事件存储（开发模式）")
    
    return _default_storage


def get_memory_storage() -> InMemoryEventStorage:
    """
    获取内存存储实例（单例）
    
    Returns:
        InMemoryEventStorage 实例
    """
    global _default_storage
    if _default_storage is None:
        _default_storage = InMemoryEventStorage()
    return _default_storage

