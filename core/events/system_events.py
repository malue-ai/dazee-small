"""
System 级事件管理 - SystemEventManager

事件类型：
- error       : 错误事件
- done        : 流结束标记（最后一个事件）
- emit_custom : 自定义事件（用于扩展）

错误类型枚举：
- network_error    : 网络错误
- timeout_error    : 超时错误
- overloaded_error : 服务过载
- internal_error   : 内部错误
- validation_error : 参数验证错误
"""

from typing import Dict, Any
from core.events.base import BaseEventManager


class SystemEventManager(BaseEventManager):
    """
    System 级事件管理器
    
    负责系统相关的事件
    """
    
    async def emit_error(
        self,
        session_id: str,
        error_type: str,
        error_message: str,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        发送 error 事件
        
        Args:
            session_id: Session ID
            error_type: 错误类型
            error_message: 错误消息
            details: 额外的错误详情（可选）
            
        Returns:
            事件对象
        """
        error_data = {
            "type": error_type,
            "message": error_message
        }
        
        # 添加额外的详情
        if details:
            error_data.update(details)
        
        event = self._create_event(
            event_type="error",
            data={"error": error_data}
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_done(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        发送 done 事件（流结束）
        
        Args:
            session_id: Session ID
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="done",
            data={"type": "done"}
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_custom(
        self,
        session_id: str,
        event_type: str,
        event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送自定义事件
        
        Args:
            session_id: Session ID
            event_type: 事件类型
            event_data: 事件数据
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type=event_type,
            data=event_data
        )
        
        return await self._send_event(session_id, event)

