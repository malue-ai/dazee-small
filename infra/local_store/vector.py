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

# 默认向量维度（与常见 embedding 模型对齐）
DEFAULT_DIMENSIONS = 1536


@dataclass
class VectorSearchResult:
    """向量搜索结果"""

    id: str
    distance: float
    metadata_json: str


async def create_vector_table(
    engine: AsyncEngine,
    table_name: str = "message_vectors",
    dimensions: int = DEFAULT_DIMENSIONS,
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
    # sqlite-vec 使用 JSON 数组格式的 embedding
    import json

    embedding_json = json.dumps(embedding)

    # 先删除（幂等）
    await session.execute(
        text(f"DELETE FROM {table_name} WHERE id = :id"),
        {"id": vector_id},
    )
    # 插入
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
    import json

    query_json = json.dumps(query_embedding)

    sql = f"""
        SELECT id, distance, metadata
        FROM {table_name}
        WHERE embedding MATCH :query
        ORDER BY distance
        LIMIT :limit
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
