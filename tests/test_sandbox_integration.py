"""
E2B 沙盒集成测试

测试完整的沙盒工作流：
1. 创建/连接沙盒
2. 文件操作（写入、读取、列表、删除）
3. 代码执行（包括流式输出）
4. 项目运行（如果有 E2B API Key）

使用方式：
    # 只测试本地逻辑（不连接 E2B）
    python tests/test_sandbox_integration.py --mock
    
    # 完整测试（需要 E2B API Key）
    python tests/test_sandbox_integration.py

    # 使用 pytest
    pytest tests/test_sandbox_integration.py -v
"""

import os
import sys
import asyncio
import pytest
from datetime import datetime
from typing import Optional
from unittest.mock import MagicMock, AsyncMock, patch

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ==================== 配置 ====================

TEST_CONVERSATION_ID = f"test_conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
TEST_USER_ID = "test_user_001"

# 检查是否有 E2B API Key
HAS_E2B_KEY = bool(os.getenv("E2B_API_KEY"))


# ==================== Mock 数据 ====================

class MockSandbox:
    """模拟 E2B Sandbox"""
    
    def __init__(self):
        self.sandbox_id = "mock_sandbox_123"
        self.files = {
            "/home/user": {},
            "/home/user/test.txt": "Hello World",
        }
        self._is_running = True
    
    def get_host(self, port):
        return f"mock-{self.sandbox_id}-{port}.e2b.dev"
    
    class files:
        @staticmethod
        def read(path):
            return MockSandbox().files.get(path, "")
        
        @staticmethod
        def write(path, content):
            MockSandbox().files[path] = content
        
        @staticmethod
        def list(path):
            return []
    
    class commands:
        @staticmethod
        def run(cmd, timeout=60):
            result = MagicMock()
            result.exit_code = 0
            result.stdout = f"Executed: {cmd}"
            result.stderr = ""
            return result
    
    def run_code(self, code, on_stdout=None, on_stderr=None, timeout=300):
        result = MagicMock()
        result.logs = MagicMock()
        result.logs.stdout = []
        result.logs.stderr = []
        result.results = []
        result.error = None
        
        if on_stdout:
            mock_log = MagicMock()
            mock_log.line = f"Output of: {code[:50]}..."
            on_stdout(mock_log)
        
        return result
    
    def pause(self):
        self._is_running = False
    
    def kill(self):
        self._is_running = False


# ==================== 测试类 ====================

class TestSandboxTools:
    """测试沙盒工具"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前设置"""
        from services.sandbox_service import SandboxService
        self.service = SandboxService()
        yield
    
    @pytest.mark.asyncio
    async def test_import_sandbox_tools(self):
        """测试工具导入"""
        from tools.sandbox_tools import (
            SANDBOX_TOOLS,
            get_sandbox_tools,
            SandboxListDir,
            SandboxReadFile,
            SandboxWriteFile,
            SandboxDeleteFile,
            SandboxFileExists,
            SandboxRunCommand,
            SandboxRunCode,
            SandboxCreateProject,
            SandboxRunProject,
        )
        
        # 验证工具数量
        assert len(SANDBOX_TOOLS) == 9, f"Expected 9 tools, got {len(SANDBOX_TOOLS)}"
        
        # 验证工具实例化
        tools = get_sandbox_tools()
        assert len(tools) == 9
        
        # 验证每个工具都有 name 和 description
        for tool in tools:
            assert tool.name, f"Tool {tool.__class__.__name__} missing name"
            assert tool.description, f"Tool {tool.name} missing description"
            assert tool.parameters, f"Tool {tool.name} missing parameters"
        
        print("✅ 所有工具导入成功")
    
    @pytest.mark.asyncio
    async def test_import_sandbox_service(self):
        """测试服务导入"""
        from services.sandbox_service import (
            SandboxService,
            get_sandbox_service,
            SandboxInfo,
            FileInfo,
            RunResult,
            CodeResult,
            SandboxServiceError,
            SandboxNotFoundError,
        )
        
        service = get_sandbox_service()
        
        # 验证关键方法存在
        methods = [
            'get_or_create_sandbox',
            'pause_sandbox',
            'resume_sandbox',
            'kill_sandbox',
            'list_files',
            'read_file',
            'write_file',
            'delete_file',
            'file_exists',
            'run_command',
            'run_code',
            'stop_project',
            'get_logs',
        ]
        
        for method in methods:
            assert hasattr(service, method), f"Service missing method: {method}"
        
        print("✅ SandboxService 验证通过")
    
    @pytest.mark.asyncio
    async def test_tool_parameters_schema(self):
        """测试工具参数 schema"""
        from tools.sandbox_tools import get_sandbox_tools
        
        tools = get_sandbox_tools()
        
        for tool in tools:
            params = tool.parameters
            
            # 验证基本结构
            assert params.get("type") == "object", f"{tool.name}: parameters type should be 'object'"
            assert "properties" in params, f"{tool.name}: parameters missing 'properties'"
            assert "required" in params, f"{tool.name}: parameters missing 'required'"
            
            # 验证必填参数
            required = params.get("required", [])
            assert "conversation_id" in required, f"{tool.name}: should require 'conversation_id'"
            
            print(f"  ✓ {tool.name}: schema valid")
        
        print("✅ 所有工具参数 schema 验证通过")


@pytest.mark.skipif(not HAS_E2B_KEY, reason="需要 E2B_API_KEY 环境变量")
class TestSandboxE2BIntegration:
    """E2B 集成测试（需要真实 API Key）"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前设置"""
        from services.sandbox_service import SandboxService
        self.service = SandboxService()
        self.conversation_id = TEST_CONVERSATION_ID
        self.user_id = TEST_USER_ID
        yield
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """完整工作流测试"""
        print("\n🧪 开始 E2B 集成测试...")
        
        # 1. 创建沙盒
        print("\n📦 Step 1: 创建沙盒")
        info = await self.service.get_or_create_sandbox(
            conversation_id=self.conversation_id,
            user_id=self.user_id
        )
        assert info.status == "running", f"Sandbox not running: {info.status}"
        assert info.e2b_sandbox_id, "Missing e2b_sandbox_id"
        print(f"  ✓ 沙盒创建成功: {info.e2b_sandbox_id}")
        
        # 2. 写入文件
        print("\n📝 Step 2: 写入文件")
        test_content = "print('Hello from E2B!')"
        result = await self.service.write_file(
            self.conversation_id,
            "/home/user/test_script.py",
            test_content
        )
        assert result["success"], f"Write failed: {result}"
        print(f"  ✓ 文件写入成功: /home/user/test_script.py")
        
        # 3. 读取文件
        print("\n📖 Step 3: 读取文件")
        content = await self.service.read_file(
            self.conversation_id,
            "/home/user/test_script.py"
        )
        assert content == test_content, f"Content mismatch: {content}"
        print(f"  ✓ 文件读取成功，内容匹配")
        
        # 4. 列出文件
        print("\n📂 Step 4: 列出文件")
        files = await self.service.list_files(self.conversation_id, "/home/user")
        file_names = [f.name for f in files]
        assert "test_script.py" in file_names, f"File not found: {file_names}"
        print(f"  ✓ 文件列表: {file_names}")
        
        # 5. 执行命令
        print("\n🖥️ Step 5: 执行命令")
        cmd_result = await self.service.run_command(
            self.conversation_id,
            "python /home/user/test_script.py"
        )
        assert cmd_result["success"], f"Command failed: {cmd_result}"
        assert "Hello from E2B!" in cmd_result["stdout"], f"Output mismatch: {cmd_result['stdout']}"
        print(f"  ✓ 命令执行成功: {cmd_result['stdout'].strip()}")
        
        # 6. 执行代码
        print("\n🐍 Step 6: 执行代码 (Code Interpreter)")
        code_result = await self.service.run_code(
            self.conversation_id,
            "print(1 + 2 + 3)"
        )
        assert code_result.success, f"Code execution failed: {code_result.error}"
        assert "6" in code_result.stdout, f"Output mismatch: {code_result.stdout}"
        print(f"  ✓ 代码执行成功: {code_result.stdout.strip()}")
        
        # 7. 删除文件
        print("\n🗑️ Step 7: 删除文件")
        delete_success = await self.service.delete_file(
            self.conversation_id,
            "/home/user/test_script.py"
        )
        assert delete_success, "Delete failed"
        print(f"  ✓ 文件删除成功")
        
        # 8. 验证文件不存在
        print("\n🔍 Step 8: 验证文件已删除")
        exists = await self.service.file_exists(
            self.conversation_id,
            "/home/user/test_script.py"
        )
        assert not exists, "File should not exist"
        print(f"  ✓ 文件已确认删除")
        
        # 9. 终止沙盒
        print("\n🔥 Step 9: 终止沙盒")
        killed = await self.service.kill_sandbox(self.conversation_id)
        assert killed, "Kill failed"
        print(f"  ✓ 沙盒已终止")
        
        print("\n✅ E2B 集成测试全部通过！")


class TestSandboxMocked:
    """模拟测试（不需要 E2B API Key）"""
    
    @pytest.mark.asyncio
    async def test_tool_execute_with_mock(self):
        """测试工具执行（使用 mock）"""
        from tools.sandbox_tools import SandboxListDir
        
        tool = SandboxListDir()
        
        # Mock service
        with patch('tools.sandbox_tools.get_sandbox_service') as mock_get_service:
            mock_service = AsyncMock()
            mock_service.list_files.return_value = [
                MagicMock(name="test.py", path="/home/user/test.py", type="file", size=100),
                MagicMock(name="data", path="/home/user/data", type="directory", size=None),
            ]
            mock_get_service.return_value = mock_service
            
            result = await tool.execute(
                conversation_id="test_conv",
                path="/home/user"
            )
            
            assert result["success"], f"Execution failed: {result}"
            assert len(result["files"]) == 2
            print(f"✅ SandboxListDir mock 测试通过")
    
    @pytest.mark.asyncio
    async def test_code_result_dataclass(self):
        """测试 CodeResult 数据类"""
        from services.sandbox_service import CodeResult
        
        result = CodeResult(
            success=True,
            stdout="Hello World",
            stderr="",
            error=None,
            execution_time=0.5,
            artifacts=[{"type": "text", "data": "output"}]
        )
        
        assert result.success
        assert result.stdout == "Hello World"
        assert len(result.artifacts) == 1
        print("✅ CodeResult 数据类测试通过")


# ==================== 手动测试入口 ====================

async def run_manual_tests(use_mock: bool = False):
    """手动运行测试"""
    print("=" * 60)
    print("🧪 E2B 沙盒集成测试")
    print("=" * 60)
    
    # 1. 测试导入
    print("\n📦 测试 1: 模块导入")
    try:
        from tools.sandbox_tools import SANDBOX_TOOLS, get_sandbox_tools
        from services.sandbox_service import SandboxService, get_sandbox_service, CodeResult
        print(f"  ✓ 工具数量: {len(SANDBOX_TOOLS)}")
        print(f"  ✓ SandboxService 可用")
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        return False
    
    # 2. 测试工具实例化
    print("\n🔧 测试 2: 工具实例化")
    try:
        tools = get_sandbox_tools()
        for tool in tools:
            print(f"  ✓ {tool.name}")
    except Exception as e:
        print(f"  ❌ 实例化失败: {e}")
        return False
    
    # 3. E2B 集成测试（如果有 API Key）
    if HAS_E2B_KEY and not use_mock:
        print("\n🌐 测试 3: E2B 集成测试")
        print("  (需要网络连接，可能需要 1-2 分钟)")
        
        try:
            service = get_sandbox_service()
            conv_id = TEST_CONVERSATION_ID
            user_id = TEST_USER_ID
            
            # 创建沙盒
            print("\n  → 创建沙盒...")
            info = await service.get_or_create_sandbox(conv_id, user_id)
            print(f"  ✓ 沙盒 ID: {info.e2b_sandbox_id}")
            
            # 执行代码
            print("\n  → 执行代码...")
            result = await service.run_code(conv_id, "print('Hello E2B!')")
            print(f"  ✓ 输出: {result.stdout.strip()}")
            
            # 写入文件
            print("\n  → 写入文件...")
            await service.write_file(conv_id, "/home/user/test.py", "x = 42")
            print(f"  ✓ 文件已写入")
            
            # 读取文件
            print("\n  → 读取文件...")
            content = await service.read_file(conv_id, "/home/user/test.py")
            print(f"  ✓ 内容: {content}")
            
            # 终止沙盒
            print("\n  → 终止沙盒...")
            await service.kill_sandbox(conv_id)
            print(f"  ✓ 沙盒已终止")
            
        except Exception as e:
            print(f"  ❌ E2B 测试失败: {e}")
            return False
    else:
        print("\n⚠️ 跳过 E2B 集成测试（未设置 E2B_API_KEY 或使用 mock 模式）")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="E2B 沙盒集成测试")
    parser.add_argument("--mock", action="store_true", help="使用 mock 模式（不连接 E2B）")
    args = parser.parse_args()
    
    success = asyncio.run(run_manual_tests(use_mock=args.mock))
    sys.exit(0 if success else 1)

