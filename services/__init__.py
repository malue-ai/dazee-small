"""
服务层包

提供业务逻辑封装，供 Router 层调用
"""

from .agent_registry import (
    AgentConfig,
    AgentNotFoundError,
    AgentRegistry,
    get_agent_registry,
)
from .chat_service import (
    AgentExecutionError,
    ChatService,
    ChatServiceError,
    get_chat_service,
)
from .confirmation_service import (
    ConfirmationExpiredError,
    ConfirmationNotFoundError,
    ConfirmationResponseError,
    ConfirmationService,
    ConfirmationServiceError,
    get_confirmation_service,
)
from .conversation_service import ConversationNotFoundError as ConvNotFoundError
from .conversation_service import (
    ConversationService,
    ConversationServiceError,
    get_conversation_service,
)
from .file_service import (
    FileService,
    FileServiceError,
    get_file_service,
)
from .knowledge_service import (
    DocumentNotFoundError,
    DocumentProcessingError,
    KnowledgeService,
    KnowledgeServiceError,
    UserNotFoundError,
    get_knowledge_service,
)
from .mcp_service import (
    MCPAlreadyExistsError,
)
from .mcp_service import MCPConnectionError as MCPServiceConnectionError
from .mcp_service import (
    MCPNotFoundError,
    MCPService,
    MCPServiceError,
    get_mcp_service,
)
from .session_service import (
    SessionNotFoundError,
    SessionService,
    SessionServiceError,
    get_session_service,
)
from .task_service import (
    TaskInfo,
    TaskRunResult,
    TaskService,
    TaskStatus,
    TriggerType,
    get_task_service,
)
from .tool_service import (  # 工具处理器; 装饰器
    ToolAlreadyExistsError,
    ToolExecutionError,
    ToolHandler,
    ToolNotFoundError,
    ToolRegistrationError,
    ToolService,
    ToolServiceError,
    get_tool_service,
    tool,
)
from .user_task_scheduler import (
    UserTaskScheduler,
    get_user_task_scheduler,
    start_user_task_scheduler,
    stop_user_task_scheduler,
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
    # Tool Service
    "ToolService",
    "get_tool_service",
    "ToolServiceError",
    "ToolNotFoundError",
    "ToolAlreadyExistsError",
    "ToolExecutionError",
    "ToolRegistrationError",
    "ToolHandler",
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
    # Confirmation Service
    "ConfirmationService",
    "get_confirmation_service",
    "ConfirmationServiceError",
    "ConfirmationNotFoundError",
    "ConfirmationExpiredError",
    "ConfirmationResponseError",
    # User Task Scheduler
    "UserTaskScheduler",
    "get_user_task_scheduler",
    "start_user_task_scheduler",
    "stop_user_task_scheduler",
]
