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
    get_or_create_user,
)
from infra.database.crud.conversation import (
    create_conversation,
    get_conversation,
    update_conversation,
    list_conversations,
    count_conversations,
    list_conversations_with_stats,
    get_conversation_summary,
    delete_conversation,
    count_messages_in_conversation,
    get_conversations_since,
)
from infra.database.crud.message import (
    create_message,
    get_message,
    update_message,
    list_messages,
    get_messages_by_conversation,
)
from infra.database.crud.file import (
    create_file,
    get_file,
    update_file,
    list_files_by_user,
    count_files_by_user,
    delete_file,
)
from infra.database.crud.knowledge import (
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
from infra.database.crud.mcp import (
    # 全局 MCP 模板
    create_global_mcp,
    get_global_mcp_by_name,
    list_global_mcps,
    update_global_mcp,
    delete_global_mcp,
    # Agent 实例化 MCP
    create_agent_mcp,
    get_agent_mcp,
    list_agent_mcps,
    update_agent_mcp,
    delete_agent_mcp,
    delete_all_agent_mcps,
    # 工具注册
    update_mcp_registered_tools,
    get_mcp_by_id,
    check_mcp_exists,
)

__all__ = [
    # 通用
    "get_by_id",
    "create",
    "update_by_id",
    "delete_by_id",
    
    # User
    "get_or_create_user",
    
    # Conversation
    "create_conversation",
    "get_conversation",
    "update_conversation",
    "list_conversations",
    "count_conversations",
    "list_conversations_with_stats",
    "get_conversation_summary",
    "delete_conversation",
    "count_messages_in_conversation",
    "get_conversations_since",
    
    # Message
    "create_message",
    "get_message",
    "update_message",
    "list_messages",
    "get_messages_by_conversation",
    
    # File
    "create_file",
    "get_file",
    "update_file",
    "list_files_by_user",
    "count_files_by_user",
    "delete_file",
    
    # Knowledge
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
    
    # MCP
    "create_global_mcp",
    "get_global_mcp_by_name",
    "list_global_mcps",
    "update_global_mcp",
    "delete_global_mcp",
    "create_agent_mcp",
    "get_agent_mcp",
    "list_agent_mcps",
    "update_agent_mcp",
    "delete_agent_mcp",
    "delete_all_agent_mcps",
    "update_mcp_registered_tools",
    "get_mcp_by_id",
    "check_mcp_exists",
]

