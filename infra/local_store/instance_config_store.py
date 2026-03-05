"""
统一实例级配置存储（Instance Config Store）

使用主引擎 zenflux.db 中的 instance_config 表。
所有函数接收 AsyncSession 参数，由调用方管理事务。

品类:
  credential  — 服务/工具 API Key
  package     — 已安装包记录
  permission  — OS 权限授权状态
  setting     — 工具/Skill 配置项
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
    """写入或更新一条实例配置。"""
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
    """删除一条配置，返回是否曾存在。"""
    result = await session.execute(
        sa_text("DELETE FROM instance_config WHERE instance_id=:iid AND category=:cat AND key=:key"),
        {"iid": instance_id, "cat": category, "key": key},
    )
    return result.rowcount > 0


async def get_by_category(session: AsyncSession, instance_id: str, category: str) -> Dict[str, str]:
    """返回 {key: value}，按品类过滤。"""
    result = await session.execute(
        sa_text("SELECT key, value FROM instance_config WHERE instance_id=:iid AND category=:cat"),
        {"iid": instance_id, "cat": category},
    )
    return dict(result.fetchall())


async def get_all(session: AsyncSession, instance_id: str) -> Dict[str, Dict[str, str]]:
    """返回 {category: {key: value}}。"""
    result = await session.execute(
        sa_text("SELECT category, key, value FROM instance_config WHERE instance_id=:iid"),
        {"iid": instance_id},
    )
    out: Dict[str, Dict[str, str]] = {}
    for cat, k, v in result.fetchall():
        out.setdefault(cat, {})[k] = v
    return out


async def check_fulfilled(
    session: AsyncSession, instance_id: str, category: str, keys: List[str]
) -> Dict[str, bool]:
    """检查指定 key 列表是否已配置。"""
    if not keys:
        return {}
    existing = await get_by_category(session, instance_id, category)
    return {k: bool(existing.get(k)) for k in keys}


async def list_keys(
    session: AsyncSession, instance_id: str, category: Optional[str] = None
) -> List[str]:
    """返回已配置的 key 列表。"""
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
