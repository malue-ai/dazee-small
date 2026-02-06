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

注意：序号（seq）由 EventBroadcaster 层统一生成
"""

from typing import Any, Dict, Optional

from core.events.base import BaseEventManager


class SystemEventManager(BaseEventManager):
    """
    System 级事件管理器

    负责系统相关的事件

    注意：推荐通过 EventBroadcaster 调用，由其统一生成 seq
    """

    async def emit_error(
        self,
        session_id: str,
        conversation_id: str,
        error_type: str,
        error_message: str,
        details: Dict[str, Any] = None,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 error 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            error_type: 错误类型
            error_message: 错误消息
            details: 额外的错误详情（可选）
            seq: 事件序号（可选，来自 EventBroadcaster）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        error_data = {"type": error_type, "message": error_message}

        # 添加额外的详情
        if details:
            error_data.update(details)

        event = self._create_event(event_type="error", data={"error": error_data})

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            seq=seq,
            event_uuid=event_uuid,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_done(
        self,
        session_id: str,
        conversation_id: str,
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 done 事件（流结束）

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            seq: 事件序号（可选）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(event_type="done", data={"type": "done"})

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            seq=seq,
            event_uuid=event_uuid,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_custom(
        self,
        session_id: str,
        conversation_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        seq: Optional[int] = None,
        event_uuid: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送自定义事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            event_type: 事件类型
            event_data: 事件数据
            seq: 事件序号（可选）
            event_uuid: 事件 UUID（可选）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(event_type=event_type, data=event_data)

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            seq=seq,
            event_uuid=event_uuid,
            output_format=output_format,
            adapter=adapter,
        )
