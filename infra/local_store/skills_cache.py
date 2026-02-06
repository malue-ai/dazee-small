"""
Skills 延迟加载缓存

设计理念：
- 首次请求时从磁盘读取 SKILL.md → 缓存到 SQLite
- 后续请求直接从 SQLite 读取，避免重复文件 I/O
- 通过 file_mtime 检测文件变更，自动刷新缓存
- 支持 LRU 风格的访问时间更新（便于清理冷数据）
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from logger import get_logger

logger = get_logger("local_store.skills_cache")


async def get_cached_skill(
    session: AsyncSession,
    instance_id: str,
    skill_name: str,
    skills_dir: Path,
) -> Optional[str]:
    """
    获取 Skill 内容（带缓存）

    流程：
    1. 检查 SQLite 缓存是否命中
    2. 命中 → 比较 file_mtime → 未变更直接返回
    3. 未命中或文件已变更 → 从磁盘读取并更新缓存

    Args:
        session: 数据库会话
        instance_id: 实例 ID
        skill_name: Skill 名称
        skills_dir: Skills 目录

    Returns:
        Skill 内容文本，不存在返回 None
    """
    from infra.local_store.models import LocalSkillCache

    skill_path = skills_dir / skill_name / "SKILL.md"

    # 文件不存在，直接返回
    if not skill_path.exists():
        logger.debug(f"Skill 文件不存在: {skill_path}")
        return None

    current_mtime = os.path.getmtime(skill_path)

    # 查询缓存
    result = await session.execute(
        select(LocalSkillCache).where(
            LocalSkillCache.instance_id == instance_id,
            LocalSkillCache.skill_name == skill_name,
        )
    )
    cached = result.scalar_one_or_none()

    if cached and cached.file_mtime >= current_mtime:
        # 缓存命中且文件未变更 → 更新访问时间，返回缓存内容
        cached.accessed_at = datetime.now()
        await session.commit()
        logger.debug(f"Skill 缓存命中: {skill_name}")
        return cached.skill_content

    # 缓存未命中或文件已变更 → 从磁盘读取
    logger.info(f"Skill 缓存{'刷新' if cached else '加载'}: {skill_name}")
    async with aiofiles.open(skill_path, "r", encoding="utf-8") as f:
        content = await f.read()

    now = datetime.now()

    if cached:
        # 更新缓存
        cached.skill_content = content
        cached.file_mtime = current_mtime
        cached.file_path = str(skill_path)
        cached.cached_at = now
        cached.accessed_at = now
    else:
        # 新建缓存
        new_cache = LocalSkillCache(
            instance_id=instance_id,
            skill_name=skill_name,
            skill_content=content,
            file_path=str(skill_path),
            file_mtime=current_mtime,
            cached_at=now,
            accessed_at=now,
        )
        session.add(new_cache)

    await session.commit()
    return content


async def get_cached_skills_batch(
    session: AsyncSession,
    instance_id: str,
    skill_names: List[str],
    skills_dir: Path,
) -> Dict[str, str]:
    """
    批量获取 Skill 内容（带缓存）

    Args:
        session: 数据库会话
        instance_id: 实例 ID
        skill_names: Skill 名称列表
        skills_dir: Skills 目录

    Returns:
        {skill_name: content} 字典（不存在的 Skill 不包含在结果中）
    """
    results = {}
    for name in skill_names:
        content = await get_cached_skill(session, instance_id, name, skills_dir)
        if content is not None:
            results[name] = content
    return results


async def invalidate_skill_cache(
    session: AsyncSession,
    instance_id: str,
    skill_name: Optional[str] = None,
):
    """
    使缓存失效

    Args:
        session: 数据库会话
        instance_id: 实例 ID
        skill_name: Skill 名称（为 None 时清空该实例的全部缓存）
    """
    from infra.local_store.models import LocalSkillCache

    stmt = delete(LocalSkillCache).where(
        LocalSkillCache.instance_id == instance_id,
    )
    if skill_name:
        stmt = stmt.where(LocalSkillCache.skill_name == skill_name)

    result = await session.execute(stmt)
    await session.commit()

    count = result.rowcount
    scope = skill_name or "全部"
    logger.info(f"Skill 缓存已清除: instance={instance_id}, scope={scope}, count={count}")


async def cleanup_stale_cache(
    session: AsyncSession,
    max_age_days: int = 30,
) -> int:
    """
    清理过期的 Skill 缓存

    按 accessed_at 清理长期未访问的冷数据。

    Args:
        session: 数据库会话
        max_age_days: 最大保留天数

    Returns:
        清理的记录数
    """
    from infra.local_store.models import LocalSkillCache

    cutoff = datetime.now().timestamp() - max_age_days * 86400
    cutoff_dt = datetime.fromtimestamp(cutoff)

    stmt = delete(LocalSkillCache).where(
        LocalSkillCache.accessed_at < cutoff_dt,
    )
    result = await session.execute(stmt)
    await session.commit()

    count = result.rowcount
    if count > 0:
        logger.info(f"清理过期 Skill 缓存: {count} 条（超过 {max_age_days} 天未访问）")
    return count


async def get_cache_stats(session: AsyncSession, instance_id: Optional[str] = None) -> Dict:
    """
    获取缓存统计信息

    Args:
        session: 数据库会话
        instance_id: 实例 ID（为 None 时统计全部）

    Returns:
        统计字典
    """
    conditions = []
    params = {}

    if instance_id:
        conditions.append("instance_id = :iid")
        params["iid"] = instance_id

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    result = await session.execute(
        text(f"""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT instance_id) as instances,
                MIN(cached_at) as oldest_cached,
                MAX(accessed_at) as latest_accessed
            FROM skills_cache
            {where_clause}
        """),
        params,
    )
    row = result.fetchone()

    return {
        "total_cached": row[0] if row else 0,
        "instance_count": row[1] if row else 0,
        "oldest_cached": row[2] if row else None,
        "latest_accessed": row[3] if row else None,
    }
