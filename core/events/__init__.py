"""
SSE 事件管理模块

职责：
1. 统一管理所有 SSE 事件的创建
2. 提供标准化的事件格式
3. 自动处理事件ID生成和 Redis 缓冲
4. 遵循统一事件协议（docs/03-EVENT-PROTOCOL.md）

架构层级：
    Session（运行会话）
        └── User（用户）
            └── Conversation（对话会话）- plan, title, context
                └── Message（消息/Turn）
                    └── Content（内容块）- thinking, text, tool_use, tool_result

事件协议说明：
    我们使用自定义的统一协议（非 Claude 原生协议），便于后续接入 OpenAI/Gemini。
    Content 级别只有 3 个核心事件：
    - content_start: 开始一个内容块
    - content_delta: 内容增量
    - content_stop: 结束一个内容块

使用示例：
    from core.events import create_event_manager
    
    events = create_event_manager(redis)
    
    # Session 级事件
    await events.session.emit_session_start(...)
    
    # User 级事件
    await events.user.emit_user_action(...)
    
    # Conversation 级事件
    await events.conversation.emit_conversation_start(...)
    await events.conversation.emit_conversation_delta(...)
    
    # Message 级事件
    await events.message.emit_message_start(...)
    await events.message.emit_message_delta(...)
    await events.message.emit_message_stop(...)
    
    # Content 级事件（核心 3 个）
    await events.content.emit_content_start(session_id, index, content_block)
    await events.content.emit_content_delta(session_id, index, delta)
    await events.content.emit_content_stop(session_id, index)
    
    # System 级事件
    await events.system.emit_error(...)
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

