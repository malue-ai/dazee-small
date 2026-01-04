"""
数据库引擎和会话管理

支持的数据库：
- SQLite（开发环境）
- PostgreSQL（生产环境推荐）
- MySQL（生产环境可选）

配置方式：
- 环境变量 DATABASE_URL
- 默认使用 SQLite
"""

import os
from typing import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from infra.database.base import Base


def get_database_url() -> str:
    """
    获取数据库连接 URL
    
    优先级：
    1. 环境变量 DATABASE_URL
    2. 默认 SQLite
    
    Returns:
        数据库连接 URL
        
    示例：
        SQLite:     sqlite+aiosqlite:///./workspace/database/zenflux.db
        PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/zenflux
        MySQL:      mysql+aiomysql://user:pass@localhost:3306/zenflux
    """
    url = os.getenv("DATABASE_URL")
    
    if url:
        # 处理 PostgreSQL URL 前缀（Heroku 等平台使用 postgres://）
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    
    # 默认使用 SQLite
    db_dir = Path("./workspace/database")
    db_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_dir}/zenflux.db"


# 数据库 URL
DATABASE_URL = get_database_url()

# 判断是否为 SQLite（SQLite 需要特殊配置）
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# 创建异步引擎
if IS_SQLITE:
    # SQLite 配置
    engine = create_async_engine(
        DATABASE_URL,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # SQLite 使用静态连接池
    )
else:
    # PostgreSQL / MySQL 配置
    engine = create_async_engine(
        DATABASE_URL,
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # 自动检测断开的连接
    )

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话（依赖注入）
    
    用于 FastAPI 依赖注入：
    
    ```python
    from fastapi import Depends
    from infra.database import get_async_session, AsyncSession
    
    @router.get("/users/{user_id}")
    async def get_user(
        user_id: str,
        session: AsyncSession = Depends(get_async_session)
    ):
        ...
    ```
    
    Yields:
        AsyncSession: 数据库会话
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_database():
    """
    初始化数据库（创建所有表）
    
    在应用启动时调用：
    
    ```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_database()
        yield
    ```
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

