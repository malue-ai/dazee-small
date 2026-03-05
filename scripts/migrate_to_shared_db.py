"""
迁移脚本：将各实例独立 DB 合并到共享 DB (data/db/zenflux.db)

背景：
    旧架构下每个实例有独立的 {instance}/db/{instance}.db，
    新架构统一使用 data/db/zenflux.db。

    此脚本将旧实例 DB 中的 conversations、messages、scheduled_tasks
    合并到共享 DB，并为 scheduled_tasks 补充 instance_id 列。

用法：
    - 自动：应用启动时由 main.py 调用 auto_migrate()
    - 手动：python scripts/migrate_to_shared_db.py
"""

import sqlite3
import sys
from pathlib import Path

# Allow running as standalone script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logger import get_logger
from utils.app_paths import get_instance_db_dir, get_shared_db_dir, get_user_data_dir

logger = get_logger("migrate_to_shared_db")

TABLES_TO_MIGRATE = ["conversations", "messages", "scheduled_tasks", "skills_cache", "indexed_files"]
MIGRATION_MARKER = ".migrated_to_shared_db"

# SQLAlchemy uses Python-side defaults (not SQL DEFAULT), so NOT NULL columns
# without SQL defaults need explicit values during raw-SQL migration.
_NOT_NULL_DEFAULTS: dict[str, dict[str, str]] = {
    "conversations": {"status": "active", "metadata": "{}"},
    "scheduled_tasks": {"instance_id": "default"},
    "messages": {"status": "complete"},
}


def _find_instance_dbs() -> list[tuple[str, Path]]:
    """Find all legacy per-instance DB files."""
    instances_dir = get_user_data_dir() / "data" / "instances"
    if not instances_dir.exists():
        return []

    results = []
    for instance_dir in instances_dir.iterdir():
        if not instance_dir.is_dir():
            continue
        db_dir = instance_dir / "db"
        if not db_dir.exists():
            continue
        for db_file in db_dir.glob("*.db"):
            if db_file.name == "zenflux.db":
                continue
            instance_name = instance_dir.name
            results.append((instance_name, db_file))
    return results


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _get_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    cursor = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
    return cursor.fetchone()[0]


def _migrate_instance(instance_name: str, src_path: Path, dst_path: Path) -> int:
    """
    Migrate data from one instance DB to the shared DB.

    Returns number of rows migrated.
    """
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))
    total = 0

    try:
        dst.execute("PRAGMA journal_mode=WAL")
        dst.execute("PRAGMA foreign_keys=OFF")

        for table in TABLES_TO_MIGRATE:
            if not _table_exists(src, table):
                continue

            src_count = _get_row_count(src, table)
            if src_count == 0:
                continue

            src_columns = [
                row[1] for row in src.execute(f"PRAGMA table_info([{table}])").fetchall()
            ]

            if not _table_exists(dst, table):
                logger.warning(f"  目标表 {table} 不存在，跳过")
                continue

            dst_columns = [
                row[1] for row in dst.execute(f"PRAGMA table_info([{table}])").fetchall()
            ]

            common_columns = [c for c in src_columns if c in dst_columns]
            if not common_columns:
                continue

            # Detect NOT NULL dst columns missing from src; supply defaults
            dst_col_info = {
                row[1]: {"notnull": bool(row[3]), "default": row[4]}
                for row in dst.execute(f"PRAGMA table_info([{table}])").fetchall()
            }
            extra_cols = []
            extra_vals = []
            table_defaults = _NOT_NULL_DEFAULTS.get(table, {})
            for col_name, info in dst_col_info.items():
                if col_name in common_columns:
                    continue
                if info["notnull"] and info["default"] is None:
                    default_val = table_defaults.get(col_name)
                    if default_val is not None:
                        extra_cols.append(col_name)
                        extra_vals.append(default_val)

            all_columns = common_columns + extra_cols
            col_list = ", ".join(f"[{c}]" for c in all_columns)
            placeholders = ", ".join("?" for _ in all_columns)

            src_col_list = ", ".join(f"[{c}]" for c in common_columns)
            rows = src.execute(f"SELECT {src_col_list} FROM [{table}]").fetchall()

            migrated = 0
            for row in rows:
                full_row = tuple(row) + tuple(extra_vals)
                try:
                    dst.execute(
                        f"INSERT OR IGNORE INTO [{table}] ({col_list}) VALUES ({placeholders})",
                        full_row,
                    )
                    migrated += 1
                except sqlite3.IntegrityError:
                    pass

            if table == "scheduled_tasks" and "instance_id" in dst_columns:
                dst.execute(
                    "UPDATE scheduled_tasks SET instance_id = ? WHERE instance_id = 'default'",
                    (instance_name,),
                )

            dst.commit()
            total += migrated
            logger.info(f"  {table}: {migrated}/{src_count} 行迁移完成")

    finally:
        src.close()
        dst.close()

    return total


def auto_migrate() -> bool:
    """
    Auto-detect and migrate legacy instance DBs to the shared DB.

    Called at application startup. Only runs once per instance DB
    (tracks completion via marker files).

    Returns True if any migration was performed.
    """
    shared_db_dir = get_shared_db_dir()
    shared_db_path = shared_db_dir / "zenflux.db"

    instance_dbs = _find_instance_dbs()
    if not instance_dbs:
        return False

    migrated_any = False

    for instance_name, src_path in instance_dbs:
        marker = src_path.parent / MIGRATION_MARKER
        if marker.exists():
            continue

        if not shared_db_path.exists():
            logger.info(f"共享 DB 尚未创建，跳过迁移（将在引擎初始化后创建）")
            return False

        logger.info(f"迁移实例 DB: {instance_name} ({src_path})")
        try:
            count = _migrate_instance(instance_name, src_path, shared_db_path)
            marker.write_text(f"migrated {count} rows\n")
            logger.info(f"实例 {instance_name} 迁移完成: {count} 行")
            migrated_any = True
        except Exception as e:
            logger.error(f"迁移实例 {instance_name} 失败: {e}", exc_info=True)

    return migrated_any


if __name__ == "__main__":
    print("=== 迁移旧实例 DB 到共享 DB ===")
    result = auto_migrate()
    if result:
        print("迁移完成")
    else:
        print("无需迁移")
