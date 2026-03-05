"""
统一数据库迁移脚本：多 DB 文件 → zenflux.db

迁移源：
  - data/db/instance_config.db → instance_config 表
  - data/instances/{name}/store/fragments.db → fragments 表
  - data/instances/{name}/store/memory_fts.db → memory_fts 表
  - data/instances/{name}/store/mem0_history.db → mem0_history 表

安全机制：
  - 每个源 DB 迁移后写入 marker 文件 (.migrated_to_unified_db)
  - 使用 INSERT OR IGNORE 保证幂等
  - 旧文件保留不删除
  - 失败时记录日志，不中断其他迁移
"""

import sqlite3
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logger import get_logger
from utils.app_paths import get_shared_db_dir, get_user_data_dir

logger = get_logger("migrate_to_unified_db")

MIGRATION_MARKER = ".migrated_to_unified_db"


def _is_migrated(db_path: Path) -> bool:
    marker = db_path.parent / f"{db_path.stem}{MIGRATION_MARKER}"
    return marker.exists()


def _mark_migrated(db_path: Path, count: int) -> None:
    marker = db_path.parent / f"{db_path.stem}{MIGRATION_MARKER}"
    marker.write_text(f"migrated {count} rows\n")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def migrate_instance_config(src_path: str, dst_path: str) -> int:
    """Migrate instance_config.db → zenflux.db instance_config table."""
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    count = 0
    try:
        dst.execute("PRAGMA journal_mode=WAL")
        if not _table_exists(src, "instance_config"):
            return 0
        rows = src.execute(
            "SELECT instance_id, category, key, value, skill_name, source, updated_at "
            "FROM instance_config"
        ).fetchall()
        for row in rows:
            try:
                dst.execute(
                    "INSERT OR IGNORE INTO instance_config "
                    "(instance_id, category, key, value, skill_name, source, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
                count += 1
            except sqlite3.IntegrityError:
                pass
        dst.commit()
    finally:
        src.close()
        dst.close()
    return count


def migrate_fragments(src_path: str, dst_path: str, instance_id: str) -> int:
    """Migrate fragments.db → zenflux.db fragments table."""
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    count = 0
    try:
        dst.execute("PRAGMA journal_mode=WAL")
        if not _table_exists(src, "fragments"):
            return 0
        rows = src.execute(
            "SELECT id, user_id, session_id, timestamp, confidence, "
            "hints_json, metadata_json, created_at FROM fragments"
        ).fetchall()
        for row in rows:
            try:
                dst.execute(
                    "INSERT OR IGNORE INTO fragments "
                    "(id, instance_id, user_id, session_id, timestamp, confidence, "
                    "hints_json, metadata_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row[0], instance_id) + row[1:],
                )
                count += 1
            except sqlite3.IntegrityError:
                pass
        dst.commit()
    finally:
        src.close()
        dst.close()
    return count


def migrate_memory_fts(src_path: str, dst_path: str) -> int:
    """Migrate memory_fts.db → zenflux.db memory_fts table."""
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    count = 0
    try:
        dst.execute("PRAGMA journal_mode=WAL")
        if not _table_exists(src, "memory_fts"):
            return 0
        rows = src.execute(
            "SELECT entry_id, section, content, category, source FROM memory_fts"
        ).fetchall()
        for row in rows:
            try:
                dst.execute(
                    "INSERT INTO memory_fts (entry_id, section, content, category, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    row,
                )
                count += 1
            except sqlite3.IntegrityError:
                pass
        dst.commit()
    finally:
        src.close()
        dst.close()
    return count


def migrate_mem0_history(src_path: str, dst_path: str, instance_id: str) -> int:
    """Migrate mem0_history.db → zenflux.db mem0_history table."""
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    count = 0
    try:
        dst.execute("PRAGMA journal_mode=WAL")
        if not _table_exists(src, "history"):
            return 0
        rows = src.execute(
            "SELECT id, memory_id, old_memory, new_memory, event, created_at, is_deleted "
            "FROM history"
        ).fetchall()
        for row in rows:
            try:
                dst.execute(
                    "INSERT OR IGNORE INTO mem0_history "
                    "(id, instance_id, memory_id, old_memory, new_memory, event, created_at, is_deleted) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (row[0], instance_id) + row[1:],
                )
                count += 1
            except sqlite3.IntegrityError:
                pass
        dst.commit()
    finally:
        src.close()
        dst.close()
    return count


def auto_migrate_to_unified_db() -> bool:
    """
    Auto-detect and migrate old DB files to unified zenflux.db.

    Called at application startup. Idempotent via marker files.
    Returns True if any migration was performed.
    """
    shared_db_dir = get_shared_db_dir()
    dst_path = str(shared_db_dir / "zenflux.db")

    if not Path(dst_path).exists():
        logger.info("zenflux.db 尚未创建，跳过统一迁移")
        return False

    migrated_any = False
    user_data = get_user_data_dir()

    # 1. instance_config.db
    ic_path = user_data / "data" / "db" / "instance_config.db"
    if ic_path.exists() and not _is_migrated(ic_path):
        try:
            count = migrate_instance_config(str(ic_path), dst_path)
            _mark_migrated(ic_path, count)
            logger.info(f"instance_config 迁移完成: {count} 行")
            migrated_any = True
        except Exception as e:
            logger.error(f"instance_config 迁移失败: {e}", exc_info=True)

    # 2-4. Per-instance stores
    instances_dir = user_data / "data" / "instances"
    if not instances_dir.exists():
        return migrated_any

    for inst_dir in instances_dir.iterdir():
        if not inst_dir.is_dir():
            continue
        instance_name = inst_dir.name
        store_dir = inst_dir / "store"
        if not store_dir.exists():
            continue

        # fragments.db
        frag_path = store_dir / "fragments.db"
        if frag_path.exists() and not _is_migrated(frag_path):
            try:
                count = migrate_fragments(str(frag_path), dst_path, instance_name)
                _mark_migrated(frag_path, count)
                logger.info(f"[{instance_name}] fragments 迁移完成: {count} 行")
                migrated_any = True
            except Exception as e:
                logger.error(f"[{instance_name}] fragments 迁移失败: {e}", exc_info=True)

        # memory_fts.db
        fts_path = store_dir / "memory_fts.db"
        if fts_path.exists() and not _is_migrated(fts_path):
            try:
                count = migrate_memory_fts(str(fts_path), dst_path)
                _mark_migrated(fts_path, count)
                logger.info(f"[{instance_name}] memory_fts 迁移完成: {count} 行")
                migrated_any = True
            except Exception as e:
                logger.error(f"[{instance_name}] memory_fts 迁移失败: {e}", exc_info=True)

        # mem0_history.db
        hist_path = store_dir / "mem0_history.db"
        if hist_path.exists() and not _is_migrated(hist_path):
            try:
                count = migrate_mem0_history(str(hist_path), dst_path, instance_name)
                _mark_migrated(hist_path, count)
                logger.info(f"[{instance_name}] mem0_history 迁移完成: {count} 行")
                migrated_any = True
            except Exception as e:
                logger.error(f"[{instance_name}] mem0_history 迁移失败: {e}", exc_info=True)

        # Log skipped vector DBs
        for vec_db in store_dir.glob("mem0_vectors_*.db"):
            if not _is_migrated(vec_db):
                logger.warning(
                    f"[{instance_name}] 跳过向量 DB {vec_db.name}（向量数据需重建）"
                )

        pb_vec = store_dir / "playbook_vectors.db"
        if pb_vec.exists() and not _is_migrated(pb_vec):
            logger.warning(
                f"[{instance_name}] 跳过 playbook_vectors.db（向量数据需重建）"
            )

    return migrated_any


if __name__ == "__main__":
    print("=== 统一数据库迁移 ===")
    result = auto_migrate_to_unified_db()
    if result:
        print("迁移完成")
    else:
        print("无需迁移")
