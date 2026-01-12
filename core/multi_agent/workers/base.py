"""
Worker 基类 - Multi-Agent Worker 抽象层

支持多种 Worker 实现形态：
1. AgentWorker: 内置 SimpleAgent 实例
2. MCPWorker: 通过 MCP 协议调用远程服务
3. WorkflowWorker: 调用 Coze/Dify 等平台的 Workflow
4. HTTPWorker: 通用 HTTP API 调用

设计原则：
- Orchestrator 不关心 Worker 的具体实现
- 统一的 execute() 接口
- 支持同步和异步执行
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncGenerator

logger = logging.getLogger(__name__)


class WorkerType(Enum):
    """Worker 类型枚举"""
    AGENT = "agent"           # 内置 SimpleAgent
    MCP = "mcp"               # MCP Server
    WORKFLOW = "workflow"     # Coze/Dify Workflow
    HTTP = "http"             # 通用 HTTP API


class WorkerStatus(Enum):
    """Worker 状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class WorkerInput:
    """Worker 输入"""
    task_id: str
    action: str  # 任务描述
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文信息
    dependencies_results: Dict[str, Any] = field(default_factory=dict)  # 依赖任务的结果
    timeout: int = 300  # 超时时间（秒）


@dataclass
class WorkerOutput:
    """Worker 输出"""
    task_id: str
    status: WorkerStatus
    result: Any = None
    error: Optional[str] = None
    artifacts: List[Dict] = field(default_factory=list)  # 产出物
    duration: float = 0.0  # 执行耗时（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据


class BaseWorker(ABC):
    """
    Worker 基类
    
    所有 Worker 实现必须继承此类，并实现 execute() 方法
    """
    
    def __init__(
        self,
        name: str,
        worker_type: WorkerType,
        specialization: str = "general",
        config: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.worker_type = worker_type
        self.specialization = specialization
        self.config = config or {}
        self.status = WorkerStatus.IDLE
        self.created_at = datetime.now()
        
        logger.info(f"Worker 初始化: {name} (类型: {worker_type.value}, 专业: {specialization})")
    
    @abstractmethod
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        执行任务（抽象方法，子类必须实现）
        
        Args:
            input: 任务输入
            
        Returns:
            WorkerOutput: 任务输出
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查（抽象方法）
        
        Returns:
            bool: 是否健康
        """
        pass
    
    async def execute_with_timeout(self, input: WorkerInput) -> WorkerOutput:
        """
        带超时的执行
        """
        try:
            self.status = WorkerStatus.RUNNING
            start_time = datetime.now()
            
            result = await asyncio.wait_for(
                self.execute(input),
                timeout=input.timeout
            )
            
            result.duration = (datetime.now() - start_time).total_seconds()
            self.status = result.status
            return result
            
        except asyncio.TimeoutError:
            self.status = WorkerStatus.TIMEOUT
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.TIMEOUT,
                error=f"Worker 执行超时 ({input.timeout}秒)",
                duration=input.timeout
            )
        except Exception as e:
            self.status = WorkerStatus.FAILED
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=(datetime.now() - start_time).total_seconds()
            )
    
    def get_info(self) -> Dict[str, Any]:
        """获取 Worker 信息"""
        return {
            "name": self.name,
            "type": self.worker_type.value,
            "specialization": self.specialization,
            "status": self.status.value,
            "created_at": self.created_at.isoformat()
        }
