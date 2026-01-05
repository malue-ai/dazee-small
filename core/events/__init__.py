"""
SSE 事件管理模块

详细文档：docs/03-EVENT-PROTOCOL.md

架构概览：
====================

    SimpleAgent
         │
         ▼
    EventBroadcaster  ← Agent 统一入口，包含增强逻辑
         │
         ▼
    EventManager      ← 聚合所有层级管理器
         │
         ├── SessionEventManager
         ├── UserEventManager
         ├── ConversationEventManager
         ├── MessageEventManager
         ├── ContentEventManager
         └── SystemEventManager
                │
                ▼
         EventStorage (Redis/Memory)

事件层级：
====================

    Session（运行会话）    session_start, session_end, ping
        │
        └── User（用户）   user_action, user_preference_update
            │
            └── Conversation  conversation_start, conversation_delta, conversation_stop
                │
                └── Message   message_start, message_delta, message_stop
                    │
                    └── Content  content_start, content_delta, content_stop

设计原则：
====================

1. 每层只有 start/delta/stop 三个核心事件
2. 所有扩展数据通过 delta 发送
3. Agent 使用 EventBroadcaster，不直接使用 EventManager
4. EventBroadcaster 负责增强逻辑（如特殊工具的 message_delta）

使用示例：
====================

    # Agent 中使用 Broadcaster
    from core.events import create_broadcaster, create_event_manager
    
    events = create_event_manager(storage)
    broadcaster = create_broadcaster(events)
    
    await broadcaster.emit_content_start(session_id, index, content_block)
    await broadcaster.emit_content_delta(session_id, index, delta)
    await broadcaster.emit_content_stop(session_id, index)
    
    # Service 中直接使用 EventManager
    await events.session.emit_session_start(...)
    await events.conversation.emit_conversation_delta(...)
"""

from core.events.manager import EventManager, create_event_manager
from core.events.session_events import SessionEventManager
from core.events.user_events import UserEventManager
from core.events.conversation_events import ConversationEventManager
from core.events.message_events import MessageEventManager
from core.events.content_events import ContentEventManager
from core.events.system_events import SystemEventManager
from core.events.broadcaster import EventBroadcaster, create_broadcaster
from core.events.storage import (
    RedisEventStorage,
    InMemoryEventStorage,
    create_event_storage,
    get_memory_storage,
)

__all__ = [
    "EventManager",
    "create_event_manager",
    "SessionEventManager",
    "UserEventManager",
    "ConversationEventManager",
    "MessageEventManager",
    "ContentEventManager",
    "SystemEventManager",
    # Broadcaster
    "EventBroadcaster",
    "create_broadcaster",
    # Storage
    "RedisEventStorage",
    "InMemoryEventStorage",
    "create_event_storage",
    "get_memory_storage",
]

