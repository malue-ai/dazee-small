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
    list_files,
    list_files_by_user,
    count_files_by_user,
    get_user_file_stats,
    soft_delete_file,
    convert_api_status_to_db,
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
    "list_files",
    "list_files_by_user",
    "count_files_by_user",
    "get_user_file_stats",
    "soft_delete_file",
    "convert_api_status_to_db",
    
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
]

