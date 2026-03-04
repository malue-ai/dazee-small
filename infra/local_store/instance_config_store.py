"""
统一实例级配置存储（Instance Config Store）

按品类持久化到当前用户本地 SQLite，按 instance_id 隔离。
使用独立 DB 文件（不依赖 AGENT_INSTANCE），以便在切换实例前即可读取。

品类:
  credential  — 服务/工具 API Key (切换实例时注入 os.environ)
  package     — 已安装包记录 (仅状态查询)
  permission  — OS 权限授权状态 (仅状态查询)
  setting     — 工具/Skill 配置项 (Skill 运行时按需读取)
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from logger import get_logger
from utils.app_paths import get_user_data_dir

logger = get_logger("instance_config_store")

VALID_CATEGORIES = frozenset({"credential", "package", "permission", "setting"})


def _db_path() -> Path:
    d = get_user_data_dir() / "db"
    d.mkdir(parents=True, exist_ok=True)
    return d / "instance_config.db"


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instance_config (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id TEXT NOT NULL,
            category    TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL DEFAULT '',
            skill_name  TEXT DEFAULT '',
            source      TEXT DEFAULT 'hitl',
            updated_at  TEXT NOT NULL,
            UNIQUE(instance_id, category, key)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ic_instance ON instance_config(instance_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ic_category ON instance_config(instance_id, category)"
    )
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(path)
    _ensure_table(conn)
    return conn


# --------------- write ---------------


def upsert(
    instance_id: str,
    category: str,
    key: str,
    value: str,
    skill_name: str = "",
    source: str = "hitl",
) -> None:
    """写入或更新一条实例配置。"""
    if category not in VALID_CATEGORIES:
        logger.warning("无效品类 %s，允许: %s", category, VALID_CATEGORIES)
        return
    conn = _conn()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO instance_config
                (instance_id, category, key, value, skill_name, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instance_id, category, key)
            DO UPDATE SET value=?, skill_name=?, source=?, updated_at=?
            """,
            (instance_id, category, key, value, skill_name, source, now,
             value, skill_name, source, now),
        )
        conn.commit()
        logger.info(
            "instance_config upsert: %s/%s/%s (source=%s, skill=%s)",
            instance_id, category, key, source, skill_name,
        )
    finally:
        conn.close()


def delete(instance_id: str, category: str, key: str) -> bool:
    """删除一条配置，返回是否曾存在。"""
    conn = _conn()
    try:
        cur = conn.execute(
            "DELETE FROM instance_config WHERE instance_id=? AND category=? AND key=?",
            (instance_id, category, key),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --------------- read ---------------


def get_by_category(instance_id: str, category: str) -> Dict[str, str]:
    """返回 {key: value}，按品类过滤。"""
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT key, value FROM instance_config WHERE instance_id=? AND category=?",
            (instance_id, category),
        )
        return dict(cur.fetchall())
    finally:
        conn.close()


def get_all(instance_id: str) -> Dict[str, Dict[str, str]]:
    """返回 {category: {key: value}}。"""
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT category, key, value FROM instance_config WHERE instance_id=?",
            (instance_id,),
        )
        result: Dict[str, Dict[str, str]] = {}
        for cat, k, v in cur.fetchall():
            result.setdefault(cat, {})[k] = v
        return result
    finally:
        conn.close()


def check_fulfilled(
    instance_id: str, category: str, keys: List[str]
) -> Dict[str, bool]:
    """检查指定 key 列表是否已配置，返回 {key: True/False}。"""
    if not keys:
        return {}
    existing = get_by_category(instance_id, category)
    return {k: bool(existing.get(k)) for k in keys}


def list_keys(instance_id: str, category: Optional[str] = None) -> List[str]:
    """返回已配置的 key 列表（不含 value）。"""
    conn = _conn()
    try:
        if category:
            cur = conn.execute(
                "SELECT key FROM instance_config WHERE instance_id=? AND category=?",
                (instance_id, category),
            )
        else:
            cur = conn.execute(
                "SELECT key FROM instance_config WHERE instance_id=?",
                (instance_id,),
            )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


# --------------- migration ---------------


def migrate_from_instance_env_db() -> int:
    """
    一次性迁移：将旧 instance_env.db 的数据导入 instance_config.db (credential 品类)。
    迁移完成后重命名旧 DB 为 .bak 防止重复迁移。返回迁移条目数。
    """
    old_path = get_user_data_dir() / "db" / "instance_env.db"
    if not old_path.exists():
        return 0
    try:
        old_conn = sqlite3.connect(old_path)
        rows = old_conn.execute(
            "SELECT instance_id, key, value, updated_at FROM instance_env"
        ).fetchall()
        old_conn.close()
    except Exception:
        return 0

    count = 0
    for inst_id, key, value, updated_at in rows:
        if value:
            upsert(inst_id, "credential", key, value, source="migrated")
            count += 1

    if count > 0:
        bak = old_path.with_suffix(".db.bak")
        old_path.rename(bak)
        logger.info("已迁移 %d 条旧 instance_env 到 instance_config，旧 DB 已重命名为 %s", count, bak)
    return count
