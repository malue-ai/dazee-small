"""
Tests for infra/local_store/engine.py

Verifies that reload_local_engine() preserves the original DB path
even when AGENT_INSTANCE has been switched to a different instance.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from infra.local_store.engine import (
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


async def test_reload_preserves_db_path():
    """reload_local_engine() must reopen the same DB, not follow AGENT_INSTANCE."""
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_a_dir = Path(tmpdir) / "instance_a" / "db"
        instance_a_dir.mkdir(parents=True)
        instance_b_dir = Path(tmpdir) / "instance_b" / "db"
        instance_b_dir.mkdir(parents=True)

        def mock_db_dir_a():
            return str(instance_a_dir)

        def mock_db_dir_b():
            return str(instance_b_dir)

        with patch("infra.local_store.engine._get_default_db_dir", mock_db_dir_a), \
             patch("infra.local_store.engine._get_default_db_name", return_value="a.db"):
            engine1 = await get_local_engine()
            url1 = str(engine1.url)

        assert "instance_a" in url1
        assert "a.db" in url1

        with patch("infra.local_store.engine._get_default_db_dir", mock_db_dir_b), \
             patch("infra.local_store.engine._get_default_db_name", return_value="b.db"):
            await reload_local_engine()
            engine2 = await get_local_engine()
            url2 = str(engine2.url)

        assert url1 == url2, (
            f"reload_local_engine() should preserve DB path.\n"
            f"  Before: {url1}\n"
            f"  After:  {url2}"
        )


async def test_close_then_reopen_uses_new_instance():
    """After close_local_engine(), the next get_local_engine() should re-resolve paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_a_dir = Path(tmpdir) / "instance_a" / "db"
        instance_a_dir.mkdir(parents=True)
        instance_b_dir = Path(tmpdir) / "instance_b" / "db"
        instance_b_dir.mkdir(parents=True)

        with patch("infra.local_store.engine._get_default_db_dir", return_value=str(instance_a_dir)), \
             patch("infra.local_store.engine._get_default_db_name", return_value="a.db"):
            engine1 = await get_local_engine()
            url1 = str(engine1.url)

        await close_local_engine()

        with patch("infra.local_store.engine._get_default_db_dir", return_value=str(instance_b_dir)), \
             patch("infra.local_store.engine._get_default_db_name", return_value="b.db"):
            engine2 = await get_local_engine()
            url2 = str(engine2.url)

        assert "instance_a" in url1
        assert "instance_b" in url2, (
            "After close_local_engine(), re-opening should use new AGENT_INSTANCE path."
        )
