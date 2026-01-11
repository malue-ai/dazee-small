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
    
    async def _get_sandbox_obj(self, conversation_id: str):
        """获取沙盒对象（内部使用）"""
        if conversation_id not in self._sandbox_pool:
            raise SandboxNotFoundError(f"沙盒不存在或未连接: {conversation_id}")
        return self._sandbox_pool[conversation_id]
    
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
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return CommandResult(
                    success=False,
                    error=f"命令执行超时（{timeout}秒）",
                    exit_code=-1
                )
            logger.error(f"❌ 命令执行失败: {e}", exc_info=True)
            return CommandResult(
                success=False,
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
        """执行代码（Code Interpreter）"""
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            # E2B Code Interpreter 的 run_code 方法
            execution = await asyncio.to_thread(
                sandbox.run_code,
                code,
                timeout=timeout
            )
            
            await self._update_activity(conversation_id)
            
            # 处理结果
            stdout = ""
            stderr = ""
            artifacts = []
            
            for log in execution.logs:
                if hasattr(log, 'type'):
                    if log.type == 'stdout':
                        stdout += log.data
                    elif log.type == 'stderr':
                        stderr += log.data
                else:
                    stdout += str(log)
            
            # 处理产物（如图表）
            if hasattr(execution, 'results'):
                for result in execution.results:
                    if hasattr(result, 'png'):
                        artifacts.append({
                            "type": "image",
                            "format": "png",
                            "data": result.png
                        })
                    elif hasattr(result, 'html'):
                        artifacts.append({
                            "type": "html",
                            "data": result.html
                        })
            
            logger.info(f"📝 代码执行完成，输出 {len(stdout)} 字符")
            
            return CodeResult(
                success=True,
                stdout=stdout,
                stderr=stderr,
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
        """读取文件"""
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            content = await asyncio.to_thread(
                sandbox.files.read,
                path
            )
            
            # 处理返回类型
            if isinstance(content, bytes):
                return content.decode('utf-8')
            return content
            
        except Exception as e:
            if "not found" in str(e).lower():
                raise FileNotFoundError(f"文件不存在: {path}")
            raise SandboxError(f"读取文件失败: {e}")
    
    async def write_file(self, conversation_id: str, path: str, content: str) -> bool:
        """写入文件"""
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
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
        """列出目录内容"""
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        
        try:
            entries = await asyncio.to_thread(
                sandbox.files.list,
                path
            )
            
            result = []
            for entry in entries:
                result.append(FileInfo(
                    name=entry.name,
                    path=f"{path}/{entry.name}".replace("//", "/"),
                    type="directory" if entry.is_dir else "file",
                    size=getattr(entry, 'size', None)
                ))
            
            return result
            
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
    
    # ==================== 项目运行 ====================
    
    async def run_project(
        self,
        conversation_id: str,
        project_path: str,
        stack: str
    ) -> Optional[str]:
        """运行项目"""
        self._check_available()
        
        sandbox = await self._get_sandbox_obj(conversation_id)
        port = self.STACK_PORTS.get(stack, 8000)
        
        # 根据技术栈确定启动命令
        start_commands = {
            "python": f"cd {project_path} && python app.py",
            "flask": f"cd {project_path} && python app.py",
            "fastapi": f"cd {project_path} && uvicorn main:app --host 0.0.0.0 --port {port}",
            "streamlit": f"cd {project_path} && streamlit run app.py --server.port {port}",
            "nodejs": f"cd {project_path} && npm start",
            "react": f"cd {project_path} && npm run dev",
            "nextjs": f"cd {project_path} && npm run dev",
            "vue": f"cd {project_path} && npm run dev",
        }
        
        command = start_commands.get(stack, f"cd {project_path} && python app.py")
        
        try:
            # 检查 requirements.txt
            req_path = f"{project_path}/requirements.txt"
            if await self.file_exists(conversation_id, req_path):
                logger.info(f"📦 安装依赖: {req_path}")
                await self.run_command(
                    conversation_id,
                    f"cd {project_path} && pip install -q -r requirements.txt",
                    timeout=120
                )
            
            # 后台启动项目
            logger.info(f"🚀 启动项目: {command}")
            await asyncio.to_thread(
                sandbox.commands.run,
                f"nohup {command} > /tmp/app.log 2>&1 &",
                timeout=30
            )
            
            # 等待启动
            await asyncio.sleep(3)
            
            # 获取预览 URL
            host = sandbox.get_host(port)
            preview_url = f"https://{host}"
            
            # 更新数据库
            if DB_AVAILABLE:
                async with AsyncSessionLocal() as session:
                    await crud.update_sandbox_preview(
                        session, conversation_id, preview_url, stack
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

