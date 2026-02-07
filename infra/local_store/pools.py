"""
本地资源池（桌面端轻量实现）

桌面端轻量资源池：
- LocalSessionPool: 会话并发管理（内存级）
- LocalAgentPool: Agent 实例获取（委托 AgentRegistry）

设计原则：
- 零外部依赖（纯内存）
- 单用户场景，不需要分布式锁
- 接口兼容 chat_service 现有调用
"""

from typing import Any, Dict, Optional, Set

from logger import get_logger

logger = get_logger("local_store.pools")


class LocalSessionPool:
    """
    本地会话池（内存级）

    跟踪活跃会话，限制单用户并发数。
    桌面端默认允许 10 个并发会话。
    """

    def __init__(self, max_concurrent: int = 10):
       self._max_concurrent = max_concurrent
       self._active_sessions: Dict[str, Set[str]] = {}

    async def check_can_create_session(self, user_id: str) -> None:
        """
        检查用户是否可以创建新会话

        Args:
            user_id: 用户 ID

        Raises:
            ValueError: 超过并发上限
        """
        active = self._active_sessions.get(user_id, set())
        if len(active) >= self._max_concurrent:
            raise ValueError(
                f"并发会话数已达上限 ({self._max_concurrent})，"
                f"请等待当前会话完成后重试"
            )

    async def on_session_start(
        self, session_id: str, user_id: str, agent_id: str
    ) -> None:
        """记录会话开始"""
        if user_id not in self._active_sessions:
            self._active_sessions[user_id] = set()
        self._active_sessions[user_id].add(session_id)
        logger.debug(
            "会话已注册",
            extra={
                "session_id": session_id,
                "user_id": user_id,
                "active_count": len(self._active_sessions[user_id]),
            },
        )

    async def on_session_end(
        self, session_id: str, user_id: str, agent_id: str
    ) -> None:
        """记录会话结束"""
        if user_id in self._active_sessions:
            self._active_sessions[user_id].discard(session_id)
            if not self._active_sessions[user_id]:
                del self._active_sessions[user_id]
        logger.debug("会话已释放", extra={"session_id": session_id})

    def get_active_count(self, user_id: str) -> int:
        """获取用户活跃会话数"""
        return len(self._active_sessions.get(user_id, set()))


class LocalAgentPool:
    """
    本地 Agent 池（委托 AgentRegistry）

    桌面端不需要真正的对象池，每次请求通过 AgentRegistry
    克隆 Agent 原型即可（clone_for_session 是轻量操作）。
    """

    def __init__(self, agent_registry: Any = None):
        self._registry = agent_registry

    def _get_registry(self):
        """延迟获取 AgentRegistry（避免循环导入）"""
        if self._registry is None:
            from services.agent_registry import get_agent_registry
            self._registry = get_agent_registry()
        return self._registry

    async def acquire(
        self,
        agent_id: str,
        event_manager: Any = None,
        conversation_service: Any = None,
    ) -> Any:
        """
        获取 Agent 实例（委托 AgentRegistry.get_agent）

        Args:
            agent_id: Agent ID
            event_manager: 事件管理器
            conversation_service: 会话服务

        Returns:
            就绪的 Agent 实例
        """
        registry = self._get_registry()
        agent = await registry.get_agent(
            agent_id=agent_id,
            event_manager=event_manager,
            conversation_service=conversation_service,
        )
        logger.debug("Agent 已获取", extra={"agent_id": agent_id})
        return agent

    async def release(self, agent_id: str) -> None:
        """
        释放 Agent 实例（桌面端为空操作）

        克隆的 Agent 实例无需归还池，GC 自动回收。
        """
        logger.debug("Agent 已释放", extra={"agent_id": agent_id})


# ==================== 单例 ====================

_session_pool: Optional[LocalSessionPool] = None
_agent_pool: Optional[LocalAgentPool] = None


def get_local_session_pool() -> LocalSessionPool:
    """获取 LocalSessionPool 单例"""
    global _session_pool
    if _session_pool is None:
        _session_pool = LocalSessionPool()
    return _session_pool


def get_local_agent_pool() -> LocalAgentPool:
    """获取 LocalAgentPool 单例"""
    global _agent_pool
    if _agent_pool is None:
        _agent_pool = LocalAgentPool()
    return _agent_pool
