"""
SQLite 异步引擎

桌面端实例使用 SQLite 作为唯一存储后端（100% 本地），
100% 本地运行，零外部依赖。

特性：
- aiosqlite 异步驱动
- WAL 模式（支持并发读写）
- 自动建表 + FTS5 虚拟表
- 可选 sqlite-vec 扩展
"""

import os
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from logger import get_logger
from utils.app_paths import get_instance_db_dir

logger = get_logger("local_store.engine")


def _get_default_db_dir() -> str:
    """Resolve DB directory lazily (reads AGENT_INSTANCE at call time)."""
    env_override = os.getenv("LOCAL_STORE_DIR")
    if env_override:
        return env_override
    instance = os.getenv("AGENT_INSTANCE", "default")
    return str(get_instance_db_dir(instance))


def _get_default_db_name() -> str:
    """Resolve DB name lazily."""
    return os.getenv("LOCAL_STORE_DB", "instance.db")


def _resolve_db_path(db_dir: Optional[str] = None, db_name: Optional[str] = None) -> Path:
    """
    Resolve database file path (instance-aware via lazy env read).

    Args:
        db_dir: Database directory (default: auto-resolved from AGENT_INSTANCE)
        db_name: Database filename (default: instance.db or zenflux.db)

    Returns:
        Full database file path
    """
    directory = Path(db_dir or _get_default_db_dir())
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (db_name or _get_default_db_name())


def create_local_engine(
    db_dir: Optional[str] = None,
    db_name: Optional[str] = None,
    echo: bool = False,
) -> AsyncEngine:
    """
    创建 SQLite 异步引擎

    Args:
        db_dir: 数据库目录
        db_name: 数据库文件名
        echo: 是否输出 SQL 日志

    Returns:
        AsyncEngine 实例
    """
    db_path = _resolve_db_path(db_dir, db_name)
    url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(
        url,
        echo=echo or os.getenv("LOCAL_STORE_ECHO", "false").lower() == "true",
        # SQLite 不需要连接池配置，但 pool_size=1 + max_overflow=0 保证 WAL 安全
        pool_size=1,
        max_overflow=0,
    )

    # SQLite 连接初始化：启用 WAL、外键、性能参数
    # 参考 SQLite 官方最佳实践 https://www.sqlite.org/pragma.html
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")          # WAL 模式：支持并发读写
        cursor.execute("PRAGMA foreign_keys=ON")            # 启用外键约束
        cursor.execute("PRAGMA synchronous=NORMAL")         # WAL 模式下 NORMAL 即安全
        cursor.execute("PRAGMA cache_size=-64000")          # 64MB 页缓存
        cursor.execute("PRAGMA busy_timeout=5000")          # 5 秒忙等待（避免 SQLITE_BUSY）
        cursor.execute("PRAGMA temp_store=MEMORY")          # 临时表/索引放内存（桌面端内存充足）
        cursor.execute("PRAGMA mmap_size=268435456")        # 256MB 内存映射 I/O（提升读取性能）
        cursor.close()

    logger.info(f"SQLite 引擎已创建: {db_path}")
    return engine


def create_local_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    创建异步会话工厂

    Args:
        engine: AsyncEngine 实例

    Returns:
        async_sessionmaker 实例
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def init_local_database(engine: AsyncEngine):
    """
    初始化数据库（建表 + FTS5 虚拟表）

    在应用启动时调用。

    Args:
        engine: AsyncEngine 实例
    """
    from infra.local_store.models import LocalBase

    async with engine.begin() as conn:
        await conn.run_sync(LocalBase.metadata.create_all)

    # 创建 FTS5 虚拟表（SQLAlchemy 不直接支持，手动执行）
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                message_id UNINDEXED,
                conversation_id UNINDEXED,
                role UNINDEXED,
                text_content,
                tokenize='unicode61'
            )
        """))

    logger.info("SQLite 数据库初始化完成（含 FTS5）")


async def init_vector_extension(engine: AsyncEngine) -> bool:
    """
    尝试加载 sqlite-vec 扩展（可选）

    Returns:
        是否加载成功
    """
    try:
        import sqlite_vec

        vec_path = sqlite_vec.loadable_path()

        async with engine.begin() as conn:
            # sqlite-vec: use loadable_path() for reliable extension loading
            raw_conn = await conn.get_raw_connection()
            await raw_conn.driver_connection.enable_load_extension(True)
            await raw_conn.driver_connection.load_extension(vec_path)
            await raw_conn.driver_connection.enable_load_extension(False)

        logger.info("sqlite-vec 扩展加载成功")
        return True
    except ImportError:
        logger.info("sqlite-vec 未安装（可选功能，pip install sqlite-vec）")
        return False
    except Exception as e:
        logger.info(f"sqlite-vec 扩展不可用（可选功能，不影响运行）: {e}")
        return False


# ==================== 全局单例 ====================

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_vec_available: bool = False


async def get_local_engine() -> AsyncEngine:
    """获取全局 SQLite 引擎（懒初始化）"""
    global _engine
    if _engine is None:
        _engine = create_local_engine()
        await init_local_database(_engine)
        global _vec_available
        _vec_available = await init_vector_extension(_engine)
    return _engine


async def get_local_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取全局会话工厂（懒初始化）"""
    global _session_factory
    if _session_factory is None:
        engine = await get_local_engine()
        _session_factory = create_local_session_factory(engine)
    return _session_factory


async def get_local_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话（依赖注入）

    Yields:
        AsyncSession: SQLite 数据库会话
    """
    factory = await get_local_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


def is_vec_available() -> bool:
    """sqlite-vec 扩展是否可用"""
    return _vec_available


async def close_local_engine():
    """关闭 SQLite 引擎（应用退出时调用）"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("SQLite 引擎已关闭")
