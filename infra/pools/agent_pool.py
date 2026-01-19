"""
Agent 池 - AgentPool

职责：
- 管理 Agent 原型实例（本地缓存）
- 统计 Agent 使用情况（Redis）
- 控制 Agent 并发实例数量

设计原则：
- 混合存储：本地缓存原型实例 + Redis 存储元数据/统计
- 克隆模式：每次请求从原型克隆新实例，注入会话级依赖
- 原子计数：使用 Redis INCR/DECR 实现分布式计数

Redis Key 设计：
- zf:agent:{agent_id}:instances    # String: 当前活跃实例数（原子计数）
- zf:agent:{agent_id}:stats        # Hash: Agent 调用统计
- zf:agent:{agent_id}:meta         # Hash: Agent 元数据
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from logger import get_logger

if TYPE_CHECKING:
    from core.agent import SimpleAgent
    from services.agent_registry import AgentRegistry

logger = get_logger("agent_pool")


class AgentPool:
    """
    Agent 池
    
    使用方式：
        pool = get_agent_pool()
        
        # 预加载所有 Agent 原型
        await pool.preload_all()
        
        # 获取 Agent 实例（克隆）
        agent = await pool.acquire("test_agent", event_manager, conversation_service)
        
        # 释放 Agent（减少计数）
        await pool.release("test_agent")
        
        # 查看统计
        stats = await pool.get_stats()
    """
    
    # Redis Key 前缀
    KEY_PREFIX = "zf:agent"
    
    # 默认 Agent 标识
    DEFAULT_AGENT_KEY = "__default__"
    
    def __init__(self, redis_manager, registry: "AgentRegistry"):
        """
        初始化 Agent 池
        
        Args:
            redis_manager: RedisSessionManager 实例
            registry: AgentRegistry 实例
        """
        self.redis = redis_manager
        self.registry = registry
        
        # 本地原型缓存（agent_id -> SimpleAgent 原型）
        self._prototypes: Dict[str, "SimpleAgent"] = {}
        self._prototype_lock = asyncio.Lock()
        self._initialized = False
        
        # 配置
        self.max_instances_per_agent = int(os.getenv("POOL_AGENT_MAX_INSTANCES", "10"))
        self.default_model = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929")
        
        logger.info(
            f"✅ AgentPool 初始化完成: "
            f"max_instances_per_agent={self.max_instances_per_agent}"
        )
    
    # ==================== 原型管理 ====================
    
    async def preload_all(self) -> int:
        """
        预加载所有 Agent 原型
        
        从 AgentRegistry 获取所有已注册的 Agent，创建原型实例并缓存
        
        Returns:
            成功加载的原型数量
        """
        async with self._prototype_lock:
            if self._initialized:
                logger.info("✅ Agent 原型已加载，跳过重复加载")
                return len(self._prototypes)
            
            logger.info("🏊 开始预加载 Agent 原型...")
            
            # 创建临时 event_manager（原型不需要真实的）
            from core.events import create_event_manager, get_memory_storage
            temp_event_manager = create_event_manager(get_memory_storage())
            
            loaded_count = 0
            
            # 1. 加载 Registry 中的 Agent
            for agent_info in self.registry.list_agents():
                agent_id = agent_info["agent_id"]
                try:
                    prototype = await self.registry.get_agent(
                        agent_id=agent_id,
                        event_manager=temp_event_manager,
                        conversation_service=None
                    )
                    self._prototypes[agent_id] = prototype
                    
                    # 初始化 Redis 元数据
                    await self._init_agent_meta(agent_id, agent_info)
                    
                    loaded_count += 1
                    logger.info(f"   ✅ Agent 原型已创建: {agent_id}")
                except Exception as e:
                    logger.warning(f"   ⚠️ Agent 原型创建失败: {agent_id}, {e}")
            
            # 2. 创建默认 Agent 原型
            try:
                from core.agent import create_simple_agent
                default_prototype = create_simple_agent(
                    model=self.default_model,
                    event_manager=temp_event_manager,
                    conversation_service=None
                )
                self._prototypes[self.DEFAULT_AGENT_KEY] = default_prototype
                
                await self._init_agent_meta(self.DEFAULT_AGENT_KEY, {
                    "agent_id": self.DEFAULT_AGENT_KEY,
                    "description": "默认 Agent",
                })
                
                loaded_count += 1
                logger.info(f"   ✅ 默认 Agent 原型已创建: {self.DEFAULT_AGENT_KEY}")
            except Exception as e:
                logger.warning(f"   ⚠️ 默认 Agent 原型创建失败: {e}")
            
            self._initialized = True
            logger.info(f"🏊 Agent 原型预加载完成: {loaded_count} 个")
            
            return loaded_count
    
    async def _init_agent_meta(self, agent_id: str, info: Dict[str, Any]) -> None:
        """
        初始化 Agent 元数据到 Redis
        
        Args:
            agent_id: Agent ID
            info: Agent 信息
        """
        client = await self.redis._get_client()
        
        # 元数据
        meta_key = f"{self.KEY_PREFIX}:{agent_id}:meta"
        await client.hset(meta_key, mapping={
            "agent_id": agent_id,
            "description": info.get("description", ""),
            "loaded_at": datetime.now().isoformat(),
        })
        
        # 初始化实例计数为 0
        instances_key = f"{self.KEY_PREFIX}:{agent_id}:instances"
        await client.set(instances_key, "0")
    
    # ==================== 实例获取/释放 ====================
    
    async def acquire(
        self,
        agent_id: str,
        event_manager,
        conversation_service,
        event_dispatcher = None
    ) -> "SimpleAgent":
        """
        获取 Agent 实例（从原型克隆）
        
        获取策略：
        1. 快路径：agent_id 在原型池中 → prototype.clone() (< 1ms)
        2. 慢路径（fallback）：不在池中 → Registry.get_agent() (50-100ms)
        
        Args:
            agent_id: Agent ID（使用 DEFAULT_AGENT_KEY 获取默认 Agent）
            event_manager: 事件管理器
            conversation_service: 会话服务
            event_dispatcher: 事件分发器（用于 ZenO 格式转换，可选）
            
        Returns:
            克隆的 Agent 实例
            
        Raises:
            ValueError: Agent 不存在或超过最大实例数
        """
        # 确保已初始化
        if not self._initialized:
            await self.preload_all()
        
        # 检查是否超过最大实例数
        current_count = await self._get_instance_count(agent_id)
        if current_count >= self.max_instances_per_agent:
            logger.warning(
                f"⚠️ Agent {agent_id} 实例数超限: "
                f"{current_count}/{self.max_instances_per_agent}"
            )
            # 当前只警告，不阻止（未来可改为抛异常）
        
        # 从原型克隆
        if agent_id in self._prototypes:
            # 快路径：从原型克隆
            prototype = self._prototypes[agent_id]
            agent = prototype.clone(
                event_manager=event_manager,
                conversation_service=conversation_service,
                event_dispatcher=event_dispatcher
            )
            logger.debug(f"🏊 从原型克隆 Agent: {agent_id}")
        else:
            # 慢路径（fallback）：直接从 Registry 创建
            logger.warning(f"⚠️ Agent {agent_id} 不在原型池中，使用 fallback 创建")
            
            if agent_id == self.DEFAULT_AGENT_KEY:
                from core.agent import create_simple_agent
                agent = create_simple_agent(
                    model=self.default_model,
                    event_manager=event_manager,
                    conversation_service=conversation_service
                )
            else:
                agent = await self.registry.get_agent(
                    agent_id=agent_id,
                    event_manager=event_manager,
                    conversation_service=conversation_service,
                    event_dispatcher=event_dispatcher
                )
        
        # 增加实例计数
        await self._increment_instance_count(agent_id)
        
        # 更新统计
        await self.increment_stat(agent_id, "total_acquires")
        
        return agent
    
    async def release(self, agent_id: str) -> None:
        """
        释放 Agent 实例（减少计数）
        
        Args:
            agent_id: Agent ID
        """
        await self._decrement_instance_count(agent_id)
        await self.increment_stat(agent_id, "total_releases")
        
        logger.debug(f"🏊 Agent 实例已释放: {agent_id}")
    
    # ==================== Redis 计数操作 ====================
    
    async def _get_instance_count(self, agent_id: str) -> int:
        """获取 Agent 当前实例数"""
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{agent_id}:instances"
        
        count = await client.get(key)
        return int(count) if count else 0
    
    async def _increment_instance_count(self, agent_id: str) -> int:
        """增加 Agent 实例计数"""
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{agent_id}:instances"
        
        return await client.incr(key)
    
    async def _decrement_instance_count(self, agent_id: str) -> int:
        """减少 Agent 实例计数"""
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{agent_id}:instances"
        
        # 使用 DECR，但不能小于 0
        count = await client.decr(key)
        if count < 0:
            await client.set(key, "0")
            return 0
        return count
    
    async def increment_stat(self, agent_id: str, stat_name: str, amount: int = 1) -> int:
        """
        增加 Agent 统计
        
        Args:
            agent_id: Agent ID
            stat_name: 统计项名称
            amount: 增加量
            
        Returns:
            增加后的值
        """
        client = await self.redis._get_client()
        key = f"{self.KEY_PREFIX}:{agent_id}:stats"
        
        return await client.hincrby(key, stat_name, amount)
    
    # ==================== 查询方法 ====================
    
    async def get_stats(self, agent_id: str = None) -> Dict[str, Any]:
        """
        获取 Agent 统计信息
        
        Args:
            agent_id: Agent ID，不提供则返回所有
            
        Returns:
            统计信息
        """
        client = await self.redis._get_client()
        
        if agent_id:
            # 单个 Agent
            stats_key = f"{self.KEY_PREFIX}:{agent_id}:stats"
            instances_key = f"{self.KEY_PREFIX}:{agent_id}:instances"
            
            stats = await client.hgetall(stats_key)
            instances = await client.get(instances_key)
            
            return {
                "agent_id": agent_id,
                "current_instances": int(instances) if instances else 0,
                "total_acquires": int(stats.get("total_acquires", 0)),
                "total_releases": int(stats.get("total_releases", 0)),
                "in_prototype_cache": agent_id in self._prototypes,
            }
        else:
            # 所有 Agent
            result = {
                "total_prototypes": len(self._prototypes),
                "agents": {}
            }
            
            for aid in self._prototypes.keys():
                result["agents"][aid] = await self.get_stats(aid)
            
            return result
    
    def list_prototypes(self) -> List[str]:
        """
        列出所有已缓存的原型
        
        Returns:
            Agent ID 列表
        """
        return list(self._prototypes.keys())
    
    def has_prototype(self, agent_id: str) -> bool:
        """
        检查原型是否存在
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否存在
        """
        return agent_id in self._prototypes
    
    # ==================== 清理 ====================
    
    def clear_prototypes(self) -> None:
        """
        清空原型缓存（用于热更新）
        """
        self._prototypes.clear()
        self._initialized = False
        logger.info("🏊 Agent 原型缓存已清空")
    
    async def cleanup(self) -> None:
        """
        清理资源
        """
        # 重置所有 Agent 的实例计数
        client = await self.redis._get_client()
        
        for agent_id in self._prototypes.keys():
            key = f"{self.KEY_PREFIX}:{agent_id}:instances"
            await client.set(key, "0")
        
        self._prototypes.clear()
        self._initialized = False
        
        logger.info("🧹 AgentPool 清理完成")


# ==================== 单例 ====================

_agent_pool: Optional[AgentPool] = None


def get_agent_pool() -> AgentPool:
    """
    获取 AgentPool 单例
    
    Returns:
        AgentPool 实例
    """
    global _agent_pool
    if _agent_pool is None:
        from services.redis_manager import get_redis_manager
        from services.agent_registry import get_agent_registry
        _agent_pool = AgentPool(
            redis_manager=get_redis_manager(),
            registry=get_agent_registry()
        )
    return _agent_pool


def reset_agent_pool() -> None:
    """
    重置单例（仅用于测试）
    """
    global _agent_pool
    _agent_pool = None
