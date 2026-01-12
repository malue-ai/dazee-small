"""
E2B 沙盒实现

E2B (e2b.dev) 提供的云端沙盒环境：
- 完全隔离的 Linux 容器
- 支持代码执行和文件操作
- 自动暂停和恢复（节省成本）
- 支持多种技术栈预览

使用前提：
- 安装 SDK: pip install e2b-code-interpreter
- 配置 E2B_API_KEY 环境变量
"""

import os
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

from logger import get_logger
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

# E2B 命令执行异常
try:
    from e2b.sandbox.commands.command_handle import CommandExitException
except ImportError:
    CommandExitException = None

logger = get_logger("infra.sandbox.e2b")

# E2B SDK 导入
try:
    from e2b_code_interpreter import Sandbox as CodeInterpreter
    E2B_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ E2B SDK 未安装，请运行: pip install e2b-code-interpreter")
    E2B_AVAILABLE = False
    CodeInterpreter = None

# 数据库导入（用于持久化沙盒状态）
try:
    from infra.database import AsyncSessionLocal, crud
    DB_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ 数据库模块未初始化")
    DB_AVAILABLE = False
    AsyncSessionLocal = None
    crud = None


class E2BSandboxProvider(SandboxProvider):
    """
    E2B 沙盒实现
    
    特点：
    - 云端隔离环境，多用户安全
    - 支持 auto_pause，无活动时自动暂停
    - 每个 conversation 独立沙盒
    """
    
    # 技术栈对应的端口
    STACK_PORTS = {
        "python": 8000,
        "flask": 5000,
        "fastapi": 8000,
        "streamlit": 8501,
        "nodejs": 3000,
        "react": 3000,
        "nextjs": 3000,
        "vue": 5173,
    }
    
    # 默认超时（1 小时无活动后自动暂停）
    DEFAULT_TIMEOUT_MS = 60 * 60 * 1000
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 E2B 沙盒提供者
        
        Args:
            api_key: E2B API Key（默认从环境变量读取）
        """
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        
        # 沙盒连接池：conversation_id -> sandbox 对象
        self._sandbox_pool: Dict[str, Any] = {}
        
        if not self.api_key:
            logger.warning("⚠️ E2B_API_KEY 未设置，E2B 沙盒功能不可用")
        else:
            logger.info("✅ E2BSandboxProvider 初始化完成")
    
    @property
    def provider_name(self) -> str:
        return "e2b"
    
    @property
    def is_available(self) -> bool:
        return E2B_AVAILABLE and bool(self.api_key)
    
    def _check_available(self):
        """检查服务是否可用"""
        if not self.is_available:
            raise SandboxNotAvailableError("E2B 沙盒服务不可用，请检查 E2B_API_KEY 配置")
    
    # ==================== 生命周期管理 ====================
    
    async def ensure_sandbox(
        self,
        conversation_id: str,
        user_id: str,
        stack: Optional[str] = None
    ) -> SandboxInfo:
        """获取或创建沙盒"""
        self._check_available()
        
        # 1. 检查连接池
        if conversation_id in self._sandbox_pool:
            sandbox = self._sandbox_pool[conversation_id]
            try:
                await asyncio.to_thread(
                    sandbox.commands.run,
                    "echo 'ping'",
                    timeout=10
                )
                logger.debug(f"♻️ 复用连接池中的沙盒: {conversation_id}")
                await self._update_activity(conversation_id)
                return await self.get_sandbox(conversation_id)
            except Exception as e:
                logger.warning(f"⚠️ 连接池中的沙盒已失效: {e}")
                del self._sandbox_pool[conversation_id]
        
        # 2. 查询数据库
        if DB_AVAILABLE:
            async with AsyncSessionLocal() as session:
                db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
            
            if db_sandbox and db_sandbox.e2b_sandbox_id:
                # 3. 尝试连接已有沙盒
                try:
                    sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
                    self._sandbox_pool[conversation_id] = sandbox
                    
                    # 更新状态
                    async with AsyncSessionLocal() as session:
                        preview_url = None
                        if db_sandbox.stack:
                            port = self.STACK_PORTS.get(db_sandbox.stack, 8000)
                            host = sandbox.get_host(port)
                            preview_url = f"https://{host}"
                        
                        await crud.update_sandbox_status(
                            session, conversation_id, "running", preview_url
                        )
                    
                    logger.info(f"🔗 重新连接沙盒成功: {db_sandbox.e2b_sandbox_id}")
                    return await self.get_sandbox(conversation_id)
                    
                except Exception as e:
                    logger.warning(f"⚠️ 连接已有沙盒失败: {e}，将创建新沙盒")
        
        # 4. 创建新沙盒
        return await self._create_new_sandbox(conversation_id, user_id, stack)
    
    async def _create_new_sandbox(
        self,
        conversation_id: str,
        user_id: str,
        stack: Optional[str] = None
    ) -> SandboxInfo:
        """创建新沙盒"""
        # 确保数据库中有记录
        if DB_AVAILABLE:
            async with AsyncSessionLocal() as session:
                db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
                
                if not db_sandbox:
                    db_sandbox = await crud.create_sandbox(
                        session=session,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        status="creating",
                        stack=stack
                    )
        
        try:
            # 设置 API Key
            if self.api_key != os.getenv("E2B_API_KEY"):
                os.environ["E2B_API_KEY"] = self.api_key
            
            # 创建沙盒
            logger.info(f"🆕 创建新沙盒 (auto_pause=True): conversation={conversation_id}")
            
            sandbox = await asyncio.to_thread(
                CodeInterpreter.beta_create,
                auto_pause=True,
                timeout=self.DEFAULT_TIMEOUT_MS // 1000,
                metadata={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "stack": stack or "python"
                }
            )
            
            # 等待沙盒就绪
            await asyncio.sleep(2)
            
            # 保存到连接池
            self._sandbox_pool[conversation_id] = sandbox
            
            # 更新数据库
            if DB_AVAILABLE:
                async with AsyncSessionLocal() as session:
                    await crud.update_sandbox_e2b_id(
                        session, conversation_id, sandbox.sandbox_id
                    )
                    await crud.update_sandbox_status(
                        session, conversation_id, "running"
                    )
            
            logger.info(f"✅ 沙盒创建成功: {sandbox.sandbox_id}")
            
            return SandboxInfo(
                id=conversation_id,
                conversation_id=conversation_id,
                user_id=user_id,
                provider_sandbox_id=sandbox.sandbox_id,
                status=SandboxStatus.RUNNING,
                stack=stack,
                created_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"❌ 创建沙盒失败: {e}", exc_info=True)
            raise SandboxError(f"创建沙盒失败: {e}")
    
    async def _connect_sandbox(self, e2b_sandbox_id: str):
        """连接到已有沙盒"""
        if self.api_key != os.getenv("E2B_API_KEY"):
            os.environ["E2B_API_KEY"] = self.api_key
        
        sandbox = await asyncio.to_thread(
            CodeInterpreter.connect,
            e2b_sandbox_id
        )
        
        # 验证连接
        try:
            await asyncio.to_thread(
                sandbox.commands.run,
                "echo 'connected'",
                timeout=15
            )
        except Exception as e:
            raise SandboxConnectionError(f"沙盒连接验证失败: {e}")
        
        logger.info(f"🔗 连接/恢复沙盒成功: {e2b_sandbox_id}")
        return sandbox
    
    async def get_sandbox(self, conversation_id: str) -> Optional[SandboxInfo]:
        """获取沙盒信息"""
        if not DB_AVAILABLE:
            # 无数据库时，只检查连接池
            if conversation_id in self._sandbox_pool:
                return SandboxInfo(
                    id=conversation_id,
                    conversation_id=conversation_id,
                    user_id="unknown",
                    status=SandboxStatus.RUNNING
                )
            return None
        
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
            
            if not db_sandbox:
                return None
            
            return SandboxInfo(
                id=str(db_sandbox.id),
                conversation_id=db_sandbox.conversation_id,
                user_id=db_sandbox.user_id,
                provider_sandbox_id=db_sandbox.e2b_sandbox_id,
                status=SandboxStatus(db_sandbox.status) if db_sandbox.status else SandboxStatus.CREATING,
                stack=db_sandbox.stack,
                preview_url=db_sandbox.preview_url,
                created_at=db_sandbox.created_at.isoformat() if db_sandbox.created_at else None,
                last_active_at=db_sandbox.last_active_at.isoformat() if db_sandbox.last_active_at else None
            )
    
    async def pause_sandbox(self, conversation_id: str) -> bool:
        """暂停沙盒"""
        if conversation_id not in self._sandbox_pool:
            return False
        
        try:
            sandbox = self._sandbox_pool[conversation_id]
            await asyncio.to_thread(sandbox.pause)
            del self._sandbox_pool[conversation_id]
            
            if DB_AVAILABLE:
                async with AsyncSessionLocal() as session:
                    await crud.update_sandbox_status(session, conversation_id, "paused")
            
            logger.info(f"⏸️ 沙盒已暂停: {conversation_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 暂停沙盒失败: {e}", exc_info=True)
            return False
    
    async def resume_sandbox(self, conversation_id: str) -> SandboxInfo:
        """恢复沙盒"""
        if not DB_AVAILABLE:
            raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
        
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
        
        if not db_sandbox or not db_sandbox.e2b_sandbox_id:
            raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
        
        try:
            sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
            self._sandbox_pool[conversation_id] = sandbox
            
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(session, conversation_id, "running")
            
            logger.info(f"▶️ 沙盒已恢复: {conversation_id}")
            return await self.get_sandbox(conversation_id)
        except Exception as e:
            raise SandboxError(f"恢复沙盒失败: {e}")
    
    async def destroy_sandbox(self, conversation_id: str) -> bool:
        """销毁沙盒"""
        try:
            if conversation_id in self._sandbox_pool:
                sandbox = self._sandbox_pool[conversation_id]
                await asyncio.to_thread(sandbox.kill)
                del self._sandbox_pool[conversation_id]
            
            if DB_AVAILABLE:
                async with AsyncSessionLocal() as session:
                    await crud.update_sandbox_status(session, conversation_id, "stopped")
            
            logger.info(f"🗑️ 沙盒已销毁: {conversation_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 销毁沙盒失败: {e}", exc_info=True)
            return False
    
    async def _update_activity(self, conversation_id: str):
        """更新活跃时间"""
        if DB_AVAILABLE:
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_activity(session, conversation_id)
    
    async def _get_sandbox_obj(self, conversation_id: str, skip_validation: bool = True):
        """
        获取沙盒对象（内部使用）
        
        性能优化：默认跳过 ping 验证（skip_validation=True），
        由调用方在操作失败时通过 _invalidate_sandbox 清理连接池并重试。
        
        Args:
            conversation_id: 对话 ID
            skip_validation: 是否跳过连接验证（默认 True，提高性能）
        
        逻辑：
        1. 检查连接池（skip_validation=True 时直接返回，不验证）
        2. 连接池没有则从数据库获取 e2b_sandbox_id 尝试重连
        3. 重连成功则加入连接池
        """
        # 1. 检查连接池
        if conversation_id in self._sandbox_pool:
            sandbox = self._sandbox_pool[conversation_id]
            
            # 性能优化：默认跳过验证，直接返回
            if skip_validation:
                return sandbox
            
            # 需要验证时才执行 ping
            try:
                await asyncio.to_thread(
                    sandbox.commands.run,
                    "echo 'ping'",
                    timeout=5
                )
                return sandbox
            except Exception as e:
                logger.warning(f"⚠️ 连接池中的沙盒已失效: {e}")
                del self._sandbox_pool[conversation_id]
        
        # 2. 从数据库获取 e2b_sandbox_id 并尝试重连
        if DB_AVAILABLE:
            async with AsyncSessionLocal() as session:
                db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
            
            if db_sandbox and db_sandbox.e2b_sandbox_id:
                try:
                    logger.info(f"🔄 尝试重新连接沙盒: {db_sandbox.e2b_sandbox_id}")
                    sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
                    self._sandbox_pool[conversation_id] = sandbox
                    
                    # 更新数据库状态
                    async with AsyncSessionLocal() as session:
                        await crud.update_sandbox_status(session, conversation_id, "running")
                    
                    return sandbox
                except Exception as e:
                    logger.error(f"❌ 重新连接沙盒失败: {e}")
                    raise SandboxConnectionError(
                        f"沙盒连接失败，可能已被删除。请重新初始化沙盒。原因: {e}"
                    )
        
        raise SandboxNotFoundError(f"沙盒不存在或未连接: {conversation_id}")
    
    def _invalidate_sandbox(self, conversation_id: str):
        """
        使沙盒连接失效（从连接池移除）
        
        当操作失败时调用，下次 _get_sandbox_obj 会重新连接
        """
        if conversation_id in self._sandbox_pool:
            del self._sandbox_pool[conversation_id]
            logger.info(f"🔄 已从连接池移除失效沙盒: {conversation_id}")
    
    async def _with_retry(
        self,
        conversation_id: str,
        operation: callable,
        max_retries: int = 1
    ):
        """
        带自动重试的操作包装器
        
        性能优化的核心：首次调用跳过验证，失败时清理连接池并重试。
        这样正常情况下响应很快，只有连接失效时才会有额外延迟。
        
        Args:
            conversation_id: 对话 ID
            operation: 异步操作函数，接收 sandbox 对象作为第一个参数
            max_retries: 最大重试次数（默认 1 次）
            
        Returns:
            操作结果
            
        Raises:
            操作失败且重试耗尽时抛出原始异常
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                # 首次尝试跳过验证（性能优化）
                skip_validation = (attempt == 0)
                sandbox = await self._get_sandbox_obj(conversation_id, skip_validation=skip_validation)
                return await operation(sandbox)
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # 判断是否是连接相关错误，需要重试
                is_connection_error = any(keyword in error_str for keyword in [
                    'sandbox was not found',
                    'connection',
                    'timeout',
                    'unavailable',
                    'disconnected'
                ])
                
                if is_connection_error and attempt < max_retries:
                    logger.warning(f"⚠️ 沙盒操作失败，正在重试 ({attempt + 1}/{max_retries}): {e}")
                    self._invalidate_sandbox(conversation_id)
                    continue
                
                # 非连接错误或重试耗尽，直接抛出
                raise
        
        # 理论上不会到这里，但保险起见
        raise last_error
    
    # ==================== 命令执行 ====================
    
    async def run_command(
        self,
        conversation_id: str,
        command: str,
        timeout: int = 60,
        cwd: Optional[str] = None
    ) -> CommandResult:
        """
        在沙盒中执行命令
        
        注意：E2B SDK 对于非零退出码会抛出 CommandExitException，
        此方法会正确处理该异常，提取 stdout/stderr/exit_code 返回给调用方。
        """
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            # 如果指定了工作目录，先 cd
            if cwd:
                command = f"cd {cwd} && {command}"
            
            result = await asyncio.to_thread(
                sandbox.commands.run,
                command,
                timeout=timeout
            )
            
            await self._update_activity(conversation_id)
            
            logger.info(f"🐚 命令执行完成: {command[:50]}...")
            
            return CommandResult(
                success=result.exit_code == 0,
                output=result.stdout or "",
                error=result.stderr if result.exit_code != 0 else None,
                exit_code=result.exit_code
            )
        
        except Exception as e:
            # 🔑 关键：正确处理 E2B 的 CommandExitException
            # 这个异常在命令退出码非 0 时抛出，但包含完整的执行结果
            if CommandExitException and isinstance(e, CommandExitException):
                await self._update_activity(conversation_id)
                
                # 从异常中提取执行结果
                exit_code = getattr(e, 'exit_code', -1)
                stdout = getattr(e, 'stdout', '') or ''
                stderr = getattr(e, 'stderr', '') or ''
                error_msg = getattr(e, 'error', '') or stderr
                
                logger.info(f"🐚 命令执行完成（非零退出码 {exit_code}）: {command[:50]}...")
                
                return CommandResult(
                    success=exit_code == 0,
                    output=stdout,
                    error=error_msg if exit_code != 0 else None,
                    exit_code=exit_code
                )
            
            # 其他异常（超时、连接错误等）
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return CommandResult(
                    success=False,
                    output="",
                    error=f"命令执行超时（{timeout}秒）",
                    exit_code=-1
                )
            
            logger.error(f"❌ 命令执行失败: {e}", exc_info=True)
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )
    
    async def run_code(
        self,
        conversation_id: str,
        code: str,
        language: str = "python",
        timeout: int = 300
    ) -> CodeResult:
        """
        执行代码（Code Interpreter）
        
        E2B run_code 返回值结构：
        - execution.text: 最终文本输出（推荐使用）
        - execution.logs.stdout: stdout 日志列表
        - execution.logs.stderr: stderr 日志列表
        - execution.results: 富媒体结果（图表等）
        - execution.error: 执行错误信息
        """
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            import time
            start_time = time.time()
            
            # E2B Code Interpreter 的 run_code 方法
            execution = await asyncio.to_thread(
                sandbox.run_code,
                code,
                timeout=timeout
            )
            
            execution_time = time.time() - start_time
            await self._update_activity(conversation_id)
            
            # 处理 stdout/stderr
            stdout_lines = []
            stderr_lines = []
            
            # execution.logs 结构: logs.stdout 和 logs.stderr 是列表
            if hasattr(execution, 'logs') and execution.logs:
                if hasattr(execution.logs, 'stdout'):
                    for log in execution.logs.stdout:
                        line = log.line if hasattr(log, 'line') else str(log)
                        stdout_lines.append(line)
                if hasattr(execution.logs, 'stderr'):
                    for log in execution.logs.stderr:
                        line = log.line if hasattr(log, 'line') else str(log)
                        stderr_lines.append(line)
            
            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)
            
            # 如果有 text 属性，优先使用（包含最终输出）
            if hasattr(execution, 'text') and execution.text:
                if not stdout:
                    stdout = execution.text
            
            # 处理产物（如图表）
            artifacts = []
            if hasattr(execution, 'results') and execution.results:
                for result in execution.results:
                    artifact = {}
                    if hasattr(result, 'png') and result.png:
                        artifact = {
                            "type": "image",
                            "format": "png",
                            "data": result.png
                        }
                    elif hasattr(result, 'svg') and result.svg:
                        artifact = {
                            "type": "image",
                            "format": "svg",
                            "data": result.svg
                        }
                    elif hasattr(result, 'html') and result.html:
                        artifact = {
                            "type": "html",
                            "data": result.html
                        }
                    elif hasattr(result, 'text') and result.text:
                        artifact = {
                            "type": "text",
                            "data": result.text
                        }
                    if artifact:
                        artifacts.append(artifact)
            
            # 检查执行错误
            has_error = hasattr(execution, 'error') and execution.error is not None
            error_msg = None
            if has_error:
                error_msg = execution.error.value if hasattr(execution.error, 'value') else str(execution.error)
            
            logger.info(f"📝 代码执行完成，输出 {len(stdout)} 字符，耗时 {execution_time:.2f}s")
            
            return CodeResult(
                success=not has_error,
                stdout=stdout,
                stderr=stderr,
                error=error_msg,
                execution_time=execution_time,
                artifacts=artifacts
            )
            
        except Exception as e:
            logger.error(f"❌ 代码执行失败: {e}", exc_info=True)
            return CodeResult(
                success=False,
                error=str(e)
            )
    
    # ==================== 文件操作 ====================
    
    async def read_file(self, conversation_id: str, path: str) -> str:
        """读取文件（带自动重试）"""
        self._check_available()
        
        async def _do_read(sandbox):
            content = await asyncio.to_thread(
                sandbox.files.read,
                path
            )
            # 处理返回类型
            if isinstance(content, bytes):
                return content.decode('utf-8')
            return content
        
        try:
            return await self._with_retry(conversation_id, _do_read)
        except Exception as e:
            if "not found" in str(e).lower():
                raise FileNotFoundError(f"文件不存在: {path}")
            raise SandboxError(f"读取文件失败: {e}")
    
    async def write_file(self, conversation_id: str, path: str, content: str) -> bool:
        """写入文件（带自动重试）"""
        self._check_available()
        
        async def _do_write(sandbox):
            # 确保目录存在
            dir_path = "/".join(path.split("/")[:-1])
            if dir_path:
                await asyncio.to_thread(
                    sandbox.commands.run,
                    f"mkdir -p {dir_path}",
                    timeout=10
                )
            
            # 写入文件
            await asyncio.to_thread(
                sandbox.files.write,
                path,
                content
            )
            
            await self._update_activity(conversation_id)
            logger.info(f"📄 文件已写入: {path}")
            return True
        
        try:
            return await self._with_retry(conversation_id, _do_write)
        except Exception as e:
            logger.error(f"❌ 写入文件失败: {e}", exc_info=True)
            raise SandboxError(f"写入文件失败: {e}")
    
    async def delete_file(self, conversation_id: str, path: str) -> bool:
        """删除文件"""
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            result = await asyncio.to_thread(
                sandbox.commands.run,
                f"rm -rf {path}",
                timeout=10
            )
            return result.exit_code == 0
        except Exception as e:
            logger.error(f"❌ 删除文件失败: {e}", exc_info=True)
            return False
    
    async def list_dir(
        self,
        conversation_id: str,
        path: str = "/home/user"
    ) -> List[FileInfo]:
        """列出目录内容（带自动重试）"""
        self._check_available()
        
        async def _do_list(sandbox):
            entries = await asyncio.to_thread(
                sandbox.files.list,
                path
            )
            
            result = []
            for entry in entries:
                # E2B SDK: entry.type 是 FileType 枚举（'file' 或 'dir'）
                entry_type = getattr(entry, 'type', None)
                is_directory = (
                    entry_type is not None and 
                    (entry_type.value == 'dir' if hasattr(entry_type, 'value') else str(entry_type) == 'dir')
                )
                result.append(FileInfo(
                    name=entry.name,
                    path=f"{path}/{entry.name}".replace("//", "/"),
                    type="directory" if is_directory else "file",
                    size=getattr(entry, 'size', None)
                ))
            
            return result
        
        try:
            return await self._with_retry(conversation_id, _do_list)
        except Exception as e:
            logger.error(f"❌ 列出目录失败: {e}", exc_info=True)
            raise SandboxError(f"列出目录失败: {e}")
    
    async def file_exists(self, conversation_id: str, path: str) -> bool:
        """检查文件是否存在"""
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            result = await asyncio.to_thread(
                sandbox.commands.run,
                f"test -e {path} && echo 'exists'",
                timeout=10
            )
            return "exists" in result.stdout
        except Exception:
            return False
    
    async def list_dir_tree_fast(
        self,
        conversation_id: str,
        path: str = "/home/user",
        max_depth: int = 5
    ) -> List[FileInfo]:
        """
        快速获取目录树（单次 shell 命令）
        
        使用 find 命令一次性获取整个目录结构，避免多次 API 调用。
        性能：从 N 次 API 调用（N = 目录数）优化为 1 次。
        
        Args:
            conversation_id: 对话 ID
            path: 起始路径
            max_depth: 最大深度
            
        Returns:
            文件树结构
        """
        self._check_available()
        
        # 使用 find 命令获取目录结构，输出格式：type|path
        # -maxdepth 限制深度，-printf 格式化输出
        cmd = f"find {path} -maxdepth {max_depth} -printf '%y|%p\\n' 2>/dev/null || true"
        
        result = await self.run_command(conversation_id, cmd, timeout=30)
        
        if not result.success or not result.output:
            # 降级到普通方法
            return await self.list_dir(conversation_id, path)
        
        # 解析 find 输出，构建树结构
        lines = result.output.strip().split('\n')
        
        # 路径 -> FileInfo 的映射
        path_map: Dict[str, FileInfo] = {}
        root_files: List[FileInfo] = []
        
        for line in lines:
            if '|' not in line:
                continue
            
            file_type, file_path = line.split('|', 1)
            
            # 跳过根路径本身
            if file_path == path:
                continue
            
            name = file_path.split('/')[-1]
            is_dir = file_type == 'd'
            
            info = FileInfo(
                name=name,
                path=file_path,
                type="directory" if is_dir else "file",
                size=None,
                children=[] if is_dir else None
            )
            
            path_map[file_path] = info
            
            # 找到父目录
            parent_path = '/'.join(file_path.split('/')[:-1])
            
            if parent_path == path:
                # 直接子项
                root_files.append(info)
            elif parent_path in path_map:
                # 添加到父目录的 children
                parent = path_map[parent_path]
                if parent.children is not None:
                    parent.children.append(info)
        
        return root_files
    
    # ==================== 项目运行 ====================
    
    async def _wait_for_port(
        self,
        conversation_id: str,
        port: int,
        timeout: int = 30,
        interval: float = 1.0
    ) -> bool:
        """
        等待端口就绪
        
        Args:
            conversation_id: 对话 ID
            port: 端口号
            timeout: 超时时间（秒）
            interval: 检查间隔（秒）
            
        Returns:
            端口是否就绪
        """
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                result = await self.run_command(
                    conversation_id,
                    f"nc -z localhost {port} && echo 'ready' || echo 'waiting'",
                    timeout=5
                )
                if "ready" in result.output:
                    logger.info(f"✅ 端口 {port} 已就绪")
                    return True
            except Exception:
                pass
            
            await asyncio.sleep(interval)
        
        logger.warning(f"⚠️ 等待端口 {port} 超时")
        return False
    
    async def run_project(
        self,
        conversation_id: str,
        project_path: str,
        stack: str,
        wait_for_ready: bool = True,
        startup_timeout: int = 60
    ) -> Optional[str]:
        """
        运行项目
        
        Args:
            conversation_id: 对话 ID
            project_path: 项目路径
            stack: 技术栈
            wait_for_ready: 是否等待服务就绪
            startup_timeout: 启动超时时间
            
        Returns:
            预览 URL
        """
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        port = self.STACK_PORTS.get(stack, 8000)
        
        # 技术栈配置
        stack_configs = {
            "python": {
                "cmd": f"cd {project_path} && python app.py",
                "port": 8000,
                "startup_wait": 3
            },
            "flask": {
                "cmd": f"cd {project_path} && python app.py",
                "port": 5000,
                "startup_wait": 3
            },
            "fastapi": {
                "cmd": f"cd {project_path} && uvicorn main:app --host 0.0.0.0 --port {port}",
                "port": port,
                "startup_wait": 5
            },
            "streamlit": {
                "cmd": f"cd {project_path} && streamlit run app.py --server.port {port} --server.address 0.0.0.0",
                "port": port,
                "startup_wait": 8
            },
            "gradio": {
                "cmd": f"cd {project_path} && python app.py",
                "port": 7860,
                "startup_wait": 10
            },
            "nodejs": {
                "cmd": f"cd {project_path} && npm start",
                "port": 3000,
                "startup_wait": 5
            },
            "react": {
                "cmd": f"cd {project_path} && npm run dev -- --host 0.0.0.0",
                "port": 3000,
                "startup_wait": 10
            },
            "nextjs": {
                "cmd": f"cd {project_path} && npm run dev",
                "port": 3000,
                "startup_wait": 10
            },
            "vue": {
                "cmd": f"cd {project_path} && npm run dev -- --host 0.0.0.0",
                "port": 5173,
                "startup_wait": 8
            },
        }
        
        config = stack_configs.get(stack, {
            "cmd": f"cd {project_path} && python app.py",
            "port": 8000,
            "startup_wait": 3
        })
        
        command = config["cmd"]
        port = config["port"]
        startup_wait = config["startup_wait"]
    
        try:
            # 先停止可能存在的旧进程
            await self.run_command(
                conversation_id,
                f"pkill -f '{project_path}' 2>/dev/null || true",
                timeout=10
            )
            
            # 检查并安装依赖（优化：跳过已安装的包）
            req_path = f"{project_path}/requirements.txt"
            pkg_path = f"{project_path}/package.json"
            
            if await self.file_exists(conversation_id, req_path):
                # 检查主要依赖是否已安装（官方模板通常已预装 streamlit 等）
                check_result = await self.run_command(
                    conversation_id,
                    f"cd {project_path} && head -1 requirements.txt | cut -d'>' -f1 | cut -d'=' -f1 | xargs pip show 2>/dev/null && echo 'INSTALLED' || echo 'NOT_INSTALLED'",
                    timeout=10
                )
                
                if "NOT_INSTALLED" in (check_result.output or ""):
                    logger.info(f"📦 安装 Python 依赖: {req_path}")
                    install_result = await self.run_command(
                        conversation_id,
                        f"cd {project_path} && pip install -q -r requirements.txt 2>&1",
                        timeout=180
                    )
                    if not install_result.success:
                        logger.warning(f"⚠️ 依赖安装可能有问题: {install_result.error}")
                else:
                    logger.info(f"✅ 依赖已预装，跳过安装")
            
            if await self.file_exists(conversation_id, pkg_path):
                logger.info(f"📦 安装 Node.js 依赖")
                await self.run_command(
                    conversation_id,
                    f"cd {project_path} && npm install 2>&1",
                    timeout=180
                )
            
            # 后台启动项目
            logger.info(f"🚀 启动项目: {command}")
            # 使用 nohup + bash -c 后台启动整个命令链
            # 注意：必须用 bash -c 包裹，否则 nohup 只作用于第一个命令（如 cd）
            await self.run_command(
                conversation_id,
                f"nohup bash -c '{command}' > /tmp/app.log 2>&1 & sleep 0.5; exit 0",
                timeout=30
            )
            
            # 等待服务就绪
            if wait_for_ready:
                # 先等待基本启动时间
                await asyncio.sleep(startup_wait)
                
                # 然后检查端口
                ready = await self._wait_for_port(
                    conversation_id, 
                    port, 
                    timeout=startup_timeout - startup_wait
                )
                
                if not ready:
                    # 检查启动日志
                    logs = await self.run_command(
                        conversation_id,
                        "tail -20 /tmp/app.log 2>/dev/null || echo 'No logs'",
                        timeout=10
                    )
                    logger.warning(f"⚠️ 服务可能未完全启动，日志:\n{logs.output[:500]}")
            else:
                await asyncio.sleep(startup_wait)
            
            # 获取预览 URL
            host = sandbox.get_host(port)
            preview_url = f"https://{host}"
            
            # 更新数据库
            if DB_AVAILABLE:
                async with AsyncSessionLocal() as session:
                    await crud.update_sandbox_status(
                        session, conversation_id, "running", preview_url
                    )
            
            logger.info(f"✅ 项目启动成功: {preview_url}")
            return preview_url
            
        except Exception as e:
            logger.error(f"❌ 运行项目失败: {e}", exc_info=True)
            return None
    
    async def get_preview_url(
        self,
        conversation_id: str,
        port: int = 8000
    ) -> Optional[str]:
        """获取预览 URL"""
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            host = sandbox.get_host(port)
            return f"https://{host}"
        except Exception:
            return None
    
    # ==================== 连接池管理 ====================
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态（用于诊断）
        
        Returns:
            连接池状态信息
        """
        return {
            "provider": self.provider_name,
            "available": self.is_available,
            "pool_size": len(self._sandbox_pool),
            "conversations": list(self._sandbox_pool.keys())
        }
    
    async def cleanup_pool(self) -> int:
        """
        清理失效的连接池条目
        
        Returns:
            清理的条目数量
        """
        invalid_ids = []
        
        for conv_id, sandbox in list(self._sandbox_pool.items()):
            try:
                await asyncio.to_thread(
                    sandbox.commands.run,
                    "echo 'ping'",
                    timeout=5
                )
            except Exception:
                invalid_ids.append(conv_id)
        
        for conv_id in invalid_ids:
            del self._sandbox_pool[conv_id]
            logger.info(f"🧹 清理失效沙盒连接: {conv_id}")
        
        return len(invalid_ids)
    
    async def get_sandbox_metrics(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        获取沙盒运行指标
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            指标信息
        """
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            
            # 获取系统信息
            result = await asyncio.to_thread(
                sandbox.commands.run,
                "echo $(free -m | awk 'NR==2{print $3}') $(df -h /home/user | awk 'NR==2{print $5}')",
                timeout=10
            )
            
            parts = result.stdout.strip().split()
            memory_used_mb = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
            disk_usage = parts[1] if len(parts) > 1 else None
            
            return {
                "conversation_id": conversation_id,
                "in_pool": conversation_id in self._sandbox_pool,
                "memory_used_mb": memory_used_mb,
                "disk_usage": disk_usage
            }
        except Exception as e:
            logger.error(f"❌ 获取沙盒指标失败: {e}")
            return None
    

