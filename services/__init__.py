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
from .session_service import (
    SessionNotFoundError,
    SessionService,
    SessionServiceError,
    get_session_service,
)
from .user_task_scheduler import (
    UserTaskScheduler,
    get_user_task_scheduler,
    start_user_task_scheduler,
    stop_user_task_scheduler,
)

__all__ = [
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
    # Agent Registry
    "AgentRegistry",
    "get_agent_registry",
    "AgentConfig",
    "AgentNotFoundError",
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
