"""
数据库模块

提供：
- SQLAlchemy 2.0 异步引擎
- 会话管理
- ORM 模型
- CRUD 操作
- 支持 SQLite / PostgreSQL / MySQL
"""

from infra.database.engine import (
    engine,
    AsyncSessionLocal,
    get_async_session,
    init_database,
)
from infra.database.base import Base

# 导入所有模型（用于 Alembic 自动检测）
from infra.database.models import (
    User,
    Conversation,
    Message,
    File,
    Knowledge,
    Sandbox,
)

# 导入 CRUD 操作
from infra.database import crud

__all__ = [
    # 引擎和会话
    "engine",
    "AsyncSessionLocal",
    "get_async_session",
    "init_database",
    "Base",
    
    # 模型
    "User",
    "Conversation",
    "Message",
    "File",
    "Knowledge",
    "Sandbox",
    
    # CRUD
    "crud",
]

