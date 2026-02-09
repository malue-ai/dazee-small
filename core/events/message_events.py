"""
Message 级事件管理 - MessageEventManager

事件类型（只有 3 个）：
- message_start : 消息开始
- message_delta : 消息增量（统一结构）
- message_stop  : 消息结束

message_delta 统一结构：
{
    "type": "xxx",         # 类型标识
    "content": {...}/str   # 内容（对象或字符串）
}

支持的 type：
- usage       : 使用统计 {"type": "usage", "content": {"stop_reason": "end_turn"}}
- recommended : 推荐问题 {"type": "recommended", "content": "[...]"}
- search      : 搜索结果 {"type": "search", "content": "..."}
- knowledge   : 知识检索 {"type": "knowledge", "content": "..."}
- ppt         : PPT 生成 {"type": "ppt", "content": "..."}
- intent      : 意图分析 {"type": "intent", "content": {...}}
- billing     : 计费信息 {"type": "billing", "content": {...}}

注意：Plan 数据通过 tool_result (plan_todo 工具) 发送，不使用 message_delta

注意：
- Tool 事件通过 Content 级事件发送（tool_use/tool_result）
- 序号（seq）由 EventBroadcaster 层统一生成
"""

from typing import Any, Dict, Optional

from core.events.base import BaseEventManager


class MessageEventManager(BaseEventManager):
    """
    Message 级事件管理器

    负责消息轮次相关的事件：
    - message_start: 消息开始
    - message_delta: 消息增量（通用，支持多种 delta 类型）
    - message_stop: 消息结束

    注意：
    - Tool 事件通过 Content 级事件发送
    - 推荐通过 EventBroadcaster 调用，由其统一生成 seq
    """

    async def emit_message_start(
        self,
        session_id: str,
        conversation_id: str,
        message_id: str,
        model: str,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_start 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            message_id: 消息ID
            model: 模型名称
            seq: 事件序号（可选，来自 EventBroadcaster）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
            "timestamp": self._get_timestamp(),
        }

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            message_id=message_id,
            seq=seq,
            event_uuid=event_uuid,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_message_delta(
        self,
        session_id: str,
        conversation_id: str,
        delta: Dict[str, Any],
        message_id: Optional[str] = None,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_delta 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            delta: Delta 内容，统一结构 {"type": "xxx", "content": ...}
            message_id: 消息 ID（可选）
            seq: 事件序号（可选）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None

        事件结构（简化后）：
            {
                "type": "message_delta",
                "data": {
                    "type": "intent",        # delta 类型
                    "content": {...}         # delta 内容
                }
            }

        Examples:
            delta = {"type": "intent", "content": {...}}
            delta = {"type": "recommended", "content": "[...]"}
        """
        # delta 直接作为 data（不再包裹）
        event = self._create_event(event_type="message_delta", data=delta)

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            message_id=message_id,
            seq=seq,
            event_uuid=event_uuid,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_message_stop(
        self,
        session_id: str,
        conversation_id: str,
        message_id: Optional[str] = None,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 message_stop 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            message_id: Message ID（可选）
            seq: 事件序号（可选）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(event_type="message_stop", data={})

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            message_id=message_id,
            seq=seq,
            event_uuid=event_uuid,
            output_format=output_format,
            adapter=adapter,
        )

    def _get_timestamp(self) -> str:
        """获取当前时间戳（ISO格式）"""
        from datetime import datetime

        return datetime.now().isoformat()
