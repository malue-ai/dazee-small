"""
E2B Code Interpreter 沙盒实现（简化版）

E2B (e2b.dev) 提供的云端代码执行环境：
- 基于 Code Interpreter 模板，内置 Jupyter 内核
- 支持代码执行间的上下文共享（变量、导入等）
- 预装数据科学常用包（pandas、numpy、matplotlib 等）
- 完全隔离的 Linux 容器，支持文件操作和命令执行
- 支持暂停和恢复（节省成本，30 天内可恢复）
- 使用 beta_create(auto_pause=True) 超时后自动暂停

依赖：
- pip install e2b-code-interpreter
- 环境变量 E2B_API_KEY

参考文档：
- https://e2b.dev/docs/sandbox/persistence
"""

import os
import asyncio
import time
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from e2b_code_interpreter import AsyncSandbox

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

logger = get_logger("infra.sandbox.e2b")


class E2BSandboxProvider(SandboxProvider):
    """
    E2B Code Interpreter 沙盒提供者（简化版）
    
    核心功能：
    - 沙盒生命周期管理（创建、暂停、恢复、销毁）
    - 文件操作（读、写、删除、列目录）
    - 命令执行
    - Code Interpreter（代码执行）
    - 连接池管理
    """
    
    # 默认超时（30 分钟）
    DEFAULT_TIMEOUT_SECONDS: int = 30 * 60
    
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
        """检查服务是否可用"""
        if not self.is_available:
            raise SandboxNotAvailableError("E2B 沙盒服务不可用，请检查配置")

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
                    await crud.update_sandbox_status(
                        session, conversation_id, "running"
                    )
                
                logger.info(f"🔗 重新连接沙盒成功: {db_sandbox.e2b_sandbox_id}")
                return await self.get_sandbox(conversation_id)
                
            except Exception as e:
                logger.warning(f"⚠️ 连接已有沙盒失败: {e}，将创建新沙盒")
        
        # 3. 创建新沙盒
        return await self._create_new_sandbox(conversation_id, user_id, stack)
    
    # 创建沙盒时可重试的网络错误关键词
    _RETRYABLE_CREATE_ERRORS = [
        'disconnected', 'connection', 'timeout', 'temporarily unavailable',
        'server error', '502', '503', '504', 'network'
    ]
    
    async def _create_new_sandbox(
        self,
        conversation_id: str,
        user_id: str,
        stack: Optional[str] = None,
        max_retries: int = 2,
        base_delay: float = 1.0
    ) -> SandboxInfo:
        """
        创建新沙盒（带重试机制）
        
        Args:
            conversation_id: 对话 ID
            user_id: 用户 ID
            stack: 技术栈
            max_retries: 最大重试次数
            base_delay: 基础重试延迟（秒），采用指数退避
        """
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
        
        if self.api_key != os.getenv("E2B_API_KEY"):
            os.environ["E2B_API_KEY"] = self.api_key
        
        last_error: Optional[Exception] = None
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    f"🆕 创建 Code Interpreter 沙盒: conversation={conversation_id}"
                    + (f" (重试 {attempt}/{max_retries})" if attempt > 0 else "")
                )
                
                # 使用 beta_create 启用自动暂停功能
                # 超时后沙盒会自动暂停（而不是销毁），可以恢复
                sandbox = await AsyncSandbox.beta_create(
                    auto_pause=True,  # 超时后自动暂停
                    timeout=self.DEFAULT_TIMEOUT_SECONDS,
                    metadata={"conversation_id": conversation_id, "user_id": user_id}
                )
                
                await asyncio.sleep(1)
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
                last_error = e
                error_str = str(e).lower()
                
                # 判断是否为可重试的网络错误
                is_retryable = any(
                    kw in error_str for kw in self._RETRYABLE_CREATE_ERRORS
                )
                
                if is_retryable and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"⚠️ 创建沙盒失败，将在 {delay:.1f}s 后重试 "
                        f"({attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                
                # 不可重试或已达到最大重试次数
                logger.error(f"❌ 创建沙盒失败: {e}", exc_info=True)
                raise SandboxError(f"创建沙盒失败: {e}")
    
    async def _connect_sandbox(self, e2b_sandbox_id: str) -> Any:
        """连接到已有沙盒"""
        if self.api_key != os.getenv("E2B_API_KEY"):
            os.environ["E2B_API_KEY"] = self.api_key
        
        # 恢复沙盒时设置 30 分钟超时（与创建时一致）
        sandbox = await AsyncSandbox.connect(
            e2b_sandbox_id,
            timeout=self.DEFAULT_TIMEOUT_SECONDS
        )
        
        try:
            await sandbox.commands.run("echo 'connected'", timeout=15)
        except Exception as e:
            raise SandboxConnectionError(f"沙盒连接验证失败: {e}")
        
        logger.info(f"🔗 连接沙盒成功: {e2b_sandbox_id}")
        return sandbox
    
    async def get_sandbox(self, conversation_id: str) -> Optional[SandboxInfo]:
        """获取沙盒信息"""
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
        
        支持从内存池或数据库恢复连接后暂停：
        1. 先检查内存池中是否有活跃连接
        2. 如果没有，从数据库获取 e2b_sandbox_id 并连接后暂停
        """
        sandbox = None
        e2b_sandbox_id = None
        
        try:
            # 1. 优先使用内存池中的连接
            if conversation_id in self._sandbox_pool:
                sandbox = self._sandbox_pool[conversation_id]
                del self._sandbox_pool[conversation_id]
            else:
                # 2. 从数据库获取 e2b_sandbox_id 并连接
                async with AsyncSessionLocal() as session:
                    db_sandbox = await crud.get_sandbox_by_conversation(
                        session, conversation_id
                    )
                
                if not db_sandbox or not db_sandbox.e2b_sandbox_id:
                    logger.warning(f"⚠️ 沙盒不存在或无 e2b_sandbox_id: {conversation_id}")
                    return False
                
                e2b_sandbox_id = db_sandbox.e2b_sandbox_id
                
                # 连接到沙盒
                try:
                    sandbox = await self._connect_sandbox(e2b_sandbox_id)
                except Exception as conn_err:
                    # 连接失败可能沙盒已不存在，更新 DB 状态
                    logger.warning(f"⚠️ 连接沙盒失败，可能已被删除: {conn_err}")
                    async with AsyncSessionLocal() as session:
                        await crud.update_sandbox_status(
                            session, conversation_id, "stopped"
                        )
                    return False
            
            # 3. 执行暂停
            await sandbox.beta_pause()  # beta 功能
            
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
        """恢复沙盒"""
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(
                session, conversation_id
            )
        
        if not db_sandbox or not db_sandbox.e2b_sandbox_id:
            raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
        
        try:
            sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
            self._sandbox_pool[conversation_id] = sandbox
            
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(
                    session, conversation_id, "running"
                )
            
            logger.info(f"▶️ 沙盒已恢复: {conversation_id}")
            return await self.get_sandbox(conversation_id)
        except Exception as e:
            raise SandboxError(f"恢复沙盒失败: {e}")
    
    async def destroy_sandbox(self, conversation_id: str) -> bool:
        """
        销毁沙盒
        
        支持从内存池或数据库恢复连接后销毁：
        1. 先检查内存池中是否有活跃连接
        2. 如果没有，从数据库获取 e2b_sandbox_id 并连接后销毁
        """
        sandbox = None
        e2b_sandbox_id = None
        
        try:
            # 1. 优先使用内存池中的连接
            if conversation_id in self._sandbox_pool:
                sandbox = self._sandbox_pool[conversation_id]
                del self._sandbox_pool[conversation_id]
            else:
                # 2. 从数据库获取 e2b_sandbox_id
                async with AsyncSessionLocal() as session:
                    db_sandbox = await crud.get_sandbox_by_conversation(
                        session, conversation_id
                    )
                
                if db_sandbox and db_sandbox.e2b_sandbox_id:
                    e2b_sandbox_id = db_sandbox.e2b_sandbox_id
                    
                    # 尝试连接并销毁
                    try:
                        sandbox = await self._connect_sandbox(e2b_sandbox_id)
                    except Exception as conn_err:
                        # 连接失败可能沙盒已不存在，这是正常情况
                        logger.info(
                            f"ℹ️ 连接沙盒失败（可能已被 E2B 自动销毁）: {conn_err}"
                        )
                        sandbox = None
            
            # 3. 如果有连接，执行销毁
            if sandbox:
                try:
                    await sandbox.kill()
                    logger.info(f"🗑️ E2B 沙盒已销毁: {e2b_sandbox_id or conversation_id}")
                except Exception as kill_err:
                    # 销毁失败也继续更新 DB 状态
                    logger.warning(f"⚠️ 销毁沙盒时出错（可能已不存在）: {kill_err}")
            
            # 4. 更新数据库状态
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(
                    session, conversation_id, "stopped"
                )
            
            logger.info(f"🗑️ 沙盒状态已更新为 stopped: {conversation_id}")
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
        """获取沙盒对象（内部使用）"""
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
                if "not found" in error_str:
                    logger.warning(
                        f"⚠️ 沙盒已被删除，将自动重建: {db_sandbox.e2b_sandbox_id}"
                    )
                    async with AsyncSessionLocal() as session:
                        await crud.update_sandbox_e2b_id(
                            session, conversation_id, "", status="deleted"
                        )
                    
                    await self._create_new_sandbox(
                        conversation_id,
                        user_id=db_sandbox.user_id,
                        stack=db_sandbox.stack
                    )
                    return self._sandbox_pool[conversation_id]
                
                logger.error(f"❌ 重新连接沙盒失败: {e}")
                raise SandboxConnectionError(
                    f"沙盒连接失败，可能已被删除: {e}"
                )
        
        raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
    
    def _invalidate_sandbox(self, conversation_id: str) -> None:
        """使沙盒连接失效"""
        if conversation_id in self._sandbox_pool:
            del self._sandbox_pool[conversation_id]
            logger.info(f"🔄 已从连接池移除失效沙盒: {conversation_id}")
    
    async def _with_retry(
        self,
        conversation_id: str,
        operation: Callable,
        max_retries: int = 1
    ) -> Any:
        """带自动重试的操作包装器"""
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
        """在沙盒中执行命令"""
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
            return self._handle_command_exception(e, command, timeout)
    
    def _handle_command_exception(
        self,
        e: Exception,
        command: str,
        timeout: int
    ) -> CommandResult:
        """处理命令执行异常"""
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
        执行代码（基于 Code Interpreter 的 Jupyter 内核）
        
        Code Interpreter 特性：
        - 上下文共享：多次执行间变量、导入、函数定义会保留
        - 图表支持：matplotlib 等图表会自动捕获并返回
        - 预装包：pandas、numpy、matplotlib 等无需手动安装
        """
        self._check_available()
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            start_time = time.time()
            execution = await sandbox.run_code(code, timeout=timeout)
            execution_time = time.time() - start_time
            
            await self._update_activity(conversation_id)
            
            stdout, stderr = self._parse_execution_logs(execution)
            artifacts = await self._parse_execution_results(execution, conversation_id)
            
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
        """解析执行日志"""
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
        
        if hasattr(execution, 'text') and execution.text and not stdout:
            stdout = execution.text
        
        return stdout, stderr
    
    async def _parse_execution_results(
        self,
        execution: Any,
        conversation_id: str
    ) -> List[Dict[str, Any]]:
        """
        解析执行结果（图表等）
        
        注意：为避免 base64 图片数据导致对话历史膨胀，
        图片会被上传到 S3，返回结果中只包含 URL。
        """
        artifacts = []
        
        if not hasattr(execution, 'results') or not execution.results:
            return artifacts
        
        for idx, result in enumerate(execution.results):
            artifact = {}
            
            # 处理 PNG 图片：上传到 S3，只返回 URL
            if hasattr(result, 'png') and result.png:
                url = await self._upload_image_to_s3(
                    result.png, "png", conversation_id, idx
                )
                if url:
                    artifact = {"type": "image", "format": "png", "url": url}
                else:
                    # 上传失败时，截断 base64 数据，避免上下文爆炸
                    artifact = {
                        "type": "image",
                        "format": "png",
                        "data_preview": result.png[:100] + "..." if len(result.png) > 100 else result.png,
                        "data_length": len(result.png),
                        "note": "图片已生成，但上传失败"
                    }
            
            # 处理 SVG 图片：同样上传到 S3
            elif hasattr(result, 'svg') and result.svg:
                url = await self._upload_image_to_s3(
                    result.svg, "svg", conversation_id, idx
                )
                if url:
                    artifact = {"type": "image", "format": "svg", "url": url}
                else:
                    artifact = {
                        "type": "image",
                        "format": "svg",
                        "data_preview": result.svg[:200] + "..." if len(result.svg) > 200 else result.svg,
                        "data_length": len(result.svg),
                        "note": "图片已生成，但上传失败"
                    }
            
            elif hasattr(result, 'html') and result.html:
                # HTML 内容通常不会太大，但也做截断保护
                html_data = result.html
                if len(html_data) > 10000:
                    artifact = {
                        "type": "html",
                        "data_preview": html_data[:500] + "...",
                        "data_length": len(html_data),
                        "note": "HTML 内容已截断"
                    }
                else:
                    artifact = {"type": "html", "data": html_data}
            
            elif hasattr(result, 'text') and result.text:
                artifact = {"type": "text", "data": result.text}
            
            if artifact:
                artifacts.append(artifact)
        
        return artifacts
    
    async def _upload_image_to_s3(
        self,
        image_data: str,
        format: str,
        conversation_id: str,
        index: int
    ) -> Optional[str]:
        """
        将图片上传到 S3 并返回 URL
        
        Args:
            image_data: base64 编码的图片数据
            format: 图片格式（png/svg）
            conversation_id: 对话 ID
            index: 图片索引
            
        Returns:
            预签名 URL，失败返回 None
        """
        try:
            import base64
            from utils.s3_uploader import get_s3_uploader
            
            uploader = get_s3_uploader()
            await uploader.initialize()
            
            # 生成唯一文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sandbox_{conversation_id[:8]}_{timestamp}_{index}.{format}"
            object_name = f"sandbox-artifacts/{conversation_id}/{filename}"
            
            # 确定内容类型
            content_type = "image/png" if format == "png" else "image/svg+xml"
            
            # 解码 base64（如果是 PNG）
            if format == "png":
                file_content = base64.b64decode(image_data)
            else:
                # SVG 是文本格式
                file_content = image_data.encode('utf-8')
            
            # 上传到 S3
            result = await uploader.upload_bytes(
                file_content=file_content,
                object_name=object_name,
                content_type=content_type,
                acl="public-read"  # 允许直接访问
            )
            
            # 生成预签名 URL（7天有效）
            url = uploader.get_presigned_url(result["key"], expires_in=7 * 24 * 3600)
            
            logger.info(f"📤 沙盒图片已上传到 S3: {filename}, size={len(file_content)}")
            return url
            
        except Exception as e:
            logger.warning(f"⚠️ 沙盒图片上传 S3 失败: {e}")
            return None

    # ==================== 文件操作 ====================
    
    async def read_file(self, conversation_id: str, path: str) -> str:
        """读取文件"""
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
    
    async def read_file_binary(self, conversation_id: str, path: str) -> bytes:
        """
        读取二进制文件
        
        用于读取非文本文件（如 Excel、PDF、图片等），
        使用 E2B SDK 的 format="bytes" 参数直接读取原始字节。
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            文件的二进制内容（bytes）
            
        Raises:
            FileNotFoundError: 文件不存在
            SandboxError: 读取失败
        """
        self._check_available()
        
        async def _do_read_binary(sandbox: Any) -> bytes:
            # 使用 format="bytes" 直接读取二进制内容
            # E2B SDK: sandbox.files.read(path, format="bytes") -> bytearray
            content = await sandbox.files.read(path, format="bytes")
            # bytearray 转换为 bytes
            if isinstance(content, bytearray):
                return bytes(content)
            if isinstance(content, bytes):
                return content
            # 兜底：如果返回的是字符串，编码为 bytes
            return content.encode('utf-8')
        
        try:
            return await self._with_retry(conversation_id, _do_read_binary)
        except Exception as e:
            if "not found" in str(e).lower():
                raise FileNotFoundError(f"文件不存在: {path}")
            raise SandboxError(f"读取二进制文件失败: {e}")
    
    async def write_file(
        self,
        conversation_id: str,
        path: str,
        content: str
    ) -> bool:
        """写入文件"""
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
        """删除文件"""
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
        """列出目录内容"""
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
        """检查文件是否存在"""
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            result = await sandbox.commands.run(
                f"test -e {path} && echo 'exists'", timeout=10
            )
            return "exists" in result.stdout
        except Exception:
            return False

    # ==================== 连接池管理 ====================
    
    def get_pool_status(self) -> Dict[str, Any]:
        """获取连接池状态"""
        return {
            "provider": self.provider_name,
            "available": self.is_available,
            "pool_size": len(self._sandbox_pool),
            "conversations": list(self._sandbox_pool.keys())
        }
    
    async def cleanup_pool(self) -> int:
        """清理失效的连接池条目"""
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
        """获取沙盒运行指标"""
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

    # ==================== 项目运行 ====================
    
    async def run_project(
        self,
        conversation_id: str,
        project_path: str,
        stack: str
    ) -> Optional[str]:
        """
        运行项目并返回预览 URL
        
        Args:
            conversation_id: 对话 ID
            project_path: 项目路径
            stack: 技术栈（python/nodejs/react/nextjs 等）
            
        Returns:
            预览 URL，失败时返回 None
        """
        self._check_available()
        
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            
            # 根据技术栈确定启动命令和端口
            start_cmd, port = self._get_start_command(stack)
            
            # 清理可能残留的旧进程
            await self.run_command(
                conversation_id,
                "pkill -f 'node|python|npm' 2>/dev/null || true",
                timeout=5
            )
            
            # 后台启动项目
            startup_cmd = f"cd {project_path} && {start_cmd} > /tmp/app.log 2>&1"
            logger.info(f"🚀 启动项目: {startup_cmd}")
            
            try:
                await sandbox.commands.run(startup_cmd, background=True, timeout=10)
            except Exception as e:
                # 后台启动可能会超时，但这是正常的
                if "timeout" not in str(e).lower():
                    logger.warning(f"⚠️ 启动命令返回异常（可能正常）: {e}")
            
            # 等待服务启动
            await asyncio.sleep(3)
            
            # 检查端口是否就绪
            ready = await self._wait_for_port(conversation_id, port, timeout=30)
            
            if ready:
                preview_url = await self.get_preview_url(conversation_id, port)
                
                # 更新数据库中的预览 URL 和项目信息
                async with AsyncSessionLocal() as session:
                    await crud.update_sandbox_project(
                        session,
                        conversation_id,
                        active_project_path=project_path,
                        active_project_stack=stack,
                        preview_url=preview_url
                    )
                
                logger.info(f"✅ 项目启动成功: {preview_url}")
                return preview_url
            else:
                logger.warning(f"⚠️ 项目未能在端口 {port} 上启动")
                return None
                
        except Exception as e:
            logger.error(f"❌ 运行项目失败: {e}", exc_info=True)
            return None
    
    def _get_start_command(self, stack: str) -> tuple[str, int]:
        """
        根据技术栈获取启动命令和端口
        
        Returns:
            (启动命令, 端口号)
        """
        stack_lower = stack.lower()
        
        if stack_lower in ("nodejs", "node", "express"):
            return "npm start", 3000
        elif stack_lower in ("react", "vite", "vue"):
            return "npm run dev -- --host 0.0.0.0", 5173
        elif stack_lower in ("nextjs", "next"):
            return "npm run dev", 3000
        elif stack_lower in ("python", "flask"):
            return "python app.py", 5000
        elif stack_lower in ("fastapi", "uvicorn"):
            return "uvicorn main:app --host 0.0.0.0 --port 8000", 8000
        elif stack_lower in ("django",):
            return "python manage.py runserver 0.0.0.0:8000", 8000
        else:
            # 默认尝试 npm start
            return "npm start", 3000
    
    async def _wait_for_port(
        self,
        conversation_id: str,
        port: int,
        timeout: int = 30
    ) -> bool:
        """等待端口就绪"""
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout:
            check_count += 1
            
            result = await self.run_command(
                conversation_id,
                f"nc -z localhost {port} 2>/dev/null && echo 'READY' || echo 'WAITING'",
                timeout=5
            )
            
            if "READY" in (result.output or ""):
                logger.info(f"✅ 端口 {port} 已就绪（检查次数: {check_count}）")
                return True
            
            if check_count % 5 == 0:
                logger.info(f"⏳ 等待端口 {port}... (已等待 {check_count * 2}s)")
            
            await asyncio.sleep(2)
        
        logger.warning(f"⚠️ 端口 {port} 在 {timeout}s 内未就绪")
        return False
    
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
            预览 URL
        """
        self._check_available()
        
        try:
            sandbox = await self._get_sandbox_obj(conversation_id)
            host = sandbox.get_host(port)
            preview_url = f"https://{host}"
            
            logger.info(f"🔗 获取预览 URL: {preview_url}")
            return preview_url
            
        except Exception as e:
            logger.error(f"❌ 获取预览 URL 失败: {e}", exc_info=True)
            return None
