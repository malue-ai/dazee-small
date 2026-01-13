"""
MCP 服务器 CRUD 操作

支持两级结构：
- 全局 MCP 模板（agent_id = null）
- Agent 实例化的 MCP（agent_id = xxx）
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.agent import MCPServerInstance


# ==================== 全局 MCP 模板 ====================

async def create_global_mcp(
    session: AsyncSession,
    server_name: str,
    server_url: str,
    auth_type: str = "none",
    auth_env: Optional[str] = None,
    capability: Optional[str] = None,
    description: str = "",
    metadata: Optional[Dict[str, Any]] = None
) -> MCPServerInstance:
    """
    创建全局 MCP 模板
    
    Args:
        session: 数据库会话
        server_name: 服务器名称（唯一）
        server_url: 服务器 URL
        auth_type: 认证类型
        auth_env: 认证环境变量名
        capability: 能力分类
        description: 描述
        metadata: 元数据
        
    Returns:
        创建的 MCP 实例
    """
    instance = MCPServerInstance(
        server_name=server_name,
        server_url=server_url,
        auth_type=auth_type,
        auth_env=auth_env,
        capability=capability,
        description=description,
        agent_id=None,  # 全局模板
        is_active=True,
    )
    
    if metadata:
        instance.extra_data = metadata
    
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


async def get_global_mcp_by_name(
    session: AsyncSession,
    server_name: str
) -> Optional[MCPServerInstance]:
    """根据名称获取全局 MCP 模板"""
    result = await session.execute(
        select(MCPServerInstance).where(
            and_(
                MCPServerInstance.server_name == server_name,
                MCPServerInstance.agent_id.is_(None)
            )
        )
    )
    return result.scalar_one_or_none()


async def list_global_mcps(
    session: AsyncSession,
    include_inactive: bool = False
) -> List[MCPServerInstance]:
    """列出所有全局 MCP 模板"""
    query = select(MCPServerInstance).where(
        MCPServerInstance.agent_id.is_(None)
    )
    
    if not include_inactive:
        query = query.where(MCPServerInstance.is_active == True)
    
    query = query.order_by(MCPServerInstance.created_at.desc())
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_global_mcp(
    session: AsyncSession,
    server_name: str,
    **kwargs
) -> Optional[MCPServerInstance]:
    """更新全局 MCP 模板"""
    # 过滤掉 None 值
    update_data = {k: v for k, v in kwargs.items() if v is not None}
    
    if not update_data:
        return await get_global_mcp_by_name(session, server_name)
    
    await session.execute(
        update(MCPServerInstance)
        .where(
            and_(
                MCPServerInstance.server_name == server_name,
                MCPServerInstance.agent_id.is_(None)
            )
        )
        .values(**update_data)
    )
    await session.commit()
    
    return await get_global_mcp_by_name(session, server_name)


async def delete_global_mcp(
    session: AsyncSession,
    server_name: str
) -> bool:
    """删除全局 MCP 模板"""
    result = await session.execute(
        delete(MCPServerInstance).where(
            and_(
                MCPServerInstance.server_name == server_name,
                MCPServerInstance.agent_id.is_(None)
            )
        )
    )
    await session.commit()
    return result.rowcount > 0


# ==================== Agent 实例化 MCP ====================

async def create_agent_mcp(
    session: AsyncSession,
    agent_id: str,
    server_name: str,
    server_url: str,
    auth_type: str = "none",
    auth_env: Optional[str] = None,
    capability: Optional[str] = None,
    description: str = "",
    metadata: Optional[Dict[str, Any]] = None
) -> MCPServerInstance:
    """
    为 Agent 创建 MCP 实例
    
    Args:
        session: 数据库会话
        agent_id: Agent ID
        server_name: 服务器名称
        server_url: 服务器 URL
        auth_type: 认证类型
        auth_env: 认证环境变量名
        capability: 能力分类
        description: 描述
        metadata: 元数据
        
    Returns:
        创建的 MCP 实例
    """
    # 生成唯一的 server_name（agent_id + 原始名称）
    unique_name = f"{agent_id}:{server_name}"
    
    instance = MCPServerInstance(
        server_name=unique_name,
        server_url=server_url,
        auth_type=auth_type,
        auth_env=auth_env,
        capability=capability,
        description=description,
        agent_id=agent_id,
        is_active=True,
    )
    
    if metadata:
        instance.extra_data = metadata
    
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


async def get_agent_mcp(
    session: AsyncSession,
    agent_id: str,
    server_name: str
) -> Optional[MCPServerInstance]:
    """获取 Agent 的某个 MCP 实例"""
    unique_name = f"{agent_id}:{server_name}"
    
    result = await session.execute(
        select(MCPServerInstance).where(
            and_(
                MCPServerInstance.server_name == unique_name,
                MCPServerInstance.agent_id == agent_id
            )
        )
    )
    return result.scalar_one_or_none()


async def list_agent_mcps(
    session: AsyncSession,
    agent_id: str,
    include_inactive: bool = False
) -> List[MCPServerInstance]:
    """列出 Agent 的所有 MCP 实例"""
    query = select(MCPServerInstance).where(
        MCPServerInstance.agent_id == agent_id
    )
    
    if not include_inactive:
        query = query.where(MCPServerInstance.is_active == True)
    
    query = query.order_by(MCPServerInstance.created_at.desc())
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_agent_mcp(
    session: AsyncSession,
    agent_id: str,
    server_name: str,
    **kwargs
) -> Optional[MCPServerInstance]:
    """更新 Agent 的 MCP 配置"""
    unique_name = f"{agent_id}:{server_name}"
    
    # 过滤掉 None 值
    update_data = {k: v for k, v in kwargs.items() if v is not None}
    
    if not update_data:
        return await get_agent_mcp(session, agent_id, server_name)
    
    await session.execute(
        update(MCPServerInstance)
        .where(
            and_(
                MCPServerInstance.server_name == unique_name,
                MCPServerInstance.agent_id == agent_id
            )
        )
        .values(**update_data)
    )
    await session.commit()
    
    return await get_agent_mcp(session, agent_id, server_name)


async def delete_agent_mcp(
    session: AsyncSession,
    agent_id: str,
    server_name: str
) -> bool:
    """删除 Agent 的 MCP 实例"""
    unique_name = f"{agent_id}:{server_name}"
    
    result = await session.execute(
        delete(MCPServerInstance).where(
            and_(
                MCPServerInstance.server_name == unique_name,
                MCPServerInstance.agent_id == agent_id
            )
        )
    )
    await session.commit()
    return result.rowcount > 0


async def delete_all_agent_mcps(
    session: AsyncSession,
    agent_id: str
) -> int:
    """删除 Agent 的所有 MCP 实例"""
    result = await session.execute(
        delete(MCPServerInstance).where(
            MCPServerInstance.agent_id == agent_id
        )
    )
    await session.commit()
    return result.rowcount


# ==================== 工具注册 ====================

async def update_mcp_registered_tools(
    session: AsyncSession,
    mcp_id: int,
    tools: List[str]
) -> Optional[MCPServerInstance]:
    """更新 MCP 的已注册工具列表"""
    import json
    
    await session.execute(
        update(MCPServerInstance)
        .where(MCPServerInstance.id == mcp_id)
        .values(
            _registered_tools=json.dumps(tools, ensure_ascii=False),
            last_connected_at=datetime.now()
        )
    )
    await session.commit()
    
    result = await session.execute(
        select(MCPServerInstance).where(MCPServerInstance.id == mcp_id)
    )
    return result.scalar_one_or_none()


async def get_mcp_by_id(
    session: AsyncSession,
    mcp_id: int
) -> Optional[MCPServerInstance]:
    """根据 ID 获取 MCP 实例"""
    result = await session.execute(
        select(MCPServerInstance).where(MCPServerInstance.id == mcp_id)
    )
    return result.scalar_one_or_none()


async def check_mcp_exists(
    session: AsyncSession,
    server_name: str,
    agent_id: Optional[str] = None
) -> bool:
    """检查 MCP 是否已存在"""
    if agent_id:
        unique_name = f"{agent_id}:{server_name}"
        query = select(MCPServerInstance).where(
            MCPServerInstance.server_name == unique_name
        )
    else:
        query = select(MCPServerInstance).where(
            and_(
                MCPServerInstance.server_name == server_name,
                MCPServerInstance.agent_id.is_(None)
            )
        )
    
    result = await session.execute(query)
    return result.scalar_one_or_none() is not None

