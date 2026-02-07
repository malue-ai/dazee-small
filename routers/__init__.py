from .agents import router as agents_router
from .chat import router as chat_router
from .conversation import router as conversation_router
from .docs import router as docs_router
from .files import router as files_router
from .health import router as health_router
from .human_confirmation import router as human_confirmation_router
from .mem0_router import router as mem0_router
from .models import router as models_router
from .realtime import router as realtime_router
from .settings import router as settings_router
from .skills import router as skills_router
from .tasks import router as tasks_router
from .tools import router as tools_router

# V11.0: 移除 knowledge_router（云端 Ragie 已删除）

__all__ = [
    "chat_router",
    "files_router",
    "tools_router",
    "mem0_router",
    "tasks_router",
    "agents_router",
    "conversation_router",
    "health_router",
    "human_confirmation_router",
    "skills_router",
    "docs_router",
    "realtime_router",
    "models_router",
    "settings_router",
]
