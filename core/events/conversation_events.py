"""
Conversation 级事件管理 - ConversationEventManager

事件类型（只有 3 个）：
- conversation_start : 对话开始
- conversation_delta : 对话增量更新
- conversation_stop  : 对话结束

conversation_delta 统一结构：

支持的 type：
- title      : 标题更新 {"title": "新标题"}
- metadata   : 元数据   {"metadata": {...}}
- compressed : 压缩通知 {"compressed": {...}}

注意：快捷方法在 broadcaster 中，这里只提供核心 3 个事件
"""

from typing import Dict, Any, Optional
from datetime import datetime
from core.events.base import BaseEventManager


class ConversationEventManager(BaseEventManager):
    """
    Conversation 级事件管理器
    
    核心 3 个事件：start / delta / stop
    快捷方法（emit_title_update, emit_plan_update 等）在 broadcaster 中
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
                "updated_at": conversation.get("updated_at"),
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
        发送 conversation_delta 事件
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            delta: 增量更新数据，直接用字段名作为 key
            
        Returns:
            事件对象
            
        事件结构：
            {
                "type": "conversation_delta",
                "data": {
                    "title": "新标题"          # 直接字段名
                }
            }
            
        Examples:
            delta = {"title": "新标题"}
            delta = {"metadata": {"tags": [...]}}
            delta = {"compressed": {"summary": "..."}}
        """
        data = {
            "conversation_id": conversation_id,
            **delta  # 直接展开：title / metadata / compressed
        }
        
        event = self._create_event(
            event_type="conversation_delta",
            data=data
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
            final_status: 最终状态（completed/stopped/failed）
            summary: 会话摘要（可选）
            
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
