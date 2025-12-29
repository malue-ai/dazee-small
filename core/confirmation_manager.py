"""
确认请求管理器 (ConfirmationManager)

管理 HITL (Human-in-the-Loop) 确认请求的全局单例。

核心机制：
1. 使用 asyncio.Event 实现异步等待（阻塞工具，不阻塞事件循环）
2. 全局单例模式，支持跨请求共享
3. 超时保护，避免无限等待
4. 定期清理过期请求

工作流程：
1. Agent 调用 HITL 工具 → 创建 ConfirmationRequest
2. 工具通过回调发送 SSE 事件 → 前端显示确认框
3. 工具调用 wait_for_response() → 异步等待
4. 用户点击确认 → HTTP POST 提交响应
5. HTTP 接口调用 set_response() → 唤醒等待的工具
6. 工具返回结果 → Agent 继续执行

参考文档: docs/HITL-SSE-CONFIRMATION-DESIGN.md
"""

import uuid
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ConfirmationType(Enum):
    """确认类型枚举"""
    YES_NO = "yes_no"           # 是/否确认
    SINGLE_CHOICE = "single_choice"   # 单选题
    MULTIPLE_CHOICE = "multiple_choice"  # 多选题
    TEXT_INPUT = "text_input"      # 文本输入


@dataclass
class ConfirmationRequest:
    """
    确认请求数据类
    
    核心字段：
    - request_id: 唯一标识符
    - event: asyncio.Event，用于异步等待
    - response: 用户响应
    """
    request_id: str
    question: str
    options: List[str]
    timeout: int
    confirmation_type: ConfirmationType
    metadata: Dict[str, Any]
    session_id: str  # 关联的会话ID
    created_at: datetime
    
    # 🔥 核心：asyncio.Event 用于异步等待
    event: asyncio.Event = field(default_factory=asyncio.Event)
    response: Optional[str] = None
    response_metadata: Optional[Dict[str, Any]] = None
    
    def is_expired(self) -> bool:
        """检查请求是否已过期"""
        return datetime.now() > self.created_at + timedelta(seconds=self.timeout)
    
    async def wait(self, timeout: Optional[float] = None) -> str:
        """
        等待用户响应
        
        Args:
            timeout: 超时时间（秒），None 使用默认超时
            
        Returns:
            用户响应
            
        Raises:
            asyncio.TimeoutError: 超时
        """
        wait_timeout = timeout or self.timeout
        await asyncio.wait_for(self.event.wait(), timeout=wait_timeout)
        return self.response
    
    def set_response(self, response: str, metadata: Optional[Dict[str, Any]] = None):
        """
        设置用户响应并唤醒等待的协程
        
        Args:
            response: 用户响应
            metadata: 额外元数据
        """
        self.response = response
        self.response_metadata = metadata or {}
        self.event.set()  # 🔥 唤醒等待的协程
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 SSE 事件）"""
        return {
            "request_id": self.request_id,
            "question": self.question,
            "options": self.options,
            "timeout": self.timeout,
            "type": self.confirmation_type.value,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat()
        }


class ConfirmationManager:
    """
    确认请求管理器（全局单例）
    
    职责：
    1. 管理所有待处理的确认请求
    2. 提供创建、等待、响应、清理等 API
    3. 跨请求共享（FastAPI 和 Agent 在同一事件循环中）
    
    使用示例：
        manager = get_confirmation_manager()
        
        # 创建请求
        request = manager.create_request(
            question="是否删除文件？",
            options=["confirm", "cancel"],
            session_id="session-123"
        )
        
        # 异步等待响应
        response = await manager.wait_for_response(request.request_id)
        
        # HTTP 接口设置响应
        manager.set_response(request.request_id, "confirm")
    """
    
    _instance: Optional['ConfirmationManager'] = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化管理器"""
        if self._initialized:
            return
        
        self._pending_requests: Dict[str, ConfirmationRequest] = {}
        self._history: List[Dict[str, Any]] = []  # 历史记录
        self._initialized = True
        
        logger.info("ConfirmationManager 初始化完成")
    
    def create_request(
        self,
        question: str,
        options: Optional[List[str]] = None,
        timeout: int = 60,
        confirmation_type: ConfirmationType = ConfirmationType.YES_NO,
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConfirmationRequest:
        """
        创建确认请求
        
        Args:
            question: 要询问用户的问题
            options: 可选项列表，默认 ["confirm", "cancel"]
            timeout: 超时时间（秒），默认 60
            confirmation_type: 确认类型
            session_id: 关联的会话ID
            metadata: 额外元数据
            
        Returns:
            创建的确认请求
        """
        request_id = str(uuid.uuid4())
        
        # 默认选项
        if options is None:
            options = ["confirm", "cancel"]
        
        request = ConfirmationRequest(
            request_id=request_id,
            question=question,
            options=options,
            timeout=timeout,
            confirmation_type=confirmation_type,
            metadata=metadata or {},
            session_id=session_id,
            created_at=datetime.now()
        )
        
        self._pending_requests[request_id] = request
        
        logger.info(f"创建确认请求: request_id={request_id}, question={question[:50]}...")
        
        return request
    
    async def wait_for_response(
        self,
        request_id: str,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        等待用户响应
        
        Args:
            request_id: 请求ID
            timeout: 超时时间（秒），None 使用请求的默认超时
            
        Returns:
            {
                "success": bool,
                "response": str,
                "metadata": dict,
                "timed_out": bool
            }
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return {
                "success": False,
                "error": f"请求 {request_id} 不存在",
                "response": None,
                "timed_out": False
            }
        
        try:
            response = await request.wait(timeout)
            
            # 记录历史
            self._log_history(request, response, timed_out=False)
            
            # 清理请求
            self._cleanup_request(request_id)
            
            return {
                "success": True,
                "response": response,
                "metadata": request.response_metadata or {},
                "timed_out": False
            }
        
        except asyncio.TimeoutError:
            logger.warning(f"确认请求超时: request_id={request_id}")
            
            # 记录历史
            self._log_history(request, "timeout", timed_out=True)
            
            # 清理请求
            self._cleanup_request(request_id)
            
            return {
                "success": False,
                "response": "timeout",
                "metadata": {},
                "timed_out": True,
                "message": f"用户未在 {request.timeout} 秒内响应"
            }
    
    def set_response(
        self,
        request_id: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        设置用户响应（由 HTTP 接口调用）
        
        Args:
            request_id: 请求ID
            response: 用户响应
            metadata: 额外元数据
            
        Returns:
            是否成功
        """
        request = self._pending_requests.get(request_id)
        if not request:
            logger.warning(f"设置响应失败: 请求 {request_id} 不存在")
            return False
        
        if request.is_expired():
            logger.warning(f"设置响应失败: 请求 {request_id} 已过期")
            self._cleanup_request(request_id)
            return False
        
        # 🔥 设置响应并唤醒等待的协程
        request.set_response(response, metadata)
        
        logger.info(f"确认响应已设置: request_id={request_id}, response={response}")
        
        return True
    
    def get_request(self, request_id: str) -> Optional[ConfirmationRequest]:
        """
        获取确认请求
        
        Args:
            request_id: 请求ID
            
        Returns:
            确认请求，不存在返回 None
        """
        return self._pending_requests.get(request_id)
    
    def get_pending_requests(self, session_id: Optional[str] = None) -> List[ConfirmationRequest]:
        """
        获取待处理的确认请求
        
        Args:
            session_id: 可选，按会话ID过滤
            
        Returns:
            待处理请求列表
        """
        requests = list(self._pending_requests.values())
        
        if session_id:
            requests = [r for r in requests if r.session_id == session_id]
        
        return requests
    
    def cancel_request(self, request_id: str) -> bool:
        """
        取消确认请求
        
        Args:
            request_id: 请求ID
            
        Returns:
            是否成功
        """
        request = self._pending_requests.get(request_id)
        if not request:
            return False
        
        # 设置取消响应
        request.set_response("cancelled")
        
        # 清理
        self._cleanup_request(request_id)
        
        logger.info(f"确认请求已取消: request_id={request_id}")
        
        return True
    
    def cleanup_expired(self) -> int:
        """
        清理过期请求
        
        Returns:
            清理的请求数量
        """
        expired_ids = [
            request_id
            for request_id, request in self._pending_requests.items()
            if request.is_expired()
        ]
        
        for request_id in expired_ids:
            request = self._pending_requests[request_id]
            request.set_response("timeout")
            self._cleanup_request(request_id)
        
        if expired_ids:
            logger.info(f"清理过期请求: {len(expired_ids)} 个")
        
        return len(expired_ids)
    
    def _cleanup_request(self, request_id: str):
        """清理单个请求"""
        if request_id in self._pending_requests:
            del self._pending_requests[request_id]
    
    def _log_history(self, request: ConfirmationRequest, response: str, timed_out: bool):
        """记录历史"""
        self._history.append({
            "request_id": request.request_id,
            "question": request.question,
            "options": request.options,
            "response": response,
            "timed_out": timed_out,
            "session_id": request.session_id,
            "created_at": request.created_at.isoformat(),
            "responded_at": datetime.now().isoformat()
        })
        
        # 保留最近 100 条历史
        if len(self._history) > 100:
            self._history = self._history[-100:]
    
    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取历史记录"""
        return self._history[-limit:]
    
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "pending_count": len(self._pending_requests),
            "history_count": len(self._history),
            "pending_sessions": list(set(
                r.session_id for r in self._pending_requests.values()
            ))
        }


# ==================== 全局单例访问 ====================

_manager: Optional[ConfirmationManager] = None


def get_confirmation_manager() -> ConfirmationManager:
    """
    获取全局 ConfirmationManager 实例
    
    Returns:
        ConfirmationManager 单例
    """
    global _manager
    if _manager is None:
        _manager = ConfirmationManager()
    return _manager


def reset_confirmation_manager():
    """
    重置全局实例（用于测试）
    """
    global _manager
    _manager = None
    ConfirmationManager._instance = None

