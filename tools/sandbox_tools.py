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
from core.tool.base import BaseTool, ToolContext
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
    """写文件到沙盒（input_schema 由 capabilities.yaml 定义）"""
    
    name = "sandbox_write_file"
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """执行写文件操作"""
        conversation_id = context.conversation_id
        path = params.get("path", "")
        content = params.get("content", "")
        user_id = context.user_id or "default_user"
        
        try:
            await ensure_sandbox(conversation_id, user_id)
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
    """从沙盒读取文件（input_schema 由 capabilities.yaml 定义）"""
    
    name = "sandbox_read_file"
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """执行读文件操作"""
        conversation_id = context.conversation_id
        path = params.get("path", "")
        user_id = context.user_id or "default_user"
        
        try:
            await ensure_sandbox(conversation_id, user_id)
            
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
    """列出沙盒中的目录内容（input_schema 由 capabilities.yaml 定义）"""
    
    name = "sandbox_list_files"
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """执行列出目录操作"""
        conversation_id = context.conversation_id
        path = params.get("path")
        user_id = context.user_id or "default_user"
        
        try:
            await ensure_sandbox(conversation_id, user_id)
            
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
    """在沙盒中执行命令（input_schema 由 capabilities.yaml 定义）"""
    
    name = "sandbox_run_command"
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """执行命令"""
        conversation_id = context.conversation_id
        command = params.get("command", "")
        background = params.get("background", False)
        port = params.get("port")
        cwd = params.get("cwd")
        timeout = params.get("timeout", 120)
        user_id = context.user_id or "default_user"
        
        try:
            await ensure_sandbox(conversation_id, user_id)
            
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
                                
                                logger.debug(
                                    f"📊 查询沙盒记录: conversation_id={conversation_id}, "
                                    f"db_sandbox={db_sandbox is not None}, "
                                    f"last_active_at={db_sandbox.last_active_at if db_sandbox else 'N/A'}"
                                )
                                
                                if db_sandbox and db_sandbox.last_active_at:
                                    default_timeout = provider.DEFAULT_TIMEOUT_SECONDS
                                    last_active_ts = db_sandbox.last_active_at.timestamp()
                                    expires_ts = last_active_ts + default_timeout
                                    result["expires_at"] = int(expires_ts * 1000)
                                    result["timeout_seconds"] = max(0, int(expires_ts - time.time()))
                                    logger.info(
                                        f"📅 沙盒过期时间: expires_at={result['expires_at']}, "
                                        f"timeout_seconds={result['timeout_seconds']}"
                                    )
                                else:
                                    logger.warning(
                                        f"⚠️ 无法计算过期时间: db_sandbox存在={db_sandbox is not None}, "
                                        f"last_active_at={getattr(db_sandbox, 'last_active_at', 'N/A')}"
                                    )
                        except Exception as e:
                            logger.warning(f"⚠️ 获取沙盒过期时间失败: {e}", exc_info=True)
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
    """在沙盒中执行 Python 代码（input_schema 由 capabilities.yaml 定义）"""
    
    name = "sandbox_execute_python"
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """执行 Python 代码"""
        conversation_id = context.conversation_id
        code = params.get("code", "")
        timeout = params.get("timeout", 300)
        user_id = context.user_id or "default_user"
        
        try:
            await ensure_sandbox(conversation_id, user_id)
            
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
    """获取沙盒服务的公开 URL（input_schema 由 capabilities.yaml 定义）"""
    
    name = "sandbox_get_public_url"
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """获取公开 URL"""
        conversation_id = context.conversation_id
        port = params.get("port", 3000)
        user_id = context.user_id or "default_user"
        
        try:
            await ensure_sandbox(conversation_id, user_id)
            
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
                    
                    logger.debug(
                        f"📊 查询沙盒记录: conversation_id={conversation_id}, "
                        f"db_sandbox={db_sandbox is not None}, "
                        f"last_active_at={db_sandbox.last_active_at if db_sandbox else 'N/A'}"
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
                        
                        logger.info(
                            f"📅 沙盒过期时间: expires_at={expires_at}, "
                            f"timeout_seconds={timeout_seconds}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ 无法计算过期时间: db_sandbox存在={db_sandbox is not None}, "
                            f"last_active_at={getattr(db_sandbox, 'last_active_at', 'N/A')}"
                        )
            except Exception as e:
                # 获取过期时间失败不影响主功能
                logger.warning(f"⚠️ 获取沙盒过期时间失败: {e}", exc_info=True)
            
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


# ==================== 工具 7: 上传文件到 S3 ====================

class SandboxUploadFile(BaseTool):
    """
    将沙盒中的文件上传到 S3 并返回下载链接（input_schema 由 capabilities.yaml 定义）
    
    工作流程：
    1. 从沙盒读取文件（使用 format="bytes" 支持二进制文件）
    2. 上传到 S3
    3. 返回预签名 URL（24小时有效）
    """
    
    name = "sandbox_upload_file"
    
    # 文件类型到 Content-Type 的映射
    CONTENT_TYPES = {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.json': 'application/json',
        '.csv': 'text/csv',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml',
        '.mp3': 'audio/mpeg',
        '.mp4': 'video/mp4',
        '.wav': 'audio/wav',
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.html': 'text/html',
    }
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行文件上传
        
        Args:
            params: 工具参数
                - path: 沙盒中的文件路径
                - filename: 下载时显示的文件名（可选）
            context: 工具执行上下文
            
        Returns:
            {
                "success": bool,
                "url": str,          # 预签名下载链接
                "filename": str,     # 文件名
                "size": int,         # 文件大小（字节）
                "s3_key": str        # S3 对象键
            }
        """
        import hashlib
        from pathlib import Path
        
        conversation_id = context.conversation_id
        path = params.get("path", "")
        filename = params.get("filename")
        user_id = context.user_id or "default_user"
        
        try:
            await ensure_sandbox(conversation_id, user_id)
            
            # 标准化路径
            normalized_path = _normalize_path(path)
            
            # 确定文件名
            if not filename:
                filename = Path(normalized_path).name
            
            # 1. 从沙盒读取文件（二进制模式）
            provider = get_sandbox_provider()
            file_content = await provider.read_file_binary(conversation_id, normalized_path)
            file_size = len(file_content)
            
            logger.info(f"📖 从沙盒读取文件: {normalized_path} ({file_size} bytes)")
            
            # 2. 生成 S3 key
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_hash = hashlib.md5(f"{filename}{timestamp}".encode()).hexdigest()[:8]
            file_ext = Path(filename).suffix
            unique_filename = f"{Path(filename).stem}_{file_hash}{file_ext}"
            s3_key = f"outputs/sandbox/{conversation_id}/{unique_filename}"
            
            # 3. 确定 Content-Type
            content_type = self.CONTENT_TYPES.get(
                file_ext.lower(),
                'application/octet-stream'
            )
            
            # 4. 上传到 S3
            from utils.s3_uploader import get_s3_uploader
            
            s3_uploader = get_s3_uploader()
            await s3_uploader.initialize()
            
            await s3_uploader.upload_bytes(
                file_content=file_content,
                object_name=s3_key,
                content_type=content_type,
                metadata={
                    "conversation_id": conversation_id,
                    "original_filename": filename,
                    "sandbox_path": normalized_path
                },
                acl="private"
            )
            
            # 5. 生成预签名 URL（24小时有效）
            presigned_url = s3_uploader.get_presigned_url(s3_key, expires_in=86400)
            
            logger.info(f"✅ 沙盒文件已上传 S3: {filename} → {s3_key}")
            
            return {
                "success": True,
                "url": presigned_url,
                "filename": filename,
                "size": file_size,
                "s3_key": s3_key
            }
            
        except FileNotFoundError:
            return {"success": False, "error": f"文件不存在: {path}"}
        except Exception as e:
            logger.error(f"❌ 沙盒文件上传失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# ==================== 工具注册 ====================

# 7 个标准工具（贴近 E2B 原生 API）
SANDBOX_TOOLS = [
    SandboxWriteFile,       # 写入文件
    SandboxReadFile,        # 读取文件
    SandboxListFiles,       # 列出目录
    SandboxRunCommand,      # 执行命令（支持 background）
    SandboxExecutePython,   # 执行 Python 代码
    SandboxGetPublicUrl,    # 获取公开 URL
    SandboxUploadFile,      # 上传文件到 S3
]


def get_sandbox_tools() -> list[BaseTool]:
    """获取所有沙盒工具实例"""
    return [t() for t in SANDBOX_TOOLS]
