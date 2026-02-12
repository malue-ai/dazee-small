"""
SSE 事件管理模块

详细文档：docs/03-EVENT-PROTOCOL.md

架构概览：
====================

    Agent
         │
         ▼
    EventBroadcaster  ← Agent 统一入口
         │
         │  1. 内部处理（累积、增强逻辑）
         │  2. 调用 storage.buffer_event()
         │     - 格式转换（如果需要）
         │     - 自增生成 seq
         │     - 存入内存 + 通知订阅者
         │
         └──→ EventDispatcher → 外部 Webhook（可选）

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
4. seq 由 buffer_event 统一自增生成
5. 格式转换在 buffer_event 中完成

使用示例：
====================

    # Agent 中使用 Broadcaster（推荐）
    from core.events import create_broadcaster, create_event_manager

    events = create_event_manager(storage)
    broadcaster = create_broadcaster(events)

    await broadcaster.emit_content_start(session_id, index, content_block)
    await broadcaster.emit_content_delta(session_id, index, delta)
    await broadcaster.emit_content_stop(session_id, index)
"""

from core.events.broadcaster import EventBroadcaster, create_broadcaster
from core.events.content_events import ContentEventManager
from core.events.conversation_events import ConversationEventManager
from core.events.dispatcher import EventDispatcher, create_event_dispatcher
from core.events.manager import EventManager, create_event_manager
from core.events.message_events import MessageEventManager
from core.events.session_events import SessionEventManager
from core.events.storage import (
    InMemoryEventStorage,
    get_memory_storage,
)
from core.events.system_events import SystemEventManager
from core.events.user_events import UserEventManager

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
    # Dispatcher（外部适配器）
    "EventDispatcher",
    "create_event_dispatcher",
    # Storage（开发环境）
    "InMemoryEventStorage",
    "get_memory_storage",
]
