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
from sqlalchemy.pool import NullPool

from logger import get_logger
from utils.app_paths import get_shared_db_dir

logger = get_logger("local_store.engine")

_vec_loadable_path: Optional[str] = None

SHARED_DB_NAME = "zenflux.db"


def _get_default_db_dir() -> str:
    """Return the shared database directory (instance-independent)."""
    env_override = os.getenv("LOCAL_STORE_DIR")
    if env_override:
        return env_override
    return str(get_shared_db_dir())


def _get_default_db_name() -> str:
    """Return the shared database filename."""
    env_override = os.getenv("LOCAL_STORE_DB")
    if env_override:
        return env_override
    return SHARED_DB_NAME


def _resolve_db_path(db_dir: Optional[str] = None, db_name: Optional[str] = None) -> Path:
    """
    Resolve database file path.

    Args:
        db_dir: Database directory (default: shared dir data/db/)
        db_name: Database filename (default: zenflux.db)

    Returns:
        Full database file path
    """
    directory = Path(db_dir or _get_default_db_dir())
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (db_name or _get_default_db_name())


def _load_vec_on_connect(dbapi_conn) -> None:
    """Load sqlite-vec extension on a DBAPI connection.

    With NullPool, each operation gets a fresh sqlite3 connection.
    SQLite extensions are per-connection, so we must reload on each connect.

    The dbapi_conn from SQLAlchemy's aiosqlite adapter is NOT a raw
    sqlite3.Connection — we must unwrap through the adapter chain:
      AsyncAdapt_aiosqlite_connection._connection  (aiosqlite.Connection)
        ._conn  (sqlite3.Connection)
    """
    try:
        aio_conn = getattr(dbapi_conn, "_connection", None)
        if aio_conn is None:
            return
        raw_conn = getattr(aio_conn, "_conn", None)
        if raw_conn is None:
            return
        raw_conn.enable_load_extension(True)
        raw_conn.load_extension(_vec_loadable_path)
        raw_conn.enable_load_extension(False)
    except Exception as e:
        logger.warning(f"连接级 sqlite-vec 加载失败: {e}")


def create_local_engine(
    db_dir: Optional[str] = None,
    db_name: Optional[str] = None,
    echo: bool = False,
) -> AsyncEngine:
    """
    创建 SQLite 异步引擎

    统一使用 NullPool：每次操作新建连接、用完即关。
    aiosqlite + QueuePool 在 async 上下文切换时会因连接未归还导致死锁，
    NullPool 彻底避免此问题。SQLite 连接创建仅打开文件句柄（微秒级），
    配合 WAL 模式 + busy_timeout 可安全并发读写。

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
        poolclass=NullPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=268435456")
        except Exception as e:
            logger.warning(f"PRAGMA 设置失败（数据库可能只读或损坏）: {e}")
        finally:
            cursor.close()

        if _vec_loadable_path:
            _load_vec_on_connect(dbapi_conn)

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
    import core.cloud.models  # noqa: F401 — 确保 cloud_tasks 表模型注册到 metadata

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
        # memory FTS5 (previously in separate memory_fts.db)
        await conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                entry_id UNINDEXED,
                section,
                content,
                category UNINDEXED,
                source UNINDEXED,
                tokenize='unicode61 remove_diacritics 2'
            )
        """))

    logger.info("SQLite 数据库初始化完成（含 FTS5 + 统一表）")


async def init_vector_extension(engine: AsyncEngine) -> bool:
    """
    探测 sqlite-vec 扩展并注册到全局变量，使后续每个新连接自动加载。

    NullPool 下每次操作新建连接，因此扩展必须在 connect 事件中重复加载，
    而非只在初始化连接上加载一次。

    Returns:
        是否可用
    """
    global _vec_loadable_path
    try:
        import sqlite_vec

        vec_path = sqlite_vec.loadable_path()

        async with engine.begin() as conn:
            raw_conn = await conn.get_raw_connection()
            driver = raw_conn.driver_connection
            if driver is None:
                raise RuntimeError("driver_connection is None")
            await driver.enable_load_extension(True)
            await driver.load_extension(vec_path)
            await driver.enable_load_extension(False)

        _vec_loadable_path = vec_path
        logger.info("sqlite-vec 扩展加载成功（已注册到 connect 事件）")
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
    """获取全局 SQLite 引擎（懒初始化，使用共享 DB 路径）"""
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
    global _engine, _session_factory, _vec_available, _vec_loadable_path
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        _vec_available = False
        _vec_loadable_path = None
        logger.info("SQLite 引擎已关闭")


async def reload_local_engine() -> None:
    """
    重新加载 SQLite 引擎（用于依赖变更后重新检测扩展）
    
    Use case: 用户在运行时安装了 sqlite-vec 依赖，需要重新检测扩展可用性。
    关闭旧引擎并清理全局状态，下次 get_local_engine() 时会重新初始化。

    DB 路径为固定的共享路径 (data/db/zenflux.db)，不依赖 AGENT_INSTANCE，
    因此 reload 不会导致路径漂移。
    """
    global _engine, _session_factory, _vec_available, _vec_loadable_path
    if _engine is not None:
        await _engine.dispose()
        logger.info("SQLite 引擎已关闭，准备重新加载")
    _engine = None
    _session_factory = None
    _vec_available = False
    _vec_loadable_path = None
    
    await get_local_engine()
    logger.info(f"SQLite 引擎已重新加载 (vec_available={_vec_available})")
