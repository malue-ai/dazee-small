"""Test async instance_config_store using main engine."""
import pytest
import tempfile


@pytest.fixture
async def session_factory():
    """Create a temp engine and init DB for testing."""
    from infra.local_store.engine import (
        create_local_engine,
        init_local_database,
        create_local_session_factory,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = create_local_engine(db_dir=tmpdir, db_name="test.db")
        await init_local_database(engine)
        factory = create_local_session_factory(engine)
        yield factory
        await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_and_get(session_factory):
    from infra.local_store.instance_config_store import upsert, get_by_category

    async with session_factory() as session:
        await upsert(session, "inst1", "credential", "API_KEY", "sk-123")
        await session.commit()
    async with session_factory() as session:
        result = await get_by_category(session, "inst1", "credential")
        assert result == {"API_KEY": "sk-123"}


@pytest.mark.asyncio
async def test_upsert_overwrite(session_factory):
    from infra.local_store.instance_config_store import upsert, get_by_category

    async with session_factory() as session:
        await upsert(session, "inst1", "credential", "KEY", "old")
        await session.commit()
    async with session_factory() as session:
        await upsert(session, "inst1", "credential", "KEY", "new")
        await session.commit()
    async with session_factory() as session:
        result = await get_by_category(session, "inst1", "credential")
        assert result == {"KEY": "new"}


@pytest.mark.asyncio
async def test_invalid_category_ignored(session_factory):
    from infra.local_store.instance_config_store import upsert, get_all

    async with session_factory() as session:
        await upsert(session, "inst1", "invalid_cat", "KEY", "val")
        await session.commit()
    async with session_factory() as session:
        result = await get_all(session, "inst1")
        assert result == {}


@pytest.mark.asyncio
async def test_delete(session_factory):
    from infra.local_store.instance_config_store import upsert, delete, get_by_category

    async with session_factory() as session:
        await upsert(session, "inst1", "credential", "KEY", "val")
        await session.commit()
    async with session_factory() as session:
        deleted = await delete(session, "inst1", "credential", "KEY")
        await session.commit()
        assert deleted is True
    async with session_factory() as session:
        result = await get_by_category(session, "inst1", "credential")
        assert result == {}


@pytest.mark.asyncio
async def test_delete_nonexistent(session_factory):
    from infra.local_store.instance_config_store import delete

    async with session_factory() as session:
        deleted = await delete(session, "inst1", "credential", "NOPE")
        assert deleted is False


@pytest.mark.asyncio
async def test_get_all(session_factory):
    from infra.local_store.instance_config_store import upsert, get_all

    async with session_factory() as session:
        await upsert(session, "inst1", "credential", "K1", "V1")
        await upsert(session, "inst1", "setting", "K2", "V2")
        await session.commit()
    async with session_factory() as session:
        result = await get_all(session, "inst1")
        assert result == {"credential": {"K1": "V1"}, "setting": {"K2": "V2"}}


@pytest.mark.asyncio
async def test_check_fulfilled(session_factory):
    from infra.local_store.instance_config_store import upsert, check_fulfilled

    async with session_factory() as session:
        await upsert(session, "inst1", "credential", "KEY_A", "val")
        await session.commit()
    async with session_factory() as session:
        result = await check_fulfilled(session, "inst1", "credential", ["KEY_A", "KEY_B"])
        assert result == {"KEY_A": True, "KEY_B": False}


@pytest.mark.asyncio
async def test_list_keys(session_factory):
    from infra.local_store.instance_config_store import upsert, list_keys

    async with session_factory() as session:
        await upsert(session, "inst1", "credential", "K1", "V1")
        await upsert(session, "inst1", "credential", "K2", "V2")
        await upsert(session, "inst1", "setting", "K3", "V3")
        await session.commit()
    async with session_factory() as session:
        cred_keys = await list_keys(session, "inst1", "credential")
        assert set(cred_keys) == {"K1", "K2"}
    async with session_factory() as session:
        all_keys = await list_keys(session, "inst1")
        assert set(all_keys) == {"K1", "K2", "K3"}
