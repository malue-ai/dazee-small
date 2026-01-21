"""
数据库引擎和会话管理

使用 PostgreSQL 作为唯一数据库后端。

配置方式：
- 必须配置环境变量 DATABASE_URL
- 示例：postgresql+asyncpg://user:pass@localhost:5432/zenflux
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from infra.database.base import Base


def get_database_url() -> str:
    """
    获取数据库连接 URL（必须配置 DATABASE_URL 环境变量）
    
    Returns:
        数据库连接 URL
        
    Raises:
        RuntimeError: 未配置 DATABASE_URL 时抛出
        
    示例：
        PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/zenflux
    """
    url = os.getenv("DATABASE_URL")
    
    if not url:
        raise RuntimeError(
            "DATABASE_URL 环境变量未配置。"
            "请配置 PostgreSQL 连接字符串，例如：\n"
            "DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/zenflux"
        )
    
    # 处理 PostgreSQL URL 前缀（Heroku 等平台使用 postgres://）
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url


# 数据库 URL
DATABASE_URL = get_database_url()

# 创建异步引擎（PostgreSQL）
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
