"""
序号管理器 - SeqManager

职责：
1. 生成 session 内递增序号（从 1 开始）
2. 支持 Redis（生产）和内存（开发）两种模式
3. 保证序号的原子性和唯一性

设计原则：
- 序号在 EventBroadcaster 层统一生成
- 无论事件走哪条路径（EventManager 或 EventDispatcher），seq 都是一致的
"""

from collections import defaultdict
from typing import Dict, Optional

from logger import get_logger

logger = get_logger("events.seq_manager")


class SeqManager:
    """
    序号管理器
    
    负责生成 session 内递增序号，支持 Redis 和内存两种存储方式。
    
    使用示例：
        seq_manager = SeqManager(redis_client)
        seq = await seq_manager.get_next_seq(session_id)
    """
    
    def __init__(
        self,
        redis_client=None,
        key_prefix: str = "zenflux"
    ):
        """
        初始化序号管理器
        
        Args:
            redis_client: Redis 客户端（可选，为空时使用内存存储）
            key_prefix: Redis Key 前缀
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        
        # 内存存储（降级方案）
        self._memory_seq: Dict[str, int] = defaultdict(int)
    
    def _key(self, session_id: str) -> str:
        """生成 Redis Key"""
        return f"{self.key_prefix}:session:{session_id}:seq"
    
    @property
    def is_redis_available(self) -> bool:
        """检查 Redis 是否可用"""
        return self.redis is not None and self.redis.is_connected
    
    async def get_next_seq(self, session_id: str) -> int:
        """
        获取下一个序号（原子操作）
        
        Args:
            session_id: Session ID
            
        Returns:
            序号（从 1 开始递增）
        """
        if self.is_redis_available:
            try:
                key = self._key(session_id)
                seq = await self.redis.incr(key)
                
                # 首次创建时设置 TTL（1小时）
                if seq == 1:
                    await self.redis.expire(key, 3600)
                
                return seq
            except Exception as e:
                logger.warning(f"Redis 序号生成失败，降级到内存: {e}")
                # 降级到内存
                self._memory_seq[session_id] += 1
                return self._memory_seq[session_id]
        else:
            # 使用内存存储
            self._memory_seq[session_id] += 1
            return self._memory_seq[session_id]
    
    async def get_current_seq(self, session_id: str) -> int:
        """
        获取当前序号（不递增）
        
        Args:
            session_id: Session ID
            
        Returns:
            当前序号，如果不存在返回 0
        """
        if self.is_redis_available:
            try:
                key = self._key(session_id)
                seq = await self.redis.get(key)
                return int(seq) if seq else 0
            except Exception:
                return self._memory_seq.get(session_id, 0)
        else:
            return self._memory_seq.get(session_id, 0)
    
    async def reset_seq(self, session_id: str) -> None:
        """
        重置序号（用于 session 清理）
        
        Args:
            session_id: Session ID
        """
        if self.is_redis_available:
            try:
                key = self._key(session_id)
                await self.redis.delete(key)
            except Exception as e:
                logger.warning(f"Redis 序号重置失败: {e}")
        
        # 同时清理内存
        self._memory_seq.pop(session_id, None)
    
    def reset_memory_seq(self, session_id: str) -> None:
        """重置内存序号（同步方法）"""
        self._memory_seq.pop(session_id, None)


# ==================== 工厂函数 ====================

_default_seq_manager: Optional[SeqManager] = None


async def create_seq_manager(redis_client=None) -> SeqManager:
    """
    创建序号管理器
    
    Args:
        redis_client: Redis 客户端（可选）
        
    Returns:
        SeqManager 实例
    """
    global _default_seq_manager
    
    # 如果提供了 Redis 客户端
    if redis_client:
        return SeqManager(redis_client=redis_client)
    
    # 尝试从 infra.cache 获取
    try:
        from infra.cache import get_redis_client
        client = await get_redis_client()
        if client and client.is_connected:
            logger.info("✅ SeqManager 使用 Redis 存储")
            return SeqManager(redis_client=client)
    except Exception as e:
        logger.debug(f"无法获取 Redis 客户端: {e}")
    
    # 降级到内存
    if _default_seq_manager is None:
        _default_seq_manager = SeqManager()
        logger.info("📦 SeqManager 使用内存存储（开发模式）")
    
    return _default_seq_manager


def get_memory_seq_manager() -> SeqManager:
    """
    获取内存序号管理器（单例）
    
    Returns:
        SeqManager 实例（内存模式）
    """
    global _default_seq_manager
    if _default_seq_manager is None:
        _default_seq_manager = SeqManager()
    return _default_seq_manager
