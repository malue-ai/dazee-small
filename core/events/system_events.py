"""
系统级事件管理

职责：管理系统级别的事件（错误、心跳、完成）
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
        error_message: str
    ) -> Dict[str, Any]:
        """
        发送 error 事件
        
        Args:
            session_id: Session ID
            error_type: 错误类型
            error_message: 错误消息
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="error",
            data={
                "error": {
                    "type": error_type,
                    "message": error_message
                }
            }
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
    
    async def emit_agent_status(
        self,
        session_id: str,
        status: str,
        message: str
    ) -> Dict[str, Any]:
        """
        发送 agent_status 事件
        
        Args:
            session_id: Session ID
            status: Agent 状态
            message: 状态描述
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="agent_status",
            data={
                "status": status,
                "message": message
            }
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

