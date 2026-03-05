# 统一 SQLite 数据库 — 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 7+ 个散落的 SQLite 数据库文件合并为单一 `zenflux.db`，包含已有用户数据的无损迁移。

**Architecture:** 所有表统一到 `data/db/zenflux.db`，通过 `instance_id` 列区分实例数据。sqlite-vec 向量表通过表名后缀区分 embedding 模型。已有用户数据在应用启动时自动迁移（幂等、可重试、旧文件保留）。

**Tech Stack:** Python 3.12, SQLAlchemy 2.x (async), aiosqlite, sqlite-vec, FTS5

---

## Task 1: 新增 ORM 模型（instance_config, fragments, mem0_history）

**Files:**
- Modify: `infra/local_store/models.py`
- Test: `tests/unit/test_unified_db_models.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_unified_db_models.py
"""Verify new ORM models register correctly with LocalBase metadata."""
import pytest
from infra.local_store.models import (
    LocalBase,
    LocalInstanceConfig,
    LocalFragment,
    LocalMem0History,
)


def test_instance_config_table_name():
    assert LocalInstanceConfig.__tablename__ == "instance_config"


def test_instance_config_columns():
    cols = {c.name for c in LocalInstanceConfig.__table__.columns}
    assert {"id", "instance_id", "category", "key", "value", "skill_name", "source", "updated_at"} <= cols


def test_fragment_table_name():
    assert LocalFragment.__tablename__ == "fragments"


def test_fragment_has_instance_id():
    cols = {c.name for c in LocalFragment.__table__.columns}
    assert "instance_id" in cols


def test_mem0_history_table_name():
    assert LocalMem0History.__tablename__ == "mem0_history"


def test_mem0_history_has_instance_id():
    cols = {c.name for c in LocalMem0History.__table__.columns}
    assert "instance_id" in cols


def test_all_tables_in_metadata():
    table_names = set(LocalBase.metadata.tables.keys())
    assert "instance_config" in table_names
    assert "fragments" in table_names
    assert "mem0_history" in table_names
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_unified_db_models.py -v`
Expected: FAIL with ImportError (models don't exist yet)

**Step 3: Write minimal implementation**

Add to `infra/local_store/models.py` after `LocalIndexedFile`:

```python
class LocalInstanceConfig(LocalBase):
    """实例级配置（credential / package / permission / setting）"""

    __tablename__ = "instance_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="hitl")
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("idx_ic_unique", "instance_id", "category", "key", unique=True),
        Index("idx_ic_instance", "instance_id"),
        Index("idx_ic_category", "instance_id", "category"),
    )


class LocalFragment(LocalBase):
    """FragmentMemory 持久化"""

    __tablename__ = "fragments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    hints_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("idx_fragments_user_time", "user_id", "timestamp"),
        Index("idx_fragments_instance", "instance_id"),
    )


class LocalMem0History(LocalBase):
    """Mem0 操作历史"""

    __tablename__ = "mem0_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    memory_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    old_memory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_memory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("idx_mem0_history_instance", "instance_id"),
        Index("idx_mem0_history_memory", "memory_id"),
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_unified_db_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add infra/local_store/models.py tests/unit/test_unified_db_models.py
git commit -m "feat(db): add ORM models for instance_config, fragments, mem0_history"
```

---

## Task 2: 更新 engine.py — 在 init_local_database 中创建所有新表

**Files:**
- Modify: `infra/local_store/engine.py:148-175`
- Test: `tests/unit/test_engine_init.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_engine_init.py
"""Verify init_local_database creates all unified tables."""
import pytest
import tempfile
from pathlib import Path
from sqlalchemy import text


@pytest.fixture
async def temp_engine():
    from infra.local_store.engine import create_local_engine, init_local_database
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = create_local_engine(db_dir=tmpdir, db_name="test.db")
        await init_local_database(engine)
        yield engine
        await engine.dispose()


@pytest.mark.asyncio
async def test_all_tables_created(temp_engine):
    async with temp_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = {row[0] for row in result.fetchall()}

    expected = {
        "conversations", "messages", "scheduled_tasks", "skills_cache",
        "indexed_files", "cloud_tasks",
        "instance_config", "fragments", "mem0_history",
        "messages_fts", "memory_fts",
    }
    assert expected <= tables, f"Missing tables: {expected - tables}"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_engine_init.py -v`
Expected: FAIL (new tables not yet created by init_local_database)

**Step 3: Modify init_local_database**

In `infra/local_store/engine.py`, update `init_local_database` to also create the `memory_fts` FTS5 table:

```python
async def init_local_database(engine: AsyncEngine):
    from infra.local_store.models import LocalBase
    import core.cloud.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(LocalBase.metadata.create_all)

    async with engine.begin() as conn:
        # messages FTS5
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_engine_init.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add infra/local_store/engine.py tests/unit/test_engine_init.py
git commit -m "feat(db): init_local_database creates all unified tables including memory_fts"
```

---

## Task 3: 重写 instance_config_store — 同步 sqlite3 → 异步 SQLAlchemy

**Files:**
- Modify: `infra/local_store/instance_config_store.py` (full rewrite)
- Test: `tests/unit/test_instance_config_store.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_instance_config_store.py
"""Test async instance_config_store using main engine."""
import pytest
import tempfile
from pathlib import Path


@pytest.fixture
async def setup_engine():
    """Create a temp engine and init DB for testing."""
    from infra.local_store.engine import create_local_engine, init_local_database, create_local_session_factory
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = create_local_engine(db_dir=tmpdir, db_name="test.db")
        await init_local_database(engine)
        factory = create_local_session_factory(engine)
        yield factory
        await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_and_get(setup_engine):
    from infra.local_store.instance_config_store import upsert, get_by_category
    factory = setup_engine
    async with factory() as session:
        await upsert(session, "inst1", "credential", "API_KEY", "sk-123")
        await session.commit()
    async with factory() as session:
        result = await get_by_category(session, "inst1", "credential")
        assert result == {"API_KEY": "sk-123"}


@pytest.mark.asyncio
async def test_upsert_overwrite(setup_engine):
    from infra.local_store.instance_config_store import upsert, get_by_category
    factory = setup_engine
    async with factory() as session:
        await upsert(session, "inst1", "credential", "KEY", "old")
        await session.commit()
    async with factory() as session:
        await upsert(session, "inst1", "credential", "KEY", "new")
        await session.commit()
    async with factory() as session:
        result = await get_by_category(session, "inst1", "credential")
        assert result == {"KEY": "new"}


@pytest.mark.asyncio
async def test_delete(setup_engine):
    from infra.local_store.instance_config_store import upsert, delete, get_by_category
    factory = setup_engine
    async with factory() as session:
        await upsert(session, "inst1", "credential", "KEY", "val")
        await session.commit()
    async with factory() as session:
        deleted = await delete(session, "inst1", "credential", "KEY")
        await session.commit()
        assert deleted is True
    async with factory() as session:
        result = await get_by_category(session, "inst1", "credential")
        assert result == {}


@pytest.mark.asyncio
async def test_get_all(setup_engine):
    from infra.local_store.instance_config_store import upsert, get_all
    factory = setup_engine
    async with factory() as session:
        await upsert(session, "inst1", "credential", "K1", "V1")
        await upsert(session, "inst1", "setting", "K2", "V2")
        await session.commit()
    async with factory() as session:
        result = await get_all(session, "inst1")
        assert result == {"credential": {"K1": "V1"}, "setting": {"K2": "V2"}}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_instance_config_store.py -v`
Expected: FAIL (functions are still sync)

**Step 3: Rewrite instance_config_store.py**

Full rewrite of `infra/local_store/instance_config_store.py` — replace all sync `sqlite3` code with async SQLAlchemy using the main engine session:

```python
"""
统一实例级配置存储（Instance Config Store）

使用主引擎 zenflux.db 中的 instance_config 表。
所有函数接收 AsyncSession 参数，由调用方管理事务。
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from logger import get_logger

logger = get_logger("instance_config_store")

VALID_CATEGORIES = frozenset({"credential", "package", "permission", "setting"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def upsert(
    session: AsyncSession,
    instance_id: str,
    category: str,
    key: str,
    value: str,
    skill_name: str = "",
    source: str = "hitl",
) -> None:
    if category not in VALID_CATEGORIES:
        logger.warning("无效品类 %s，允许: %s", category, VALID_CATEGORIES)
        return
    now = _now_iso()
    await session.execute(
        sa_text("""
            INSERT INTO instance_config
                (instance_id, category, key, value, skill_name, source, updated_at)
            VALUES (:instance_id, :category, :key, :value, :skill_name, :source, :now)
            ON CONFLICT(instance_id, category, key)
            DO UPDATE SET value=:value, skill_name=:skill_name, source=:source, updated_at=:now
        """),
        {"instance_id": instance_id, "category": category, "key": key,
         "value": value, "skill_name": skill_name, "source": source, "now": now},
    )


async def delete(session: AsyncSession, instance_id: str, category: str, key: str) -> bool:
    result = await session.execute(
        sa_text("DELETE FROM instance_config WHERE instance_id=:iid AND category=:cat AND key=:key"),
        {"iid": instance_id, "cat": category, "key": key},
    )
    return result.rowcount > 0


async def get_by_category(session: AsyncSession, instance_id: str, category: str) -> Dict[str, str]:
    result = await session.execute(
        sa_text("SELECT key, value FROM instance_config WHERE instance_id=:iid AND category=:cat"),
        {"iid": instance_id, "cat": category},
    )
    return dict(result.fetchall())


async def get_all(session: AsyncSession, instance_id: str) -> Dict[str, Dict[str, str]]:
    result = await session.execute(
        sa_text("SELECT category, key, value FROM instance_config WHERE instance_id=:iid"),
        {"iid": instance_id},
    )
    out: Dict[str, Dict[str, str]] = {}
    for cat, k, v in result.fetchall():
        out.setdefault(cat, {})[k] = v
    return out


async def check_fulfilled(session: AsyncSession, instance_id: str, category: str, keys: List[str]) -> Dict[str, bool]:
    if not keys:
        return {}
    existing = await get_by_category(session, instance_id, category)
    return {k: bool(existing.get(k)) for k in keys}


async def list_keys(session: AsyncSession, instance_id: str, category: Optional[str] = None) -> List[str]:
    if category:
        result = await session.execute(
            sa_text("SELECT key FROM instance_config WHERE instance_id=:iid AND category=:cat"),
            {"iid": instance_id, "cat": category},
        )
    else:
        result = await session.execute(
            sa_text("SELECT key FROM instance_config WHERE instance_id=:iid"),
            {"iid": instance_id},
        )
    return [row[0] for row in result.fetchall()]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_instance_config_store.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add infra/local_store/instance_config_store.py tests/unit/test_instance_config_store.py
git commit -m "refactor(db): rewrite instance_config_store from sync sqlite3 to async SQLAlchemy"
```

---

## Task 4: 更新 instance_config_store 的所有调用方

**Files:**
- Modify: `utils/instance_loader.py` (lines ~834-835)
- Modify: `routers/skills.py` (line ~1056)
- Modify: `routers/settings.py` (lines ~337-363)
- Modify: `tools/configure_instance.py` (line ~48)

**Step 1: Read each caller and update**

每个调用方需要：
1. 获取 async session（通过 `get_local_session()` 或 `get_local_session_factory()`）
2. 将同步调用改为 `await`
3. 如果调用方本身是同步函数（如 `load_instance_env_from_config`），需要改为 async

**关键改动：**

- `utils/instance_loader.py` 中 `load_instance_env_from_config()` 从同步改为 async
  - 所有调用它的地方加 `await`
  - 同步脚本（`run_e2e_eval.py`, `run_e2e_auto.py`）用 `asyncio.run()` 包装
- `routers/settings.py` 和 `routers/skills.py` 已经是 async 路由，只需改调用方式
- `tools/configure_instance.py` 已经是 async，只需改调用方式

**Step 2: Run related tests**

Run: `pytest tests/ -k "instance_config or settings or skills" -v`
Expected: PASS

**Step 3: Commit**

```bash
git add utils/instance_loader.py routers/skills.py routers/settings.py tools/configure_instance.py
git commit -m "refactor(db): update all instance_config_store callers to async"
```

---

## Task 5: 重构 FragmentStore — 移除独立引擎，使用主引擎

**Files:**
- Modify: `core/memory/fragment_store.py`
- Test: `tests/unit/test_fragment_store.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_fragment_store.py
"""Test FragmentStore uses main engine (no independent DB file)."""
import pytest
import tempfile
from unittest.mock import patch


@pytest.mark.asyncio
async def test_fragment_store_uses_main_engine():
    from infra.local_store.engine import create_local_engine, init_local_database
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = create_local_engine(db_dir=tmpdir, db_name="test.db")
        await init_local_database(engine)

        with patch("infra.local_store.engine._engine", engine):
            from core.memory.fragment_store import FragmentStore
            store = FragmentStore(instance_name="test_inst")
            await store._ensure_engine()
            assert store._table_ready is True

        await engine.dispose()
```

**Step 2: Rewrite FragmentStore**

Remove independent engine creation. Instead, use the global engine from `get_local_engine()`. Add `instance_id` to all queries.

Key changes:
- Remove `_engine_cache`, `create_local_engine` calls
- Use `get_local_session_factory()` from main engine
- Add `instance_id` parameter to `save()`, `query_recent()`, `count_since()`
- Table is now created by `init_local_database` (Task 2), not by FragmentStore

**Step 3: Run test**

Run: `pytest tests/unit/test_fragment_store.py -v`
Expected: PASS

**Step 4: Update callers**

- `core/memory/instance_memory.py:386-387` — pass `instance_name` to `store.save()`
- `utils/background_tasks/tasks/persona_build.py:99-132` — pass `instance_name`

**Step 5: Commit**

```bash
git add core/memory/fragment_store.py tests/unit/test_fragment_store.py core/memory/instance_memory.py utils/background_tasks/tasks/persona_build.py
git commit -m "refactor(db): FragmentStore uses main engine with instance_id isolation"
```

---

## Task 6: 重构 InstanceMemoryManager FTS5 — 使用主引擎

**Files:**
- Modify: `core/memory/instance_memory.py` (lines ~510-690)

**Step 1: Modify _ensure_fts**

Remove independent engine creation for `memory_fts.db`. Instead, use the main engine. The `memory_fts` FTS5 table is now created by `init_local_database` (Task 2).

Key changes:
- Remove `_fts_engine_cache`, `create_local_engine` calls
- Use `get_local_session_factory()` for FTS sessions
- Remove `_fts_engine` and `_fts_session_factory` instance vars
- FTS queries remain the same (table name `memory_fts` unchanged)

**Step 2: Run existing memory tests**

Run: `pytest tests/ -k "memory" -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/memory/instance_memory.py
git commit -m "refactor(db): InstanceMemoryManager FTS5 uses main engine"
```

---

## Task 7: 重构 Mem0 sqlite_vec_store — 连接主 DB 文件

**Files:**
- Modify: `core/memory/mem0/sqlite_vec_store.py` (line ~110: `__init__`, `_create_connection`)
- Modify: `core/memory/mem0/pool.py` (lines ~181-264)
- Modify: `core/memory/mem0/config.py` (remove `db_path`, `history_db_name`)

**Step 1: Modify sqlite_vec_store.py**

Change `__init__` to accept `db_path` pointing to `zenflux.db` instead of per-model DB files. The collection/table name already includes the model tag, so different models are isolated by table name within the same DB.

Key changes in `__init__`:
- `db_path` now points to `zenflux.db`
- `_ensure_table` creates `mem0_vec_{collection_name}` table in the shared DB
- FTS5 table name also scoped: `mem0_fts_{collection_name}`

**Step 2: Modify pool.py**

Change `_create_memory` to:
- Get `db_path` from `get_shared_db_dir() / "zenflux.db"` instead of per-instance store dir
- Pass shared DB path to `SqliteVecVectorStore`
- Pass shared DB path to `SQLiteManager` (Mem0 history)

**Step 3: Modify config.py**

- Remove `db_path` property
- Remove `history_db_name` property
- Add helper to get shared DB path

**Step 4: Run Mem0 tests**

Run: `pytest tests/ -k "mem0" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/memory/mem0/sqlite_vec_store.py core/memory/mem0/pool.py core/memory/mem0/config.py
git commit -m "refactor(db): Mem0 vector store and history use shared zenflux.db"
```

---

## Task 8: 重构 PlaybookManager — 连接主 DB 文件

**Files:**
- Modify: `core/playbook/manager.py` (line ~293)

**Step 1: Modify _get_vector_store**

Change `db_path` from `get_instance_playbook_vectors_path()` to shared `zenflux.db`. Use `playbook_vec_{instance_name}` as collection name for isolation.

**Step 2: Run playbook tests**

Run: `pytest tests/ -k "playbook" -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/playbook/manager.py
git commit -m "refactor(db): PlaybookManager vector store uses shared zenflux.db"
```

---

## Task 9: 编写统一迁移脚本

**Files:**
- Create: `scripts/migrate_to_unified_db.py`
- Test: `tests/unit/test_migrate_unified.py`

**Step 1: Write migration script**

The script handles:

1. **instance_config.db → instance_config 表**
   - 读取旧 `db/instance_config.db`
   - INSERT OR IGNORE 到 zenflux.db 的 `instance_config` 表

2. **fragments.db → fragments 表**（每实例）
   - 遍历 `data/instances/*/store/fragments.db`
   - 读取所有行，加 `instance_id` 列
   - INSERT OR IGNORE 到 zenflux.db

3. **memory_fts.db → memory_fts 表**（每实例）
   - 遍历 `data/instances/*/store/memory_fts.db`
   - FTS5 数据需要逐行读取 + 重新插入

4. **mem0_vectors_{tag}.db → mem0_vec_{tag} 表**（每实例*每模型）
   - 遍历 `data/instances/*/store/mem0_vectors_*.db`
   - 通过 sqlite-vec API 读取向量 + payload
   - 在 zenflux.db 中创建对应虚拟表并写入
   - sqlite-vec 不可用时跳过（向量可重建）

5. **mem0_history.db → mem0_history 表**（每实例）
   - 遍历 `data/instances/*/store/mem0_history.db`
   - 读取 `history` 表，加 `instance_id`
   - INSERT OR IGNORE

6. **playbook_vectors.db**（每实例）
   - 同 mem0_vectors 处理方式

Safety:
- Marker file: `.migrated_to_unified_db` per source DB
- INSERT OR IGNORE for idempotency
- Old files preserved (not deleted)
- Logged with counts

**Step 2: Write test**

```python
# tests/unit/test_migrate_unified.py
"""Test unified DB migration script."""
import pytest
import sqlite3
import tempfile
from pathlib import Path


@pytest.mark.asyncio
async def test_migrate_instance_config():
    """Verify instance_config.db data migrates to zenflux.db."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create old instance_config.db
        old_db = Path(tmpdir) / "db" / "instance_config.db"
        old_db.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(old_db))
        conn.execute("""
            CREATE TABLE instance_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT, category TEXT, key TEXT,
                value TEXT, skill_name TEXT, source TEXT, updated_at TEXT,
                UNIQUE(instance_id, category, key)
            )
        """)
        conn.execute(
            "INSERT INTO instance_config (instance_id, category, key, value, skill_name, source, updated_at) "
            "VALUES ('inst1', 'credential', 'API_KEY', 'sk-test', '', 'hitl', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        # Create zenflux.db with schema
        from infra.local_store.engine import create_local_engine, init_local_database
        shared_dir = Path(tmpdir) / "data" / "db"
        shared_dir.mkdir(parents=True)
        engine = create_local_engine(db_dir=str(shared_dir), db_name="zenflux.db")
        await init_local_database(engine)

        # Run migration
        from scripts.migrate_to_unified_db import migrate_instance_config
        count = migrate_instance_config(str(old_db), str(shared_dir / "zenflux.db"))
        assert count == 1

        # Verify
        verify_conn = sqlite3.connect(str(shared_dir / "zenflux.db"))
        row = verify_conn.execute("SELECT value FROM instance_config WHERE key='API_KEY'").fetchone()
        assert row[0] == "sk-test"
        verify_conn.close()

        await engine.dispose()
```

**Step 3: Run test**

Run: `pytest tests/unit/test_migrate_unified.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add scripts/migrate_to_unified_db.py tests/unit/test_migrate_unified.py
git commit -m "feat(db): add unified DB migration script with idempotent data transfer"
```

---

## Task 10: 集成到 main.py 启动流程

**Files:**
- Modify: `main.py` (line ~111-125: `_init_local_store`)

**Step 1: Update _init_local_store**

```python
async def _init_local_store() -> None:
    """初始化本地存储（SQLite 统一引擎 + 数据迁移）"""
    print("💾 初始化本地存储...")
    try:
        from infra.local_store.engine import get_local_engine
        await get_local_engine()

        # 旧版实例 DB → 共享 DB（已有迁移）
        from scripts.migrate_to_shared_db import auto_migrate
        if auto_migrate():
            print("📦 已完成旧实例数据迁移")

        # 多 DB → 统一 DB（新迁移）
        from scripts.migrate_to_unified_db import auto_migrate_to_unified_db
        if auto_migrate_to_unified_db():
            print("📦 已完成数据库统一迁移")

        print("✅ 本地存储就绪（统一引擎模式）")
    except Exception as e:
        print(f"❌ 本地存储初始化失败: {e}", flush=True)
```

**Step 2: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: PASS

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat(db): integrate unified DB migration into startup flow"
```

---

## Task 11: 清理废弃路径和代码

**Files:**
- Modify: `utils/app_paths.py` — deprecate `get_instance_db_dir`, `get_instance_playbook_vectors_path`
- Modify: `core/memory/mem0/config.py` — remove `db_path`, `history_db_name` properties
- Remove or deprecate: old migration marker checks

**Step 1: Add deprecation warnings**

```python
# In utils/app_paths.py
import warnings

def get_instance_playbook_vectors_path(instance_name: str) -> Path:
    """DEPRECATED: Playbook vectors now stored in zenflux.db."""
    warnings.warn(
        "get_instance_playbook_vectors_path is deprecated. "
        "Playbook vectors are now in zenflux.db.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_instance_store_dir(instance_name) / "playbook_vectors.db"
```

**Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: PASS (no breakage from deprecation warnings)

**Step 3: Commit**

```bash
git add utils/app_paths.py core/memory/mem0/config.py
git commit -m "chore(db): deprecate old per-instance DB path helpers"
```

---

## Task 12: 端到端验证

**Step 1: Start dev server**

Run: `make dev` (or `python main.py`)
Expected: Server starts, migration runs, all tables created

**Step 2: Verify migration logs**

Check logs for:
- "SQLite 数据库初始化完成（含 FTS5 + 统一表）"
- "已完成数据库统一迁移" (if old data exists)

**Step 3: Verify single DB file**

```bash
ls -la data/db/zenflux.db
sqlite3 data/db/zenflux.db ".tables"
```

Expected: All tables visible in single file

**Step 4: Run full test suite**

Run: `make test` or `pytest tests/ -v`
Expected: All tests PASS

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat(db): complete unified SQLite DB migration — 7+ files → 1"
```
