"""
Sandbox 服务层 - 沙盒业务封装

职责：
1. 路径标准化（相对路径 -> 绝对路径）
2. 项目运行管理（检测、启动、停止）
3. 流式代码执行输出

设计原则：
- 直接使用 infra/sandbox 层的类型定义（避免重复）
- 只保留业务特有功能
- 连接池由 infra 层统一管理
"""

import asyncio
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass

from logger import get_logger

logger = get_logger("sandbox_service")

# ==================== 直接使用 infra 层类型 ====================
from infra.sandbox import (
    get_sandbox_provider,
    SandboxProvider,
    SandboxInfo as InfraSandboxInfo,
    FileInfo,  # 直接使用，不再重复定义
    CommandResult,  # 直接使用
    CodeResult,  # 直接使用
    SandboxError,
    SandboxNotFoundError as InfraSandboxNotFoundError,
    SandboxConnectionError as InfraSandboxConnectionError,
    SandboxNotAvailableError,
)


# ==================== 服务层特有类型 ====================

@dataclass
class SandboxInfo:
    """
    沙盒信息（服务层视图）
    
    与 infra 层的区别：使用 e2b_sandbox_id 而非 provider_sandbox_id
    """
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
    """项目运行结果"""
    success: bool
    preview_url: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


# ==================== 异常类 ====================

class SandboxServiceError(Exception):
    """沙盒服务异常基类"""
    pass


class SandboxNotFoundError(SandboxServiceError):
    """沙盒不存在"""
    pass


class SandboxConnectionError(SandboxServiceError):
    """沙盒连接失败"""
    pass


# ==================== 类型转换 ====================

def _convert_sandbox_info(info: InfraSandboxInfo) -> SandboxInfo:
    """将 infra 层 SandboxInfo 转换为服务层视图"""
    return SandboxInfo(
        id=info.id,
        conversation_id=info.conversation_id,
        user_id=info.user_id,
        e2b_sandbox_id=info.provider_sandbox_id,
        status=info.status.value if hasattr(info.status, 'value') else str(info.status),
        stack=info.stack,
        preview_url=info.preview_url,
        created_at=info.created_at,
        last_active_at=info.last_active_at
    )


# ==================== SandboxService ====================

class SandboxService:
    """
    沙盒服务（业务层封装）
    
    职责：
    1. 路径标准化：相对路径 -> 绝对路径
    2. 异常转换：infra 层异常 -> 服务层异常
    3. 业务功能：递归目录列表、项目管理、日志获取
    
    注意：
    - 数据类型直接使用 infra/sandbox 层定义（FileInfo, CommandResult, CodeResult）
    - 连接池由 infra 层统一管理，确保 bash 工具和 sandbox_* 工具共享连接
    - 性能优化在 infra 层实现（skip_validation、_with_retry）
    """
    
    # E2B 沙盒的工作目录
    SANDBOX_HOME = "/home/user"
    
    def __init__(self) -> None:
        """初始化沙盒服务"""
        self._provider: Optional[SandboxProvider] = None
        logger.info("✅ SandboxService 初始化完成（使用 infra/sandbox 层）")
    
    @property
    def provider(self) -> SandboxProvider:
        """获取 infra 层的沙盒提供者"""
        if self._provider is None:
            self._provider = get_sandbox_provider()
        return self._provider
    
    # ==================== 生命周期管理 ====================
    
    async def get_or_create_sandbox(
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
            stack: 技术栈（可选）
            
        Returns:
            沙盒信息
        """
        try:
            info = await self.provider.ensure_sandbox(conversation_id, user_id, stack)
            return _convert_sandbox_info(info)
        except SandboxNotAvailableError as e:
            raise SandboxServiceError(f"E2B 沙盒服务不可用: {e}")
        except Exception as e:
            logger.error(f"❌ 获取或创建沙盒失败: {e}", exc_info=True)
            raise SandboxServiceError(f"沙盒操作失败: {e}")
    
    async def pause_sandbox(self, conversation_id: str) -> bool:
        """暂停沙盒"""
        try:
            return await self.provider.pause_sandbox(conversation_id)
        except Exception as e:
            logger.error(f"❌ 暂停沙盒失败: {e}", exc_info=True)
            return False
    
    async def resume_sandbox(self, conversation_id: str) -> SandboxInfo:
        """恢复沙盒"""
        try:
            info = await self.provider.resume_sandbox(conversation_id)
            return _convert_sandbox_info(info)
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except Exception as e:
            logger.error(f"❌ 恢复沙盒失败: {e}", exc_info=True)
            raise SandboxServiceError(f"恢复沙盒失败: {e}")
    
    async def kill_sandbox(self, conversation_id: str) -> bool:
        """终止沙盒"""
        try:
            return await self.provider.destroy_sandbox(conversation_id)
        except Exception as e:
            logger.error(f"❌ 终止沙盒失败: {e}", exc_info=True)
            return False
    
    async def get_sandbox_status(self, conversation_id: str) -> Optional[SandboxInfo]:
        """获取沙盒状态"""
        try:
            info = await self.provider.get_sandbox(conversation_id)
            if info is None:
                return None
            return _convert_sandbox_info(info)
        except Exception as e:
            logger.error(f"❌ 获取沙盒状态失败: {e}", exc_info=True)
            return None
    
    # ==================== 路径处理 ====================
    
    def _normalize_path(self, path: str) -> str:
        """
        标准化路径，确保是绝对路径
        
        支持的输入格式：
        - /home/user/xxx -> /home/user/xxx（已经是绝对路径）
        - home/user/xxx -> /home/user/xxx（URL 传输时去掉了开头的 /）
        - xxx -> /home/user/xxx（相对路径）
        - . 或空 -> /home/user
        """
        if not path or path == ".":
            return self.SANDBOX_HOME
        
        if path.startswith("/"):
            return path
        
        if path.startswith("home/user"):
            return f"/{path}"
        
        return f"{self.SANDBOX_HOME}/{path}".replace("//", "/")
    
    # ==================== 文件操作 ====================
    
    async def list_files(
        self,
        conversation_id: str,
        path: str = "/home/user"
    ) -> List[FileInfo]:
        """列出沙盒目录内容"""
        abs_path = self._normalize_path(path)
        
        try:
            # FileInfo 直接使用 infra 层类型，无需转换
            return await self.provider.list_dir(conversation_id, abs_path)
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except Exception as e:
            logger.error(f"❌ 列出目录失败: {abs_path} - {e}", exc_info=True)
            raise SandboxServiceError(f"列出目录失败: {e}")
    
    async def list_files_tree(
        self,
        conversation_id: str,
        path: str = "/home/user",
        max_depth: int = 5
    ) -> List[FileInfo]:
        """
        递归列出沙盒目录内容（树形结构）
        
        性能优化：使用单次 shell 命令获取整个目录树，
        从 N 次 API 调用优化为 1 次（N = 目录数量）
        """
        abs_path = self._normalize_path(path)
        
        try:
            # 使用 find 命令快速获取目录树
            cmd = f"find {abs_path} -maxdepth {max_depth} -printf '%y|%p\\n' 2>/dev/null || true"
            result = await self.provider.run_command(conversation_id, cmd, timeout=30)
            
            if not result.success or not result.output:
                return await self._list_files_tree_fallback(conversation_id, abs_path, max_depth)
            
            # 解析 find 输出，构建树结构
            lines = result.output.strip().split('\n')
            path_map: dict[str, FileInfo] = {}
            root_files: List[FileInfo] = []
            
            for line in lines:
                if '|' not in line:
                    continue
                file_type, file_path = line.split('|', 1)
                if file_path == abs_path:
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
                
                parent_path = '/'.join(file_path.split('/')[:-1])
                if parent_path == abs_path:
                    root_files.append(info)
                elif parent_path in path_map and path_map[parent_path].children is not None:
                    path_map[parent_path].children.append(info)
            
            return root_files
        except Exception as e:
            logger.warning(f"⚠️ 快速目录树获取失败，降级到普通方法: {e}")
            return await self._list_files_tree_fallback(conversation_id, abs_path, max_depth)
    
    async def _list_files_tree_fallback(
        self,
        conversation_id: str,
        path: str,
        max_depth: int
    ) -> List[FileInfo]:
        """目录树获取的降级方法（并行递归）"""
        if max_depth <= 0:
            return await self.list_files(conversation_id, path)
        
        files = await self.list_files(conversation_id, path)
        directories = [f for f in files if f.type == "directory"]
        
        if not directories:
            return files
        
        # 并行获取所有子目录内容
        async def get_children(dir_info: FileInfo) -> tuple[FileInfo, List[FileInfo]]:
            try:
                children = await self._list_files_tree_fallback(
                    conversation_id,
                    dir_info.path,
                    max_depth - 1
                )
                return (dir_info, children)
            except Exception as e:
                logger.warning(f"⚠️ 获取子目录失败: {dir_info.path}, {e}")
                return (dir_info, [])
        
        results = await asyncio.gather(*[get_children(d) for d in directories])
        
        for dir_info, children in results:
            dir_info.children = children
        
        return files
    
    async def read_file(
        self,
        conversation_id: str,
        path: str
    ) -> str:
        """读取沙盒文件内容"""
        abs_path = self._normalize_path(path)
        
        try:
            return await self.provider.read_file(conversation_id, abs_path)
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"❌ 读取文件失败: {abs_path} - {e}", exc_info=True)
            raise SandboxServiceError(f"读取文件失败: {e}")
    
    async def read_file_bytes(
        self,
        conversation_id: str,
        path: str
    ) -> bytes:
        """读取沙盒文件内容（二进制）"""
        content = await self.read_file(conversation_id, path)
        if isinstance(content, bytes):
            return content
        return content.encode('utf-8')
    
    async def write_file(
        self,
        conversation_id: str,
        path: str,
        content: str | bytes
    ) -> Dict[str, Any]:
        """写入沙盒文件"""
        abs_path = self._normalize_path(path)
        
        # 如果是 bytes，转换为 str
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        try:
            success = await self.provider.write_file(conversation_id, abs_path, content)
            
            if success:
                logger.info(f"✅ 文件已写入: {abs_path}")
            
            return {
                "success": success,
                "path": abs_path,
                "size": len(content) if content else 0
            }
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except Exception as e:
            logger.error(f"❌ 写入文件失败: {abs_path} - {e}", exc_info=True)
            raise SandboxServiceError(f"写入文件失败: {e}")
    
    async def delete_file(
        self,
        conversation_id: str,
        path: str
    ) -> bool:
        """删除沙盒文件"""
        abs_path = self._normalize_path(path)
        
        try:
            success = await self.provider.delete_file(conversation_id, abs_path)
            if success:
                logger.info(f"🗑️ 文件已删除: {abs_path}")
            return success
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except Exception as e:
            logger.error(f"❌ 删除文件失败: {abs_path} - {e}", exc_info=True)
            raise SandboxServiceError(f"删除文件失败: {e}")
    
    async def file_exists(
        self,
        conversation_id: str,
        path: str
    ) -> bool:
        """检查文件是否存在"""
        abs_path = self._normalize_path(path)
        
        try:
            return await self.provider.file_exists(conversation_id, abs_path)
        except Exception as e:
            logger.error(f"❌ 检查文件失败: {abs_path} - {e}", exc_info=True)
            return False
    
    # ==================== 项目运行 ====================
    
    async def run_project(
        self,
        conversation_id: str,
        project_path: str,
        stack: str
    ) -> RunResult:
        """运行项目"""
        try:
            preview_url = await self.provider.run_project(
                conversation_id, project_path, stack
            )
            
            if preview_url:
                logger.info(f"✅ 项目启动成功: {preview_url}")
                return RunResult(
                    success=True,
                    preview_url=preview_url,
                    message=f"项目已启动，访问: {preview_url}"
                )
            else:
                return RunResult(
                    success=False,
                    error="项目启动失败"
                )
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except Exception as e:
            logger.error(f"❌ 运行项目失败: {e}", exc_info=True)
            return RunResult(
                success=False,
                error=str(e)
            )
    
    async def stop_project(self, conversation_id: str) -> bool:
        """停止项目"""
        try:
            # 通过 run_command 杀死进程
            result = await self.run_command(
                conversation_id,
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
        """获取项目日志"""
        try:
            result = await self.run_command(
                conversation_id,
                f"tail -n {lines} /tmp/app.log 2>/dev/null || echo 'No logs found'",
                timeout=30
            )
            return result.get("stdout", "")
        except Exception as e:
            logger.error(f"❌ 获取日志失败: {e}", exc_info=True)
            return f"获取日志失败: {e}"
    
    # ==================== 命令执行 ====================
    
    async def run_command(
        self,
        conversation_id: str,
        command: str,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """在沙盒中执行命令"""
        try:
            result = await self.provider.run_command(
                conversation_id, command, timeout
            )
            
            return {
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.output,
                "stderr": result.error or ""
            }
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except Exception as e:
            logger.error(f"❌ 执行命令失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== 代码执行 ====================
    
    async def run_code(
        self,
        conversation_id: str,
        code: str,
        timeout: int = 300,
        on_stdout: Optional[Callable[[str], None]] = None,
        on_stderr: Optional[Callable[[str], None]] = None
    ) -> CodeResult:
        """
        执行 Python 代码（Code Interpreter）
        
        注意：流式回调在 infra 层不直接支持，此处简化处理
        """
        try:
            result = await self.provider.run_code(
                conversation_id, code, "python", timeout
            )
            
            # 如果有回调，在返回前调用
            if on_stdout and result.stdout:
                for line in result.stdout.split('\n'):
                    on_stdout(line)
            if on_stderr and result.stderr:
                for line in result.stderr.split('\n'):
                    on_stderr(line)
            
            # CodeResult 直接使用 infra 层类型，无需转换
            return result
            
        except InfraSandboxNotFoundError as e:
            raise SandboxNotFoundError(str(e))
        except Exception as e:
            logger.error(f"❌ 代码执行失败: {e}", exc_info=True)
            return CodeResult(
                success=False,
                error=str(e)
            )
    


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
