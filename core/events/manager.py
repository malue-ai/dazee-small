"""
统一事件管理器 - EventManager

职责：聚合所有层级的事件管理器，提供统一接口

注意：
- Agent 应使用 EventBroadcaster，不直接使用 EventManager
- Service 层可以直接使用 EventManager
- EventManager 是纯粹的事件发送层，无增强逻辑
"""

from typing import Dict, Any

from core.events.base import EventStorage  # ← 导入 Protocol
from core.events.session_events import SessionEventManager
from core.events.user_events import UserEventManager
from core.events.conversation_events import ConversationEventManager
from core.events.message_events import MessageEventManager
from core.events.content_events import ContentEventManager
from core.events.system_events import SystemEventManager


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
        events = EventManager(redis)
        
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
        
        # 初始化各层级事件管理器（storage 传递给它们）
        self.session = SessionEventManager(storage)
        self.user = UserEventManager(storage)
        self.conversation = ConversationEventManager(storage)
        self.message = MessageEventManager(storage)
        self.content = ContentEventManager(storage)
        self.system = SystemEventManager(storage)
    
    # ==================== 便捷方法（保持向后兼容） ====================
    
    async def emit_conversation_start(
        self,
        session_id: str,
        conversation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """便捷方法：发送 conversation_start 事件"""
        return await self.conversation.emit_conversation_start(session_id, conversation)
    
    async def emit_message_start(
        self,
        session_id: str,
        message_id: str,
        model: str
    ) -> Dict[str, Any]:
        """便捷方法：发送 message_start 事件"""
        return await self.message.emit_message_start(session_id, message_id, model)
    
    async def emit_message_stop(
        self,
        session_id: str,
        message_id: str = None
    ) -> Dict[str, Any]:
        """便捷方法：发送 message_stop 事件"""
        return await self.message.emit_message_stop(session_id, message_id)
    
    async def emit_error(
        self,
        session_id: str,
        error_type: str,
        error_message: str
    ) -> Dict[str, Any]:
        """便捷方法：发送 error 事件"""
        return await self.system.emit_error(session_id, error_type, error_message)
    
    async def emit_custom(
        self,
        session_id: str,
        event_type: str,
        event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """便捷方法：发送自定义事件"""
        return await self.system.emit_custom(session_id, event_type, event_data)


def create_event_manager(storage: EventStorage) -> EventManager:
    """
    创建 EventManager 实例
    
    Args:
        storage: 事件存储实现（可以是 Redis、内存、WebSocket 等）
        
    Returns:
        EventManager 实例
    """
    return EventManager(storage)

