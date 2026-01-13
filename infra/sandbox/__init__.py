"""
Sandbox 模块 - 沙盒执行环境

提供统一的沙盒操作接口，支持多种后端实现：
- E2B (e2b.dev) - 云端沙盒，推荐用于生产环境
- Docker - 本地容器（预留）
- Firecracker - 轻量级虚拟机（预留）

使用示例：
    from infra.sandbox import (
        get_sandbox_provider,
        sandbox_run_command,
        sandbox_write_file,
        sandbox_read_file,
    )
    
    # 方式 1：使用快捷函数
    result = await sandbox_run_command("conv_123", "pip install pandas")
    await sandbox_write_file("conv_123", "/app/main.py", "print('hello')")
    
    # 方式 2：使用 Provider 实例
    sandbox = get_sandbox_provider()
    await sandbox.ensure_sandbox("conv_123", "user_456")
    result = await sandbox.run_command("conv_123", "ls -la")
"""

# 抽象基类和数据类型
from .base import (
    SandboxProvider,
    SandboxInfo,
    SandboxStatus,
    FileInfo,
    CommandResult,
    CodeResult,
    SandboxError,
    SandboxNotFoundError,
    SandboxConnectionError,
    SandboxNotAvailableError,
)

# 工厂函数和单例
from .factory import (
    create_sandbox_provider,
    get_sandbox_provider,
    reset_sandbox_provider,
)

# 快捷函数
from .factory import (
    sandbox_ensure,
    sandbox_run_command,
    sandbox_read_file,
    sandbox_write_file,
    sandbox_delete_file,
    sandbox_list_dir,
    sandbox_file_exists,
    sandbox_run_project,
)

# E2B 实现（可选导入）
try:
    from .e2b import E2BSandboxProvider
except ImportError:
    E2BSandboxProvider = None


__all__ = [
    # 抽象基类
    "SandboxProvider",
    
    # 数据类型
    "SandboxInfo",
    "SandboxStatus",
    "FileInfo",
    "CommandResult",
    "CodeResult",
    
    # 异常
    "SandboxError",
    "SandboxNotFoundError",
    "SandboxConnectionError",
    "SandboxNotAvailableError",
    
    # 工厂函数
    "create_sandbox_provider",
    "get_sandbox_provider",
    "reset_sandbox_provider",
    
    # 快捷函数
    "sandbox_ensure",
    "sandbox_run_command",
    "sandbox_read_file",
    "sandbox_write_file",
    "sandbox_delete_file",
    "sandbox_list_dir",
    "sandbox_file_exists",
    "sandbox_run_project",
    
    # 实现类
    "E2BSandboxProvider",
]

