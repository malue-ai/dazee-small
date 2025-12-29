"""
SSE 事件管理模块

职责：
1. 统一管理所有 SSE 事件的创建
2. 提供标准化的事件格式
3. 自动处理事件ID生成和 Redis 缓冲
4. 遵循 SSE 事件协议（docs/03-SSE-EVENT-PROTOCOL.md）

架构层级：
    Session（运行会话）
        └── User（用户）
            └── Conversation（对话会话）- plan, title, context
                └── Message（消息/Turn）
                    └── Content（内容块）- thinking, text, tool_use

使用示例：
    from core.events import create_event_manager
    
    events = create_event_manager(redis)
    
    # Session 级事件
    await events.session.emit_session_start(...)
    
    # User 级事件
    await events.user.emit_user_action(...)
    
    # Conversation 级事件
    await events.conversation.emit_conversation_start(...)
    await events.conversation.emit_conversation_plan_created(...)
    await events.conversation.emit_conversation_context_compressed(...)
    
    # Message 级事件
    await events.message.emit_message_start(...)
    await events.message.emit_tool_call_start(...)
    await events.message.emit_plan_step_start(...)
    
    # Content 级事件
    await events.content.emit_content_block_start(...)
    await events.content.emit_thinking_delta(...)
    await events.content.emit_text_delta(...)
    
    # System 级事件
    await events.system.emit_error(...)
    await events.system.emit_agent_status(...)
"""

from core.events.manager import EventManager, create_event_manager
from core.events.session_events import SessionEventManager
from core.events.user_events import UserEventManager
from core.events.conversation_events import ConversationEventManager
from core.events.message_events import MessageEventManager
from core.events.content_events import ContentEventManager
from core.events.system_events import SystemEventManager

__all__ = [
    "EventManager",
    "create_event_manager",
    "SessionEventManager",
    "UserEventManager",
    "ConversationEventManager",
    "MessageEventManager",
    "ContentEventManager",
    "SystemEventManager",
]

