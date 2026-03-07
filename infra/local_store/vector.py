"""
sqlite-vec 可选向量搜索

提供基于向量的语义搜索能力（可选功能）：
- 依赖 sqlite-vec 扩展（不可用时优雅降级）
- 支持余弦相似度搜索
- 用于消息语义检索、记忆召回

安装 sqlite-vec:
    pip install sqlite-vec
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from logger import get_logger

logger = get_logger("local_store.vector")

_ALLOWED_TABLE_NAMES = frozenset({
    "message_vectors", "memory_vectors", "knowledge_vectors",
})


def validate_embedding(embedding: List[float], label: str = "embedding") -> bool:
    """Validate vector before passing to sqlite-vec C layer.

    Prevents SIGSEGV by rejecting malformed inputs that the C extension
    cannot safely handle (NaN, Inf, wrong types, empty).
    """
    if not embedding or not isinstance(embedding, (list, tuple)):
        logger.warning(f"[vector] {label}: empty or wrong type")
        return False
    import math
    for i, v in enumerate(embedding):
        if not isinstance(v, (int, float)):
            logger.warning(f"[vector] {label}[{i}]: not a number ({type(v).__name__})")
            return False
        if not math.isfinite(v):
            logger.warning(f"[vector] {label}[{i}]: NaN/Inf")
            return False
    return True


@dataclass
class VectorSearchResult:
    """向量搜索结果"""

    id: str
    distance: float
    metadata_json: str


async def create_vector_table(
    engine: AsyncEngine,
    table_name: str,
    dimensions: int,
) -> bool:
    """
    创建向量虚拟表

    Args:
        engine: 数据库引擎
        table_name: 表名
        dimensions: 向量维度

    Returns:
        是否创建成功
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(
                    id TEXT PRIMARY KEY,
                    embedding FLOAT[{dimensions}],
                    metadata TEXT
                )
            """))
        logger.info(f"向量表 {table_name} 创建成功（维度: {dimensions}）")
        return True
    except Exception as e:
        logger.warning(f"创建向量表失败（sqlite-vec 可能不可用）: {e}")
        return False


async def upsert_vector(
    session: AsyncSession,
    table_name: str,
    vector_id: str,
    embedding: List[float],
    metadata: str = "{}",
):
    """
    插入或更新向量

    Args:
        session: 数据库会话
        table_name: 表名
        vector_id: 向量 ID
        embedding: 向量数据
        metadata: 元数据 JSON 字符串
    """
    if not validate_embedding(embedding, "upsert"):
        return

    import json
    embedding_json = json.dumps(embedding)

    try:
        await session.execute(
            text(f"DELETE FROM {table_name} WHERE id = :id"),
            {"id": vector_id},
        )
        await session.execute(
            text(f"""
                INSERT INTO {table_name}(id, embedding, metadata)
                VALUES (:id, :embedding, :metadata)
            """),
            {
                "id": vector_id,
                "embedding": embedding_json,
                "metadata": metadata,
            },
        )
    except Exception as e:
        logger.warning(f"向量 upsert 失败 (id={vector_id}): {e}")
        raise


async def search_vectors(
    session: AsyncSession,
    table_name: str,
    query_embedding: List[float],
    limit: int = 10,
    where_clause: Optional[str] = None,
) -> List[VectorSearchResult]:
    """
    向量相似度搜索

    Args:
        session: 数据库会话
        table_name: 表名
        query_embedding: 查询向量
        limit: 返回数量
        where_clause: 额外过滤条件（可选）

    Returns:
        VectorSearchResult 列表（按距离升序）
    """
    if not validate_embedding(query_embedding, "search_query"):
        return []

    import json
    query_json = json.dumps(query_embedding)

    sql = f"""
        SELECT id, distance, metadata
        FROM {table_name}
        WHERE embedding MATCH :query AND k = :limit
        ORDER BY distance
    """

    try:
        result = await session.execute(
            text(sql),
            {"query": query_json, "limit": limit},
        )
        rows = result.fetchall()

        return [
            VectorSearchResult(
                id=row[0],
                distance=row[1],
                metadata_json=row[2] or "{}",
            )
            for row in rows
        ]
    except Exception as e:
        logger.warning(f"向量搜索失败: {e}")
        return []


async def delete_vector(session: AsyncSession, table_name: str, vector_id: str):
    """
    删除向量

    Args:
        session: 数据库会话
        table_name: 表名
        vector_id: 向量 ID
    """
    await session.execute(
        text(f"DELETE FROM {table_name} WHERE id = :id"),
        {"id": vector_id},
    )


async def count_vectors(session: AsyncSession, table_name: str) -> int:
    """
    统计向量数量

    Args:
        session: 数据库会话
        table_name: 表名

    Returns:
        向量数量
    """
    try:
        result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar() or 0
    except Exception:
        return 0
