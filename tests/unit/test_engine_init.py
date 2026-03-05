"""Verify init_local_database creates all unified tables."""
import pytest
import tempfile
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
