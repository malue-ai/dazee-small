"""
User 级事件管理 - UserEventManager

事件类型：
- user_action            : 用户行为（login, logout, send_message）
- user_preference_update : 用户偏好更新

注意：当前使用较少，保留以备后续扩展（如用户行为分析、个性化推荐）
"""

from typing import Any, Dict, Optional

from core.events.base import BaseEventManager


class UserEventManager(BaseEventManager):
    """
    User 级事件管理器

    负责用户相关的事件
    """

    async def emit_user_action(
        self,
        session_id: str,
        conversation_id: str,
        user_id: str,
        action: str,
        action_data: Optional[Dict[str, Any]] = None,
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送用户行为事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            user_id: 用户ID
            action: 行为类型（如 login, logout, send_message）
            action_data: 行为数据
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="user_action",
            data={"user_id": user_id, "action": action, "action_data": action_data or {}},
        )

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            output_format=output_format,
            adapter=adapter,
        )

    async def emit_user_preference_update(
        self,
        session_id: str,
        conversation_id: str,
        user_id: str,
        preferences: Dict[str, Any],
        output_format: str = "zenflux",
        adapter: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        发送用户偏好更新事件

        Args:
            session_id: Session ID
            conversation_id: 对话 ID（必填）
            user_id: 用户ID
            preferences: 用户偏好设置
            output_format: 输出格式，默认 zenflux
            adapter: 格式转换适配器（可选）

        Returns:
            事件对象，如果被过滤则返回 None
        """
        event = self._create_event(
            event_type="user_preference_update",
            data={"user_id": user_id, "preferences": preferences},
        )

        return await self._send_event(
            session_id,
            event,
            conversation_id=conversation_id,
            output_format=output_format,
            adapter=adapter,
        )
