"""
Tests for infra/local_store/engine.py

Verifies that the global engine always uses the shared fixed path
(data/db/zenflux.db) and is independent of AGENT_INSTANCE.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from infra.local_store.engine import (
    SHARED_DB_NAME,
    close_local_engine,
    get_local_engine,
    reload_local_engine,
)


@pytest.fixture(autouse=True)
async def _clean_engine():
    """Ensure engine globals are clean before and after each test."""
    await close_local_engine()
    yield
    await close_local_engine()


async def test_engine_uses_shared_db_path():
    """Global engine should always point to zenflux.db, not instance-specific DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shared_dir = Path(tmpdir) / "data" / "db"
        shared_dir.mkdir(parents=True)

        with patch("infra.local_store.engine._get_default_db_dir", return_value=str(shared_dir)), \
             patch("infra.local_store.engine._get_default_db_name", return_value=SHARED_DB_NAME):
            engine = await get_local_engine()
            url = str(engine.url)

        assert SHARED_DB_NAME in url, f"Engine URL should contain {SHARED_DB_NAME}, got: {url}"
        assert "data/db" in url or "data\\db" in url, f"Engine should use shared dir, got: {url}"


async def test_reload_keeps_same_shared_path():
    """reload_local_engine() should reopen the same shared DB path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shared_dir = Path(tmpdir) / "data" / "db"
        shared_dir.mkdir(parents=True)

        with patch("infra.local_store.engine._get_default_db_dir", return_value=str(shared_dir)), \
             patch("infra.local_store.engine._get_default_db_name", return_value=SHARED_DB_NAME):
            engine1 = await get_local_engine()
            url1 = str(engine1.url)

            await reload_local_engine()

            engine2 = await get_local_engine()
            url2 = str(engine2.url)

        assert url1 == url2, (
            f"reload should produce same URL.\n"
            f"  Before: {url1}\n"
            f"  After:  {url2}"
        )


async def test_engine_independent_of_agent_instance():
    """Changing AGENT_INSTANCE env var should NOT affect the engine path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shared_dir = Path(tmpdir) / "data" / "db"
        shared_dir.mkdir(parents=True)

        with patch("infra.local_store.engine._get_default_db_dir", return_value=str(shared_dir)), \
             patch("infra.local_store.engine._get_default_db_name", return_value=SHARED_DB_NAME):

            with patch.dict("os.environ", {"AGENT_INSTANCE": "instance_a"}):
                engine1 = await get_local_engine()
                url1 = str(engine1.url)

            assert SHARED_DB_NAME in url1
            assert "instance_a" not in url1, (
                f"Engine should not contain instance name, got: {url1}"
            )
