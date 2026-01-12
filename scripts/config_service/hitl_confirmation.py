"""
HITL 确认流程

面向运营的人机协同确认机制

设计原则：
- 异步确认，不阻塞线上服务
- 支持确认、修改、迭代
- 确认结果持久化
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Awaitable
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logger import get_logger

logger = get_logger("hitl_confirmation")


class ConfirmationStatus(str, Enum):
    """确认状态"""
    PENDING = "pending"           # 等待确认
    CONFIRMED = "confirmed"       # 已确认
    MODIFIED = "modified"         # 已修改确认
    REJECTED = "rejected"         # 已拒绝
    EXPIRED = "expired"           # 已过期
    ITERATING = "iterating"       # 迭代优化中


class ConfirmationType(str, Enum):
    """确认类型"""
    WORKER_PROMPT = "worker_prompt"   # Worker 系统提示词
    TASK_PLAN = "task_plan"           # 任务计划
    TOOL_CONFIG = "tool_config"       # 工具配置


@dataclass
class ConfirmationRequest:
    """确认请求"""
    request_id: str
    confirmation_type: ConfirmationType
    instance_name: str
    content: Dict[str, Any]           # 待确认的内容
    reasoning: str                     # AI 生成推理
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    
    # 确认信息
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    confirmation_comment: str = ""
    
    # 修改信息
    modifications: List[Dict] = field(default_factory=list)
    iteration_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "request_id": self.request_id,
            "confirmation_type": self.confirmation_type.value,
            "instance_name": self.instance_name,
            "content": self.content,
            "reasoning": self.reasoning,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "confirmed_by": self.confirmed_by,
            "confirmation_comment": self.confirmation_comment,
            "modifications": self.modifications,
            "iteration_count": self.iteration_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ConfirmationRequest":
        return cls(
            request_id=data["request_id"],
            confirmation_type=ConfirmationType(data["confirmation_type"]),
            instance_name=data["instance_name"],
            content=data["content"],
            reasoning=data.get("reasoning", ""),
            status=ConfirmationStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            created_by=data.get("created_by", "system"),
            confirmed_at=datetime.fromisoformat(data["confirmed_at"]) if data.get("confirmed_at") else None,
            confirmed_by=data.get("confirmed_by"),
            confirmation_comment=data.get("confirmation_comment", ""),
            modifications=data.get("modifications", []),
            iteration_count=data.get("iteration_count", 0)
        )


@dataclass
class ConfirmationResponse:
    """确认响应"""
    request_id: str
    action: str                        # confirm | modify | reject | iterate
    operator: str                      # 操作人
    comment: str = ""
    modifications: Dict[str, Any] = None  # 修改内容
    feedback: str = ""                 # 迭代反馈
    
    def to_dict(self) -> Dict:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "operator": self.operator,
            "comment": self.comment,
            "modifications": self.modifications,
            "feedback": self.feedback
        }


class HITLConfirmation:
    """
    HITL 确认管理器
    
    管理面向运营的人机协同确认流程
    
    使用示例：
        hitl = HITLConfirmation(storage_dir="./confirmations")
        
        # 创建确认请求
        request = await hitl.create_request(
            confirmation_type=ConfirmationType.WORKER_PROMPT,
            instance_name="test_agent",
            content={"system_prompt": "..."},
            reasoning="AI 生成的提示词..."
        )
        
        # 等待确认（异步）
        result = await hitl.wait_for_confirmation(request.request_id)
        
        # 或者运营直接响应
        await hitl.respond(ConfirmationResponse(
            request_id=request.request_id,
            action="confirm",
            operator="admin"
        ))
    """
    
    def __init__(
        self,
        storage_dir: str = None,
        on_optimize: Callable[[str, str], Awaitable[str]] = None,
        auto_confirm_timeout: int = 0  # 秒，0 表示永不自动确认
    ):
        """
        初始化 HITL 管理器
        
        Args:
            storage_dir: 存储目录
            on_optimize: 优化回调（用于迭代）
            auto_confirm_timeout: 自动确认超时时间
        """
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.on_optimize = on_optimize
        self.auto_confirm_timeout = auto_confirm_timeout
        
        # 内存存储
        self._requests: Dict[str, ConfirmationRequest] = {}
        
        # 等待队列
        self._wait_events: Dict[str, asyncio.Event] = {}
        
        # 确保存储目录存在
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("HITLConfirmation 初始化完成")
    
    async def create_request(
        self,
        confirmation_type: ConfirmationType,
        instance_name: str,
        content: Dict[str, Any],
        reasoning: str = "",
        created_by: str = "system"
    ) -> ConfirmationRequest:
        """
        创建确认请求
        
        Args:
            confirmation_type: 确认类型
            instance_name: 实例名称
            content: 待确认内容
            reasoning: AI 推理过程
            created_by: 创建者
            
        Returns:
            ConfirmationRequest
        """
        request_id = f"confirm-{uuid.uuid4().hex[:8]}"
        
        request = ConfirmationRequest(
            request_id=request_id,
            confirmation_type=confirmation_type,
            instance_name=instance_name,
            content=content,
            reasoning=reasoning,
            status=ConfirmationStatus.PENDING,
            created_by=created_by
        )
        
        # 存储
        self._requests[request_id] = request
        self._wait_events[request_id] = asyncio.Event()
        
        # 持久化
        await self._save_request(request)
        
        logger.info(
            f"创建确认请求: request_id={request_id}, "
            f"type={confirmation_type.value}, "
            f"instance={instance_name}"
        )
        
        return request
    
    async def respond(self, response: ConfirmationResponse) -> ConfirmationRequest:
        """
        响应确认请求
        
        Args:
            response: 确认响应
            
        Returns:
            更新后的 ConfirmationRequest
        """
        request = self._requests.get(response.request_id)
        if not request:
            raise ValueError(f"确认请求不存在: {response.request_id}")
        
        logger.info(
            f"收到确认响应: request_id={response.request_id}, "
            f"action={response.action}, "
            f"operator={response.operator}"
        )
        
        if response.action == "confirm":
            # 直接确认
            request.status = ConfirmationStatus.CONFIRMED
            request.confirmed_at = datetime.now()
            request.confirmed_by = response.operator
            request.confirmation_comment = response.comment
            
        elif response.action == "modify":
            # 修改后确认
            request.status = ConfirmationStatus.MODIFIED
            request.confirmed_at = datetime.now()
            request.confirmed_by = response.operator
            request.confirmation_comment = response.comment
            
            # 记录修改
            if response.modifications:
                request.modifications.append({
                    "timestamp": datetime.now().isoformat(),
                    "operator": response.operator,
                    "changes": response.modifications
                })
                
                # 应用修改到 content
                request.content.update(response.modifications)
            
        elif response.action == "reject":
            # 拒绝
            request.status = ConfirmationStatus.REJECTED
            request.confirmed_at = datetime.now()
            request.confirmed_by = response.operator
            request.confirmation_comment = response.comment
            
        elif response.action == "iterate":
            # 迭代优化
            request.status = ConfirmationStatus.ITERATING
            request.iteration_count += 1
            
            # 调用优化回调
            if self.on_optimize and response.feedback:
                optimized = await self.on_optimize(
                    request.content.get("system_prompt", ""),
                    response.feedback
                )
                request.content["system_prompt"] = optimized
                
                # 记录迭代
                request.modifications.append({
                    "timestamp": datetime.now().isoformat(),
                    "operator": response.operator,
                    "type": "iteration",
                    "feedback": response.feedback
                })
            
            # 迭代后仍需确认
            request.status = ConfirmationStatus.PENDING
        
        # 持久化
        await self._save_request(request)
        
        # 通知等待者
        event = self._wait_events.get(response.request_id)
        if event and request.status in {
            ConfirmationStatus.CONFIRMED,
            ConfirmationStatus.MODIFIED,
            ConfirmationStatus.REJECTED
        }:
            event.set()
        
        return request
    
    async def wait_for_confirmation(
        self,
        request_id: str,
        timeout: int = None
    ) -> ConfirmationRequest:
        """
        等待确认完成
        
        Args:
            request_id: 请求 ID
            timeout: 超时时间（秒）
            
        Returns:
            确认后的 ConfirmationRequest
        """
        request = self._requests.get(request_id)
        if not request:
            raise ValueError(f"确认请求不存在: {request_id}")
        
        # 已经完成
        if request.status in {
            ConfirmationStatus.CONFIRMED,
            ConfirmationStatus.MODIFIED,
            ConfirmationStatus.REJECTED
        }:
            return request
        
        # 等待
        event = self._wait_events.get(request_id)
        if not event:
            event = asyncio.Event()
            self._wait_events[request_id] = event
        
        timeout = timeout or self.auto_confirm_timeout
        
        try:
            if timeout > 0:
                await asyncio.wait_for(event.wait(), timeout=timeout)
            else:
                await event.wait()
        except asyncio.TimeoutError:
            # 超时自动确认
            request.status = ConfirmationStatus.CONFIRMED
            request.confirmed_at = datetime.now()
            request.confirmed_by = "auto"
            request.confirmation_comment = f"自动确认（超时 {timeout} 秒）"
            await self._save_request(request)
        
        return self._requests[request_id]
    
    def get_request(self, request_id: str) -> Optional[ConfirmationRequest]:
        """获取确认请求"""
        return self._requests.get(request_id)
    
    def get_pending_requests(
        self,
        instance_name: str = None,
        confirmation_type: ConfirmationType = None
    ) -> List[ConfirmationRequest]:
        """
        获取待处理的确认请求
        
        Args:
            instance_name: 筛选实例名
            confirmation_type: 筛选类型
        """
        requests = [
            r for r in self._requests.values()
            if r.status == ConfirmationStatus.PENDING
        ]
        
        if instance_name:
            requests = [r for r in requests if r.instance_name == instance_name]
        
        if confirmation_type:
            requests = [r for r in requests if r.confirmation_type == confirmation_type]
        
        return requests
    
    async def _save_request(self, request: ConfirmationRequest):
        """持久化请求"""
        if not self.storage_dir:
            return
        
        file_path = self.storage_dir / f"{request.request_id}.json"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(request.to_dict(), f, ensure_ascii=False, indent=2)
    
    async def load_requests(self):
        """从存储加载请求"""
        if not self.storage_dir or not self.storage_dir.exists():
            return
        
        for file_path in self.storage_dir.glob("confirm-*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    request = ConfirmationRequest.from_dict(data)
                    self._requests[request.request_id] = request
            except Exception as e:
                logger.warning(f"加载确认请求失败: {file_path} - {e}")
        
        logger.info(f"加载 {len(self._requests)} 个确认请求")
