"""
资源池模块 (infra/pools)

提供三个核心资源池：
- UserPool: 用户状态追踪和统计
- AgentPool: Agent 实例管理（原型缓存 + 统计）
- SessionPool: 活跃 Session 追踪（整合 UserPool 和 AgentPool，提供系统统计）

注意：
- Session 的生命周期管理由 SessionService (services/session_service.py) 负责
- SessionPool 只追踪活跃 Session 集合，不管理单个 Session

使用方式：
    from infra.pools import get_session_pool, get_agent_pool
    
    # 获取系统统计
    stats = await get_session_pool().get_system_stats()
    
    # 获取 Agent
    agent = await get_agent_pool().acquire(agent_id, ...)
    
    # 校准活跃 Session 数据（定期或重启时调用）
    result = await get_session_pool().calibrate()
"""

from .user_pool import UserPool, get_user_pool, reset_user_pool
from .agent_pool import AgentPool, get_agent_pool, reset_agent_pool
from .session_pool import (
    SessionPool,
    get_session_pool,
    reset_session_pool,
)


__all__ = [
    # 类
    "UserPool",
    "AgentPool",
    "SessionPool",
    # 单例获取函数
    "get_user_pool",
    "get_agent_pool",
    "get_session_pool",
    # 测试支持（重置单例）
    "reset_user_pool",
    "reset_agent_pool",
    "reset_session_pool",
]
