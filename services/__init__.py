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
    ConversationNotFoundError,
    AgentExecutionError,
)

from .conversation_service import (
    ConversationService,
    get_conversation_service,
    ConversationServiceError,
    ConversationNotFoundError as ConvNotFoundError,
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
    "ConversationNotFoundError",
    "AgentExecutionError",
    # Conversation Service
    "ConversationService",
    "get_conversation_service",
    "ConversationServiceError",
    "ConvNotFoundError",
]

