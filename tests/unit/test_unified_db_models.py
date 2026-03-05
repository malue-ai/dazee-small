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


def test_fragment_columns():
    cols = {c.name for c in LocalFragment.__table__.columns}
    assert {"id", "instance_id", "user_id", "session_id", "timestamp", "confidence", "hints_json", "metadata_json", "created_at"} <= cols


def test_mem0_history_table_name():
    assert LocalMem0History.__tablename__ == "mem0_history"


def test_mem0_history_columns():
    cols = {c.name for c in LocalMem0History.__table__.columns}
    assert {"id", "instance_id", "memory_id", "old_memory", "new_memory", "event", "created_at", "is_deleted"} <= cols


def test_all_tables_in_metadata():
    table_names = set(LocalBase.metadata.tables.keys())
    assert "instance_config" in table_names
    assert "fragments" in table_names
    assert "mem0_history" in table_names
