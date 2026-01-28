"""
MCP 客户端池 - MCPPool

职责：
- 应用启动时预连接所有 MCP 服务器
- 提供统一的客户端获取接口（带并发控制）
- 健康检查和自动重连
- 统计监控

设计原则：
- 独立生命周期：MCP 连接与 Agent 原型解耦
- 预连接：应用启动时建立连接，避免首次请求延迟
- 自动恢复：后台检测连接状态，异步重连
- 分布式统计：使用 Redis 存储统计数据

Redis Key 设计：
- zf:mcp:{server_name}:stats        # Hash: 调用统计
- zf:mcp:{server_name}:health       # String: 最后健康检查时间
- zf:mcp:active                     # Set: 活跃的 MCP 服务器

使用方式：
    pool = get_mcp_pool()
    
    # 应用启动时预连接
    results = await pool.preconnect_all()
    
    # 获取客户端
    client = await pool.get_client(server_url, server_name, auth_token)
    
    # 查看统计
    stats = await pool.get_stats()
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from logger import get_logger

if TYPE_CHECKING:
    from services.mcp_client import MCPClientWrapper

logger = get_logger("mcp_pool")


@dataclass
class MCPConfig:
    """
    MCP 服务器配置
    
    存储连接 MCP 服务器所需的配置信息
    """
    server_url: str                           # MCP 服务器 URL
    server_name: str = "unknown"              # 服务器名称（用于日志和统计）
    auth_type: str = "none"                   # 认证类型（none/bearer/api_key）
    auth_env: Optional[str] = None            # 认证环境变量名
    capability: Optional[str] = None          # 能力类别
    description: str = ""                     # 描述
    
    # 连接参数
    tool_timeout: float = 1200.0              # 工具调用超时（秒）
    connect_timeout: float = 30.0             # 连接超时（秒）
    max_retries: int = 2                      # 最大重试次数
    
    def get_auth_token(self) -> Optional[str]:
        """
        获取认证令牌
        
        Returns:
            认证令牌（如果配置了环境变量）
        """
        if self.auth_type in ("bearer", "api_key") and self.auth_env:
            return os.getenv(self.auth_env)
        return None


@dataclass
class MCPServerState:
    """
    MCP 服务器状态
    
    跟踪单个 MCP 服务器的运行状态
    """
    config: MCPConfig
    client: Optional["MCPClientWrapper"] = None
    connected: bool = False
    last_connected_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    reconnect_attempts: int = 0
    tools_count: int = 0


class MCPPool:
    """
    MCP 客户端池
    
    管理所有 MCP 服务器的连接，提供：
    - 预连接：应用启动时并行建立连接
    - 连接复用：运行时复用已建立的连接
    - 并发控制：限制每个服务器的并发调用数
    - 健康检查：后台检测连接状态，自动重连
    - 统计监控：跟踪调用次数、成功率等
    
    使用方式：
        pool = get_mcp_pool()
        
        # 预连接（启动时调用）
        results = await pool.preconnect_all()
        
        # 获取客户端
        client = await pool.get_client(server_url, server_name, auth_token)
        
        # 启动健康检查
        pool.start_health_check()
    """
    
    # Redis Key 前缀
    KEY_PREFIX = "zf:mcp"
    
    def __init__(self, redis_manager):
        """
        初始化 MCP 池
        
        Args:
            redis_manager: RedisSessionManager 实例
        """
        self.redis = redis_manager
        
        # 服务器状态缓存（server_url -> MCPServerState）
        self._servers: Dict[str, MCPServerState] = {}
        
        # 并发控制信号量（server_url -> Semaphore）
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        
        # 锁
        self._lock = asyncio.Lock()
        
        # 健康检查任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        # 配置
        self.max_concurrent_per_server = int(os.getenv("MCP_MAX_CONCURRENT", "20"))
        self.health_check_interval = int(os.getenv("MCP_HEALTH_CHECK_INTERVAL", "60"))
        self.connect_timeout = float(os.getenv("MCP_CONNECT_TIMEOUT", "30.0"))
        self.tool_timeout = float(os.getenv("MCP_TOOL_TIMEOUT", "1200.0"))
        self.max_retries = int(os.getenv("MCP_MAX_RETRIES", "2"))
        
        logger.info(
            f"✅ MCPPool 初始化完成: "
            f"max_concurrent={self.max_concurrent_per_server}, "
            f"health_check_interval={self.health_check_interval}s"
        )
    
    # ==================== 预连接 ====================
    
    async def preconnect_all(self) -> Dict[str, bool]:
        """
        预连接所有 MCP 服务器
        
        从 AgentRegistry 收集所有 Agent 配置中的 MCP 工具，
        并行建立连接。
        
        Returns:
            连接结果 {server_url: success}
        """
        logger.info("🔌 开始预连接 MCP 服务器...")
        
        # 1. 收集 MCP 配置
        configs = await self._collect_mcp_configs()
        
        if not configs:
            logger.info("   📭 未发现 MCP 配置")
            return {}
        
        logger.info(f"   📦 发现 {len(configs)} 个 MCP 服务器")
        
        # 2. 并行连接（每个连接有独立超时）
        results = {}
        
        async def connect_with_timeout(server_url: str, config: MCPConfig) -> tuple[str, bool]:
            """带超时的连接"""
            # 使用 URL 后缀区分相同 server_name 的不同服务器
            url_suffix = server_url.split("/")[-2][:8] if "/" in server_url else ""
            display_name = f"{config.server_name}({url_suffix})" if url_suffix else config.server_name
            
            try:
                # 单个连接最多等 30 秒
                result = await asyncio.wait_for(
                    self._connect_server(server_url, config),
                    timeout=30.0
                )
                return (server_url, result)
            except asyncio.TimeoutError:
                logger.warning(f"   ⏱️ {display_name}: 连接超时")
                return (server_url, False)
            except Exception as e:
                logger.warning(f"   ❌ {display_name}: {type(e).__name__}")
                return (server_url, False)
        
        tasks = [
            connect_with_timeout(server_url, config)
            for server_url, config in configs.items()
        ]
        
        # 等待所有连接完成（总超时 60 秒）
        try:
            connect_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            logger.warning("⚠️ MCP 预连接总体超时")
            connect_results = []
        
        # 3. 整理结果
        for result in connect_results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, tuple) and len(result) == 2:
                server_url, success = result
                results[server_url] = success
                config = configs.get(server_url)
                if config:
                    # 使用工具名称 + 简化 URL 后缀来区分相同 server_name 的不同服务器
                    url_suffix = server_url.split("/")[-2][:8] if "/" in server_url else ""
                    display_name = f"{config.server_name}({url_suffix})" if url_suffix else config.server_name
                    if success:
                        logger.info(f"   ✅ {display_name}: 已连接")

        
        # 4. 更新 Redis 统计（静默失败）
        try:
            await self._update_active_servers()
        except Exception:
            pass
        
        connected = sum(1 for v in results.values() if v)
        logger.info(f"🔌 MCP 预连接完成: {connected}/{len(results)} 个服务器")
        
        return results
    
    async def _collect_mcp_configs(self) -> Dict[str, MCPConfig]:
        """
        从所有 Agent 配置收集 MCP 服务器信息
        
        Returns:
            {server_url: MCPConfig}
        """
        configs = {}
        
        try:
            from services.agent_registry import get_agent_registry
            registry = get_agent_registry()
            
            for agent_config in registry._configs.values():
                instance_config = agent_config.instance_config
                if not instance_config or not instance_config.mcp_tools:
                    continue
                
                for mcp_tool in instance_config.mcp_tools:
                    server_url = mcp_tool.get("server_url")
                    if not server_url or server_url in configs:
                        continue
                    
                    configs[server_url] = MCPConfig(
                        server_url=server_url,
                        server_name=mcp_tool.get("server_name", "unknown"),
                        auth_type=mcp_tool.get("auth_type", "none"),
                        auth_env=mcp_tool.get("auth_env"),
                        capability=mcp_tool.get("capability"),
                        description=mcp_tool.get("description", ""),
                        tool_timeout=self.tool_timeout,
                        connect_timeout=self.connect_timeout,
                        max_retries=self.max_retries,
                    )
            
        except Exception as e:
            logger.error(f"收集 MCP 配置失败: {e}", exc_info=True)
        
        return configs
    
    async def _connect_server(
        self,
        server_url: str,
        config: MCPConfig
    ) -> bool:
        """
        连接单个 MCP 服务器
        
        Args:
            server_url: 服务器 URL
            config: 服务器配置
            
        Returns:
            是否连接成功
        """
        from services.mcp_client import MCPClientWrapper
        
        # 使用 URL 后缀区分相同 server_name 的不同服务器
        url_suffix = server_url.split("/")[-2][:8] if "/" in server_url else ""
        display_name = f"{config.server_name}({url_suffix})" if url_suffix else config.server_name
        
        try:
            # 获取认证令牌
            auth_token = config.get_auth_token()
            if config.auth_type in ("bearer", "api_key") and not auth_token:
                logger.warning(
                    f"⚠️ MCP {display_name} 的密钥环境变量 "
                    f"{config.auth_env} 未设置，跳过"
                )
                return False
            
            # 创建客户端
            client = MCPClientWrapper(
                server_url=server_url,
                server_name=config.server_name,
                auth_token=auth_token,
                tool_timeout=config.tool_timeout,
                connect_timeout=config.connect_timeout,
                max_retries=config.max_retries,
            )
            
            # 连接
            success = await client.connect()
            
            if success:
                # 发现工具
                try:
                    tools = await client.discover_tools()
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    # 工具发现失败不影响连接
                    tools = []
                
                # 保存状态
                async with self._lock:
                    self._servers[server_url] = MCPServerState(
                        config=config,
                        client=client,
                        connected=True,
                        last_connected_at=datetime.now(),
                        tools_count=len(tools),
                    )
                
                # 更新统计（静默失败）
                try:
                    await self.increment_stat(config.server_name, "connects")
                except Exception:
                    pass
                
                return True
            else:
                # 连接失败，保存配置以便后续重连
                async with self._lock:
                    self._servers[server_url] = MCPServerState(
                        config=config,
                        client=None,
                        connected=False,
                    )
                
                return False
        
        except asyncio.CancelledError:
            # CancelledError 需要特殊处理，不要在取消上下文中 await
            logger.warning(f"⚠️ MCP 连接被取消 {config.server_name}")
            return False
        
        except (GeneratorExit, RuntimeError) as e:
            # anyio cancel scope 相关的异常
            logger.warning(f"⚠️ MCP 连接异常退出 {config.server_name}: {type(e).__name__}")
            return False
        
        except BaseException as e:
            # 捕获所有异常，包括 BaseExceptionGroup
            logger.error(f"连接 MCP 服务器失败 {config.server_name}: {type(e).__name__}: {e}")
            
            # 保存配置以便后续重连
            try:
                async with self._lock:
                    self._servers[server_url] = MCPServerState(
                        config=config,
                        client=None,
                        connected=False,
                    )
            except Exception:
                pass
            
            return False
    
    # ==================== 客户端获取 ====================
    
    async def get_client(
        self,
        server_url: str,
        server_name: Optional[str] = None,
        auth_token: Optional[str] = None,
        force_reconnect: bool = False
    ) -> Optional["MCPClientWrapper"]:
        """
        获取 MCP 客户端
        
        优先从池中获取已连接的客户端，如果不存在或已断开则创建新连接。
        
        Args:
            server_url: 服务器 URL
            server_name: 服务器名称
            auth_token: 认证令牌
            force_reconnect: 是否强制重连
            
        Returns:
            MCPClientWrapper 实例，连接失败返回 None
        """
        # 获取/创建信号量
        if server_url not in self._semaphores:
            self._semaphores[server_url] = asyncio.Semaphore(
                self.max_concurrent_per_server
            )
        
        async with self._semaphores[server_url]:
            return await self._get_client_internal(
                server_url, server_name, auth_token, force_reconnect
            )
    
    async def _get_client_internal(
        self,
        server_url: str,
        server_name: Optional[str],
        auth_token: Optional[str],
        force_reconnect: bool
    ) -> Optional["MCPClientWrapper"]:
        """
        内部获取客户端方法（已在信号量保护下）
        """
        server_state = self._servers.get(server_url)
        
        # 1. 检查是否有可用的连接
        if server_state and server_state.client and server_state.connected:
            if not force_reconnect:
                # 验证连接状态
                if server_state.client._connected:
                    await self.increment_stat(
                        server_state.config.server_name, "cache_hits"
                    )
                    return server_state.client
                else:
                    # 连接已断开，需要重连
                    logger.info(f"🔄 MCP 连接已断开，重连: {server_name or server_url}")
        
        # 2. 需要创建新连接
        name = server_name or (server_state.config.server_name if server_state else "unknown")
        logger.info(f"🔌 创建 MCP 连接: {name}")
        
        # 使用现有配置或创建新配置
        if server_state:
            config = server_state.config
            # 如果传入了新的 auth_token，更新配置
            if auth_token:
                # 不修改原配置，直接使用传入的 token
                pass
        else:
            config = MCPConfig(
                server_url=server_url,
                server_name=server_name or "unknown",
                tool_timeout=self.tool_timeout,
                connect_timeout=self.connect_timeout,
                max_retries=self.max_retries,
            )
        
        # 使用传入的 auth_token 或从配置获取
        token = auth_token or config.get_auth_token()
        
        # 创建新客户端
        from services.mcp_client import MCPClientWrapper
        
        try:
            client = MCPClientWrapper(
                server_url=server_url,
                server_name=config.server_name,
                auth_token=token,
                tool_timeout=config.tool_timeout,
                connect_timeout=config.connect_timeout,
                max_retries=config.max_retries,
            )
            
            # 连接 MCP 服务器
            success = await client.connect()
            
            if success:
                # 发现工具
                try:
                    tools = await client.discover_tools()
                except (asyncio.CancelledError, asyncio.TimeoutError) as e:
                    logger.warning(f"⚠️ MCP 工具发现超时/取消 {config.server_name}: {e}")
                    # 连接成功但工具发现失败，仍然返回客户端（工具列表为空）
                    tools = []
                
                # 更新状态
                async with self._lock:
                    self._servers[server_url] = MCPServerState(
                        config=config,
                        client=client,
                        connected=True,
                        last_connected_at=datetime.now(),
                        tools_count=len(tools),
                    )
                
                await self.increment_stat(config.server_name, "reconnects")
                
                return client
            else:
                logger.warning(f"⚠️ MCP 连接失败: {config.server_name}")
                await self.increment_stat(config.server_name, "connect_failures")
                return None
        
        except asyncio.CancelledError:
            # CancelledError 不继承自 Exception，需要单独捕获
            # 注意：在取消上下文中不要再 await 其他操作，否则会导致 anyio cancel scope 问题
            logger.warning(f"⚠️ MCP 连接被取消 {config.server_name}")
            # 不在这里记录统计，避免在取消上下文中 await
            return None
        
        except (KeyboardInterrupt, SystemExit):
            # 这些异常需要向上传播
            raise
        
        except (GeneratorExit, RuntimeError) as e:
            # GeneratorExit 和某些 RuntimeError（如 anyio cancel scope 问题）
            # 不应该记录统计，直接返回
            logger.warning(f"⚠️ MCP 连接异常退出 {config.server_name}: {type(e).__name__}")
            return None
                
        except BaseException as e:
            # 捕获所有异常，包括 BaseExceptionGroup
            logger.error(f"❌ MCP 连接异常 {config.server_name}: {type(e).__name__}: {e}")
            # 尝试记录统计，但如果失败也不抛出异常
            try:
                await self.increment_stat(config.server_name, "connect_failures")
            except Exception:
                pass  # 静默忽略统计失败
            return None
    
    def get_client_sync(self, server_url: str) -> Optional["MCPClientWrapper"]:
        """
        同步获取客户端（仅返回已缓存的连接，不创建新连接）
        
        用于需要同步访问的场景（如 Agent.clone）
        
        Args:
            server_url: 服务器 URL
            
        Returns:
            已缓存的客户端，如果不存在返回 None
        """
        server_state = self._servers.get(server_url)
        if server_state and server_state.client and server_state.connected:
            return server_state.client
        return None
    
    def get_all_clients(self) -> Dict[str, "MCPClientWrapper"]:
        """
        获取所有已连接的客户端
        
        Returns:
            {server_url: client}
        """
        return {
            url: state.client
            for url, state in self._servers.items()
            if state.client and state.connected
        }
    
    # ==================== 健康检查 ====================
    
    def start_health_check(self) -> None:
        """
        启动后台健康检查任务
        """
        if self._health_check_task is not None:
            logger.warning("⚠️ 健康检查任务已在运行")
            return
        
        self._shutdown = False
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"🏥 MCP 健康检查已启动（间隔 {self.health_check_interval}s）")
    
    def stop_health_check(self) -> None:
        """
        停止健康检查任务
        """
        self._shutdown = True
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
            logger.info("🏥 MCP 健康检查已停止")
    
    async def _health_check_loop(self) -> None:
        """
        健康检查循环
        """
        while not self._shutdown:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                if self._shutdown:
                    break
                
                await self._do_health_check()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查循环异常: {e}", exc_info=True)
    
    async def _do_health_check(self) -> None:
        """
        执行一次健康检查
        
        检查所有已知服务器的连接状态，自动重连断开的连接。
        如果 _servers 为空（尚无连接），会尝试从 AgentRegistry 收集配置并预连接。
        """
        check_time = datetime.now()
        
        # 如果没有已知服务器，尝试从配置收集（延迟初始化）
        if not self._servers:
            try:
                configs = await self._collect_mcp_configs()
                if configs:
                    logger.info(f"🏥 健康检查发现 {len(configs)} 个 MCP 配置，尝试连接...")
                    for server_url, config in configs.items():
                        # 只创建配置记录，不立即连接（避免阻塞健康检查）
                        async with self._lock:
                            if server_url not in self._servers:
                                self._servers[server_url] = MCPServerState(
                                    config=config,
                                    client=None,
                                    connected=False,
                                )
            except Exception as e:
                logger.debug(f"健康检查收集配置失败: {e}")
        
        # 统计
        total_servers = len(self._servers)
        connected_count = 0
        disconnected_count = 0
        
        for server_url, state in list(self._servers.items()):
            try:
                if state.client is None:
                    # 从未成功连接，尝试重连
                    disconnected_count += 1
                    if state.reconnect_attempts < 3:
                        logger.info(f"🔄 尝试连接 MCP: {state.config.server_name}")
                        state.reconnect_attempts += 1
                        success = await self._reconnect(server_url)
                        if success:
                            connected_count += 1
                            disconnected_count -= 1
                    continue
                
                if not state.client._connected:
                    # 连接已断开，尝试重连
                    disconnected_count += 1
                    logger.warning(
                        f"🔄 MCP 连接断开，重连: {state.config.server_name}"
                    )
                    success = await self._reconnect(server_url)
                    if success:
                        connected_count += 1
                        disconnected_count -= 1
                else:
                    # 连接正常，更新健康检查时间
                    connected_count += 1
                    state.last_health_check = check_time
                    state.reconnect_attempts = 0
                    await self._update_health(state.config.server_name)
                    
            except Exception as e:
                disconnected_count += 1
                logger.error(
                    f"健康检查失败 {state.config.server_name}: {e}"
                )
        
        # 日志输出健康检查结果（仅在有服务器时输出）
        if total_servers > 0:
            logger.debug(
                f"🏥 健康检查完成: {connected_count}/{total_servers} 个服务器在线"
            )
    
    async def _reconnect(self, server_url: str) -> bool:
        """
        重连 MCP 服务器
        
        Args:
            server_url: 服务器 URL
            
        Returns:
            是否重连成功
        """
        state = self._servers.get(server_url)
        if not state:
            return False
        
        # 断开旧连接
        if state.client:
            try:
                await state.client.disconnect()
            except Exception:
                pass
        
        # 建立新连接
        success = await self._connect_server(server_url, state.config)
        
        if success:
            logger.info(f"✅ MCP 重连成功: {state.config.server_name}")
            await self.increment_stat(state.config.server_name, "reconnects")
        else:
            logger.warning(f"❌ MCP 重连失败: {state.config.server_name}")
            await self.increment_stat(state.config.server_name, "reconnect_failures")
        
        return success
    
    # ==================== 统计 ====================
    
    async def increment_stat(
        self,
        server_name: str,
        stat_name: str,
        amount: int = 1
    ) -> int:
        """
        增加 MCP 统计计数
        
        Args:
            server_name: 服务器名称
            stat_name: 统计项名称
            amount: 增加量
            
        Returns:
            增加后的值
        """
        try:
            client = await self.redis._get_client()
            key = f"{self.KEY_PREFIX}:{server_name}:stats"
            
            return await client.hincrby(key, stat_name, amount)
        except Exception as e:
            logger.debug(f"更新 MCP 统计失败: {e}")
            return 0
    
    async def _update_health(self, server_name: str) -> None:
        """
        更新健康检查时间戳
        
        Args:
            server_name: 服务器名称
        """
        try:
            client = await self.redis._get_client()
            key = f"{self.KEY_PREFIX}:{server_name}:health"
            
            await client.set(key, datetime.now().isoformat())
            await client.expire(key, self.health_check_interval * 3)
        except Exception as e:
            logger.debug(f"更新健康状态失败: {e}")
    
    async def _update_active_servers(self) -> None:
        """
        更新活跃服务器集合
        """
        try:
            client = await self.redis._get_client()
            key = f"{self.KEY_PREFIX}:active"
            
            # 清空并重新添加
            await client.delete(key)
            
            active_names = [
                state.config.server_name
                for state in self._servers.values()
                if state.connected
            ]
            
            if active_names:
                await client.sadd(key, *active_names)
        except Exception as e:
            logger.debug(f"更新活跃服务器列表失败: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取 MCP 池统计信息
        
        Returns:
            统计信息字典
        """
        servers_info = {}
        
        for url, state in self._servers.items():
            server_stats = await self._get_server_stats(state.config.server_name)
            
            servers_info[url] = {
                "server_name": state.config.server_name,
                "connected": state.connected and (
                    state.client._connected if state.client else False
                ),
                "tools_count": state.tools_count,
                "last_connected_at": (
                    state.last_connected_at.isoformat()
                    if state.last_connected_at else None
                ),
                "last_health_check": (
                    state.last_health_check.isoformat()
                    if state.last_health_check else None
                ),
                "reconnect_attempts": state.reconnect_attempts,
                "stats": server_stats,
            }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_servers": len(self._servers),
            "connected_servers": sum(
                1 for s in self._servers.values()
                if s.connected and s.client and s.client._connected
            ),
            "health_check_running": self._health_check_task is not None,
            "servers": servers_info,
        }
    
    async def _get_server_stats(self, server_name: str) -> Dict[str, int]:
        """
        获取单个服务器的统计
        
        Args:
            server_name: 服务器名称
            
        Returns:
            统计字典
        """
        try:
            client = await self.redis._get_client()
            key = f"{self.KEY_PREFIX}:{server_name}:stats"
            
            stats = await client.hgetall(key)
            
            return {k: int(v) for k, v in stats.items()} if stats else {}
        except Exception:
            return {}
    
    # ==================== 清理 ====================
    
    async def cleanup(self) -> None:
        """
        清理所有资源（关闭时调用）
        """
        logger.info("🧹 开始清理 MCPPool...")
        
        # 停止健康检查
        self.stop_health_check()
        
        # 断开所有连接
        for url, state in self._servers.items():
            if state.client:
                try:
                    await state.client.disconnect()
                except Exception as e:
                    logger.debug(f"断开 MCP 连接失败 {url}: {e}")
        
        self._servers.clear()
        self._semaphores.clear()
        
        logger.info("✅ MCPPool 清理完成")


# ==================== 单例 ====================

_mcp_pool: Optional[MCPPool] = None


def get_mcp_pool() -> MCPPool:
    """
    获取 MCPPool 单例
    
    Returns:
        MCPPool 实例
    """
    global _mcp_pool
    if _mcp_pool is None:
        from services.redis_manager import get_redis_manager
        _mcp_pool = MCPPool(redis_manager=get_redis_manager())
    return _mcp_pool


def reset_mcp_pool() -> None:
    """
    重置单例（仅用于测试）
    """
    global _mcp_pool
    _mcp_pool = None
