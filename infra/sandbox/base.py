"""
沙盒执行环境抽象基类

设计原则：
1. 抽象接口：定义统一的沙盒操作接口
2. 多实现支持：E2B、Docker、Firecracker 等
3. 生命周期管理：创建、暂停、恢复、销毁
4. 安全隔离：每个会话独立沙盒，多用户安全

使用示例：
    # 获取沙盒实例
    sandbox = get_sandbox_provider()
    
    # 确保沙盒存在
    await sandbox.ensure_sandbox("conv_123", "user_456")
    
    # 执行命令
    result = await sandbox.run_command("conv_123", "pip install pandas")
    
    # 读写文件
    await sandbox.write_file("conv_123", "/app/main.py", "print('hello')")
    content = await sandbox.read_file("conv_123", "/app/main.py")
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class SandboxStatus(str, Enum):
    """沙盒状态"""
    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class SandboxInfo:
    """沙盒信息"""
    id: str
    conversation_id: str
    user_id: str
    provider_sandbox_id: Optional[str] = None  # 外部服务的沙盒 ID（如 E2B sandbox ID）
    status: SandboxStatus = SandboxStatus.CREATING
    stack: Optional[str] = None
    preview_url: Optional[str] = None
    active_project_path: Optional[str] = None  # 当前运行的项目路径
    active_project_stack: Optional[str] = None  # 当前运行的项目技术栈
    created_at: Optional[str] = None
    last_active_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileInfo:
    """文件信息"""
    name: str
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    modified_at: Optional[str] = None
    children: Optional[List["FileInfo"]] = None


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    execution_time: float = 0.0


@dataclass
class CodeResult:
    """代码执行结果（Code Interpreter）"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    execution_time: float = 0.0
    artifacts: List[Dict[str, Any]] = field(default_factory=list)


class SandboxError(Exception):
    """沙盒错误基类"""
    pass


class SandboxNotFoundError(SandboxError):
    """沙盒不存在"""
    pass


class SandboxConnectionError(SandboxError):
    """沙盒连接失败"""
    pass


class SandboxNotAvailableError(SandboxError):
    """沙盒服务不可用"""
    pass


class SandboxProvider(ABC):
    """
    沙盒执行环境抽象基类
    
    定义统一的沙盒操作接口，具体实现可以是 E2B、Docker、Firecracker 等
    每个 conversation 对应一个独立的沙盒实例，确保多用户安全隔离
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名称"""
        pass
    
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """服务是否可用"""
        pass
    
    # ==================== 生命周期管理 ====================
    
    @abstractmethod
    async def ensure_sandbox(
        self,
        conversation_id: str,
        user_id: str,
        stack: Optional[str] = None
    ) -> SandboxInfo:
        """
        确保沙盒存在（获取或创建）
        
        如果沙盒已存在且可用，复用；否则创建新沙盒
        
        Args:
            conversation_id: 对话 ID（沙盒的唯一标识）
            user_id: 用户 ID
            stack: 技术栈（可选，如 python/nodejs/react）
            
        Returns:
            沙盒信息
            
        Raises:
            SandboxNotAvailableError: 沙盒服务不可用
        """
        pass
    
    @abstractmethod
    async def get_sandbox(self, conversation_id: str) -> Optional[SandboxInfo]:
        """
        获取沙盒信息
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            沙盒信息，不存在时返回 None
        """
        pass
    
    @abstractmethod
    async def pause_sandbox(self, conversation_id: str) -> bool:
        """
        暂停沙盒（保留状态，释放计算资源）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        pass
    
    @abstractmethod
    async def resume_sandbox(self, conversation_id: str) -> SandboxInfo:
        """
        恢复沙盒
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            沙盒信息
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
        """
        pass
    
    @abstractmethod
    async def destroy_sandbox(self, conversation_id: str) -> bool:
        """
        销毁沙盒（释放所有资源，无法恢复）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否成功
        """
        pass
    
    # ==================== 命令执行 ====================
    
    @abstractmethod
    async def run_command(
        self,
        conversation_id: str,
        command: str,
        timeout: int = 60,
        cwd: Optional[str] = None
    ) -> CommandResult:
        """
        在沙盒中执行 shell 命令
        
        Args:
            conversation_id: 对话 ID
            command: 要执行的命令
            timeout: 超时时间（秒）
            cwd: 工作目录（可选）
            
        Returns:
            命令执行结果
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
        """
        pass
    
    @abstractmethod
    async def run_code(
        self,
        conversation_id: str,
        code: str,
        language: str = "python",
        timeout: int = 300
    ) -> CodeResult:
        """
        在沙盒中执行代码（Code Interpreter）
        
        Args:
            conversation_id: 对话 ID
            code: 要执行的代码
            language: 编程语言（默认 python）
            timeout: 超时时间（秒）
            
        Returns:
            代码执行结果
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
        """
        pass
    
    # ==================== 文件操作 ====================
    
    @abstractmethod
    async def read_file(
        self,
        conversation_id: str,
        path: str
    ) -> str:
        """
        读取文件内容
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径（沙盒内的绝对路径）
            
        Returns:
            文件内容
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
            FileNotFoundError: 文件不存在
        """
        pass
    
    @abstractmethod
    async def write_file(
        self,
        conversation_id: str,
        path: str,
        content: str
    ) -> bool:
        """
        写入文件内容
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径（沙盒内的绝对路径）
            content: 文件内容
            
        Returns:
            是否成功
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
        """
        pass
    
    @abstractmethod
    async def delete_file(
        self,
        conversation_id: str,
        path: str
    ) -> bool:
        """
        删除文件
        
        Args:
            conversation_id: 对话 ID
            path: 文件路径
            
        Returns:
            是否成功
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
        """
        pass
    
    @abstractmethod
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
            文件列表
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
        """
        pass
    
    @abstractmethod
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
        pass
    
    # ==================== 项目运行 ====================
    
    @abstractmethod
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
            
        Raises:
            SandboxNotFoundError: 沙盒不存在
        """
        pass
    
    @abstractmethod
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
        pass
    
    # ==================== 可选方法（有默认实现） ====================
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态（用于诊断）
        
        Returns:
            连接池状态信息
        """
        return {"provider": self.provider_name, "available": self.is_available}
    
    async def cleanup_pool(self) -> int:
        """
        清理失效的连接池条目
        
        Returns:
            清理的条目数量
        """
        return 0
    
    async def get_sandbox_metrics(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        获取沙盒运行指标
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            指标信息
        """
        return None
    
    async def get_project_logs(
        self,
        conversation_id: str,
        lines: int = 100
    ) -> str:
        """
        获取项目运行日志
        
        Args:
            conversation_id: 对话 ID
            lines: 行数
            
        Returns:
            日志内容
        """
        return "Not implemented"

