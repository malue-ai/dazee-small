"""
MCP 客户端 - 使用官方 MCP SDK 实现

支持通过 SSE 协议连接 MCP 服务器并调用工具
"""
import re
import asyncio
import os
import httpx
from typing import Dict, Any, List, Optional

from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from logger import get_logger

logger = get_logger("mcp_client")


def sanitize_tool_name(name: str) -> str:
    """
    清理工具名称，使其符合 Anthropic API 的要求
    
    Anthropic API 要求工具名称匹配正则表达式: ^[a-zA-Z0-9_-]{1,128}$
    即只允许字母、数字、下划线和连字符，长度 1-128
    
    Args:
        name: 原始工具名称
        
    Returns:
        清理后的工具名称
    """
    # 将空格替换为下划线
    sanitized = name.replace(" ", "_")
    # 移除所有不合法的字符（只保留字母、数字、下划线、连字符）
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', sanitized)
    # 确保长度不超过 128
    sanitized = sanitized[:128]
    # 确保名称不为空
    if not sanitized:
        sanitized = "unnamed_tool"
    return sanitized


class MCPClientWrapper:
    """
    MCP 客户端封装
    
    使用官方 MCP SDK 连接 MCP 服务器
    """
    
    def __init__(
        self,
        server_url: str,
        server_name: str,
        auth_token: Optional[str] = None,
        tool_timeout: float = 1200.0,  # 工具调用超时时间（默认 20 分钟）
        connect_timeout: float = 30.0,  # 🆕 连接超时时间（默认 30 秒）
        max_retries: int = 2  # 🆕 最大重试次数（默认 2 次）
    ):
        """
        初始化 MCP 客户端
        
        Args:
            server_url: MCP 服务器 URL
            server_name: 服务器名称（用于工具命名空间）
            auth_token: 认证令牌
            tool_timeout: 工具调用超时时间（秒），默认 300 秒（5 分钟）
            connect_timeout: 连接超时时间（秒），默认 30 秒
            max_retries: 最大重试次数，默认 2 次
        """
        self.server_url = server_url
        self.server_name = server_name
        self.auth_token = auth_token
        self.tool_timeout = tool_timeout
        self.connect_timeout = connect_timeout  # 🆕 连接超时配置
        self.max_retries = max_retries  # 🆕 重试次数配置
        self._session = None
        self._tools: Dict[str, Dict] = {}
        self._connected = False
        self._connection_failed = False  # 🆕 标记连接是否彻底失败（用于缓存清理）
    
    async def connect(self) -> bool:
        """
        连接到 MCP 服务器（使用 Streamable HTTP 传输）
        
        支持超时控制和自动重试
        
        Returns:
            是否连接成功
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    # 重试前等待（指数退避）
                    delay = min(2 ** attempt, 10)  # 最大等待 10 秒
                    logger.info(f"⏳ MCP 连接重试 {attempt}/{self.max_retries}，等待 {delay}s...")
                    await asyncio.sleep(delay)
                
                logger.info(f"🔌 连接 MCP 服务器: {self.server_url} (超时: {self.connect_timeout}s)")
                
                # 准备认证 headers
                headers = {}
                if self.auth_token:
                    headers["Authorization"] = f"Bearer {self.auth_token}"
                
                # 使用 asyncio.wait_for 添加连接超时
                try:
                    # 创建带认证的 HTTP 客户端
                    self._httpx_client = httpx.AsyncClient(
                        headers=headers,
                        timeout=httpx.Timeout(self.tool_timeout)
                    )
                    
                    # 使用 Streamable HTTP 客户端连接（新版 API：传入 http_client）
                    self._http_cm = streamable_http_client(
                        self.server_url, 
                        http_client=self._httpx_client
                    )
                    read_stream, write_stream, _ = await asyncio.wait_for(
                        self._http_cm.__aenter__(),
                        timeout=self.connect_timeout
                    )
                    
                    # 创建 ClientSession
                    self._session = ClientSession(read_stream, write_stream)
                    
                    # 初始化会话（带超时）
                    await asyncio.wait_for(
                        self._session.__aenter__(),
                        timeout=self.connect_timeout
                    )
                    
                    # 发送 initialize 请求（带超时）
                    result = await asyncio.wait_for(
                        self._session.initialize(),
                        timeout=self.connect_timeout
                    )
                    
                except asyncio.TimeoutError:
                    raise TimeoutError(f"连接超时（{self.connect_timeout}秒）")
                
                server_name = result.serverInfo.name if result.serverInfo else 'unknown'
                logger.info(f"✅ MCP 服务器连接成功: {server_name}")
                
                self._connected = True
                self._connection_failed = False
                return True
                
            except (RuntimeError, GeneratorExit) as e:
                # 🆕 anyio cancel scope 错误：不重试，直接标记失败
                logger.error(f"❌ MCP 连接出现 anyio 错误（不可重试）: {type(e).__name__}: {str(e)}")
                last_error = e
                self._connection_failed = True
                break
                
            except (TimeoutError, asyncio.TimeoutError) as e:
                # 超时错误：可以重试
                logger.warning(f"⚠️ MCP 连接超时: {str(e)}")
                last_error = e
                # 清理可能残留的资源
                await self._cleanup_connection()
                
            except Exception as e:
                # 其他错误：记录并尝试重试
                error_type = type(e).__name__
                logger.warning(f"⚠️ MCP 连接失败 (尝试 {attempt + 1}/{self.max_retries + 1}): {error_type}: {str(e)}")
                last_error = e
                # 清理可能残留的资源
                await self._cleanup_connection()
        
        # 所有重试都失败
        logger.error(f"❌ MCP 服务器连接彻底失败（已重试 {self.max_retries} 次）: {str(last_error)}")
        self._connected = False
        self._connection_failed = True
        return False
    
    async def _cleanup_connection(self):
        """
        清理连接资源（用于重试前的清理）
        """
        try:
            if self._session:
                try:
                    await self._session.__aexit__(None, None, None)
                except Exception:
                    pass
                self._session = None
            
            if hasattr(self, '_http_cm') and self._http_cm:
                try:
                    await self._http_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                self._http_cm = None
            
            # 关闭 httpx 客户端
            if hasattr(self, '_httpx_client') and self._httpx_client:
                try:
                    await self._httpx_client.aclose()
                except Exception:
                    pass
                self._httpx_client = None
        except Exception as e:
            logger.debug(f"清理连接资源时出错: {e}")
    
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
        
        # 安全地关闭 HTTP 上下文管理器
        if hasattr(self, '_http_cm') and self._http_cm:
            try:
                await self._http_cm.__aexit__(None, None, None)
            except (RuntimeError, GeneratorExit) as e:
                # 忽略异步上下文在不同任务退出的错误
                logger.debug(f"HTTP 上下文关闭时出现预期错误: {type(e).__name__}")
            except Exception as e:
                logger.warning(f"HTTP 上下文关闭时出错: {e}")
            finally:
                self._http_cm = None
        
        # 安全地关闭 httpx 客户端
        if hasattr(self, '_httpx_client') and self._httpx_client:
            try:
                await self._httpx_client.aclose()
            except Exception as e:
                logger.debug(f"httpx 客户端关闭时出错: {e}")
            finally:
                self._httpx_client = None
        
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
                # 清理工具名称，确保符合 Anthropic API 要求
                sanitized_name = sanitize_tool_name(f"{self.server_name}_{tool.name}")
                tool_info = {
                    "name": sanitized_name,  # 添加命名空间并清理
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
        # #region agent log
        import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:call_tool:entry", "message": "进入 call_tool", "data": {"tool_name": tool_name, "server_name": self.server_name, "_connected": self._connected, "has_session": self._session is not None}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,B,C,E"}) + '\n')
        # #endregion
        
        # 检查连接状态（不在这里重连，避免 anyio 任务作用域错误）
        if not self._connected or not self._session:
            logger.warning(f"⚠️ MCP 连接已断开，请重新初始化客户端")
            # #region agent log
            import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:call_tool:disconnected", "message": "连接检查失败", "data": {"tool_name": tool_name, "_connected": self._connected, "has_session": self._session is not None}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,B,E"}) + '\n')
            # #endregion
            return {
                "success": False,
                "error": "MCP 连接已断开，请重试（系统会自动重连）"
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
            logger.info(f"   ⏱️ 超时设置: {self.tool_timeout}s")
            
            # 调用工具（带超时）
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(original_name, arguments),
                    timeout=self.tool_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ MCP 工具执行超时（{self.tool_timeout}s）: {original_name}")
                return {
                    "success": False,
                    "error": f"工具执行超时（{self.tool_timeout}秒），请稍后重试"
                }
            
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
            
            # #region agent log
            import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:call_tool:success", "message": "工具调用成功", "data": {"tool_name": original_name, "output_len": len(output)}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "G"}) + '\n')
            # #endregion
            
            return {
                "success": True,
                "data": output,
                "is_error": result.isError if hasattr(result, 'isError') else False
            }
            
        except (RuntimeError, GeneratorExit) as e:
            # 连接相关错误：标记断开，下次调用时会自动重连
            error_type = type(e).__name__
            error_msg = str(e) if str(e) else f"MCP 会话已断开 ({error_type})"
            
            logger.error(f"❌ MCP 连接错误: {error_type}: {error_msg}")
            # #region agent log
            import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:call_tool:runtime_error", "message": "RuntimeError/GeneratorExit", "data": {"error_type": error_type, "error_msg": error_msg, "tool_name": tool_name}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "C"}) + '\n')
            # #endregion
            self._connected = False
            self._session = None
            
            return {
                "success": False,
                "error": error_msg
            }
            
        except Exception as e:
            # 获取详细的异常信息
            error_type = type(e).__name__
            error_msg = str(e) if str(e) else f"{error_type}: (无错误消息)"
            
            # 记录完整的异常信息，包括类型和堆栈
            logger.error(f"❌ MCP 工具执行失败: {error_type}: {error_msg}", exc_info=True)
            
            # #region agent log
            import json as _json, traceback as _tb; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:call_tool:exception", "message": "捕获异常", "data": {"error_type": error_type, "error_msg": error_msg, "tool_name": tool_name, "traceback": _tb.format_exc()[:800]}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,B,C,E"}) + '\n')
            # #endregion
            
            # 检查是否是连接相关的错误，如果是则标记断开
            if "closed" in error_msg.lower() or "cancelled" in error_msg.lower() or error_type == "ClosedResourceError":
                self._connected = False
                self._session = None
                self._connection_failed = True  # 标记需要从缓存移除
            
            return {
                "success": False,
                "error": f"{error_type}: (无错误消息)" if not str(e) else error_msg,
                "_need_reconnect": True  # 标记需要重连
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
        "_original_name": tool_info.get("original_name", tool_info["name"]),
        # 保存连接信息，用于断线重连
        "_server_url": client.server_url,
        "_server_name": client.server_name,
        "_auth_token": client.auth_token
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
    force_reconnect: bool = False,
    tool_timeout: float = 1200.0,  # 工具调用超时时间（默认 20 分钟）
    connect_timeout: float = 30.0,  # 连接超时时间（默认 30 秒）
    max_retries: int = 2  # 最大重试次数（默认 2 次）
) -> Optional[MCPClientWrapper]:
    """
    获取 MCP 客户端（带缓存）
    
    同一个 server_url 只创建一次连接，后续复用。
    避免每次用户 query 都重新连接 MCP 服务器。
    
    Args:
        server_url: MCP 服务器 URL
        server_name: 服务器名称
        auth_token: 认证令牌
        force_reconnect: 是否强制重新连接
        tool_timeout: 工具调用超时时间（秒），默认 300 秒（5 分钟）
        connect_timeout: 连接超时时间（秒），默认 30 秒
        max_retries: 最大重试次数，默认 2 次
        
    Returns:
        已连接的 MCPClientWrapper 实例，连接失败时返回 None
    """
    global _mcp_client_cache
    
    # #region agent log
    import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:get_mcp_client:entry", "message": "进入 get_mcp_client", "data": {"server_name": server_name, "force_reconnect": force_reconnect, "cache_keys": list(_mcp_client_cache.keys())}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,E"}) + '\n')
    # #endregion
    
    # 检查缓存
    if server_url in _mcp_client_cache:
        cached_client = _mcp_client_cache[server_url]
        
        # #region agent log
        import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:get_mcp_client:cache_hit", "message": "缓存命中", "data": {"server_name": server_name, "_connected": cached_client._connected, "has_session": cached_client._session is not None}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,B,E"}) + '\n')
        # #endregion
        
        if cached_client._connected and not force_reconnect:
            # 连接正常，复用
            logger.debug(f"📦 复用已缓存的 MCP 客户端: {server_name}")
            return cached_client
        else:
            # 连接已断开或强制重连，移除旧缓存（创建新客户端）
            logger.info(f"🔄 MCP 客户端已断开，创建新连接: {server_name}")
            # #region agent log
            import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "mcp_client.py:get_mcp_client:cache_invalid", "message": "缓存失效需重连", "data": {"server_name": server_name, "_connected": cached_client._connected}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,B"}) + '\n')
            # #endregion
            del _mcp_client_cache[server_url]
    
    # 创建新客户端
    logger.info(f"🔧 创建新 MCP 客户端: {server_name} ({server_url})")
    client = MCPClientWrapper(
        server_url=server_url,
        server_name=server_name,
        auth_token=auth_token,
        tool_timeout=tool_timeout,
        connect_timeout=connect_timeout,  # 🆕 传递连接超时配置
        max_retries=max_retries  # 🆕 传递重试次数配置
    )
    
    # 连接
    success = await client.connect()
    if success:
        # 发现工具
        await client.discover_tools()
        # 缓存
        _mcp_client_cache[server_url] = client
        return client
    else:
        # 🆕 连接失败，不缓存，返回 None
        logger.warning(f"⚠️ MCP 客户端连接失败，不加入缓存: {server_name}")
        return None


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
