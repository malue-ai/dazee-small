"""
服务层包

提供业务逻辑封装，供 Router 层调用
"""

from .knowledge_service import (
    KnowledgeService,
    get_knowledge_service,
    KnowledgeServiceError,
    DocumentNotFoundError,
    UserNotFoundError,
    DocumentProcessingError,
)

from .session_service import (
    SessionService,
    get_session_service,
    SessionServiceError,
    SessionNotFoundError,
)

from .chat_service import (
    ChatService,
    get_chat_service,
    ChatServiceError,
    AgentExecutionError,
)

from .conversation_service import (
    ConversationService,
    get_conversation_service,
    ConversationServiceError,
    ConversationNotFoundError as ConvNotFoundError,
)

from .file_service import (
    FileService,
    get_file_service,
    FileServiceError,
    FileNotFoundError as FileNotFoundErr,
)

from .tool_service import (
    ToolService,
    get_tool_service,
    ToolServiceError,
    ToolNotFoundError,
    ToolAlreadyExistsError,
    ToolExecutionError,
    MCPConnectionError,
    ToolRegistrationError,
    # 工具处理器
    ToolHandler,
    MCPClient,
    # 装饰器
    tool,
)

from .task_service import (
    TaskService,
    get_task_service,
    TaskInfo,
    TaskRunResult,
    TaskStatus,
    TriggerType,
)

from .agent_registry import (
    AgentRegistry,
    get_agent_registry,
    AgentConfig,
    AgentNotFoundError,
)

from .mcp_service import (
    MCPService,
    get_mcp_service,
    MCPServiceError,
    MCPNotFoundError,
    MCPAlreadyExistsError,
    MCPConnectionError as MCPServiceConnectionError,
)

__all__ = [
    # Knowledge Service
    "KnowledgeService",
    "get_knowledge_service",
    "KnowledgeServiceError",
    "DocumentNotFoundError",
    "UserNotFoundError",
    "DocumentProcessingError",
    # Session Service
    "SessionService",
    "get_session_service",
    "SessionServiceError",
    "SessionNotFoundError",
    # Chat Service
    "ChatService",
    "get_chat_service",
    "ChatServiceError",
    "AgentExecutionError",
    # Conversation Service
    "ConversationService",
    "get_conversation_service",
    "ConversationServiceError",
    "ConvNotFoundError",
    # File Service
    "FileService",
    "get_file_service",
    "FileServiceError",
    "FileNotFoundErr",
    # Tool Service
    "ToolService",
    "get_tool_service",
    "ToolServiceError",
    "ToolNotFoundError",
    "ToolAlreadyExistsError",
    "ToolExecutionError",
    "MCPConnectionError",
    "ToolRegistrationError",
    "ToolHandler",
    "MCPClient",
    "tool",
    # Task Service
    "TaskService",
    "get_task_service",
    "TaskInfo",
    "TaskRunResult",
    "TaskStatus",
    "TriggerType",
    # Agent Registry
    "AgentRegistry",
    "get_agent_registry",
    "AgentConfig",
    "AgentNotFoundError",
    # MCP Service
    "MCPService",
    "get_mcp_service",
    "MCPServiceError",
    "MCPNotFoundError",
    "MCPAlreadyExistsError",
    "MCPServiceConnectionError",
]

