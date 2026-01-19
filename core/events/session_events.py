"""
Session 级事件管理 - SessionEventManager

事件类型：
- session_start   : 会话开始（首个事件）
- session_stopped : 用户主动停止
- session_end     : 会话结束（正常/失败/取消）
- ping            : 心跳保活
"""

from typing import Dict, Any, Optional
from datetime import datetime
from core.events.base import BaseEventManager


class SessionEventManager(BaseEventManager):
    """
    Session 级事件管理器
    
    负责 Session 生命周期相关的事件
    """
    
    async def emit_session_start(
        self,
        session_id: str,
        user_id: str,
        conversation_id: str,
        output_format: str = "zenflux",
        adapter: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送 session_start 事件
        
        Args:
            session_id: Session ID
            user_id: 用户ID
            conversation_id: 对话ID
            output_format: 输出格式（zenflux/zeno），默认 zenflux
            adapter: 格式转换适配器（可选）
            
        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="session_start",
            data={
                "session_id": session_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return await self._send_event(
            session_id, event,
            output_format=output_format, adapter=adapter
        )
    
    async def emit_session_stopped(
        self,
        session_id: str,
        reason: str = "user_requested",
        output_format: str = "zenflux",
        adapter: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送 session_stopped 事件（用户主动停止）
        
        Args:
            session_id: Session ID
            reason: 停止原因（user_requested/timeout/error）
            output_format: 输出格式（zenflux/zeno），默认 zenflux
            adapter: 格式转换适配器（可选）
            
        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="session_stopped",
            data={
                "session_id": session_id,
                "reason": reason,
                "stopped_at": datetime.now().isoformat()
            }
        )
        
        return await self._send_event(
            session_id, event,
            output_format=output_format, adapter=adapter
        )
    
    async def emit_session_end(
        self,
        session_id: str,
        status: str,
        duration_ms: int,
        output_format: str = "zenflux",
        adapter: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送 session_end 事件
        
        Args:
            session_id: Session ID
            status: 会话状态（completed/failed/cancelled）
            duration_ms: 会话持续时间（毫秒）
            output_format: 输出格式（zenflux/zeno），默认 zenflux
            adapter: 格式转换适配器（可选）
            
        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="session_end",
            data={
                "session_id": session_id,
                "status": status,
                "duration_ms": duration_ms
            }
        )
        
        return await self._send_event(
            session_id, event,
            output_format=output_format, adapter=adapter
        )
    
    async def emit_heartbeat(
        self,
        session_id: str,
        output_format: str = "zenflux",
        adapter: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        发送心跳事件
        
        Args:
            session_id: Session ID
            output_format: 输出格式（zenflux/zeno），默认 zenflux
            adapter: 格式转换适配器（可选）
            
        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="ping",
            data={"type": "ping"}
        )
        
        return await self._send_event(
            session_id, event,
            output_format=output_format, adapter=adapter
        )

