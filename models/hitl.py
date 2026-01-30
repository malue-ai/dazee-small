"""
HITL (Human-in-the-Loop) 数据模型

包含确认请求的数据类型定义：
- ConfirmationType: 确认类型枚举
- ConfirmationRequest: 确认请求数据类
"""

import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ConfirmationType(Enum):
    """
    确认类型枚举
    
    统一使用 FORM 表单模式，通过 questions 数组支持：
    - single_choice: 单选（包括 yes/no，options 文本可自定义）
    - multiple_choice: 多选
    - text_input: 文本输入
    """
    FORM = "form"  # 表单模式（唯一类型）


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
            timeout: 超时时间（秒），None 表示无限等待
            
        Returns:
            用户响应
            
        Raises:
            asyncio.TimeoutError: 超时（仅当 timeout > 0 时）
        """
        if timeout is None or timeout <= 0:
            # 🆕 无限等待模式（暂时禁用超时）
            await self.event.wait()
        else:
            await asyncio.wait_for(self.event.wait(), timeout=timeout)
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
