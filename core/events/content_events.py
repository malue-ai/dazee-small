"""
Content 级事件管理

职责：管理 Content Block（内容块）级别的事件
"""

from typing import Dict, Any
from core.events.base import BaseEventManager


class ContentEventManager(BaseEventManager):
    """
    Content 级事件管理器
    
    负责内容块相关的事件（thinking, text, tool_use）
    """
    
    async def emit_content_start(
        self,
        session_id: str,
        index: int,
        block_type: str
    ) -> Dict[str, Any]:
        """
        发送 content_start 事件
        
        Args:
            session_id: Session ID
            index: 内容块索引
            block_type: 内容块类型（thinking/text/tool_use）
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="content_start",
            data={
                "index": index,
                "type": block_type
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_content_delta(
        self,
        session_id: str,
        index: int,
        delta_type: str,
        delta_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 content_delta 事件
        
        Args:
            session_id: Session ID
            index: 内容块索引
            delta_type: Delta 类型（thinking/text/tool_input）
            delta_data: Delta 数据（包含 text 或其他字段）
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="content_delta",
            data={
                "index": index,
                "delta": {
                    "type": delta_type,
                    **delta_data
                }
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_content_stop(
        self,
        session_id: str,
        index: int
    ) -> Dict[str, Any]:
        """
        发送 content_stop 事件
        
        Args:
            session_id: Session ID
            index: 内容块索引
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="content_stop",
            data={
                "index": index
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_thinking_delta(
        self,
        session_id: str,
        index: int,
        thinking_text: str
    ) -> Dict[str, Any]:
        """
        发送 thinking delta（便捷方法）
        
        Args:
            session_id: Session ID
            index: 内容块索引
            thinking_text: 思考内容
            
        Returns:
            事件对象
        """
        return await self.emit_content_delta(
            session_id=session_id,
            index=index,
            delta_type="thinking",
            delta_data={"text": thinking_text}
        )
    
    async def emit_text_delta(
        self,
        session_id: str,
        index: int,
        text: str
    ) -> Dict[str, Any]:
        """
        发送 text delta（便捷方法）
        
        Args:
            session_id: Session ID
            index: 内容块索引
            text: 文本内容
            
        Returns:
            事件对象
        """
        return await self.emit_content_delta(
            session_id=session_id,
            index=index,
            delta_type="text",
            delta_data={"text": text}
        )
    
    async def emit_tool_input_delta(
        self,
        session_id: str,
        index: int,
        partial_json: str
    ) -> Dict[str, Any]:
        """
        发送 tool input JSON delta（便捷方法）
        
        Args:
            session_id: Session ID
            index: 内容块索引
            partial_json: 部分 JSON 字符串
            
        Returns:
            事件对象
        """
        return await self.emit_content_delta(
            session_id=session_id,
            index=index,
            delta_type="tool_input",
            delta_data={"partial_json": partial_json}
        )

