"""
沙盒工厂 - 创建和管理沙盒提供者实例

使用方式：
    # 获取沙盒提供者（单例）
    sandbox = get_sandbox_provider()
    
    # 或者显式创建
    sandbox = create_sandbox_provider("e2b")
    
    # 快捷方法
    result = await sandbox_run_command("conv_123", "pip install pandas")
    content = await sandbox_read_file("conv_123", "/app/main.py")
    await sandbox_write_file("conv_123", "/app/main.py", "print('hello')")
"""

import os
from typing import Optional

from logger import get_logger
from .base import (
    SandboxProvider,
    SandboxNotAvailableError,
    CommandResult,
    CodeResult,
)

logger = get_logger("infra.sandbox.factory")

# 全局单例
_sandbox_provider: Optional[SandboxProvider] = None


def create_sandbox_provider(
    provider_type: Optional[str] = None
) -> SandboxProvider:
    """
    创建沙盒提供者实例
    
    Args:
        provider_type: 提供者类型，支持 "e2b"（默认从环境变量读取）
        
    Returns:
        沙盒提供者实例
        
    Raises:
        ValueError: 不支持的提供者类型
    """
    # 从环境变量获取类型
    if provider_type is None:
        provider_type = os.getenv("SANDBOX_PROVIDER", "e2b")
    
    provider_type = provider_type.lower()
    
    if provider_type == "e2b":
        from .e2b import E2BSandboxProvider
        return E2BSandboxProvider()
    
    # 预留其他实现
    # elif provider_type == "docker":
    #     from .docker import DockerSandboxProvider
    #     return DockerSandboxProvider()
    # elif provider_type == "firecracker":
    #     from .firecracker import FirecrackerSandboxProvider
    #     return FirecrackerSandboxProvider()
    
    raise ValueError(f"不支持的沙盒提供者类型: {provider_type}")


def get_sandbox_provider() -> SandboxProvider:
    """
    获取沙盒提供者（单例模式）
    
    Returns:
        沙盒提供者实例
    """
    global _sandbox_provider
    
    if _sandbox_provider is None:
        _sandbox_provider = create_sandbox_provider()
    
    return _sandbox_provider


def reset_sandbox_provider():
    """重置沙盒提供者（用于测试）"""
    global _sandbox_provider
    _sandbox_provider = None


# ==================== 快捷方法 ====================


async def sandbox_ensure(
    conversation_id: str,
    user_id: str,
    stack: Optional[str] = None
):
    """
    确保沙盒存在
    
    Args:
        conversation_id: 对话 ID
        user_id: 用户 ID
        stack: 技术栈
        
    Returns:
        沙盒信息
    """
    provider = get_sandbox_provider()
    return await provider.ensure_sandbox(conversation_id, user_id, stack)


async def sandbox_run_command(
    conversation_id: str,
    command: str,
    timeout: int = 60,
    cwd: Optional[str] = None,
    *,
    auto_create: bool = True,
    user_id: str = "default_user"
) -> CommandResult:
    """
    在沙盒中执行命令
    
    Args:
        conversation_id: 对话 ID
        command: 要执行的命令
        timeout: 超时时间
        cwd: 工作目录
        auto_create: 如果沙盒不存在是否自动创建
        user_id: 用户 ID（用于自动创建）
        
    Returns:
        命令执行结果
    """
    provider = get_sandbox_provider()
    
    if not provider.is_available:
        return CommandResult(
            success=False,
            error="沙盒服务不可用，请检查 E2B_API_KEY 配置"
        )
    
    # 自动确保沙盒存在
    if auto_create:
        await provider.ensure_sandbox(conversation_id, user_id)
    
    return await provider.run_command(conversation_id, command, timeout, cwd)


async def sandbox_read_file(
    conversation_id: str,
    path: str,
    *,
    auto_create: bool = False,
    user_id: str = "default_user"
) -> str:
    """
    读取沙盒中的文件
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        auto_create: 如果沙盒不存在是否自动创建
        user_id: 用户 ID
        
    Returns:
        文件内容
    """
    provider = get_sandbox_provider()
    
    if auto_create:
        await provider.ensure_sandbox(conversation_id, user_id)
    
    return await provider.read_file(conversation_id, path)


async def sandbox_write_file(
    conversation_id: str,
    path: str,
    content: str,
    *,
    auto_create: bool = True,
    user_id: str = "default_user"
) -> bool:
    """
    写入文件到沙盒
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        content: 文件内容
        auto_create: 如果沙盒不存在是否自动创建
        user_id: 用户 ID
        
    Returns:
        是否成功
    """
    provider = get_sandbox_provider()
    
    if not provider.is_available:
        logger.error("沙盒服务不可用，无法写入文件")
        return False
    
    if auto_create:
        await provider.ensure_sandbox(conversation_id, user_id)
    
    return await provider.write_file(conversation_id, path, content)


async def sandbox_delete_file(
    conversation_id: str,
    path: str
) -> bool:
    """
    删除沙盒中的文件
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        
    Returns:
        是否成功
    """
    provider = get_sandbox_provider()
    return await provider.delete_file(conversation_id, path)


async def sandbox_list_dir(
    conversation_id: str,
    path: str = "/home/user"
):
    """
    列出沙盒目录内容
    
    Args:
        conversation_id: 对话 ID
        path: 目录路径
        
    Returns:
        文件列表
    """
    provider = get_sandbox_provider()
    return await provider.list_dir(conversation_id, path)


async def sandbox_file_exists(
    conversation_id: str,
    path: str
) -> bool:
    """
    检查沙盒中文件是否存在
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        
    Returns:
        是否存在
    """
    provider = get_sandbox_provider()
    return await provider.file_exists(conversation_id, path)


async def sandbox_run_project(
    conversation_id: str,
    project_path: str,
    stack: str,
    *,
    auto_create: bool = True,
    user_id: str = "default_user"
) -> Optional[str]:
    """
    运行沙盒中的项目
    
    Args:
        conversation_id: 对话 ID
        project_path: 项目路径
        stack: 技术栈
        auto_create: 如果沙盒不存在是否自动创建
        user_id: 用户 ID
        
    Returns:
        预览 URL
    """
    provider = get_sandbox_provider()
    
    if not provider.is_available:
        return None
    
    if auto_create:
        await provider.ensure_sandbox(conversation_id, user_id, stack)
    
    return await provider.run_project(conversation_id, project_path, stack)

