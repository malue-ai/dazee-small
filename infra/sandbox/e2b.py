"""
E2B 沙盒实现

E2B (e2b.dev) 提供的云端沙盒环境：
- 完全隔离的 Linux 容器
- 支持代码执行和文件操作
- 自动暂停和恢复（节省成本）
- 支持多种技术栈预览

依赖：
- pip install e2b-code-interpreter
- 环境变量 E2B_API_KEY
"""

# 标准库
import os
import asyncio
import time
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

# 第三方库
from e2b_code_interpreter import AsyncSandbox

# 本地模块
from logger import get_logger
from infra.database import AsyncSessionLocal, crud
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

# 日志
logger = get_logger("infra.sandbox.e2b")


class E2BSandboxProvider(SandboxProvider):
    """
    E2B 沙盒提供者
    
    特点：
    - 云端隔离环境，多用户安全
    - 支持 auto_pause，无活动时自动暂停
    - 每个 conversation 独立沙盒
    """
    
    # 技术栈对应的端口
    STACK_PORTS: Dict[str, int] = {
        "python": 8000,
        "flask": 5000,
        "fastapi": 8000,
        "streamlit": 8501,
        "nodejs": 3000,
        "react": 5173,
        "nextjs": 3000,
        "vue": 5173,
    }
    
    # 默认超时（临时设为 5 分钟用于测试）
    # 配合 auto_pause=True，超时后沙盒会自动暂停而非销毁
    # 暂停的沙盒可在 30 天内恢复，节省成本
    # TODO: 测试完成后改回 30 * 60（30 分钟）
    DEFAULT_TIMEOUT_SECONDS: int = 5 * 60  # 5 分钟（测试用）
    
    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        初始化 E2B 沙盒提供者
        
        Args:
            api_key: E2B API Key（默认从环境变量读取）
        """
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        self._sandbox_pool: Dict[str, Any] = {}
        
        if not self.api_key:
            logger.warning("⚠️ E2B_API_KEY 未设置")
        else:
            logger.info("✅ E2BSandboxProvider 初始化完成")
    
    @property
    def provider_name(self) -> str:
        """提供者名称"""
        return "e2b"
    
    @property
    def is_available(self) -> bool:
        """服务是否可用"""
        return bool(self.api_key)
    
    def _check_available(self) -> None:
        """
        检查服务是否可用
        
        Raises:
            SandboxNotAvailableError: 服务不可用时
        """
        if not self.is_available:
            raise SandboxNotAvailableError("E2B 沙盒服务不可用，请检查配置")

    # ==================== 生命周期管理 ====================
    
    async def ensure_sandbox(
        self,
        conversation_id: str,
        user_id: str,
        stack: Optional[str] = None
    ) -> SandboxInfo:
        """
        获取或创建沙盒
        
        Args:
            conversation_id: 对话 ID
            user_id: 用户 ID
            stack: 技术栈
            
        Returns:
            沙盒信息
        """
        self._check_available()
        
        # 1. 检查连接池
        if conversation_id in self._sandbox_pool:
            sandbox = self._sandbox_pool[conversation_id]
            try:
                await sandbox.commands.run("echo 'ping'", timeout=10)
                logger.debug(f"♻️ 复用连接池中的沙盒: {conversation_id}")
                await self._update_activity(conversation_id)
                return await self.get_sandbox(conversation_id)
            except Exception as e:
                logger.warning(f"⚠️ 连接池中的沙盒已失效: {e}")
                del self._sandbox_pool[conversation_id]
        
        # 2. 查询数据库
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(
                session, conversation_id
            )
        
        if db_sandbox and db_sandbox.e2b_sandbox_id:
            try:
                sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
                self._sandbox_pool[conversation_id] = sandbox
                
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
        
        # 3. 创建新沙盒
        return await self._create_new_sandbox(conversation_id, user_id, stack)
    
    async def _create_new_sandbox(
        self,
        conversation_id: str,
        user_id: str,
        stack: Optional[str] = None
    ) -> SandboxInfo:
        """
        创建新沙盒
        
        Args:
            conversation_id: 对话 ID
            user_id: 用户 ID
            stack: 技术栈
            
        Returns:
            沙盒信息
            
        Raises:
            SandboxError: 创建失败时
        """
        # 确保数据库中有记录
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(
                session, conversation_id
            )
            if not db_sandbox:
                await crud.create_sandbox(
                    session=session,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    status="creating",
                    stack=stack
                )
        
        try:
            if self.api_key != os.getenv("E2B_API_KEY"):
                os.environ["E2B_API_KEY"] = self.api_key
            
            logger.info(f"🆕 创建新沙盒: conversation={conversation_id}")
            
            # 使用 _create 直接创建沙盒，启用 auto_pause
            # auto_pause=True: 超时后自动暂停而非销毁，可在 30 天内恢复
            # 注意：AsyncSandbox.create() 硬编码了 auto_pause=False，所以需要直接调用 _create
            sandbox = await AsyncSandbox._create(
                template=None,
                timeout=self.DEFAULT_TIMEOUT_SECONDS,
                auto_pause=True,
                allow_internet_access=True,
                metadata=None,
                envs=None,
                secure=True
            )
            
            await asyncio.sleep(2)
            self._sandbox_pool[conversation_id] = sandbox
            
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
    
    async def _connect_sandbox(self, e2b_sandbox_id: str) -> Any:
        """
        连接到已有沙盒
        
        Args:
            e2b_sandbox_id: E2B 沙盒 ID
            
        Returns:
            沙盒对象
            
        Raises:
            SandboxConnectionError: 连接失败时
        """
        if self.api_key != os.getenv("E2B_API_KEY"):
            os.environ["E2B_API_KEY"] = self.api_key
        
        sandbox = await AsyncSandbox.connect(e2b_sandbox_id)
        
        try:
            await sandbox.commands.run("echo 'connected'", timeout=15)
        except Exception as e:
            raise SandboxConnectionError(f"沙盒连接验证失败: {e}")
        
        logger.info(f"🔗 连接沙盒成功: {e2b_sandbox_id}")
        return sandbox
    
    async def get_sandbox(self, conversation_id: str) -> Optional[SandboxInfo]:
        """
        获取沙盒信息
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            沙盒信息，不存在时返回 None
        """
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(
                session, conversation_id
            )
            
            if not db_sandbox:
                return None
            
            return SandboxInfo(
                id=str(db_sandbox.id),
                conversation_id=db_sandbox.conversation_id,
                user_id=db_sandbox.user_id,
                provider_sandbox_id=db_sandbox.e2b_sandbox_id,
                status=SandboxStatus(db_sandbox.status) if db_sandbox.status \
                    else SandboxStatus.CREATING,
                stack=db_sandbox.stack,
                preview_url=db_sandbox.preview_url,
                active_project_path=db_sandbox.active_project_path,
                active_project_stack=db_sandbox.active_project_stack,
                created_at=db_sandbox.created_at.isoformat() \
                    if db_sandbox.created_at else None,
                last_active_at=db_sandbox.last_active_at.isoformat() \
                    if db_sandbox.last_active_at else None
            )
    
    async def pause_sandbox(self, conversation_id: str) -> bool:
        """
        暂停沙盒
        
        暂停前会自动停止运行中的项目（但不清除数据库记录），
        恢复时会自动重启项目
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        if conversation_id not in self._sandbox_pool:
            return False
        
        try:
            # 1. 先停止运行中的项目（不清除数据库记录，恢复时需要用）
            logger.info(f"⏹️ 暂停前停止项目进程: {conversation_id}")
            await self._stop_running_project(conversation_id)
            
            # 2. 暂停沙盒
            sandbox = self._sandbox_pool[conversation_id]
            await sandbox.pause()
            del self._sandbox_pool[conversation_id]
            
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(
                    session, conversation_id, "paused"
                )
            
            logger.info(f"⏸️ 沙盒已暂停: {conversation_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 暂停沙盒失败: {e}", exc_info=True)
            return False
    
    async def resume_sandbox(self, conversation_id: str) -> SandboxInfo:
        """
        恢复沙盒
        
        恢复后会自动重启暂停前运行的项目（如果有记录）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            沙盒信息
            
        Raises:
            SandboxNotFoundError: 沙盒不存在时
            SandboxError: 恢复失败时
        """
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(
                session, conversation_id
            )
        
        if not db_sandbox or not db_sandbox.e2b_sandbox_id:
            raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
        
        # 保存项目信息（恢复后需要用）
        active_project_path = db_sandbox.active_project_path
        active_project_stack = db_sandbox.active_project_stack
        
        try:
            # 1. 重连沙盒
            sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
            self._sandbox_pool[conversation_id] = sandbox
            
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(
                    session, conversation_id, "running"
                )
            
            logger.info(f"▶️ 沙盒已恢复: {conversation_id}")
            
            # 2. 如果有记录的项目，自动重启
            if active_project_path and active_project_stack:
                logger.info(
                    f"🔄 检测到之前运行的项目，自动重启: "
                    f"{active_project_path} ({active_project_stack})"
                )
                preview_url = await self.run_project(
                    conversation_id,
                    active_project_path,
                    active_project_stack,
                    wait_for_ready=True
                )
                if preview_url:
                    logger.info(f"✅ 项目已自动重启: {preview_url}")
                else:
                    logger.warning(f"⚠️ 项目自动重启失败")
            
            return await self.get_sandbox(conversation_id)
        except Exception as e:
            raise SandboxError(f"恢复沙盒失败: {e}")
    
    async def destroy_sandbox(self, conversation_id: str) -> bool:
        """
        销毁沙盒
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        try:
            if conversation_id in self._sandbox_pool:
                sandbox = self._sandbox_pool[conversation_id]
                await sandbox.kill()
                del self._sandbox_pool[conversation_id]
            
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(
                    session, conversation_id, "stopped"
                )
            
            logger.info(f"🗑️ 沙盒已销毁: {conversation_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 销毁沙盒失败: {e}", exc_info=True)
            return False
    
    async def _update_activity(self, conversation_id: str) -> None:
        """更新活跃时间"""
        async with AsyncSessionLocal() as session:
            await crud.update_sandbox_activity(session, conversation_id)
    
    async def _get_sandbox_obj(
        self,
        conversation_id: str,
        skip_validation: bool = True
    ) -> Any:
        """
        获取沙盒对象（内部使用）
        
        Args:
            conversation_id: 对话 ID
            skip_validation: 是否跳过连接验证
            
        Returns:
            沙盒对象
            
        Raises:
            SandboxNotFoundError: 沙盒不存在时
            SandboxConnectionError: 连接失败时
        """
        # 1. 检查连接池
        if conversation_id in self._sandbox_pool:
            sandbox = self._sandbox_pool[conversation_id]
            
            if skip_validation:
                return sandbox
            
            try:
                await sandbox.commands.run("echo 'ping'", timeout=5)
                return sandbox
            except Exception as e:
                logger.warning(f"⚠️ 连接池中的沙盒已失效: {e}")
                del self._sandbox_pool[conversation_id]
        
        # 2. 从数据库获取并重连
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(
                session, conversation_id
            )
        
        if db_sandbox and db_sandbox.e2b_sandbox_id:
            try:
                logger.info(f"🔄 尝试重新连接沙盒: {db_sandbox.e2b_sandbox_id}")
                sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
                self._sandbox_pool[conversation_id] = sandbox
                
                async with AsyncSessionLocal() as session:
                    await crud.update_sandbox_status(
                        session, conversation_id, "running"
                    )
                
                return sandbox
            except Exception as e:
                error_str = str(e).lower()
                # 检测沙盒是否已被 E2B 删除（not found / paused sandbox not found）
                if "not found" in error_str:
                    logger.warning(
                        f"⚠️ 沙盒已被删除，将自动重建: {db_sandbox.e2b_sandbox_id}"
                    )
                    # 清理旧的 e2b_sandbox_id 并创建新沙盒
                    async with AsyncSessionLocal() as session:
                        await crud.update_sandbox_e2b_id(
                            session, conversation_id, "", status="deleted"
                        )
                    
                    # 使用保存的 user_id 和 stack 创建新沙盒
                    await self._create_new_sandbox(
                        conversation_id,
                        user_id=db_sandbox.user_id,
                        stack=db_sandbox.stack
                    )
                    # 返回新创建的沙盒对象
                    return self._sandbox_pool[conversation_id]
                
                logger.error(f"❌ 重新连接沙盒失败: {e}")
                raise SandboxConnectionError(
                    f"沙盒连接失败，可能已被删除: {e}"
                )
        
        raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
    
    def _invalidate_sandbox(self, conversation_id: str) -> None:
        """
        使沙盒连接失效
        
        Args:
            conversation_id: 对话 ID
        """
        if conversation_id in self._sandbox_pool:
            del self._sandbox_pool[conversation_id]
            logger.info(f"🔄 已从连接池移除失效沙盒: {conversation_id}")
    
    async def _with_retry(
        self,
        conversation_id: str,
        operation: Callable,
        max_retries: int = 1
    ) -> Any:
        """
        带自动重试的操作包装器
        
        Args:
            conversation_id: 对话 ID
            operation: 异步操作函数
            max_retries: 最大重试次数
            
        Returns:
            操作结果
            
        Raises:
            操作失败且重试耗尽时抛出原始异常
        """
        last_error = None
        connection_keywords = [
            'not found', 'connection', 'timeout',
            'unavailable', 'disconnected'
        ]
        
        for attempt in range(max_retries + 1):
            try:
                skip_validation = (attempt == 0)
                sandbox = await self._get_sandbox_obj(
                    conversation_id, skip_validation=skip_validation
                )
                return await operation(sandbox)
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                is_connection_error = any(
                    kw in error_str for kw in connection_keywords
                )
                
                if is_connection_error and attempt < max_retries:
                    logger.warning(
                        f"⚠️ 沙盒操作失败，重试 ({attempt + 1}/{max_retries}): {e}"
                    )
                    self._invalidate_sandbox(conversation_id)
                    continue
                
                raise
        
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
        
        Args:
            conversation_id: 对话 ID
            command: 要执行的命令
            timeout: 超时时间（秒）
            cwd: 工作目录
            
        Returns:
            命令执行结果
        """
        self._check_available()
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            if cwd:
                command = f"cd {cwd} && {command}"
            
            result = await sandbox.commands.run(command, timeout=timeout)
            await self._update_activity(conversation_id)
            
            logger.info(f"🐚 命令执行完成: {command[:50]}...")
            
            return CommandResult(
                success=result.exit_code == 0,
                output=result.stdout or "",
                error=result.stderr if result.exit_code != 0 else None,
                exit_code=result.exit_code
            )
            
        except Exception as e:
            return self._handle_command_exception(e, command, timeout, conversation_id)
    
    def _handle_command_exception(
        self,
        e: Exception,
        command: str,
        timeout: int,
        conversation_id: str
    ) -> CommandResult:
        """
        处理命令执行异常
        
        Args:
            e: 异常对象
            command: 命令
            timeout: 超时时间
            conversation_id: 对话 ID
            
        Returns:
            命令执行结果
        """
        # 检查是否是命令退出异常（通过属性或类名判断）
        is_exit_error = (
            hasattr(e, 'exit_code') and hasattr(e, 'stdout')
        ) or (
            'CommandExit' in type(e).__name__ or 'ProcessExit' in type(e).__name__
        )
        
        if is_exit_error:
            exit_code = getattr(e, 'exit_code', -1)
            stdout = getattr(e, 'stdout', '') or ''
            stderr = getattr(e, 'stderr', '') or ''
            error_msg = getattr(e, 'error', '') or stderr
            
            logger.info(f"🐚 命令执行完成（退出码 {exit_code}）: {command[:50]}...")
            
            return CommandResult(
                success=exit_code == 0,
                output=stdout,
                error=error_msg if exit_code != 0 else None,
                exit_code=exit_code
            )
        
        # 其他异常
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
        执行代码
        
        Args:
            conversation_id: 对话 ID
            code: 代码内容
            language: 编程语言
            timeout: 超时时间（秒）
            
        Returns:
            代码执行结果
        """
        self._check_available()
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            start_time = time.time()
            execution = await sandbox.run_code(code, timeout=timeout)
            execution_time = time.time() - start_time
            
            await self._update_activity(conversation_id)
            
            # 处理输出
            stdout, stderr = self._parse_execution_logs(execution)
            artifacts = self._parse_execution_results(execution)
            
            # 检查错误
            has_error = hasattr(execution, 'error') and execution.error is not None
            error_msg = None
            if has_error:
                error_msg = execution.error.value \
                    if hasattr(execution.error, 'value') else str(execution.error)
            
            logger.info(
                f"📝 代码执行完成，输出 {len(stdout)} 字符，耗时 {execution_time:.2f}s"
            )
            
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
            return CodeResult(success=False, error=str(e))
    
    def _parse_execution_logs(self, execution: Any) -> tuple[str, str]:
        """
        解析执行日志
        
        Args:
            execution: 执行结果对象
            
        Returns:
            (stdout, stderr) 元组
        """
        stdout_lines = []
        stderr_lines = []
        
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
        
        # 优先使用 text 属性
        if hasattr(execution, 'text') and execution.text and not stdout:
            stdout = execution.text
        
        return stdout, stderr
    
    def _parse_execution_results(self, execution: Any) -> List[Dict[str, Any]]:
        """
        解析执行结果（图表等）
        
        Args:
            execution: 执行结果对象
            
        Returns:
            产物列表
        """
        artifacts = []
        
        if not hasattr(execution, 'results') or not execution.results:
            return artifacts
        
        for result in execution.results:
            artifact = {}
            if hasattr(result, 'png') and result.png:
                artifact = {"type": "image", "format": "png", "data": result.png}
            elif hasattr(result, 'svg') and result.svg:
                artifact = {"type": "image", "format": "svg", "data": result.svg}
            elif hasattr(result, 'html') and result.html:
                artifact = {"type": "html", "data": result.html}
            elif hasattr(result, 'text') and result.text:
                artifact = {"type": "text", "data": result.text}
            
            if artifact:
                artifacts.append(artifact)
        
        return artifacts

    # ==================== 文件操作 ====================
    
    async def read_file(self, conversation_id: str, path: str) -> str:
        """
        读取文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            文件内容
            
        Raises:
            FileNotFoundError: 文件不存在时
            SandboxError: 读取失败时
        """
        self._check_available()
        
        async def _do_read(sandbox: Any) -> str:
            content = await sandbox.files.read(path)
            if isinstance(content, bytes):
                return content.decode('utf-8')
            return content
        
        try:
            return await self._with_retry(conversation_id, _do_read)
        except Exception as e:
            if "not found" in str(e).lower():
                raise FileNotFoundError(f"文件不存在: {path}")
            raise SandboxError(f"读取文件失败: {e}")
    
    async def write_file(
        self,
        conversation_id: str,
        path: str,
        content: str
    ) -> bool:
        """
        写入文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            content: 文件内容
            
        Returns:
            是否成功
            
        Raises:
            SandboxError: 写入失败时
        """
        self._check_available()
        
        async def _do_write(sandbox: Any) -> bool:
            dir_path = "/".join(path.split("/")[:-1])
            if dir_path:
                await sandbox.commands.run(f"mkdir -p {dir_path}", timeout=10)
            
            await sandbox.files.write(path, content)
            await self._update_activity(conversation_id)
            logger.info(f"📄 文件已写入: {path}")
            return True
        
        try:
            return await self._with_retry(conversation_id, _do_write)
        except Exception as e:
            logger.error(f"❌ 写入文件失败: {e}", exc_info=True)
            raise SandboxError(f"写入文件失败: {e}")
    
    async def delete_file(self, conversation_id: str, path: str) -> bool:
        """
        删除文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            是否成功
        """
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            result = await sandbox.commands.run(f"rm -rf {path}", timeout=10)
            return result.exit_code == 0
        except Exception as e:
            logger.error(f"❌ 删除文件失败: {e}", exc_info=True)
            return False
    
    async def list_dir(
        self,
        conversation_id: str,
        path: str = "/home/user"
    ) -> List[FileInfo]:
        """
        列出目录内容
        
        Args:
            conversation_id: 对话 ID
            path: 目录路径
            
        Returns:
            文件信息列表
            
        Raises:
            SandboxError: 列出失败时
        """
        self._check_available()
        
        async def _do_list(sandbox: Any) -> List[FileInfo]:
            entries = await sandbox.files.list(path)
            
            result = []
            for entry in entries:
                entry_type = getattr(entry, 'type', None)
                is_dir = (
                    entry_type is not None and
                    (entry_type.value == 'dir' if hasattr(entry_type, 'value')
                     else str(entry_type) == 'dir')
                )
                result.append(FileInfo(
                    name=entry.name,
                    path=f"{path}/{entry.name}".replace("//", "/"),
                    type="directory" if is_dir else "file",
                    size=getattr(entry, 'size', None)
                ))
            
            return result
        
        try:
            return await self._with_retry(conversation_id, _do_list)
        except Exception as e:
            logger.error(f"❌ 列出目录失败: {e}", exc_info=True)
            raise SandboxError(f"列出目录失败: {e}")
    
    async def file_exists(self, conversation_id: str, path: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            是否存在
        """
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            result = await sandbox.commands.run(
                f"test -e {path} && echo 'exists'", timeout=10
            )
            return "exists" in result.stdout
        except Exception:
            return False

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
        start_time = time.time()
        
        check_cmd = (
            f"(nc -z localhost {port} 2>/dev/null && echo 'PORT_READY') || "
            f"(python3 -c \"import socket; s=socket.socket(); s.settimeout(1); "
            f"r=s.connect_ex(('localhost',{port})); s.close(); "
            f"exit(0 if r==0 else 1)\" 2>/dev/null && echo 'PORT_READY') || "
            f"(curl -s --max-time 1 http://localhost:{port}/ >/dev/null 2>&1 "
            f"&& echo 'PORT_READY') || echo 'PORT_WAITING'"
        )
        
        while time.time() - start_time < timeout:
            try:
                result = await self.run_command(
                    conversation_id, check_cmd, timeout=5
                )
                if "PORT_READY" in (result.output or ""):
                    elapsed = time.time() - start_time
                    logger.info(f"✅ 端口 {port} 已就绪 (耗时 {elapsed:.1f}s)")
                    return True
            except Exception as e:
                logger.debug(f"端口检测异常: {e}")
            
            await asyncio.sleep(interval)
        
        logger.warning(f"⚠️ 等待端口 {port} 超时 ({timeout}s)")
        return False
    
    async def _stop_running_project(self, conversation_id: str) -> bool:
        """
        停止当前运行的项目
        
        通过 pkill 杀掉所有可能的项目进程，
        但不清除数据库中的项目记录（用于恢复时重启）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        try:
            # 杀掉常见的项目进程
            kill_commands = [
                "pkill -f 'streamlit' 2>/dev/null || true",
                "pkill -f 'gradio' 2>/dev/null || true",
                "pkill -f 'uvicorn' 2>/dev/null || true",
                "pkill -f 'flask' 2>/dev/null || true",
                "pkill -f 'python app.py' 2>/dev/null || true",
                "pkill -f 'python main.py' 2>/dev/null || true",
                "pkill -f 'npm run dev' 2>/dev/null || true",
                "pkill -f 'node' 2>/dev/null || true",
                "pkill -f 'vite' 2>/dev/null || true",
            ]
            
            for cmd in kill_commands:
                await self.run_command(conversation_id, cmd, timeout=5)
            
            logger.info(f"⏹️ 已停止沙盒中的项目进程: {conversation_id}")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ 停止项目进程时出错: {e}")
            return False
    
    async def run_project(
        self,
        conversation_id: str,
        project_path: str,
        stack: str,
        wait_for_ready: bool = True,
        startup_timeout: int = 3600  # 🆕 V7.6: 改为 1 小时（3600 秒）
    ) -> Optional[str]:
        """
        运行项目
        
        注意：每个沙盒只能运行一个对外项目，
        如果已有项目在运行，会先停止旧项目
        
        Args:
            conversation_id: 对话 ID
            project_path: 项目路径
            stack: 技术栈
            wait_for_ready: 是否等待服务就绪
            startup_timeout: 启动超时时间
            
        Returns:
            预览 URL，失败时返回 None
        """
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        port = self.STACK_PORTS.get(stack, 8000)
        
        # 路径规范化
        if not project_path.startswith("/"):
            project_path = f"/home/user/{project_path}"
        
        logger.info(f"📂 项目路径: {project_path}, 技术栈: {stack}")
        
        # 检查是否已有项目在运行，如有则先停止
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(
                session, conversation_id
            )
            if db_sandbox and db_sandbox.active_project_path:
                logger.info(
                    f"⚠️ 检测到已有项目运行中: {db_sandbox.active_project_path}，将先停止"
                )
                await self._stop_running_project(conversation_id)
        
        # 技术栈配置
        config = self._get_stack_config(stack, port)
        command = config["cmd"]
        port = config["port"]
        startup_wait = config["startup_wait"]
        
        try:
            # 停止可能残留的进程
            await self.run_command(
                conversation_id,
                f"pkill -f '{project_path}' 2>/dev/null || true",
                timeout=10
            )
            
            # 安装依赖
            await self._install_dependencies(conversation_id, project_path)
            
            # 后台启动
            logger.info(f"🚀 后台启动项目: cd {project_path} && {command}")
            await sandbox.commands.run(
                f"cd {project_path} && {command}",
                background=True,
                timeout=startup_timeout
            )
            
            # 等待服务就绪
            if wait_for_ready:
                logger.info(f"⏳ 等待服务启动 ({startup_wait}s)...")
                await asyncio.sleep(startup_wait)
                
                ready = await self._wait_for_port(
                    conversation_id, port,
                    timeout=startup_timeout - startup_wait
                )
                
                if not ready:
                    await self._log_startup_diagnostics(conversation_id, project_path)
            else:
                await asyncio.sleep(startup_wait)
            
            # 获取预览 URL
            host = sandbox.get_host(port)
            preview_url = f"https://{host}"
            
            # 更新数据库：保存项目信息和预览 URL
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_project(
                    session, conversation_id, project_path, stack, preview_url
                )
                await crud.update_sandbox_status(
                    session, conversation_id, "running", preview_url
                )
            
            logger.info(f"✅ 项目启动成功: {preview_url}")
            return preview_url
            
        except Exception as e:
            logger.error(f"❌ 运行项目失败: {e}", exc_info=True)
            return None
    
    def _get_stack_config(self, stack: str, port: int) -> Dict[str, Any]:
        """
        获取技术栈配置
        
        Args:
            stack: 技术栈名称
            port: 端口号
            
        Returns:
            配置字典
        """
        configs = {
            "python": {"cmd": "python app.py", "port": 8000, "startup_wait": 3},
            "flask": {"cmd": "python app.py", "port": 5000, "startup_wait": 3},
            "fastapi": {
                "cmd": f"uvicorn main:app --host 0.0.0.0 --port {port}",
                "port": port, "startup_wait": 5
            },
            "streamlit": {
                "cmd": f"streamlit run app.py --server.port {port} "
                       f"--server.address 0.0.0.0",
                "port": port, "startup_wait": 8
            },
            "gradio": {"cmd": "python app.py", "port": 7860, "startup_wait": 10},
            "nodejs": {"cmd": "npm start", "port": 3000, "startup_wait": 5},
            "react": {
                "cmd": "npm run dev -- --host 0.0.0.0 --port 5173 --strictPort",
                "port": 5173, "startup_wait": 10
            },
            "nextjs": {"cmd": "npm run dev", "port": 3000, "startup_wait": 10},
            "vue": {
                "cmd": "npm run dev -- --host 0.0.0.0 --port 5173 --strictPort",
                "port": 5173, "startup_wait": 8
            },
        }
        
        return configs.get(stack, {
            "cmd": "python app.py", "port": 8000, "startup_wait": 3
        })
    
    async def _install_dependencies(
        self,
        conversation_id: str,
        project_path: str
    ) -> None:
        """
        安装项目依赖
        
        Args:
            conversation_id: 对话 ID
            project_path: 项目路径
        """
        req_path = f"{project_path}/requirements.txt"
        pkg_path = f"{project_path}/package.json"
        
        # Python 依赖
        if await self.file_exists(conversation_id, req_path):
            check_result = await self.run_command(
                conversation_id,
                f"cd {project_path} && head -1 requirements.txt | "
                f"cut -d'>' -f1 | cut -d'=' -f1 | xargs pip show 2>/dev/null "
                f"&& echo 'INSTALLED' || echo 'NOT_INSTALLED'",
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
                logger.info("✅ 依赖已预装，跳过安装")
        
        # Node.js 依赖
        if await self.file_exists(conversation_id, pkg_path):
            logger.info("📦 安装 Node.js 依赖")
            await self.run_command(
                conversation_id,
                f"cd {project_path} && npm install 2>&1",
                timeout=180
            )
    
    async def _log_startup_diagnostics(
        self,
        conversation_id: str,
        project_path: str
    ) -> None:
        """
        记录启动诊断信息
        
        Args:
            conversation_id: 对话 ID
            project_path: 项目路径
        """
        diag_result = await self.run_command(
            conversation_id,
            f"ps aux | grep -E 'python|node|streamlit' | head -5; "
            f"tail -30 /tmp/app.log 2>/dev/null || "
            f"tail -30 {project_path}/nohup.out 2>/dev/null || "
            f"echo '(无启动日志)'",
            timeout=10
        )
        diag_info = (diag_result.output or "")[:500]
        logger.warning(f"⚠️ 服务未就绪，诊断信息:\n{diag_info}")
    
    async def get_preview_url(
        self,
        conversation_id: str,
        port: int = 8000
    ) -> Optional[str]:
        """
        获取预览 URL
        
        Args:
            conversation_id: 对话 ID
            port: 端口号
            
        Returns:
            预览 URL，失败时返回 None
        """
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            host = sandbox.get_host(port)
            return f"https://{host}"
        except Exception:
            return None

    # ==================== 连接池管理 ====================
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态
        
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
                await sandbox.commands.run("echo 'ping'", timeout=5)
            except Exception:
                invalid_ids.append(conv_id)
        
        for conv_id in invalid_ids:
            del self._sandbox_pool[conv_id]
            logger.info(f"🧹 清理失效沙盒连接: {conv_id}")
        
        return len(invalid_ids)
    
    async def get_sandbox_metrics(
        self,
        conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取沙盒运行指标
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            指标信息，失败时返回 None
        """
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            
            result = await sandbox.commands.run(
                "echo $(free -m | awk 'NR==2{print $3}') "
                "$(df -h /home/user | awk 'NR==2{print $5}')",
                timeout=10
            )
            
            parts = result.stdout.strip().split()
            memory_used_mb = int(parts[0]) \
                if len(parts) > 0 and parts[0].isdigit() else None
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
