"""
MCP 客户端 - 使用官方 MCP SDK 实现

支持通过 SSE 协议连接 MCP 服务器并调用工具
"""

import asyncio
import os
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from logger import get_logger

logger = get_logger("mcp_client")


class MCPClientWrapper:
    """
    MCP 客户端封装
    
    使用官方 MCP SDK 连接 MCP 服务器
    """
    
    def __init__(
        self,
        server_url: str,
        server_name: str,
        auth_token: Optional[str] = None
    ):
        """
        初始化 MCP 客户端
        
        Args:
            server_url: MCP 服务器 URL
            server_name: 服务器名称（用于工具命名空间）
            auth_token: 认证令牌
        """
        self.server_url = server_url
        self.server_name = server_name
        self.auth_token = auth_token
        self._session = None
        self._tools: Dict[str, Dict] = {}
        self._connected = False
    
    async def connect(self) -> bool:
        """
        连接到 MCP 服务器（使用 Streamable HTTP 传输）
        
        Returns:
            是否连接成功
        """
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
            
            logger.info(f"🔌 连接 MCP 服务器: {self.server_url}")
            
            # 准备 headers
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            
            # 使用 Streamable HTTP 客户端连接
            self._http_cm = streamablehttp_client(self.server_url, headers=headers)
            read_stream, write_stream, _ = await self._http_cm.__aenter__()
            
            # 创建 ClientSession
            self._session = ClientSession(read_stream, write_stream)
            
            # 初始化会话
            await self._session.__aenter__()
            
            # 发送 initialize 请求
            result = await self._session.initialize()
            server_name = result.serverInfo.name if result.serverInfo else 'unknown'
            logger.info(f"✅ MCP 服务器连接成功: {server_name}")
            
            self._connected = True
            return True
            
        except Exception as e:
            logger.error(f"❌ MCP 服务器连接失败: {str(e)}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """
        断开连接
        
        注意：由于异步上下文管理器的限制，如果在不同的任务中调用 disconnect()
        可能会出现 RuntimeError。这里我们安全地忽略这类错误。
        """
        self._connected = False  # 先标记为断开，避免重复调用
        
        # 🆕 安全地关闭 session
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except (RuntimeError, GeneratorExit) as e:
                # 忽略异步上下文在不同任务退出的错误
                logger.debug(f"Session 关闭时出现预期错误: {type(e).__name__}")
            except Exception as e:
                logger.warning(f"Session 关闭时出错: {e}")
            finally:
                self._session = None
        
        # 🆕 安全地关闭 HTTP 客户端
        if hasattr(self, '_http_cm') and self._http_cm:
            try:
                await self._http_cm.__aexit__(None, None, None)
            except (RuntimeError, GeneratorExit) as e:
                # 忽略异步上下文在不同任务退出的错误
                logger.debug(f"HTTP 客户端关闭时出现预期错误: {type(e).__name__}")
            except Exception as e:
                logger.warning(f"HTTP 客户端关闭时出错: {e}")
            finally:
                self._http_cm = None
        
        logger.info(f"🔌 已断开 MCP 服务器: {self.server_name}")
    
    async def discover_tools(self) -> List[Dict[str, Any]]:
        """
        发现 MCP 服务器上的工具
        
        Returns:
            工具列表
        """
        if not self._connected:
            await self.connect()
        
        if not self._session:
            logger.error("❌ 未连接到 MCP 服务器")
            return []
        
        try:
            logger.info(f"🔍 发现 MCP 工具: {self.server_url}")
            
            # 调用 list_tools
            result = await self._session.list_tools()
            
            tools = []
            for tool in result.tools:
                tool_info = {
                    "name": f"{self.server_name}_{tool.name}",  # 添加命名空间
                    "original_name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    "server_name": self.server_name
                }
                self._tools[tool_info["name"]] = tool_info
                tools.append(tool_info)
            
            logger.info(f"✅ 发现 {len(tools)} 个 MCP 工具")
            for t in tools:
                logger.info(f"   • {t['name']}: {t['description'][:50]}...")
            
            return tools
            
        except Exception as e:
            logger.error(f"❌ 发现 MCP 工具失败: {str(e)}")
            return []
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调用 MCP 工具
        
        Args:
            tool_name: 工具名称（可以是带命名空间的名称）
            arguments: 工具参数
            
        Returns:
            执行结果
        """
        if not self._connected or not self._session:
            success = await self.connect()
            if not success:
                return {
                    "success": False,
                    "error": "无法连接到 MCP 服务器"
                }
        
        try:
            # 获取原始工具名称
            original_name = tool_name
            if tool_name in self._tools:
                original_name = self._tools[tool_name].get("original_name", tool_name)
            elif tool_name.startswith(f"{self.server_name}_"):
                original_name = tool_name[len(f"{self.server_name}_"):]
            
            logger.info(f"🔧 调用 MCP 工具: {original_name}")
            logger.debug(f"   参数: {arguments}")
            
            # 调用工具
            result = await self._session.call_tool(original_name, arguments)
            
            # 解析结果
            content_parts = []
            for content in result.content:
                if hasattr(content, 'text'):
                    content_parts.append(content.text)
                elif hasattr(content, 'data'):
                    content_parts.append(str(content.data))
                else:
                    content_parts.append(str(content))
            
            output = "\n".join(content_parts)
            
            logger.info(f"✅ MCP 工具执行完成: {original_name}")
            
            return {
                "success": True,
                "data": output,
                "is_error": result.isError if hasattr(result, 'isError') else False
            }
            
        except Exception as e:
            logger.error(f"❌ MCP 工具执行失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    @property
    def available_tools(self) -> Dict[str, Dict]:
        """获取已发现的工具"""
        return self._tools


# ============================================================
# MCP 工具包装器（转换为 Claude 可用的工具格式）
# ============================================================

def create_mcp_tool_definition(tool_info: Dict[str, Any], client: 'MCPClientWrapper') -> Dict[str, Any]:
    """
    创建 Claude API 兼容的工具定义
    
    Args:
        tool_info: MCP 工具信息
        client: MCP 客户端实例
        
    Returns:
        Claude API 工具定义
    """
    return {
        "name": tool_info["name"],
        "description": tool_info.get("description", ""),
        "input_schema": tool_info.get("input_schema", {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "输入文本"
                }
            },
            "required": ["query"]
        }),
        "_mcp_client": client,  # 保存客户端引用
        "_original_name": tool_info.get("original_name", tool_info["name"])
    }


class MCPToolExecutor:
    """
    MCP 工具执行器
    
    封装 MCP 工具调用，供 Agent 使用
    """
    
    def __init__(self, client: MCPClientWrapper, tool_name: str, original_name: str):
        self.client = client
        self.tool_name = tool_name
        self.original_name = original_name
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行 MCP 工具"""
        return await self.client.call_tool(self.original_name, kwargs)


# ============================================================
# 便捷函数
# ============================================================

async def quick_mcp_call(
    server_url: str,
    tool_name: str,
    arguments: Dict[str, Any],
    auth_token: Optional[str] = None,
    server_name: str = "mcp"
) -> Dict[str, Any]:
    """
    快速调用 MCP 工具（一次性连接）
    
    Args:
        server_url: MCP 服务器 URL
        tool_name: 工具名称
        arguments: 工具参数
        auth_token: 认证令牌
        server_name: 服务器名称
        
    Returns:
        执行结果
    """
    client = MCPClientWrapper(
        server_url=server_url,
        server_name=server_name,
        auth_token=auth_token
    )
    
    try:
        success = await client.connect()
        if not success:
            return {"success": False, "error": "连接失败"}
        
        # 发现工具
        await client.discover_tools()
        
        # 调用工具
        result = await client.call_tool(tool_name, arguments)
        
        return result
        
    finally:
        await client.disconnect()


# ============================================================
# 测试
# ============================================================

async def test_mcp_connection():
    """测试 MCP 连接"""
    import os
    
    server_url = "https://api.dify.ai/mcp/server/8qw7chBYhmhBSwWb/mcp"
    auth_token = os.getenv("DIFY_API_KEY")
    
    if not auth_token:
        print("❌ DIFY_API_KEY 未设置")
        return
    
    client = MCPClientWrapper(
        server_url=server_url,
        server_name="dify",
        auth_token=auth_token
    )
    
    try:
        # 连接
        success = await client.connect()
        if not success:
            print("❌ 连接失败")
            return
        
        # 发现工具
        tools = await client.discover_tools()
        print(f"✅ 发现 {len(tools)} 个工具:")
        for tool in tools:
            print(f"   • {tool['name']}: {tool['description']}")
        
        # 测试调用
        if tools:
            first_tool = tools[0]
            result = await client.call_tool(
                first_tool["name"],
                {"query": "用户管理系统包含用户、角色、权限"}
            )
            print(f"📊 调用结果: {result}")
        
    finally:
        await client.disconnect()


# ==================== MCP 客户端缓存管理 ====================

# 全局 MCP 客户端缓存（按 server_url 索引）
_mcp_client_cache: Dict[str, MCPClientWrapper] = {}


async def get_mcp_client(
    server_url: str,
    server_name: str,
    auth_token: Optional[str] = None,
    force_reconnect: bool = False
) -> MCPClientWrapper:
    """
    获取 MCP 客户端（带缓存）
    
    同一个 server_url 只创建一次连接，后续复用。
    避免每次用户 query 都重新连接 MCP 服务器。
    
    Args:
        server_url: MCP 服务器 URL
        server_name: 服务器名称
        auth_token: 认证令牌
        force_reconnect: 是否强制重新连接
        
    Returns:
        已连接的 MCPClientWrapper 实例
    """
    global _mcp_client_cache
    
    # 检查缓存
    if server_url in _mcp_client_cache and not force_reconnect:
        client = _mcp_client_cache[server_url]
        if client._connected:
            logger.debug(f"📦 复用已缓存的 MCP 客户端: {server_name}")
            return client
    
    # 创建新客户端
    logger.info(f"🔧 创建新 MCP 客户端: {server_name} ({server_url})")
    client = MCPClientWrapper(
        server_url=server_url,
        server_name=server_name,
        auth_token=auth_token
    )
    
    # 连接
    success = await client.connect()
    if success:
        # 发现工具
        await client.discover_tools()
        # 缓存
        _mcp_client_cache[server_url] = client
    
    return client


def get_cached_mcp_clients() -> Dict[str, MCPClientWrapper]:
    """获取所有缓存的 MCP 客户端"""
    return _mcp_client_cache.copy()


async def clear_mcp_client_cache():
    """清除所有 MCP 客户端缓存（断开连接）"""
    global _mcp_client_cache
    
    for url, client in _mcp_client_cache.items():
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f"断开 MCP 客户端 {url} 失败: {e}")
    
    _mcp_client_cache.clear()
    logger.info("🧹 已清除所有 MCP 客户端缓存")


if __name__ == "__main__":
    asyncio.run(test_mcp_connection())
