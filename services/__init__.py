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

from .chat_event_handler import ChatEventHandler

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
    "ChatEventHandler",
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
]

