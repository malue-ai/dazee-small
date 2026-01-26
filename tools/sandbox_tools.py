"""
沙盒工具 - E2B 沙盒操作

设计原则：
1. 贴近 E2B 原生 API
2. 原子化：每个工具只做一件事
3. 灵活性：让 Agent 自己决定如何组合

标准工具（6 个）：
- sandbox_write_file: 写入文件
- sandbox_read_file: 读取文件
- sandbox_list_files: 列出目录
- sandbox_run_command: 执行命令（支持 background 参数）
- sandbox_execute_python: 执行 Python 代码（Code Interpreter）
- sandbox_get_public_url: 获取公开 URL

典型工作流：
1. sandbox_write_file("package.json", content)
2. sandbox_write_file("index.js", content)
3. sandbox_run_command("npm install")
4. sandbox_run_command("npm start", background=True)
5. sandbox_get_public_url(port=3000)
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional

from logger import get_logger
from tools.base import BaseTool
from services.sandbox_service import (
    get_sandbox_service,
    SandboxServiceError,
    SandboxNotFoundError
)
from infra.sandbox import get_sandbox_provider
from infra.database import AsyncSessionLocal, crud

logger = get_logger("sandbox_tools")


# ==================== 后台沙盒创建任务跟踪 ====================

# 存储进行中的沙盒创建任务: conversation_id -> Task
_sandbox_creation_tasks: Dict[str, asyncio.Task] = {}


def start_sandbox_creation_background(conversation_id: str, user_id: str = "default_user") -> None:
    """
    后台启动沙盒创建（不阻塞调用方）
    
    Args:
        conversation_id: 对话 ID
        user_id: 用户 ID
    """
    # 如果已有进行中的任务，跳过
    if conversation_id in _sandbox_creation_tasks:
        task = _sandbox_creation_tasks[conversation_id]
        if not task.done():
            logger.debug(f"⏳ 沙盒创建任务已在进行中: {conversation_id}")
            return
    
    async def _create_sandbox():
        """后台创建沙盒的协程"""
        try:
            service = get_sandbox_service()
            await service.get_or_create_sandbox(conversation_id, user_id)
            logger.info(f"🏖️ 后台沙盒创建完成: {conversation_id}")
        except Exception as e:
            logger.warning(f"⚠️ 后台沙盒创建失败: {conversation_id}, {e}")
        finally:
            # 清理任务引用
            _sandbox_creation_tasks.pop(conversation_id, None)
    
    # 创建后台任务
    task = asyncio.create_task(_create_sandbox())
    _sandbox_creation_tasks[conversation_id] = task
    logger.info(f"🚀 已启动后台沙盒创建: {conversation_id}")


async def wait_for_sandbox_creation(conversation_id: str, timeout: float = 60.0) -> bool:
    """
    等待后台沙盒创建完成（如果有进行中的任务）
    
    Args:
        conversation_id: 对话 ID
        timeout: 最大等待时间（秒）
        
    Returns:
        True 如果沙盒已就绪，False 如果超时或失败
    """
    task = _sandbox_creation_tasks.get(conversation_id)
    if task is None or task.done():
        return True
    
    try:
        logger.debug(f"⏳ 等待后台沙盒创建完成: {conversation_id}")
        await asyncio.wait_for(task, timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ 等待后台沙盒创建超时: {conversation_id}")
        return False
    except Exception as e:
        logger.warning(f"⚠️ 后台沙盒创建任务异常: {conversation_id}, {e}")
        return False


# 沙盒默认项目目录（所有操作的根目录）
SANDBOX_PROJECT_ROOT = "/home/user/project"


def _normalize_path(path: str) -> str:
    """
    标准化路径为沙盒绝对路径。
    
    所有相对路径都基于 /home/user/project 目录。
    Agent 只需传相对路径（如 src/index.js），工具会自动处理。

    Args:
        path: 路径（相对路径或绝对路径）
              - 空/None → /home/user/project
              - src/index.js → /home/user/project/src/index.js
              - /home/user/xxx → /home/user/xxx（保持原样）

    Returns:
        标准化后的绝对路径
    """
    if not path:
        return SANDBOX_PROJECT_ROOT

    # 绝对路径保持原样
    if path.startswith("/"):
        return path

    # 相对路径基于项目根目录
    return f"{SANDBOX_PROJECT_ROOT}/{path}".replace("//", "/")


async def ensure_sandbox(conversation_id: str, user_id: str = "default_user") -> bool:
    """
    确保沙盒存在
    
    如果有后台创建任务正在进行，会先等待其完成
    """
    # 1. 先等待后台任务完成（如果有）
    await wait_for_sandbox_creation(conversation_id, timeout=60.0)
    
    # 2. 检查沙盒状态并按需创建
    service = get_sandbox_service()
    try:
        status = await service.get_sandbox_status(conversation_id)
        if status is None:
            await service.get_or_create_sandbox(conversation_id, user_id)
        elif status.status == "paused":
            await service.resume_sandbox(conversation_id)
        elif status.status not in ("running",):
            await service.get_or_create_sandbox(conversation_id, user_id)
        return True
    except SandboxNotFoundError:
        await service.get_or_create_sandbox(conversation_id, user_id)
        return True
    except Exception as e:
        logger.error(f"❌ 沙盒初始化失败: {e}", exc_info=True)
        raise


# ==================== 工具 1: 写文件 ====================

class SandboxWriteFile(BaseTool):
    """写文件到沙盒"""
    
    @property
    def name(self) -> str:
        return "sandbox_write_file"
    
    @property
    def description(self) -> str:
        return (
            "在沙盒中写入文件。目录不存在会自动创建。\n"
            "默认项目目录: /home/user/project\n"
            "路径示例：src/index.js → /home/user/project/src/index.js"
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "path": {"type": "string", "description": "文件路径（相对路径自动基于 /home/user/project）"},
                "content": {"type": "string", "description": "文件内容"}
            },
            "required": ["path", "content"]
        }
    
    async def execute(self, conversation_id: str, path: str, content: str, **kwargs) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            service = get_sandbox_service()
            
            normalized_path = _normalize_path(path)
            result = await service.write_file(conversation_id, normalized_path, content)
            
            return {
                "success": True,
                "path": normalized_path,
                "size": result["size"]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 工具 2: 读取文件 ====================

class SandboxReadFile(BaseTool):
    """从沙盒读取文件"""
    
    @property
    def name(self) -> str:
        return "sandbox_read_file"
    
    @property
    def description(self) -> str:
        return (
            "读取沙盒中的文件内容。\n"
            "默认项目目录: /home/user/project\n"
            "路径示例：src/index.js → /home/user/project/src/index.js"
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "path": {"type": "string", "description": "文件路径（相对路径自动基于 /home/user/project）"}
            },
            "required": ["path"]
        }
    
    async def execute(self, conversation_id: str, path: str, **kwargs) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            
            provider = get_sandbox_provider()
            normalized_path = _normalize_path(path)
            content = await provider.read_file(conversation_id, normalized_path)
            
            return {
                "success": True,
                "path": normalized_path,
                "content": content
            }
        except FileNotFoundError:
            return {"success": False, "error": f"文件不存在: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 工具 3: 列出目录 ====================

class SandboxListFiles(BaseTool):
    """列出沙盒中的目录内容"""
    
    @property
    def name(self) -> str:
        return "sandbox_list_files"
    
    @property
    def description(self) -> str:
        return (
            "列出沙盒中指定目录的文件和子目录。\n"
            "默认目录: /home/user/project"
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID（系统自动注入，无需手动传递）"},
                "path": {"type": "string", "description": "目录路径（默认 /home/user/project）"}
            },
            "required": []
        }
    
    async def execute(
        self,
        conversation_id: str,
        path: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            
            provider = get_sandbox_provider()
            normalized_path = _normalize_path(path) if path else SANDBOX_PROJECT_ROOT
            entries = await provider.list_dir(conversation_id, normalized_path)
            
            # 转换为简单的列表格式
            files = [
                {
                    "name": entry.name,
                    "type": entry.type,
                    "size": entry.size
                }
                for entry in entries
            ]
            
            return {
                "success": True,
                "path": normalized_path,
                "files": files
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 工具 4: 执行命令 ====================

class SandboxRunCommand(BaseTool):
    """在沙盒中执行命令"""
    
    @property
    def name(self) -> str:
        return "sandbox_run_command"
    
    @property
    def description(self) -> str:
        return (
            "在沙盒中执行终端命令。\n\n"
            "用途：\n"
            "- 安装依赖：npm install, pip install\n"
            "- 启动服务器：npm start, python app.py（使用 background=true + port）\n"
            "- 文件操作：cat, ls, rm, mkdir\n\n"
            "默认工作目录: /home/user/project\n\n"
            "⚠️ 启动服务器时：\n"
            "- 设置 background=true 让服务在后台运行\n"
            "- 设置 port 参数，会自动返回公开访问 URL\n"
            "- 服务必须监听 0.0.0.0 才能从外部访问"
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "command": {"type": "string", "description": "要执行的命令"},
                "background": {"type": "boolean", "description": "是否在后台运行（用于启动服务器）", "default": False},
                "port": {"type": "integer", "description": "服务端口（background=true 时指定，会自动返回公开 URL）"},
                "cwd": {"type": "string", "description": "工作目录（默认 /home/user/project）"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 120，background 模式忽略）", "default": 120}
            },
            "required": ["command"]
        }
    
    async def execute(
        self,
        conversation_id: str,
        command: str,
        background: bool = False,
        port: Optional[int] = None,
        cwd: Optional[str] = None,
        timeout: int = 120,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            
            provider = get_sandbox_provider()
            sandbox = await provider._get_sandbox_obj(conversation_id)
            
            # 标准化工作目录
            normalized_cwd = _normalize_path(cwd) if cwd else SANDBOX_PROJECT_ROOT
            
            # 构建完整命令
            full_command = f"cd {normalized_cwd} && {command}"
            
            if background:
                # 后台模式：立即返回，不等待结果
                logger.info(f"🚀 后台执行命令: {command}")
                try:
                    await sandbox.commands.run(
                        f"{full_command} > /tmp/app.log 2>&1",
                        background=True,
                        timeout=10
                    )
                except Exception as e:
                    # 后台启动可能会超时，但这是正常的
                    if "timeout" not in str(e).lower():
                        logger.warning(f"⚠️ 后台命令异常（可能正常）: {e}")
                
                result = {
                    "success": True,
                    "background": True,
                    "message": f"命令已在后台启动: {command}",
                    "sandbox_id": sandbox.sandbox_id,  # E2B 实际沙箱 ID
                }
                
                # 如果指定了端口，自动返回公开 URL
                if port:
                    try:
                        host = sandbox.get_host(port)
                        url = f"https://{host}"
                        result["url"] = url
                        result["port"] = port
                        logger.info(f"🌐 服务 URL: {url}")
                        
                        # 🆕 添加过期时间信息
                        try:
                            async with AsyncSessionLocal() as session:
                                db_sandbox = await crud.get_sandbox_by_conversation(
                                    session, conversation_id
                                )
                                
                                if db_sandbox and db_sandbox.last_active_at:
                                    default_timeout = provider.DEFAULT_TIMEOUT_SECONDS
                                    last_active_ts = db_sandbox.last_active_at.timestamp()
                                    expires_ts = last_active_ts + default_timeout
                                    result["expires_at"] = int(expires_ts * 1000)
                                    result["timeout_seconds"] = max(0, int(expires_ts - time.time()))
                        except Exception as e:
                            logger.warning(f"⚠️ 获取沙盒过期时间失败: {e}")
                    except Exception as e:
                        logger.warning(f"⚠️ 获取 URL 失败: {e}")
                        result["url_error"] = str(e)
                
                return result
            else:
                # 同步模式：等待结果
                result = await sandbox.commands.run(full_command, timeout=timeout)
                
                return {
                    "success": result.exit_code == 0,
                    "output": result.stdout or "",
                    "error": result.stderr if result.exit_code != 0 else None,
                    "exit_code": result.exit_code
                }
                
        except Exception as e:
            logger.error(f"❌ 执行命令失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# ==================== 工具 5: 执行 Python 代码 ====================

class SandboxExecutePython(BaseTool):
    """在沙盒中执行 Python 代码（Code Interpreter）"""
    
    @property
    def name(self) -> str:
        return "sandbox_execute_python"
    
    @property
    def description(self) -> str:
        return (
            "执行 Python 代码并返回结果（基于 Jupyter 内核）。\n\n"
            "特性：\n"
            "- 上下文共享：多次执行间变量、导入、函数定义会保留\n"
            "- 图表支持：matplotlib 等图表会自动捕获并返回\n"
            "- 预装包：pandas、numpy、matplotlib 等无需手动安装\n\n"
            "适用场景：\n"
            "- 数据分析和可视化\n"
            "- 快速计算和验证\n"
            "- 生成图表"
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID"},
                "code": {"type": "string", "description": "要执行的 Python 代码"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 300）", "default": 300}
            },
            "required": ["code"]
        }
    
    async def execute(
        self,
        conversation_id: str,
        code: str,
        timeout: int = 300,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            
            provider = get_sandbox_provider()
            result = await provider.run_code(conversation_id, code, timeout=timeout)
            
            return {
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.error,
                "execution_time": result.execution_time,
                "artifacts": result.artifacts  # 图表等
            }
            
        except Exception as e:
            logger.error(f"❌ 执行 Python 代码失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# ==================== 工具 6: 获取公开 URL ====================

class SandboxGetPublicUrl(BaseTool):
    """获取沙盒服务的公开 URL"""
    
    @property
    def name(self) -> str:
        return "sandbox_get_public_url"
    
    @property
    def description(self) -> str:
        return (
            "获取沙盒中运行服务的公开 URL。\n"
            "在使用 sandbox_run_command(background=true) 启动服务后调用此工具获取访问链接。\n"
            "默认端口: 3000"
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "对话 ID（系统自动注入，无需手动传递）"},
                "port": {"type": "integer", "description": "服务端口", "default": 3000}
            },
            "required": []
        }
    
    async def execute(
        self,
        conversation_id: str,
        port: int = 3000,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            await ensure_sandbox(conversation_id, kwargs.get("user_id", "default_user"))
            
            provider = get_sandbox_provider()
            sandbox = await provider._get_sandbox_obj(conversation_id)
            
            host = sandbox.get_host(port)
            url = f"https://{host}"
            
            # 计算过期时间
            expires_at = None
            timeout_seconds = None
            
            try:
                # 从数据库获取沙盒的最后活跃时间
                async with AsyncSessionLocal() as session:
                    db_sandbox = await crud.get_sandbox_by_conversation(
                        session, conversation_id
                    )
                    
                    if db_sandbox and db_sandbox.last_active_at:
                        # E2B 默认超时时间（30 分钟）
                        default_timeout = provider.DEFAULT_TIMEOUT_SECONDS
                        
                        # 计算过期时间戳（毫秒）
                        last_active_ts = db_sandbox.last_active_at.timestamp()
                        expires_ts = last_active_ts + default_timeout
                        expires_at = int(expires_ts * 1000)  # 转换为毫秒
                        
                        # 计算剩余秒数
                        now_ts = time.time()
                        timeout_seconds = max(0, int(expires_ts - now_ts))
                        
                        logger.debug(
                            f"📅 沙盒过期时间: expires_at={expires_at}, "
                            f"timeout_seconds={timeout_seconds}"
                        )
            except Exception as e:
                # 获取过期时间失败不影响主功能
                logger.warning(f"⚠️ 获取沙盒过期时间失败: {e}")
            
            result = {
                "success": True,
                "url": url,
                "port": port,
                "sandbox_id": sandbox.sandbox_id  # E2B 实际沙箱 ID
            }
            
            # 添加过期时间信息（如果获取成功）
            if expires_at is not None:
                result["expires_at"] = expires_at
            if timeout_seconds is not None:
                result["timeout_seconds"] = timeout_seconds
            
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 工具注册 ====================

# 6 个标准工具（贴近 E2B 原生 API）
SANDBOX_TOOLS = [
    SandboxWriteFile,       # 写入文件
    SandboxReadFile,        # 读取文件
    SandboxListFiles,       # 列出目录
    SandboxRunCommand,      # 执行命令（支持 background）
    SandboxExecutePython,   # 执行 Python 代码
    SandboxGetPublicUrl,    # 获取公开 URL
]


def get_sandbox_tools() -> list[BaseTool]:
    """获取所有沙盒工具实例"""
    return [t() for t in SANDBOX_TOOLS]
