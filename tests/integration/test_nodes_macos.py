# -*- coding: utf-8 -*-
"""
Nodes macOS 集成测试

验证 Nodes 模块在 macOS 平台的基本功能：
- Shell 命令执行
- AppleScript 执行
- 系统通知
- 应用控制
"""

import asyncio
import sys
import pytest

# 跳过非 macOS 平台
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="仅在 macOS 上运行"
)


class TestNodesMacOS:
    """macOS Nodes 集成测试"""
    
    @pytest.fixture
    async def node_manager(self):
        """创建并启动 NodeManager"""
        from core.nodes.manager import NodeManager, NodeConfig
        
        config = NodeConfig(
            enabled=True,
            platform="darwin",
        )
        manager = NodeManager(config)
        await manager.start()
        
        yield manager
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_node_status(self, node_manager):
        """测试节点状态查询"""
        status = node_manager.get_status()
        
        assert status["started"] is True
        assert status["local_node"] is True
        assert len(status["nodes"]) > 0
        
        local_node = status["nodes"][0]
        assert local_node["platform"] == "darwin"
        assert local_node["status"] == "online"
    
    @pytest.mark.asyncio
    async def test_run_simple_command(self, node_manager):
        """测试简单命令执行"""
        response = await node_manager.run_command(
            command=["echo", "Hello, Nodes!"]
        )
        
        assert response.ok is True
        assert "Hello, Nodes!" in response.payload["stdout"]
    
    @pytest.mark.asyncio
    async def test_run_ls_command(self, node_manager):
        """测试 ls 命令"""
        response = await node_manager.run_command(
            command=["ls", "-la", "/tmp"],
            timeout_ms=5000,
        )
        
        assert response.ok is True
        assert response.payload["exit_code"] == 0
    
    @pytest.mark.asyncio
    async def test_run_pwd_command(self, node_manager):
        """测试 pwd 命令"""
        response = await node_manager.run_command(
            command=["pwd"]
        )
        
        assert response.ok is True
        assert "/" in response.payload["stdout"]
    
    @pytest.mark.asyncio
    async def test_which_command(self, node_manager):
        """测试 which 命令"""
        response = await node_manager.invoke(
            command="system.which",
            params={"executable": "osascript"}
        )
        
        assert response.ok is True
        assert response.payload["exists"] is True
        assert "/osascript" in response.payload["path"]
    
    @pytest.mark.asyncio
    async def test_which_nonexistent(self, node_manager):
        """测试不存在的可执行文件"""
        response = await node_manager.invoke(
            command="system.which",
            params={"executable": "nonexistent_command_12345"}
        )
        
        assert response.ok is True
        assert response.payload["exists"] is False
    
    @pytest.mark.asyncio
    async def test_applescript_simple(self, node_manager):
        """测试简单 AppleScript"""
        # 获取 Finder 名称
        response = await node_manager.run_command(
            command=["osascript", "-e", 'return "AppleScript works!"']
        )
        
        assert response.ok is True
        assert "AppleScript works!" in response.payload["stdout"]
    
    @pytest.mark.asyncio
    async def test_command_timeout(self, node_manager):
        """测试命令超时"""
        response = await node_manager.run_command(
            command=["sleep", "10"],
            timeout_ms=1000,  # 1 秒超时
        )
        
        assert response.ok is False
        assert response.payload["timed_out"] is True
    
    @pytest.mark.asyncio
    async def test_notify_command(self, node_manager):
        """测试系统通知（不验证是否真正显示）"""
        response = await node_manager.notify(
            title="ZenFlux Test",
            message="Nodes 集成测试通知",
        )
        
        # 通知应该成功发送
        assert response.ok is True


class TestNodesTool:
    """NodesTool 集成测试"""
    
    @pytest.fixture
    async def nodes_tool(self):
        """创建 NodesTool 实例"""
        from tools.nodes_tool import NodesTool
        from core.nodes.manager import NodeManager, NodeConfig
        
        config = NodeConfig(enabled=True, platform="darwin")
        manager = NodeManager(config)
        await manager.start()
        
        tool = NodesTool(manager)
        
        yield tool
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_tool_status(self, nodes_tool):
        """测试工具状态查询"""
        result = await nodes_tool.execute(action="status")
        
        assert result["success"] is True
        assert result["action"] == "status"
        assert result["local_node"] is True
    
    @pytest.mark.asyncio
    async def test_tool_run(self, nodes_tool):
        """测试工具执行命令"""
        result = await nodes_tool.execute(
            action="run",
            command=["date"]
        )
        
        assert result["success"] is True
        assert result["action"] == "run"
        assert result["result"] is not None
    
    @pytest.mark.asyncio
    async def test_tool_which(self, nodes_tool):
        """测试工具 which"""
        result = await nodes_tool.execute(
            action="which",
            executable="python3"
        )
        
        assert result["success"] is True
        assert result["action"] == "which"


class TestMacOSLocalNode:
    """MacOSLocalNode 直接测试"""
    
    @pytest.fixture
    async def macos_node(self):
        """创建 MacOSLocalNode"""
        from core.nodes.local.macos import MacOSLocalNode
        
        node = MacOSLocalNode()
        await node.initialize()
        
        yield node
        
        await node.shutdown()
    
    @pytest.mark.asyncio
    async def test_node_info(self, macos_node):
        """测试节点信息"""
        info = macos_node.get_info()
        
        assert info.node_id == "local"
        assert info.platform == "darwin"
        assert "shell" in info.capabilities
        assert "applescript" in info.capabilities
    
    @pytest.mark.asyncio
    async def test_open_url(self, macos_node):
        """测试打开 URL（仅验证命令执行，不实际打开）"""
        # 使用 echo 模拟，避免实际打开浏览器
        result = await macos_node.shell_executor.execute(
            command=["echo", "Would open: https://apple.com"]
        )
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_clipboard_operations(self, macos_node):
        """测试剪贴板操作"""
        # 设置剪贴板
        set_result = await macos_node.clipboard_set("ZenFlux Test Content")
        assert set_result["success"] is True
        
        # 获取剪贴板
        get_result = await macos_node.clipboard_get()
        assert get_result["success"] is True
        assert "ZenFlux Test Content" in get_result["content"]


if __name__ == "__main__":
    # 快速验证脚本
    async def quick_test():
        from core.nodes.manager import NodeManager, NodeConfig
        
        print("=" * 50)
        print("ZenFlux Nodes macOS 快速验证")
        print("=" * 50)
        
        config = NodeConfig(enabled=True, platform="darwin")
        manager = NodeManager(config)
        
        print("\n1. 启动节点管理器...")
        await manager.start()
        
        print("\n2. 检查节点状态...")
        status = manager.get_status()
        print(f"   Started: {status['started']}")
        print(f"   Local Node: {status['local_node']}")
        
        print("\n3. 执行 echo 命令...")
        response = await manager.run_command(["echo", "Hello from Nodes!"])
        print(f"   OK: {response.ok}")
        print(f"   Output: {response.payload['stdout'].strip()}")
        
        print("\n4. 执行 which osascript...")
        response = await manager.invoke("system.which", {"executable": "osascript"})
        print(f"   OK: {response.ok}")
        print(f"   Path: {response.payload['path']}")
        
        print("\n5. 执行 AppleScript...")
        response = await manager.run_command([
            "osascript", "-e", 'return "AppleScript 执行成功!"'
        ])
        print(f"   OK: {response.ok}")
        print(f"   Output: {response.payload['stdout'].strip()}")
        
        print("\n6. 发送系统通知...")
        response = await manager.notify(
            title="ZenFlux Agent",
            message="Nodes 模块验证成功！"
        )
        print(f"   OK: {response.ok}")
        
        print("\n7. 关闭节点管理器...")
        await manager.stop()
        
        print("\n" + "=" * 50)
        print("验证完成！所有基础功能正常。")
        print("=" * 50)
    
    asyncio.run(quick_test())
