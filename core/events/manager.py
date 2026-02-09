"""
统一事件管理器 - EventManager

职责：聚合所有层级的事件管理器，提供统一接口

注意：
- Agent 应使用 EventBroadcaster，不直接使用 EventManager
- Service 层可以直接使用 EventManager
- EventManager 是纯粹的事件发送层，无增强逻辑
- 支持设置全局 output_format，所有子管理器共享
"""

from typing import Any, Dict, Optional

from core.events.base import EventStorage  # ← 导入 Protocol
from core.events.content_events import ContentEventManager
from core.events.conversation_events import ConversationEventManager
from core.events.message_events import MessageEventManager
from core.events.session_events import SessionEventManager
from core.events.system_events import SystemEventManager
from core.events.user_events import UserEventManager


class EventManager:
    """
    统一事件管理器

    整合 5 个层级的事件管理器：
    1. Session 级：运行会话
    2. User 级：用户行为
    3. Conversation 级：对话会话（plan, title, context）
    4. Message 级：消息轮次（turn）
    5. Content 级：内容块（thinking, text, tool_use）

    使用示例：
        events = EventManager(storage)

        # Session 级事件
        await events.session.emit_session_start(...)

        # User 级事件
        await events.user.emit_user_action(...)

        # Conversation 级事件
        await events.conversation.emit_conversation_start(...)

        # Message 级事件
        await events.message.emit_message_start(...)

        # Content 级事件
        await events.content.emit_content_block_start(...)

        # System 级事件
        await events.system.emit_error(...)
    """

    def __init__(self, storage: EventStorage):
        """
        初始化统一事件管理器

        Args:
            storage: 事件存储实现（传递给子管理器）
        """
        # 保留 storage 引用（供 Agent 等模块获取 session context 使用）
        self.storage = storage

        # 输出格式配置
        self._output_format: str = "zenflux"
        self._conversation_id: Optional[str] = None
        self._adapter = None

        # 初始化各层级事件管理器（storage 传递给它们）
        self.session = SessionEventManager(storage)
        self.user = UserEventManager(storage)
        self.conversation = ConversationEventManager(storage)
        self.message = MessageEventManager(storage)
        self.content = ContentEventManager(storage)
        self.system = SystemEventManager(storage)

    def set_output_format(self, format: str, conversation_id: str = None) -> None:
        """
        设置输出格式（全局配置）

        设置后，所有通过 EventManager 发送的事件都会使用此格式

        Args:
            format: 输出事件格式
            conversation_id: 对话 ID
        """
        self._output_format = format
        if conversation_id:
            self._conversation_id = conversation_id
        # 重置适配器，下次使用时会重新创建
        self._adapter = None

    @property
    def output_format(self) -> str:
        """获取当前输出格式"""
        return self._output_format

    @property
    def adapter(self):
        """获取当前适配器"""
        return self._adapter


def create_event_manager(storage: EventStorage) -> EventManager:
    """
    创建 EventManager 实例

    Args:
        storage: 事件存储实现（实现 EventStorage 协议）

    Returns:
        EventManager 实例
    """
    return EventManager(storage)
