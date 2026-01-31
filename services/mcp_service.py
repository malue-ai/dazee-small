"""
MCP 服务层 - MCP Server Management Service

职责：
1. 全局 MCP 模板管理（供运营人员查看和配置）
2. Agent 实例化 MCP 管理（为 Agent 启用/配置 MCP）
3. MCP 连接和工具发现

设计原则：
- 两级架构：全局模板 + Agent 实例化配置
- 全局模板：agent_id = null，所有 Agent 可见
- Agent 实例：agent_id = xxx，该 Agent 特定的配置
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from logger import get_logger
from infra.database import AsyncSessionLocal, crud
from infra.database.models.agent import MCPServerInstance
from models.tool import MCPServerRegistration

logger = get_logger("mcp_service")


class MCPServiceError(Exception):
    """MCP 服务异常基类"""
    pass


class MCPNotFoundError(MCPServiceError):
    """MCP 不存在异常"""
    pass


class MCPAlreadyExistsError(MCPServiceError):
    """MCP 已存在异常"""
    pass


class MCPConnectionError(MCPServiceError):
    """MCP 连接异常"""
    pass


class MCPService:
    """
    MCP 服务
    
    提供 MCP 服务器的完整生命周期管理
    """
    
    def __init__(self):
        """初始化 MCP 服务"""
        pass
    
    # ==================== 全局 MCP 模板管理 ====================
    
    async def register_global_mcp(
        self,
        server_name: str,
        server_url: str,
        auth_type: str = "none",
        auth_env: Optional[str] = None,
        capability: Optional[str] = None,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        注册全局 MCP 模板
        
        Args:
            server_name: 服务器名称（唯一标识）
            server_url: 服务器 URL
            auth_type: 认证类型（none/api_key/oauth）
            auth_env: 认证环境变量名
            capability: 能力分类
            description: 描述
            metadata: 元数据
            
        Returns:
            注册结果
            
        Raises:
            MCPAlreadyExistsError: MCP 已存在
        """
        async with AsyncSessionLocal() as session:
            # 检查是否已存在
            exists = await crud.check_mcp_exists(session, server_name)
            if exists:
                raise MCPAlreadyExistsError(f"全局 MCP '{server_name}' 已存在")
            
            # 创建记录
            db_mcp = await crud.create_global_mcp(
                session=session,
                server_name=server_name,
                server_url=server_url,
                auth_type=auth_type,
                auth_env=auth_env,
                capability=capability,
                description=description,
                metadata=metadata
            )
            
            logger.info(f"✅ 全局 MCP 注册成功: {server_name}")
            
            return self._mcp_to_dict(db_mcp)
    
    async def list_global_mcps(
        self,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        列出所有全局 MCP 模板
        
        Args:
            include_inactive: 是否包含已禁用的
            
        Returns:
            MCP 列表
        """
        async with AsyncSessionLocal() as session:
            mcps = await crud.list_global_mcps(
                session=session,
                include_inactive=include_inactive
            )
            
            return [self._mcp_to_dict(mcp) for mcp in mcps]
    
    async def get_global_mcp(self, server_name: str) -> Dict[str, Any]:
        """
        获取全局 MCP 详情
        
        Args:
            server_name: 服务器名称
            
        Returns:
            MCP 详情
            
        Raises:
            MCPNotFoundError: MCP 不存在
        """
        async with AsyncSessionLocal() as session:
            db_mcp = await crud.get_global_mcp_by_name(session, server_name)
            
            if not db_mcp:
                raise MCPNotFoundError(f"全局 MCP '{server_name}' 不存在")
            
            return self._mcp_to_dict(db_mcp)
    
    async def update_global_mcp(
        self,
        server_name: str,
        server_url: Optional[str] = None,
        auth_type: Optional[str] = None,
        auth_env: Optional[str] = None,
        capability: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        更新全局 MCP 配置
        
        Args:
            server_name: 服务器名称
            其他参数: 要更新的字段
            
        Returns:
            更新后的 MCP 详情
            
        Raises:
            MCPNotFoundError: MCP 不存在
        """
        async with AsyncSessionLocal() as session:
            # 检查是否存在
            existing = await crud.get_global_mcp_by_name(session, server_name)
            if not existing:
                raise MCPNotFoundError(f"全局 MCP '{server_name}' 不存在")
            
            # 构建更新数据
            update_data = {}
            if server_url is not None:
                update_data["server_url"] = server_url
            if auth_type is not None:
                update_data["auth_type"] = auth_type
            if auth_env is not None:
                update_data["auth_env"] = auth_env
            if capability is not None:
                update_data["capability"] = capability
            if description is not None:
                update_data["description"] = description
            if is_active is not None:
                update_data["is_active"] = is_active
            
            db_mcp = await crud.update_global_mcp(
                session=session,
                server_name=server_name,
                **update_data
            )
            
            # 单独处理 metadata
            if metadata is not None and db_mcp:
                db_mcp.extra_data = metadata
                await session.commit()
                await session.refresh(db_mcp)
            
            logger.info(f"✅ 全局 MCP 更新成功: {server_name}")
            
            return self._mcp_to_dict(db_mcp)
    
    async def delete_global_mcp(self, server_name: str) -> bool:
        """
        删除全局 MCP 模板
        
        Args:
            server_name: 服务器名称
            
        Returns:
            是否删除成功
            
        Raises:
            MCPNotFoundError: MCP 不存在
        """
        async with AsyncSessionLocal() as session:
            # 检查是否存在
            existing = await crud.get_global_mcp_by_name(session, server_name)
            if not existing:
                raise MCPNotFoundError(f"全局 MCP '{server_name}' 不存在")
            
            success = await crud.delete_global_mcp(session, server_name)
            
            if success:
                logger.info(f"✅ 全局 MCP 删除成功: {server_name}")
            
            return success
    
    # ==================== Agent 实例化 MCP 管理 ====================
    
    async def enable_mcp_for_agent(
        self,
        agent_id: str,
        server_name: str,
        auth_env: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        为 Agent 启用 MCP
        
        从全局模板复制配置，并允许 Agent 自定义认证信息
        
        Args:
            agent_id: Agent ID
            server_name: 全局 MCP 名称
            auth_env: Agent 专用的认证环境变量名（覆盖全局）
            metadata: Agent 专用的元数据
            
        Returns:
            创建的 Agent MCP 实例
            
        Raises:
            MCPNotFoundError: 全局 MCP 不存在
            MCPAlreadyExistsError: Agent 已启用该 MCP
        """
        async with AsyncSessionLocal() as session:
            # 检查全局模板是否存在
            global_mcp = await crud.get_global_mcp_by_name(session, server_name)
            if not global_mcp:
                raise MCPNotFoundError(f"全局 MCP '{server_name}' 不存在")
            
            # 检查 Agent 是否已启用
            existing = await crud.get_agent_mcp(session, agent_id, server_name)
            if existing:
                raise MCPAlreadyExistsError(
                    f"Agent '{agent_id}' 已启用 MCP '{server_name}'"
                )
            
            # 从全局模板复制，允许覆盖认证信息
            db_mcp = await crud.create_agent_mcp(
                session=session,
                agent_id=agent_id,
                server_name=server_name,
                server_url=global_mcp.server_url,
                auth_type=global_mcp.auth_type,
                auth_env=auth_env or global_mcp.auth_env,
                capability=global_mcp.capability,
                description=global_mcp.description,
                metadata=metadata or global_mcp.extra_data
            )
            
            logger.info(f"✅ Agent MCP 启用成功: agent={agent_id}, mcp={server_name}")
            
            return self._mcp_to_dict(db_mcp, original_name=server_name)
    
    async def list_agent_mcps(
        self,
        agent_id: str,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        列出 Agent 启用的所有 MCP
        
        Args:
            agent_id: Agent ID
            include_inactive: 是否包含已禁用的
            
        Returns:
            Agent 的 MCP 列表
        """
        async with AsyncSessionLocal() as session:
            mcps = await crud.list_agent_mcps(
                session=session,
                agent_id=agent_id,
                include_inactive=include_inactive
            )
            
            return [
                self._mcp_to_dict(mcp, original_name=self._extract_original_name(mcp.server_name, agent_id))
                for mcp in mcps
            ]
    
    async def get_agent_mcp(
        self,
        agent_id: str,
        server_name: str
    ) -> Dict[str, Any]:
        """
        获取 Agent 的某个 MCP 配置
        
        Args:
            agent_id: Agent ID
            server_name: 原始 MCP 名称（不含 agent_id 前缀）
            
        Returns:
            MCP 详情
            
        Raises:
            MCPNotFoundError: MCP 不存在
        """
        async with AsyncSessionLocal() as session:
            db_mcp = await crud.get_agent_mcp(session, agent_id, server_name)
            
            if not db_mcp:
                raise MCPNotFoundError(
                    f"Agent '{agent_id}' 未启用 MCP '{server_name}'"
                )
            
            return self._mcp_to_dict(db_mcp, original_name=server_name)
    
    async def update_agent_mcp_config(
        self,
        agent_id: str,
        server_name: str,
        auth_env: Optional[str] = None,
        is_active: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        更新 Agent 的 MCP 配置
        
        Args:
            agent_id: Agent ID
            server_name: 原始 MCP 名称
            auth_env: 认证环境变量名
            is_active: 是否启用
            metadata: 元数据
            
        Returns:
            更新后的 MCP 详情
            
        Raises:
            MCPNotFoundError: MCP 不存在
        """
        async with AsyncSessionLocal() as session:
            # 检查是否存在
            existing = await crud.get_agent_mcp(session, agent_id, server_name)
            if not existing:
                raise MCPNotFoundError(
                    f"Agent '{agent_id}' 未启用 MCP '{server_name}'"
                )
            
            # 构建更新数据
            update_data = {}
            if auth_env is not None:
                update_data["auth_env"] = auth_env
            if is_active is not None:
                update_data["is_active"] = is_active
            
            db_mcp = await crud.update_agent_mcp(
                session=session,
                agent_id=agent_id,
                server_name=server_name,
                **update_data
            )
            
            # 单独处理 metadata
            if metadata is not None and db_mcp:
                db_mcp.extra_data = metadata
                await session.commit()
                await session.refresh(db_mcp)
            
            logger.info(f"✅ Agent MCP 更新成功: agent={agent_id}, mcp={server_name}")
            
            return self._mcp_to_dict(db_mcp, original_name=server_name)
    
    async def disable_mcp_for_agent(
        self,
        agent_id: str,
        server_name: str
    ) -> bool:
        """
        为 Agent 禁用 MCP
        
        Args:
            agent_id: Agent ID
            server_name: 原始 MCP 名称
            
        Returns:
            是否删除成功
            
        Raises:
            MCPNotFoundError: MCP 不存在
        """
        async with AsyncSessionLocal() as session:
            # 检查是否存在
            existing = await crud.get_agent_mcp(session, agent_id, server_name)
            if not existing:
                raise MCPNotFoundError(
                    f"Agent '{agent_id}' 未启用 MCP '{server_name}'"
                )
            
            success = await crud.delete_agent_mcp(session, agent_id, server_name)
            
            if success:
                logger.info(f"✅ Agent MCP 禁用成功: agent={agent_id}, mcp={server_name}")
            
            return success
    
    # ==================== 工具注册相关 ====================
    
    async def update_registered_tools(
        self,
        mcp_id: int,
        tools: List[str]
    ) -> Dict[str, Any]:
        """
        更新 MCP 的已注册工具列表
        
        Args:
            mcp_id: MCP 数据库 ID
            tools: 工具名称列表
            
        Returns:
            更新后的 MCP 详情
        """
        async with AsyncSessionLocal() as session:
            db_mcp = await crud.update_mcp_registered_tools(
                session=session,
                mcp_id=mcp_id,
                tools=tools
            )
            
            if not db_mcp:
                raise MCPNotFoundError(f"MCP ID={mcp_id} 不存在")
            
            return self._mcp_to_dict(db_mcp)
    
    async def get_mcp_by_id(self, mcp_id: int) -> Dict[str, Any]:
        """
        根据 ID 获取 MCP
        
        Args:
            mcp_id: 数据库 ID
            
        Returns:
            MCP 详情
        """
        async with AsyncSessionLocal() as session:
            db_mcp = await crud.get_mcp_by_id(session, mcp_id)
            
            if not db_mcp:
                raise MCPNotFoundError(f"MCP ID={mcp_id} 不存在")
            
            return self._mcp_to_dict(db_mcp)
    
    # ==================== 辅助方法 ====================
    
    def _mcp_to_dict(
        self,
        mcp: MCPServerInstance,
        original_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """将数据库模型转换为字典"""
        return {
            "id": mcp.id,
            "server_name": mcp.server_name,
            "original_name": original_name or mcp.server_name,
            "server_url": mcp.server_url,
            "auth_type": mcp.auth_type,
            "auth_env": mcp.auth_env,
            "agent_id": mcp.agent_id,
            "is_global": mcp.agent_id is None,
            "is_active": mcp.is_active,
            "capability": mcp.capability,
            "description": mcp.description,
            "registered_tools": mcp.registered_tools,
            "created_at": mcp.created_at.isoformat() if mcp.created_at else None,
            "updated_at": mcp.updated_at.isoformat() if mcp.updated_at else None,
            "last_connected_at": mcp.last_connected_at.isoformat() if mcp.last_connected_at else None,
            "metadata": mcp.extra_data,
        }
    
    def _extract_original_name(self, server_name: str, agent_id: str) -> str:
        """从完整名称中提取原始 MCP 名称"""
        prefix = f"{agent_id}:"
        if server_name.startswith(prefix):
            return server_name[len(prefix):]
        return server_name


# ==================== 单例和工厂函数 ====================

_mcp_service: Optional[MCPService] = None


def get_mcp_service() -> MCPService:
    """获取 MCP 服务单例"""
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = MCPService()
    return _mcp_service

