"""
本地存储 CRUD 操作

提供与 infra/database/crud/ 对称的接口，
但底层使用 SQLite 而非 PostgreSQL。
"""

from infra.local_store.crud.conversation import (
    count_conversations,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_or_create_conversation,
    list_conversations,
    update_conversation,
)
from infra.local_store.crud.message import (
    create_message,
    delete_messages_by_conversation,
    get_message,
    list_messages,
    update_message,
)
from infra.local_store.crud.scheduled_task import (
    cancel_task,
    count_user_tasks,
    create_scheduled_task,
    delete_task,
    get_pending_tasks,
    get_scheduled_task,
    list_user_tasks,
    mark_task_executed,
    update_task,
    update_task_status,
)

__all__ = [
    # 会话
    "create_conversation",
    "get_conversation",
    "get_or_create_conversation",
    "update_conversation",
    "list_conversations",
    "count_conversations",
    "delete_conversation",
    # 消息
    "create_message",
    "get_message",
    "update_message",
    "list_messages",
    "delete_messages_by_conversation",
    # 定时任务
    "create_scheduled_task",
    "get_scheduled_task",
    "list_user_tasks",
    "get_pending_tasks",
    "update_task",
    "update_task_status",
    "mark_task_executed",
    "cancel_task",
    "delete_task",
    "count_user_tasks",
]
