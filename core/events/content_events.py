"""
Content 级事件管理 - ContentEventManager

事件类型（只有 3 个）：
- content_start : 开始内容块
- content_delta : 内容增量
- content_stop  : 结束内容块

content_block 类型：
- text        : 文本内容
- thinking    : 思考过程（Extended Thinking）
- tool_use    : 工具调用
- tool_result : 工具执行结果

delta 类型：
- text_delta       : {"type": "text_delta", "text": "..."}
- thinking_delta   : {"type": "thinking_delta", "thinking": "..."}
- input_json_delta : {"type": "input_json_delta", "partial_json": "..."}
- signature_delta  : {"type": "signature_delta", "signature": "..."}

设计原则：纯粹的事件发送层，不关心具体结构，由上层决定
"""

from typing import Dict, Any
from core.events.base import BaseEventManager


class ContentEventManager(BaseEventManager):
    """
    Content 级事件管理器
    
    只有 3 个核心方法，是纯粹的事件发送层。
    不关心 content_block 和 delta 的具体结构，那是上层（Agent）的职责。
    
    这样设计的好处：
    1. 职责清晰：只负责发送事件
    2. 灵活性：上层可以构造任何结构
    3. 可扩展：后续接入 OpenAI/Gemini 时，只需要在 Agent 层做适配
    """
    
    async def emit_content_start(
        self,
        session_id: str,
        index: int,
        content_block: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 content_start 事件
        
        Args:
            session_id: Session ID
            index: 内容块索引
            content_block: 完整的内容块对象（由上层构造）
            
        Returns:
            发送的事件对象
            
        示例 content_block 结构：
        - text:        {"type": "text", "text": ""}
        - thinking:    {"type": "thinking", "thinking": ""}
        - tool_use:    {"type": "tool_use", "id": "...", "name": "...", "input": {}}
        - tool_result: {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": false}
        """
        event = self._create_event(
            event_type="content_start",
            data={
                "index": index,
                "content_block": content_block
            }
        )
        return await self._send_event(session_id, event)
    
    async def emit_content_delta(
        self,
        session_id: str,
        index: int,
        delta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 content_delta 事件
        
        Args:
            session_id: Session ID
            index: 内容块索引
            delta: Delta 对象（由上层构造）
            
        Returns:
            发送的事件对象
            
        示例 delta 结构：
        - text_delta:      {"type": "text_delta", "text": "..."}
        - thinking_delta:  {"type": "thinking_delta", "thinking": "..."}
        - input_json_delta:{"type": "input_json_delta", "partial_json": "..."}
        """
        event = self._create_event(
            event_type="content_delta",
            data={
                "index": index,
                "delta": delta
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
            发送的事件对象
        """
        event = self._create_event(
            event_type="content_stop",
            data={
                "index": index
            }
        )
        return await self._send_event(session_id, event)
