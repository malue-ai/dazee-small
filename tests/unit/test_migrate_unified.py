"""Test unified DB migration script."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from infra.local_store.engine import create_local_engine, init_local_database


@pytest.mark.asyncio
async def test_migrate_instance_config():
    """Verify instance_config.db data migrates to zenflux.db."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create old instance_config.db
        old_db = Path(tmpdir) / "old_ic.db"
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
        zen_dir = Path(tmpdir) / "zen"
        zen_dir.mkdir()
        engine = create_local_engine(db_dir=str(zen_dir), db_name="zenflux.db")
        await init_local_database(engine)
        await engine.dispose()

        # Run migration
        from scripts.migrate_to_unified_db import migrate_instance_config

        count = migrate_instance_config(str(old_db), str(zen_dir / "zenflux.db"))
        assert count == 1

        # Verify
        verify_conn = sqlite3.connect(str(zen_dir / "zenflux.db"))
        row = verify_conn.execute(
            "SELECT value FROM instance_config WHERE key='API_KEY'"
        ).fetchone()
        assert row[0] == "sk-test"
        verify_conn.close()


@pytest.mark.asyncio
async def test_migrate_fragments():
    """Verify fragments.db data migrates with instance_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create old fragments.db (no instance_id column)
        old_db = Path(tmpdir) / "old_frag.db"
        conn = sqlite3.connect(str(old_db))
        conn.execute("""
            CREATE TABLE fragments (
                id TEXT PRIMARY KEY, user_id TEXT, session_id TEXT,
                timestamp TEXT, confidence REAL, hints_json TEXT,
                metadata_json TEXT, created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO fragments VALUES ('f1', 'u1', 's1', '2026-01-01', 0.9, '[]', '{}', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        # Create zenflux.db
        zen_dir = Path(tmpdir) / "zen"
        zen_dir.mkdir()
        engine = create_local_engine(db_dir=str(zen_dir), db_name="zenflux.db")
        await init_local_database(engine)
        await engine.dispose()

        # Run migration
        from scripts.migrate_to_unified_db import migrate_fragments

        count = migrate_fragments(
            str(old_db), str(zen_dir / "zenflux.db"), "test_instance"
        )
        assert count == 1

        # Verify instance_id was added
        verify_conn = sqlite3.connect(str(zen_dir / "zenflux.db"))
        row = verify_conn.execute(
            "SELECT instance_id FROM fragments WHERE id='f1'"
        ).fetchone()
        assert row[0] == "test_instance"
        verify_conn.close()


@pytest.mark.asyncio
async def test_migrate_idempotent():
    """Verify running migration twice doesn't duplicate data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_db = Path(tmpdir) / "old_ic.db"
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
            "VALUES ('inst1', 'credential', 'KEY', 'val', '', 'hitl', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        zen_dir = Path(tmpdir) / "zen"
        zen_dir.mkdir()
        engine = create_local_engine(db_dir=str(zen_dir), db_name="zenflux.db")
        await init_local_database(engine)
        await engine.dispose()

        from scripts.migrate_to_unified_db import migrate_instance_config

        count1 = migrate_instance_config(str(old_db), str(zen_dir / "zenflux.db"))
        count2 = migrate_instance_config(str(old_db), str(zen_dir / "zenflux.db"))
        assert count1 == 1
        assert count2 == 1  # INSERT OR IGNORE still counts attempted rows

        verify_conn = sqlite3.connect(str(zen_dir / "zenflux.db"))
        total = verify_conn.execute(
            "SELECT COUNT(*) FROM instance_config"
        ).fetchone()[0]
        assert total == 1  # Only 1 row, not 2
        verify_conn.close()
