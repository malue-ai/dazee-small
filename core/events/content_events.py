"""
Content 级事件管理 - ContentEventManager

事件类型（只有 3 个）：
- content_start : 开始内容块
- content_delta : 内容增量
- content_stop  : 结束内容块

content_block 类型（在 content_start 中定义）：
- text        : 文本内容
- thinking    : 思考过程（Extended Thinking）
- tool_use    : 工具调用
- tool_result : 工具执行结果

delta 格式（简化版）：
- delta 直接是字符串，类型由 content_start 的 content_block.type 决定
- text: delta = "我"
- thinking: delta = "Let me think..."
- tool_use: delta = '{"code": "print('

设计原则：纯粹的事件发送层，不关心具体结构，由上层决定

注意：序号（seq）由 EventBroadcaster 层统一生成
"""

from typing import Any, Dict, Optional

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

    注意：推荐通过 EventBroadcaster 调用，由其统一生成 seq
    """

    async def emit_content_start(
        self,
        session_id: str,
        conversation_id: str,
        index: int,
        content_block: Dict[str, Any],
        message_id: Optional[str] = None,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 content_start 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            index: 内容块索引
            content_block: 完整的内容块对象（由上层构造）
            message_id: 消息 ID（可选）
            seq: 事件序号（可选，来自 EventBroadcaster）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            发送的事件对象，如果被过滤则返回 None

        示例 content_block 结构：
        - text:        {"type": "text", "text": ""}
        - thinking:    {"type": "thinking", "thinking": ""}
        - tool_use:    {"type": "tool_use", "id": "...", "name": "...", "input": {}}
        - tool_result: {"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": false}
        """
        event = self._create_event(
            event_type="content_start", data={"index": index, "content_block": content_block}
        )
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

    async def emit_content_delta(
        self,
        session_id: str,
        conversation_id: str,
        index: int,
        delta: str,
        message_id: Optional[str] = None,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 content_delta 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            index: 内容块索引
            delta: 增量内容（字符串）
            message_id: 消息 ID（可选）
            seq: 事件序号（可选）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            发送的事件对象，如果被过滤则返回 None

        简化格式：
        delta 直接是字符串，类型由 content_start 的 content_block.type 决定
        - text: delta = "我"
        - thinking: delta = "Let me think..."
        - tool_use: delta = '{"code": "print('
        """
        event = self._create_event(
            event_type="content_delta", data={"index": index, "delta": delta}
        )
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

    async def emit_content_stop(
        self,
        session_id: str,
        conversation_id: str,
        index: int,
        message_id: Optional[str] = None,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 content_stop 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            index: 内容块索引
            message_id: 消息 ID（可选）
            seq: 事件序号（可选）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            发送的事件对象，如果被过滤则返回 None
        """
        event = self._create_event(event_type="content_stop", data={"index": index})
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
