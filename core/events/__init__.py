"""
SSE 事件管理模块

详细文档：docs/03-EVENT-PROTOCOL.md

架构概览：
====================

    SimpleAgent
         │
         ▼
    EventBroadcaster  ← Agent 统一入口，统一生成 seq
         │
         │  1. 从 SeqManager 获取序号
         │  2. 构建完整事件（含 seq）
         │
         ├──→ EventManager → EventStorage（只做存储）
         │
         └──→ EventDispatcher → 外部系统（使用同一个 seq）

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
4. EventBroadcaster 负责：
   - 统一生成事件序号（seq）
   - 增强逻辑（如特殊工具的 message_delta）
   - 同时分发到 EventManager 和 EventDispatcher

使用示例：
====================

    # Agent 中使用 Broadcaster（推荐）
    from core.events import create_broadcaster, create_event_manager, create_seq_manager
    
    seq_manager = await create_seq_manager()
    events = create_event_manager(storage)
    broadcaster = create_broadcaster(events, seq_manager)
    
    await broadcaster.emit_content_start(session_id, index, content_block)
    await broadcaster.emit_content_delta(session_id, index, delta)
    await broadcaster.emit_content_stop(session_id, index)
    
    # Service 中直接使用 EventManager（不推荐，seq 可能不一致）
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
from core.events.dispatcher import EventDispatcher, create_event_dispatcher
from core.events.seq_manager import SeqManager, create_seq_manager, get_memory_seq_manager
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
    # Dispatcher（外部适配器）
    "EventDispatcher",
    "create_event_dispatcher",
    # SeqManager（序号管理器）
    "SeqManager",
    "create_seq_manager",
    "get_memory_seq_manager",
    # Storage
    "RedisEventStorage",
    "InMemoryEventStorage",
    "create_event_storage",
    "get_memory_storage",
]

