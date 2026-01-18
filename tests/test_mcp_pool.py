"""
测试 MCP 客户端池功能

测试内容：
1. MCPPool 初始化和配置
2. MCPConfig 数据类
3. 客户端获取和缓存
4. 统计功能
5. 健康检查（模拟）
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from infra.pools.mcp_pool import (
    MCPPool,
    MCPConfig,
    MCPServerState,
    get_mcp_pool,
    reset_mcp_pool,
)


class TestMCPConfig:
    """测试 MCPConfig 数据类"""
    
    def test_basic_config(self):
        """测试基本配置创建"""
        config = MCPConfig(
            server_url="https://api.example.com/mcp",
            server_name="test_server",
            auth_type="bearer",
            auth_env="TEST_API_KEY",
        )
        
        assert config.server_url == "https://api.example.com/mcp"
        assert config.server_name == "test_server"
        assert config.auth_type == "bearer"
        assert config.auth_env == "TEST_API_KEY"
    
    def test_default_values(self):
        """测试默认值"""
        config = MCPConfig(server_url="https://api.example.com/mcp")
        
        assert config.server_name == "unknown"
        assert config.auth_type == "none"
        assert config.auth_env is None
        assert config.tool_timeout == 1200.0
        assert config.connect_timeout == 30.0
        assert config.max_retries == 2
    
    def test_get_auth_token_with_env(self):
        """测试从环境变量获取认证令牌"""
        config = MCPConfig(
            server_url="https://api.example.com/mcp",
            auth_type="bearer",
            auth_env="TEST_MCP_TOKEN",
        )
        
        with patch.dict("os.environ", {"TEST_MCP_TOKEN": "test_token_value"}):
            token = config.get_auth_token()
            assert token == "test_token_value"
    
    def test_get_auth_token_without_env(self):
        """测试无认证配置"""
        config = MCPConfig(
            server_url="https://api.example.com/mcp",
            auth_type="none",
        )
        
        token = config.get_auth_token()
        assert token is None
    
    def test_get_auth_token_missing_env(self):
        """测试环境变量未设置"""
        config = MCPConfig(
            server_url="https://api.example.com/mcp",
            auth_type="bearer",
            auth_env="MISSING_ENV_VAR",
        )
        
        # 确保环境变量不存在
        with patch.dict("os.environ", {}, clear=True):
            token = config.get_auth_token()
            assert token is None


class TestMCPServerState:
    """测试 MCPServerState 数据类"""
    
    def test_initial_state(self):
        """测试初始状态"""
        config = MCPConfig(server_url="https://api.example.com/mcp")
        state = MCPServerState(config=config)
        
        assert state.config == config
        assert state.client is None
        assert state.connected is False
        assert state.last_connected_at is None
        assert state.last_health_check is None
        assert state.reconnect_attempts == 0
        assert state.tools_count == 0


class TestMCPPool:
    """测试 MCPPool 类"""
    
    @pytest.fixture
    def mock_redis_manager(self):
        """创建模拟的 Redis 管理器"""
        mock = MagicMock()
        mock_client = AsyncMock()
        mock_client.hincrby = AsyncMock(return_value=1)
        mock_client.set = AsyncMock()
        mock_client.expire = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.sadd = AsyncMock()
        mock_client.hgetall = AsyncMock(return_value={})
        mock._get_client = AsyncMock(return_value=mock_client)
        return mock
    
    @pytest.fixture
    def mcp_pool(self, mock_redis_manager):
        """创建 MCPPool 实例"""
        return MCPPool(redis_manager=mock_redis_manager)
    
    def test_pool_initialization(self, mcp_pool):
        """测试池初始化"""
        assert mcp_pool._servers == {}
        assert mcp_pool._semaphores == {}
        assert mcp_pool._health_check_task is None
        assert mcp_pool._shutdown is False
    
    def test_pool_config_from_env(self, mock_redis_manager):
        """测试从环境变量读取配置"""
        with patch.dict("os.environ", {
            "MCP_MAX_CONCURRENT": "10",
            "MCP_HEALTH_CHECK_INTERVAL": "120",
            "MCP_CONNECT_TIMEOUT": "60.0",
        }):
            pool = MCPPool(redis_manager=mock_redis_manager)
            
            assert pool.max_concurrent_per_server == 10
            assert pool.health_check_interval == 120
            assert pool.connect_timeout == 60.0
    
    @pytest.mark.asyncio
    async def test_increment_stat(self, mcp_pool, mock_redis_manager):
        """测试统计计数增加"""
        result = await mcp_pool.increment_stat("test_server", "cache_hits", 1)
        
        assert result == 1
        mock_client = await mock_redis_manager._get_client()
        mock_client.hincrby.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_stats_empty(self, mcp_pool):
        """测试空池的统计"""
        stats = await mcp_pool.get_stats()
        
        assert stats["total_servers"] == 0
        assert stats["connected_servers"] == 0
        assert stats["health_check_running"] is False
        assert stats["servers"] == {}
        assert "timestamp" in stats
    
    @pytest.mark.asyncio
    async def test_collect_mcp_configs_empty_registry(self, mcp_pool):
        """测试空 Agent 注册表时收集配置"""
        # patch 在函数内部导入的位置
        with patch("services.agent_registry.get_agent_registry") as mock_get_registry:
            mock_registry = MagicMock()
            mock_registry._configs = {}
            mock_get_registry.return_value = mock_registry
            
            configs = await mcp_pool._collect_mcp_configs()
            
            assert configs == {}
    
    @pytest.mark.asyncio
    async def test_preconnect_all_no_configs(self, mcp_pool):
        """测试无 MCP 配置时预连接"""
        with patch.object(mcp_pool, "_collect_mcp_configs", return_value={}):
            results = await mcp_pool.preconnect_all()
            
            assert results == {}
    
    @pytest.mark.asyncio
    async def test_start_health_check(self, mcp_pool):
        """测试启动健康检查（异步上下文）"""
        # 启动健康检查
        mcp_pool.start_health_check()
        
        assert mcp_pool._health_check_task is not None
        assert mcp_pool._shutdown is False
        
        # 清理：停止任务
        mcp_pool.stop_health_check()
        # 等待任务取消
        await asyncio.sleep(0.1)
    
    @pytest.mark.asyncio
    async def test_stop_health_check(self, mcp_pool):
        """测试停止健康检查（异步上下文）"""
        # 启动然后停止
        mcp_pool.start_health_check()
        mcp_pool.stop_health_check()
        
        assert mcp_pool._shutdown is True
        assert mcp_pool._health_check_task is None
    
    def test_get_client_sync_not_found(self, mcp_pool):
        """测试同步获取不存在的客户端"""
        client = mcp_pool.get_client_sync("https://not-exist.com/mcp")
        
        assert client is None
    
    def test_get_all_clients_empty(self, mcp_pool):
        """测试获取空池的所有客户端"""
        clients = mcp_pool.get_all_clients()
        
        assert clients == {}
    
    @pytest.mark.asyncio
    async def test_cleanup(self, mcp_pool):
        """测试清理"""
        # 启动健康检查
        mcp_pool.start_health_check()
        
        # 等待任务启动
        await asyncio.sleep(0.1)
        
        # 清理
        await mcp_pool.cleanup()
        
        assert mcp_pool._shutdown is True
        assert mcp_pool._servers == {}
        assert mcp_pool._semaphores == {}


class TestMCPPoolSingleton:
    """测试 MCPPool 单例模式"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        reset_mcp_pool()
    
    def teardown_method(self):
        """每个测试后重置单例"""
        reset_mcp_pool()
    
    def test_get_mcp_pool_singleton(self):
        """测试单例获取"""
        # patch 在函数内部导入的位置
        with patch("services.redis_manager.get_redis_manager") as mock_get_redis:
            mock_redis = MagicMock()
            mock_get_redis.return_value = mock_redis
            
            pool1 = get_mcp_pool()
            pool2 = get_mcp_pool()
            
            assert pool1 is pool2
    
    def test_reset_mcp_pool(self):
        """测试重置单例"""
        with patch("services.redis_manager.get_redis_manager") as mock_get_redis:
            mock_redis = MagicMock()
            mock_get_redis.return_value = mock_redis
            
            pool1 = get_mcp_pool()
            reset_mcp_pool()
            pool2 = get_mcp_pool()
            
            assert pool1 is not pool2


class TestMCPPoolIntegration:
    """集成测试（需要模拟 MCPClientWrapper）"""
    
    @pytest.fixture
    def mock_mcp_client(self):
        """创建模拟的 MCP 客户端"""
        mock = MagicMock()
        mock._connected = True
        mock._tools = {"tool1": {"name": "tool1", "description": "Test tool"}}
        mock.connect = AsyncMock(return_value=True)
        mock.disconnect = AsyncMock()
        mock.discover_tools = AsyncMock(return_value=[
            {"name": "tool1", "description": "Test tool"}
        ])
        mock.call_tool = AsyncMock(return_value={"success": True, "data": "result"})
        return mock
    
    @pytest.fixture
    def mock_redis_manager(self):
        """创建模拟的 Redis 管理器"""
        mock = MagicMock()
        mock_client = AsyncMock()
        mock_client.hincrby = AsyncMock(return_value=1)
        mock_client.set = AsyncMock()
        mock_client.expire = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.sadd = AsyncMock()
        mock_client.hgetall = AsyncMock(return_value={})
        mock._get_client = AsyncMock(return_value=mock_client)
        return mock
    
    @pytest.mark.asyncio
    async def test_get_client_creates_new_connection(
        self, mock_redis_manager, mock_mcp_client
    ):
        """测试获取客户端时创建新连接"""
        pool = MCPPool(redis_manager=mock_redis_manager)
        
        # patch 在函数内部导入的位置
        with patch(
            "services.mcp_client.MCPClientWrapper",
            return_value=mock_mcp_client
        ):
            client = await pool.get_client(
                server_url="https://api.example.com/mcp",
                server_name="test_server",
                auth_token="test_token"
            )
            
            assert client is mock_mcp_client
            mock_mcp_client.connect.assert_called_once()
            mock_mcp_client.discover_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_client_reuses_cached_connection(
        self, mock_redis_manager, mock_mcp_client
    ):
        """测试获取客户端时复用缓存的连接"""
        pool = MCPPool(redis_manager=mock_redis_manager)
        
        # 预先添加一个已连接的客户端
        config = MCPConfig(
            server_url="https://api.example.com/mcp",
            server_name="test_server"
        )
        pool._servers["https://api.example.com/mcp"] = MCPServerState(
            config=config,
            client=mock_mcp_client,
            connected=True,
            tools_count=1,
        )
        
        client = await pool.get_client(
            server_url="https://api.example.com/mcp",
            server_name="test_server"
        )
        
        assert client is mock_mcp_client
        # 不应该调用 connect，因为复用了缓存
        mock_mcp_client.connect.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_stats_with_servers(self, mock_redis_manager, mock_mcp_client):
        """测试有服务器时的统计"""
        pool = MCPPool(redis_manager=mock_redis_manager)
        
        # 添加一个服务器
        config = MCPConfig(
            server_url="https://api.example.com/mcp",
            server_name="test_server"
        )
        pool._servers["https://api.example.com/mcp"] = MCPServerState(
            config=config,
            client=mock_mcp_client,
            connected=True,
            tools_count=5,
            last_connected_at=datetime.now(),
        )
        
        stats = await pool.get_stats()
        
        assert stats["total_servers"] == 1
        assert stats["connected_servers"] == 1
        assert "https://api.example.com/mcp" in stats["servers"]
        assert stats["servers"]["https://api.example.com/mcp"]["tools_count"] == 5
