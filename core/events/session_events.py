"""
Session 级事件管理 - SessionEventManager

事件类型：
- session_start   : 会话开始（首个事件）
- session_stopped : 用户主动停止
- session_end     : 会话结束（正常/失败/取消）
- ping            : 心跳保活
"""

from datetime import datetime
from typing import Any, Dict, Optional

from core.events.base import BaseEventManager
from logger import get_logger

logger = get_logger("session_events")


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
        message_id: Optional[str] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 session_start 事件

        Args:
            session_id: Session ID
            user_id: 用户ID
            conversation_id: 对话ID
            message_id: 消息ID（可选，zenflux 格式中使用）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        # 🔍 追踪日志：记录入参
        logger.info(
            f"🔍 [emit_session_start] 入参追踪: "
            f"session_id={session_id}, "
            f"conversation_id={conversation_id}, "
            f"user_id={user_id}"
        )

        data = {
            "session_id": session_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
        }

        # 🆕 zenflux 格式添加 message_id
        if message_id:
            data["message_id"] = message_id

        event = self._create_event(event_type="session_start", data=data)

        # 🔍 追踪日志：记录传给 _send_event 的 conversation_id
        logger.info(
            f"🔍 [emit_session_start] 调用 _send_event: "
            f"session_id={session_id}, "
            f"conversation_id(传参)={conversation_id}"
        )

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,  # 显式传递
            message_id=message_id,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_session_stopped(
        self,
        session_id: str,
        conversation_id: str,
        reason: str = "user_requested",
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 session_stopped 事件（用户主动停止）

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            reason: 停止原因（user_requested/timeout/error）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="session_stopped",
            data={
                "session_id": session_id,
                "reason": reason,
                "stopped_at": datetime.now().isoformat(),
            },
        )

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_session_end(
        self,
        session_id: str,
        conversation_id: str,
        status: str,
        duration_ms: int,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送 session_end 事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            status: 会话状态（completed/failed/cancelled）
            duration_ms: 会话持续时间（毫秒）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="session_end",
            data={"session_id": session_id, "status": status, "duration_ms": duration_ms},
        )

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_heartbeat(
        self,
        session_id: str,
        conversation_id: str,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送心跳事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(event_type="ping", data={"type": "ping"})

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            output_format=output_format,
            adapter=adapter,
        )
