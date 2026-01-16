"""
Session 池 - SessionPool

职责：
- 追踪所有活跃 Session（使用 Redis Set 可靠存储）
- 整合 UserPool 和 AgentPool 的数据
- 提供系统级统计视图
- 提供校准机制（清理孤立 Session）

设计原则：
- 只追踪 Session 集合，不管理单个 Session 的生命周期（那是 SessionService 的事）
- 可靠追踪：使用 Set 存储活跃 Session，而非简单计数器
- 可测试：支持依赖注入和实例重置

与 SessionService 的区别：
- SessionService (services/session_service.py): 管理单个 Session 的生命周期（创建、结束、停止、查询）
- SessionPool (infra/pools/session_pool.py): 追踪所有活跃 Session 的集合，提供系统统计

Redis Key 设计：
- zf:sessions:active             # Set: 所有活跃 Session ID（可靠追踪）
- zf:sessions:meta:{session_id}  # Hash: Session 元数据（user_id, agent_id, start_time）

使用方式：
    pool = get_session_pool()
    
    # 获取系统整体统计
    stats = await pool.get_system_stats()
    
    # Session 开始时调用（更新 UserPool + AgentPool）
    await pool.on_session_start(session_id, user_id, agent_id)
    
    # Session 结束时调用（更新 UserPool + AgentPool）
    await pool.on_session_end(session_id, user_id, agent_id)
    
    # 校准计数（定期调用或重启时调用）
    await pool.calibrate()
"""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from logger import get_logger
from .user_pool import UserPool, get_user_pool
from .agent_pool import AgentPool, get_agent_pool

if TYPE_CHECKING:
    pass

logger = get_logger("session_pool")


class SessionPool:
    """
    Session 池
    
    追踪所有活跃 Session 的集合，整合 UserPool 和 AgentPool 数据，
    提供系统级统计视图。
    
    注意：Session 的创建/结束由 SessionService 负责，
    本类只负责追踪和统计。
    """
    
    # Redis Key
    ACTIVE_SESSIONS_KEY = "zf:sessions:active"  # Set: 活跃 Session ID
    SESSION_META_PREFIX = "zf:sessions:meta"    # Hash: Session 元数据
    SESSION_META_TTL = 7200  # Session 元数据过期时间（2 小时）
    
    def __init__(
        self,
        redis_manager,
        user_pool: Optional[UserPool] = None,
        agent_pool: Optional[AgentPool] = None
    ):
        """
        初始化 Session 池
        
        Args:
            redis_manager: RedisSessionManager 实例
            user_pool: UserPool 实例（可选，默认使用单例）
            agent_pool: AgentPool 实例（可选，默认使用单例）
        """
        self.redis = redis_manager
        self.user_pool = user_pool or get_user_pool()
        self.agent_pool = agent_pool or get_agent_pool()
        
        logger.info("✅ SessionPool 初始化完成")
    
    # ==================== Session 生命周期钩子 ====================
    
    async def on_session_start(
        self,
        session_id: str,
        user_id: str,
        agent_id: str
    ) -> None:
        """
        Session 开始时调用（由 ChatService 在创建 Session 后调用）
        
        更新 UserPool 和 AgentPool 的追踪状态，并记录 Session 元数据
        
        Args:
            session_id: Session ID
            user_id: 用户 ID
            agent_id: Agent ID
        """
        client = await self.redis._get_client()
        
        # 1. 添加到活跃 Session 集合（可靠追踪）
        await client.sadd(self.ACTIVE_SESSIONS_KEY, session_id)
        
        # 2. 存储 Session 元数据（用于校准和调试）
        meta_key = f"{self.SESSION_META_PREFIX}:{session_id}"
        await client.hset(meta_key, mapping={
            "user_id": user_id,
            "agent_id": agent_id,
            "start_time": datetime.now().isoformat(),
        })
        await client.expire(meta_key, self.SESSION_META_TTL)
        
        # 3. 更新 UserPool
        await self.user_pool.add_session(user_id, session_id)
        await self.user_pool.increment_stat(user_id, "sessions_created")
        
        # 4. 更新 AgentPool 统计（实例计数已在 acquire 时完成）
        await self.agent_pool.increment_stat(agent_id, "sessions_started")
        
        logger.debug(
            f"📊 Session 开始: session_id={session_id}, "
            f"user_id={user_id}, agent_id={agent_id}"
        )
    
    async def on_session_end(
        self,
        session_id: str,
        user_id: str,
        agent_id: str
    ) -> None:
        """
        Session 结束时调用（由 ChatService 在结束 Session 后调用）
        
        更新 UserPool 和 AgentPool 的追踪状态
        
        Args:
            session_id: Session ID
            user_id: 用户 ID
            agent_id: Agent ID
        """
        client = await self.redis._get_client()
        
        # 1. 从活跃 Session 集合移除
        await client.srem(self.ACTIVE_SESSIONS_KEY, session_id)
        
        # 2. 删除 Session 元数据
        meta_key = f"{self.SESSION_META_PREFIX}:{session_id}"
        await client.delete(meta_key)
        
        # 3. 更新 UserPool
        await self.user_pool.remove_session(user_id, session_id)
        
        # 4. 更新 AgentPool 统计
        await self.agent_pool.increment_stat(agent_id, "sessions_completed")
        
        logger.debug(
            f"📊 Session 结束: session_id={session_id}, "
            f"user_id={user_id}, agent_id={agent_id}"
        )
    
    # ==================== 检查方法 ====================
    
    async def check_can_create_session(self, user_id: str) -> bool:
        """
        检查是否可以创建新 Session
        
        委托给 UserPool
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否允许创建
        """
        return await self.user_pool.check_can_create_session(user_id)
    
    async def is_session_active(self, session_id: str) -> bool:
        """
        检查 Session 是否活跃
        
        Args:
            session_id: Session ID
            
        Returns:
            是否活跃
        """
        client = await self.redis._get_client()
        return await client.sismember(self.ACTIVE_SESSIONS_KEY, session_id)
    
    # ==================== 统计视图 ====================
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """
        获取系统整体统计
        
        Returns:
            系统统计信息
        """
        # Agent 统计
        agent_stats = await self.agent_pool.get_stats()
        
        # 从 Set 获取活跃 Session 数量（可靠）
        active_sessions = await self._count_active_sessions()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "sessions": {
                "active": active_sessions,
            },
            "agents": agent_stats,
            "prototypes": self.agent_pool.list_prototypes(),
        }
    
    async def _count_active_sessions(self) -> int:
        """
        获取活跃 Session 数量（从 Set 读取，可靠）
        
        Returns:
            活跃 Session 数量
        """
        try:
            client = await self.redis._get_client()
            count = await client.scard(self.ACTIVE_SESSIONS_KEY)
            return count if count else 0
        except Exception as e:
            logger.warning(f"⚠️ 获取活跃 Session 数量失败: {e}")
            return -1
    
    async def get_active_sessions(self) -> List[str]:
        """
        获取所有活跃 Session ID 列表
        
        Returns:
            Session ID 列表
        """
        try:
            client = await self.redis._get_client()
            sessions = await client.smembers(self.ACTIVE_SESSIONS_KEY)
            return list(sessions) if sessions else []
        except Exception as e:
            logger.warning(f"⚠️ 获取活跃 Session 列表失败: {e}")
            return []
    
    async def get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 Session 元数据
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 元数据（user_id, agent_id, start_time）
        """
        try:
            client = await self.redis._get_client()
            meta_key = f"{self.SESSION_META_PREFIX}:{session_id}"
            meta = await client.hgetall(meta_key)
            return dict(meta) if meta else None
        except Exception as e:
            logger.warning(f"⚠️ 获取 Session 元数据失败: {e}")
            return None
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户统计
        
        Args:
            user_id: 用户 ID
            
        Returns:
            用户统计信息
        """
        return await self.user_pool.get_stats(user_id)
    
    async def get_agent_stats(self, agent_id: str = None) -> Dict[str, Any]:
        """
        获取 Agent 统计
        
        Args:
            agent_id: Agent ID（可选，不提供则返回所有）
            
        Returns:
            Agent 统计信息
        """
        return await self.agent_pool.get_stats(agent_id)
    
    async def get_user_active_sessions(self, user_id: str) -> List[str]:
        """
        获取用户的活跃 Session 列表
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session ID 列表
        """
        return await self.user_pool.get_active_sessions(user_id)
    
    # ==================== 校准机制（解决计数器不一致问题） ====================
    
    async def calibrate(self) -> Dict[str, Any]:
        """
        校准活跃 Session 数据
        
        用于服务重启后或定期执行，清理过期/孤立的 Session 记录。
        
        校准策略：
        1. 获取活跃 Session 集合中的所有 ID
        2. 检查每个 Session 的元数据是否存在
        3. 移除没有元数据的孤立 Session
        
        Returns:
            校准结果（清理数量等）
        """
        try:
            client = await self.redis._get_client()
            
            # 获取所有活跃 Session
            active_sessions = await client.smembers(self.ACTIVE_SESSIONS_KEY)
            
            if not active_sessions:
                return {
                    "status": "success",
                    "total_checked": 0,
                    "orphaned_removed": 0,
                }
            
            orphaned_sessions = []
            
            for session_id in active_sessions:
                meta_key = f"{self.SESSION_META_PREFIX}:{session_id}"
                exists = await client.exists(meta_key)
                
                if not exists:
                    orphaned_sessions.append(session_id)
            
            # 移除孤立的 Session
            if orphaned_sessions:
                await client.srem(self.ACTIVE_SESSIONS_KEY, *orphaned_sessions)
                logger.info(f"🔄 校准完成: 移除 {len(orphaned_sessions)} 个孤立 Session")
            
            return {
                "status": "success",
                "total_checked": len(active_sessions),
                "orphaned_removed": len(orphaned_sessions),
                "orphaned_ids": orphaned_sessions[:10],  # 只返回前 10 个
            }
            
        except Exception as e:
            logger.error(f"❌ 校准失败: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }
    
    # ==================== 清理 ====================
    
    async def cleanup(self) -> None:
        """
        清理资源（关闭时调用）
        
        注意：不清理 Redis 中的数据，只清理本地资源
        """
        await self.agent_pool.cleanup()
        await self.user_pool.cleanup()
        
        logger.info("🧹 SessionPool 清理完成")
    
    async def reset_all(self) -> None:
        """
        重置所有数据（仅用于测试）
        
        警告：会清除 Redis 中的活跃 Session 数据！
        """
        try:
            client = await self.redis._get_client()
            
            # 清空活跃 Session 集合
            await client.delete(self.ACTIVE_SESSIONS_KEY)
            
            # 清理 Agent 原型
            self.agent_pool.clear_prototypes()
            
            logger.warning("⚠️ SessionPool 已重置所有数据")
            
        except Exception as e:
            logger.error(f"❌ 重置失败: {e}", exc_info=True)


# ==================== 单例管理（支持依赖注入） ====================

_session_pool: Optional[SessionPool] = None


def get_session_pool(
    redis_manager=None,
    user_pool: Optional[UserPool] = None,
    agent_pool: Optional[AgentPool] = None
) -> SessionPool:
    """
    获取 SessionPool 单例
    
    支持依赖注入：
    - 首次调用时，如果不传参数，使用默认依赖
    - 传入参数时，会创建新实例（用于测试）
    
    Args:
        redis_manager: Redis 管理器（可选）
        user_pool: UserPool 实例（可选）
        agent_pool: AgentPool 实例（可选）
        
    Returns:
        SessionPool 实例
    """
    global _session_pool
    
    # 如果传入了参数，创建新实例（用于测试或自定义配置）
    if redis_manager is not None or user_pool is not None or agent_pool is not None:
        if redis_manager is None:
            from services.redis_manager import get_redis_manager
            redis_manager = get_redis_manager()
        
        return SessionPool(
            redis_manager=redis_manager,
            user_pool=user_pool,
            agent_pool=agent_pool
        )
    
    # 默认单例
    if _session_pool is None:
        from services.redis_manager import get_redis_manager
        _session_pool = SessionPool(
            redis_manager=get_redis_manager(),
            user_pool=get_user_pool(),
            agent_pool=get_agent_pool()
        )
    
    return _session_pool


def reset_session_pool() -> None:
    """
    重置单例（仅用于测试）
    """
    global _session_pool
    _session_pool = None
