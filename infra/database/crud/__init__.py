"""
CRUD 操作模块

按表分离的数据库操作，每个表一个文件
"""

# 通用操作
from infra.database.crud.base import (
    get_by_id,
    create,
    update_by_id,
    delete_by_id,
)

# 各表操作
from infra.database.crud.user import (
    generate_user_id,
    get_or_create_user,
)
from infra.database.crud.conversation import (
    generate_conversation_id,
    create_conversation,
    get_conversation,
    update_conversation,
    list_conversations,
    count_conversations,
    list_conversations_with_stats,
    get_conversation_summary,
    delete_conversation,
    count_messages_in_conversation,
)
from infra.database.crud.message import (
    generate_message_id,
    create_message,
    get_message,
    update_message,
    list_messages,
)
from infra.database.crud.file import (
    generate_file_id,
    create_file,
    get_file,
    update_file,
    list_files_by_user,
    count_files_by_user,
    delete_file,
)
from infra.database.crud.knowledge import (
    generate_knowledge_id,
    create_knowledge,
    get_knowledge,
    update_knowledge,
    delete_knowledge,
    list_knowledge_by_user,
    count_knowledge_by_user,
    search_knowledge,
    get_knowledge_by_file,
    bulk_update_status,
)
from infra.database.crud.sandbox import (
    generate_sandbox_id,
    create_sandbox,
    get_sandbox,
    get_sandbox_by_conversation,
    get_sandbox_by_e2b_id,
    update_sandbox,
    update_sandbox_status,
    update_sandbox_e2b_id,
    update_sandbox_activity,
    list_sandboxes_by_user,
    list_sandboxes_by_status,
    delete_sandbox,
    delete_sandbox_by_conversation,
)

__all__ = [
    # 通用
    "get_by_id",
    "create",
    "update_by_id",
    "delete_by_id",
    
    # User
    "generate_user_id",
    "get_or_create_user",
    
    # Conversation
    "generate_conversation_id",
    "create_conversation",
    "get_conversation",
    "update_conversation",
    "list_conversations",
    "count_conversations",
    "list_conversations_with_stats",
    "get_conversation_summary",
    "delete_conversation",
    "count_messages_in_conversation",
    
    # Message
    "generate_message_id",
    "create_message",
    "get_message",
    "update_message",
    "list_messages",
    
    # File
    "generate_file_id",
    "create_file",
    "get_file",
    "update_file",
    "list_files_by_user",
    "count_files_by_user",
    "delete_file",
    
    # Knowledge
    "generate_knowledge_id",
    "create_knowledge",
    "get_knowledge",
    "update_knowledge",
    "delete_knowledge",
    "list_knowledge_by_user",
    "count_knowledge_by_user",
    "search_knowledge",
    "get_knowledge_by_file",
    "bulk_update_status",
    
    # Sandbox
    "generate_sandbox_id",
    "create_sandbox",
    "get_sandbox",
    "get_sandbox_by_conversation",
    "get_sandbox_by_e2b_id",
    "update_sandbox",
    "update_sandbox_status",
    "update_sandbox_e2b_id",
    "update_sandbox_activity",
    "list_sandboxes_by_user",
    "list_sandboxes_by_status",
    "delete_sandbox",
    "delete_sandbox_by_conversation",
]

