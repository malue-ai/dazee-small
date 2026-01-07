"""
Sandbox 服务层 - E2B 沙盒管理

职责：
1. 沙盒生命周期管理（create/pause/resume/kill）
2. 沙盒文件操作（代理到 E2B）
3. 项目运行管理
4. 沙盒连接池管理

设计原则：
- 每个 conversation 最多一个活跃沙盒
- 优先复用已存在的沙盒（通过 connect）
- 使用 auto_pause 实现自动暂停
- 所有文件操作通过 E2B SDK
"""

import os
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field

from e2b_code_interpreter import Sandbox as CodeInterpreter

from logger import get_logger
from infra.database import AsyncSessionLocal, crud

logger = get_logger("sandbox_service")


@dataclass
class FileInfo:
    """文件信息"""
    name: str
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    modified_at: Optional[str] = None


@dataclass
class SandboxInfo:
    """沙盒信息"""
    id: str
    conversation_id: str
    user_id: str
    e2b_sandbox_id: Optional[str]
    status: str
    stack: Optional[str]
    preview_url: Optional[str]
    created_at: Optional[str]
    last_active_at: Optional[str]


@dataclass
class RunResult:
    """运行结果"""
    success: bool
    preview_url: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


class SandboxServiceError(Exception):
    """沙盒服务异常基类"""
    pass


class SandboxNotFoundError(SandboxServiceError):
    """沙盒不存在"""
    pass


class SandboxConnectionError(SandboxServiceError):
    """沙盒连接失败"""
    pass


class SandboxService:
    """
    E2B 沙盒服务
    
    核心功能：
    - 管理沙盒生命周期（create/pause/resume/kill）
    - 代理文件操作到 E2B
    - 维护沙盒连接池
    """
    
    # 沙盒连接池：conversation_id -> sandbox 对象
    _sandbox_pool: Dict[str, Any] = {}
    
    # 默认配置
    DEFAULT_TIMEOUT_MS = 10 * 60 * 1000  # 10 分钟无活动后自动暂停
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化沙盒服务
        
        Args:
            api_key: E2B API Key（默认从环境变量读取）
        """
        self.api_key = api_key or os.getenv("E2B_API_KEY")
        
        if not self.api_key:
            logger.warning("⚠️ E2B_API_KEY 未设置，沙盒功能不可用")
        else:
            logger.info("✅ SandboxService 初始化完成")
    
    # ==================== 生命周期管理 ====================
    
    async def get_or_create_sandbox(
        self,
        conversation_id: str,
        user_id: str,
        stack: Optional[str] = None
    ) -> SandboxInfo:
        """
        获取或创建沙盒
        
        逻辑：
        1. 检查连接池中是否有活跃连接
        2. 检查数据库中是否有记录
        3. 如果有 e2b_sandbox_id，尝试 connect
        4. 如果连接失败或不存在，创建新沙盒
        
        Args:
            conversation_id: 对话 ID
            user_id: 用户 ID
            stack: 技术栈（可选）
            
        Returns:
            沙盒信息
        """
        if not E2B_AVAILABLE or not self.api_key:
            raise SandboxServiceError("E2B 沙盒服务不可用")
        
        # 1. 检查连接池
        if conversation_id in self._sandbox_pool:
            sandbox = self._sandbox_pool[conversation_id]
            try:
                # 验证连接是否有效
                await asyncio.to_thread(
                    sandbox.commands.run,
                    "echo 'ping'",
                    timeout=10
                )
                logger.debug(f"♻️ 复用连接池中的沙盒: {conversation_id}")
                
                # 更新活跃时间
                await self._update_activity(conversation_id)
                
                return await self._get_sandbox_info(conversation_id)
            except Exception as e:
                logger.warning(f"⚠️ 连接池中的沙盒已失效: {e}")
                del self._sandbox_pool[conversation_id]
        
        # 2. 查询数据库
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
        
        if db_sandbox and db_sandbox.e2b_sandbox_id:
            # 3. 尝试连接已有沙盒
            try:
                sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
                self._sandbox_pool[conversation_id] = sandbox
                
                # 更新状态为 running
                async with AsyncSessionLocal() as session:
                    # 重新获取 preview_url
                    preview_url = None
                    if db_sandbox.stack:
                        port = self._get_stack_port(db_sandbox.stack)
                        if port:
                            host = sandbox.get_host(port)
                            preview_url = f"https://{host}"
                    
                    await crud.update_sandbox_status(
                        session, conversation_id, "running", preview_url
                    )
                
                logger.info(f"🔗 重新连接沙盒成功: {db_sandbox.e2b_sandbox_id}")
                
                return await self._get_sandbox_info(conversation_id)
                
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
            
            # 创建沙盒（启用 auto_pause）
            logger.info(f"🆕 创建新沙盒: conversation={conversation_id}")
            
            sandbox = await asyncio.to_thread(
                CodeInterpreter.create,
                timeout=self.DEFAULT_TIMEOUT_MS // 1000,  # 转换为秒
                metadata={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "stack": stack or "python"
                }
            )
            
            # 等待沙盒就绪
            await asyncio.sleep(3)
            
            # 保存到连接池
            self._sandbox_pool[conversation_id] = sandbox
            
            # 更新数据库
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_e2b_id(
                    session=session,
                    conversation_id=conversation_id,
                    e2b_sandbox_id=sandbox.sandbox_id,
                    status="running"
                )
                
                if stack:
                    await crud.update_sandbox(
                        session=session,
                        sandbox_id=db_sandbox.id,
                        stack=stack
                    )
            
            logger.info(f"✅ 沙盒创建成功: {sandbox.sandbox_id}")
            
            return await self._get_sandbox_info(conversation_id)
            
        except Exception as e:
            logger.error(f"❌ 沙盒创建失败: {e}", exc_info=True)
            
            # 更新状态为失败
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(session, conversation_id, "failed")
            
            raise SandboxServiceError(f"沙盒创建失败: {e}")
    
    async def _connect_sandbox(self, e2b_sandbox_id: str) -> Any:
        """连接已有沙盒"""
        if self.api_key != os.getenv("E2B_API_KEY"):
            os.environ["E2B_API_KEY"] = self.api_key
        
        sandbox = await asyncio.to_thread(
            CodeInterpreter.connect,
            e2b_sandbox_id
        )
        
        # 验证连接
        result = await asyncio.to_thread(
            sandbox.commands.run,
            "echo 'connected'",
            timeout=10
        )
        
        if result.exit_code != 0:
            raise SandboxConnectionError("沙盒连接验证失败")
        
        return sandbox
    
    async def pause_sandbox(self, conversation_id: str) -> bool:
        """
        暂停沙盒
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        # 获取沙盒
        sandbox = self._sandbox_pool.get(conversation_id)
        
        if not sandbox:
            # 尝试从数据库获取并连接
            async with AsyncSessionLocal() as session:
                db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
            
            if not db_sandbox or not db_sandbox.e2b_sandbox_id:
                logger.warning(f"⚠️ 沙盒不存在: {conversation_id}")
                return False
            
            try:
                sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
            except Exception as e:
                logger.warning(f"⚠️ 连接沙盒失败: {e}")
                return False
        
        try:
            # 暂停沙盒
            await asyncio.to_thread(sandbox.pause)
            
            # 从连接池移除
            if conversation_id in self._sandbox_pool:
                del self._sandbox_pool[conversation_id]
            
            # 更新数据库状态
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(session, conversation_id, "paused")
            
            logger.info(f"⏸️ 沙盒已暂停: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 暂停沙盒失败: {e}", exc_info=True)
            return False
    
    async def resume_sandbox(self, conversation_id: str) -> SandboxInfo:
        """
        恢复沙盒
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            沙盒信息
        """
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
        
        if not db_sandbox or not db_sandbox.e2b_sandbox_id:
            raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
        
        try:
            # 连接会自动恢复暂停的沙盒
            sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
            self._sandbox_pool[conversation_id] = sandbox
            
            # 重新获取 preview_url
            preview_url = None
            if db_sandbox.stack:
                port = self._get_stack_port(db_sandbox.stack)
                if port:
                    host = sandbox.get_host(port)
                    preview_url = f"https://{host}"
            
            # 更新数据库状态
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox_status(
                    session, conversation_id, "running", preview_url
                )
            
            logger.info(f"▶️ 沙盒已恢复: {conversation_id}")
            
            return await self._get_sandbox_info(conversation_id)
            
        except Exception as e:
            logger.error(f"❌ 恢复沙盒失败: {e}", exc_info=True)
            raise SandboxServiceError(f"恢复沙盒失败: {e}")
    
    async def kill_sandbox(self, conversation_id: str) -> bool:
        """
        终止沙盒
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        # 从连接池获取
        sandbox = self._sandbox_pool.get(conversation_id)
        
        if sandbox:
            try:
                await asyncio.to_thread(sandbox.kill)
            except Exception as e:
                logger.warning(f"⚠️ 终止沙盒时出错: {e}")
            
            del self._sandbox_pool[conversation_id]
        
        # 更新数据库状态
        async with AsyncSessionLocal() as session:
            await crud.update_sandbox_status(session, conversation_id, "killed")
        
        logger.info(f"🗑️ 沙盒已终止: {conversation_id}")
        return True
    
    async def get_sandbox_status(self, conversation_id: str) -> Optional[SandboxInfo]:
        """
        获取沙盒状态
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            沙盒信息，不存在返回 None
        """
        return await self._get_sandbox_info(conversation_id)
    
    # ==================== 文件操作 ====================
    
    async def list_files(
        self,
        conversation_id: str,
        path: str = "/home/user"
    ) -> List[FileInfo]:
        """
        列出沙盒目录内容
        
        Args:
            conversation_id: 对话 ID
            path: 目录路径
            
        Returns:
            文件列表
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            # 使用 ls 命令获取文件列表
            result = await asyncio.to_thread(
                sandbox.commands.run,
                f"ls -la {path} 2>/dev/null || echo 'DIR_NOT_FOUND'",
                timeout=30
            )
            
            if "DIR_NOT_FOUND" in result.stdout:
                return []
            
            files = []
            lines = result.stdout.strip().split('\n')
            
            for line in lines[1:]:  # 跳过 total 行
                if not line.strip():
                    continue
                
                parts = line.split()
                if len(parts) < 9:
                    continue
                
                permissions = parts[0]
                size = int(parts[4]) if parts[4].isdigit() else 0
                name = ' '.join(parts[8:])
                
                if name in ['.', '..']:
                    continue
                
                file_type = "directory" if permissions.startswith('d') else "file"
                file_path = f"{path}/{name}".replace("//", "/")
                
                files.append(FileInfo(
                    name=name,
                    path=file_path,
                    type=file_type,
                    size=size if file_type == "file" else None
                ))
            
            return files
            
        except Exception as e:
            logger.error(f"❌ 列出目录失败: {e}", exc_info=True)
            raise SandboxServiceError(f"列出目录失败: {e}")
    
    async def read_file(
        self,
        conversation_id: str,
        path: str
    ) -> str:
        """
        读取沙盒文件内容
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            文件内容
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            content = await asyncio.to_thread(
                sandbox.files.read,
                path
            )
            
            # 如果是 bytes，尝试解码
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            
            return content
            
        except Exception as e:
            logger.error(f"❌ 读取文件失败: {path} - {e}", exc_info=True)
            raise SandboxServiceError(f"读取文件失败: {e}")
    
    async def read_file_bytes(
        self,
        conversation_id: str,
        path: str
    ) -> bytes:
        """
        读取沙盒文件内容（二进制）
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            文件内容（bytes）
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            content = await asyncio.to_thread(
                sandbox.files.read,
                path
            )
            
            if isinstance(content, str):
                content = content.encode('utf-8')
            
            return content
            
        except Exception as e:
            logger.error(f"❌ 读取文件失败: {path} - {e}", exc_info=True)
            raise SandboxServiceError(f"读取文件失败: {e}")
    
    async def write_file(
        self,
        conversation_id: str,
        path: str,
        content: str | bytes
    ) -> Dict[str, Any]:
        """
        写入沙盒文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            content: 文件内容
            
        Returns:
            写入结果
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            # 确保目录存在
            dir_path = os.path.dirname(path)
            if dir_path and dir_path != "/":
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
            
            logger.info(f"✅ 文件已写入: {path}")
            
            return {
                "success": True,
                "path": path,
                "size": len(content) if content else 0
            }
            
        except Exception as e:
            logger.error(f"❌ 写入文件失败: {path} - {e}", exc_info=True)
            raise SandboxServiceError(f"写入文件失败: {e}")
    
    async def delete_file(
        self,
        conversation_id: str,
        path: str
    ) -> bool:
        """
        删除沙盒文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            是否成功
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            result = await asyncio.to_thread(
                sandbox.commands.run,
                f"rm -rf {path}",
                timeout=30
            )
            
            logger.info(f"🗑️ 文件已删除: {path}")
            return result.exit_code == 0
            
        except Exception as e:
            logger.error(f"❌ 删除文件失败: {path} - {e}", exc_info=True)
            raise SandboxServiceError(f"删除文件失败: {e}")
    
    async def file_exists(
        self,
        conversation_id: str,
        path: str
    ) -> bool:
        """
        检查文件是否存在
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            是否存在
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            result = await asyncio.to_thread(
                sandbox.commands.run,
                f"test -e {path} && echo 'yes' || echo 'no'",
                timeout=10
            )
            
            return result.stdout.strip() == "yes"
            
        except Exception as e:
            logger.error(f"❌ 检查文件失败: {path} - {e}", exc_info=True)
            return False
    
    # ==================== 项目运行 ====================
    
    async def run_project(
        self,
        conversation_id: str,
        project_path: str,
        stack: str
    ) -> RunResult:
        """
        运行项目
        
        Args:
            conversation_id: 对话 ID
            project_path: 项目路径（相对于 /home/user）
            stack: 技术栈 (streamlit/gradio/python)
            
        Returns:
            运行结果
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        # 获取栈配置
        stack_config = self._get_stack_config(stack)
        if not stack_config:
            return RunResult(
                success=False,
                error=f"不支持的技术栈: {stack}"
            )
        
        full_path = f"/home/user/{project_path}".replace("//", "/")
        
        try:
            # 安装依赖
            req_file = f"{full_path}/requirements.txt"
            if await self.file_exists(conversation_id, req_file):
                logger.info(f"📦 安装依赖: {req_file}")
                await asyncio.to_thread(
                    sandbox.commands.run,
                    f"cd {full_path} && pip install -q -r requirements.txt",
                    timeout=120
                )
            
            # 启动服务
            start_cmd = stack_config["start_cmd"]
            entry_file = f"{full_path}/{stack_config['entry_file']}"
            
            # 替换入口文件路径
            start_cmd = start_cmd.replace("{entry}", entry_file)
            
            logger.info(f"🚀 启动项目: {start_cmd}")
            
            # 后台运行
            await asyncio.to_thread(
                sandbox.commands.run,
                f"cd {full_path} && nohup {start_cmd} > /tmp/app.log 2>&1 &",
                timeout=30
            )
            
            # 等待启动
            await asyncio.sleep(stack_config.get("startup_wait", 5))
            
            # 获取预览 URL
            port = stack_config["port"]
            host = sandbox.get_host(port)
            preview_url = f"https://{host}"
            
            # 更新数据库
            async with AsyncSessionLocal() as session:
                await crud.update_sandbox(
                    session=session,
                    sandbox_id=(await self._get_sandbox_record(conversation_id)).id,
                    stack=stack,
                    preview_url=preview_url
                )
            
            logger.info(f"✅ 项目启动成功: {preview_url}")
            
            return RunResult(
                success=True,
                preview_url=preview_url,
                message=f"项目已启动，访问: {preview_url}"
            )
            
        except Exception as e:
            logger.error(f"❌ 运行项目失败: {e}", exc_info=True)
            return RunResult(
                success=False,
                error=str(e)
            )
    
    async def stop_project(self, conversation_id: str) -> bool:
        """
        停止项目
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            # 杀死常见的服务进程
            await asyncio.to_thread(
                sandbox.commands.run,
                "pkill -f streamlit || pkill -f gradio || pkill -f 'python app.py' || true",
                timeout=30
            )
            
            logger.info(f"⏹️ 项目已停止: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 停止项目失败: {e}", exc_info=True)
            return False
    
    async def get_logs(
        self,
        conversation_id: str,
        lines: int = 100
    ) -> str:
        """
        获取项目日志
        
        Args:
            conversation_id: 对话 ID
            lines: 行数
            
        Returns:
            日志内容
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            result = await asyncio.to_thread(
                sandbox.commands.run,
                f"tail -n {lines} /tmp/app.log 2>/dev/null || echo 'No logs found'",
                timeout=30
            )
            
            return result.stdout
            
        except Exception as e:
            logger.error(f"❌ 获取日志失败: {e}", exc_info=True)
            return f"获取日志失败: {e}"
    
    async def run_command(
        self,
        conversation_id: str,
        command: str,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        在沙盒中执行命令
        
        Args:
            conversation_id: 对话 ID
            command: 命令
            timeout: 超时时间（秒）
            
        Returns:
            执行结果
        """
        sandbox = await self._get_sandbox(conversation_id)
        
        try:
            result = await asyncio.to_thread(
                sandbox.commands.run,
                command,
                timeout=timeout
            )
            
            return {
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
        except Exception as e:
            logger.error(f"❌ 执行命令失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== 辅助方法 ====================
    
    async def _get_sandbox(self, conversation_id: str) -> Any:
        """获取沙盒连接（如果不存在则创建）"""
        if conversation_id not in self._sandbox_pool:
            # 尝试获取或创建
            async with AsyncSessionLocal() as session:
                db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
            
            if not db_sandbox:
                raise SandboxNotFoundError(f"沙盒不存在: {conversation_id}")
            
            if db_sandbox.e2b_sandbox_id:
                try:
                    sandbox = await self._connect_sandbox(db_sandbox.e2b_sandbox_id)
                    self._sandbox_pool[conversation_id] = sandbox
                except Exception as e:
                    raise SandboxConnectionError(f"连接沙盒失败: {e}")
            else:
                raise SandboxNotFoundError(f"沙盒未初始化: {conversation_id}")
        
        return self._sandbox_pool[conversation_id]
    
    async def _get_sandbox_info(self, conversation_id: str) -> Optional[SandboxInfo]:
        """获取沙盒信息"""
        async with AsyncSessionLocal() as session:
            db_sandbox = await crud.get_sandbox_by_conversation(session, conversation_id)
        
        if not db_sandbox:
            return None
        
        return SandboxInfo(
            id=db_sandbox.id,
            conversation_id=db_sandbox.conversation_id,
            user_id=db_sandbox.user_id,
            e2b_sandbox_id=db_sandbox.e2b_sandbox_id,
            status=db_sandbox.status,
            stack=db_sandbox.stack,
            preview_url=db_sandbox.preview_url,
            created_at=db_sandbox.created_at.isoformat() if db_sandbox.created_at else None,
            last_active_at=db_sandbox.last_active_at.isoformat() if db_sandbox.last_active_at else None
        )
    
    async def _get_sandbox_record(self, conversation_id: str):
        """获取数据库记录"""
        async with AsyncSessionLocal() as session:
            return await crud.get_sandbox_by_conversation(session, conversation_id)
    
    async def _update_activity(self, conversation_id: str):
        """更新活跃时间"""
        async with AsyncSessionLocal() as session:
            await crud.update_sandbox_activity(session, conversation_id)
    
    def _get_stack_config(self, stack: str) -> Optional[Dict[str, Any]]:
        """获取技术栈配置"""
        configs = {
            "streamlit": {
                "entry_file": "app.py",
                "port": 8501,
                "start_cmd": "streamlit run {entry} --server.port=8501 --server.address=0.0.0.0",
                "startup_wait": 8
            },
            "gradio": {
                "entry_file": "app.py",
                "port": 7860,
                "start_cmd": "python {entry}",
                "startup_wait": 10
            },
            "python": {
                "entry_file": "main.py",
                "port": 8000,
                "start_cmd": "python {entry}",
                "startup_wait": 5
            },
            "flask": {
                "entry_file": "app.py",
                "port": 5000,
                "start_cmd": "python {entry}",
                "startup_wait": 5
            },
            "fastapi": {
                "entry_file": "main.py",
                "port": 8000,
                "start_cmd": "uvicorn main:app --host 0.0.0.0 --port 8000",
                "startup_wait": 5
            }
        }
        return configs.get(stack)
    
    def _get_stack_port(self, stack: str) -> Optional[int]:
        """获取技术栈端口"""
        config = self._get_stack_config(stack)
        return config["port"] if config else None


# ==================== 便捷函数 ====================

_default_sandbox_service: Optional[SandboxService] = None


def get_sandbox_service() -> SandboxService:
    """
    获取默认的 SandboxService 实例（单例）
    
    Returns:
        SandboxService 实例
    """
    global _default_sandbox_service
    if _default_sandbox_service is None:
        _default_sandbox_service = SandboxService()
    return _default_sandbox_service

