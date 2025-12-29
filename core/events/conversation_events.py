"""
Conversation 级事件管理

职责：管理 Conversation（对话会话）级别的事件
"""

from typing import Dict, Any, Optional
from core.events.base import BaseEventManager


class ConversationEventManager(BaseEventManager):
    """
    Conversation 级事件管理器
    
    负责对话会话相关的事件（plan, title, context）
    """
    
    async def emit_conversation_start(
        self,
        session_id: str,
        conversation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 conversation_start 事件
        
        Args:
            session_id: Session ID
            conversation: Conversation 完整数据
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_start",
            data={
                "conversation_id": conversation.get("id"),
                "title": conversation.get("title", "新对话"),
                "created_at": conversation.get("created_at"),
                "metadata": conversation.get("metadata", {})
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_conversation_delta(
        self,
        session_id: str,
        conversation_id: str,
        delta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 conversation_delta 事件（增量更新）
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            delta: 增量更新数据
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_delta",
            data={
                "conversation_id": conversation_id,
                "delta": delta
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_conversation_plan_created(
        self,
        session_id: str,
        conversation_id: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 conversation_plan_created 事件
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            plan: 执行计划
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_plan_created",
            data={
                "conversation_id": conversation_id,
                "plan": plan
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_conversation_plan_updated(
        self,
        session_id: str,
        conversation_id: str,
        plan_delta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 conversation_plan_updated 事件
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            plan_delta: 执行计划增量更新
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_plan_updated",
            data={
                "conversation_id": conversation_id,
                "plan_delta": plan_delta
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_conversation_context_compressed(
        self,
        session_id: str,
        conversation_id: str,
        context: Dict[str, Any],
        retained_messages: list
    ) -> Dict[str, Any]:
        """
        发送 conversation_context_compressed 事件
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            context: 压缩后的上下文信息
            retained_messages: 保留的消息ID列表
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_context_compressed",
            data={
                "conversation_id": conversation_id,
                "context": context,
                "retained_messages": retained_messages
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_conversation_stop(
        self,
        session_id: str,
        conversation_id: str,
        final_status: str,
        summary: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送 conversation_stop 事件
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            final_status: 最终状态
            summary: 会话摘要
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_stop",
            data={
                "conversation_id": conversation_id,
                "final_status": final_status,
                "summary": summary or {}
            }
        )
        
        return await self._send_event(session_id, event)
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳（ISO格式）"""
        from datetime import datetime
        return datetime.now().isoformat()

