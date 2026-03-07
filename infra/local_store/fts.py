"""
SQLite FTS5 全文索引

提供消息内容的全文搜索能力：
- FTS5 虚拟表自动同步（通过 insert/update/delete 触发）
- 支持中文分词（unicode61 tokenizer）
- 支持短语搜索、前缀搜索、布尔搜索
- BM25 排序
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from logger import get_logger

logger = get_logger("local_store.fts")


@dataclass
class FTSResult:
    """全文搜索结果"""

    message_id: str
    conversation_id: str
    role: str
    text_content: str
    rank: float  # BM25 得分（越小越相关）


async def sync_message_to_fts(
    session: AsyncSession,
    message_id: str,
    conversation_id: str,
    role: str,
    text_content: str,
):
    """
    将消息同步到 FTS5 索引

    在 create_message / update_message 后调用。

    Args:
        session: 数据库会话
        message_id: 消息 ID
        conversation_id: 对话 ID
        role: 角色
        text_content: 纯文本内容
    """
    if not text_content or not text_content.strip():
        return

    try:
        await session.execute(
            text("DELETE FROM messages_fts WHERE message_id = :mid"),
            {"mid": message_id},
        )
        await session.execute(
            text("""
                INSERT INTO messages_fts(message_id, conversation_id, role, text_content)
                VALUES (:mid, :cid, :role, :text)
            """),
            {
                "mid": message_id,
                "cid": conversation_id,
                "role": role,
                "text": text_content,
            },
        )
    except Exception as e:
        logger.warning(f"FTS 同步失败 (mid={message_id}), 不影响消息保存: {e}")


async def delete_message_from_fts(session: AsyncSession, message_id: str):
    """从 FTS5 索引中删除消息（best-effort，不中断主流程）"""
    try:
        await session.execute(
            text("DELETE FROM messages_fts WHERE message_id = :mid"),
            {"mid": message_id},
        )
    except Exception as e:
        logger.warning(f"FTS 删除失败 (mid={message_id}): {e}")


async def delete_conversation_from_fts(session: AsyncSession, conversation_id: str):
    """从 FTS5 索引中删除对话消息（best-effort，不中断主流程）"""
    try:
        await session.execute(
            text("DELETE FROM messages_fts WHERE conversation_id = :cid"),
            {"cid": conversation_id},
        )
    except Exception as e:
        logger.warning(f"FTS 删除失败 (cid={conversation_id}): {e}")


async def search_messages(
    session: AsyncSession,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> List[FTSResult]:
    """
    全文搜索消息

    支持 FTS5 查询语法：
    - 普通搜索: "天气预报"
    - 短语搜索: '"今天天气"'
    - 前缀搜索: "天气*"
    - 布尔搜索: "天气 AND 上海"
    - 排除搜索: "天气 NOT 北京"

    Args:
        session: 数据库会话
        query: FTS5 搜索查询
        conversation_id: 限定对话 ID（可选）
        role: 限定角色（可选）
        limit: 返回数量
        offset: 偏移量

    Returns:
        FTSResult 列表（按 BM25 得分排序）
    """
    if not query or not query.strip():
        return []

    from infra.local_store.generic_fts import GenericFTS5

    sanitized = GenericFTS5._sanitize_query(query)
    if not sanitized:
        return []

    conditions = ["messages_fts MATCH :query"]
    params: dict = {"query": sanitized, "limit": limit, "offset": offset}

    if conversation_id:
        conditions.append("conversation_id = :cid")
        params["cid"] = conversation_id

    if role:
        conditions.append("role = :role")
        params["role"] = role

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT
            message_id,
            conversation_id,
            role,
            text_content,
            rank
        FROM messages_fts
        WHERE {where_clause}
        ORDER BY rank
        LIMIT :limit OFFSET :offset
    """

    try:
        result = await session.execute(text(sql), params)
    except Exception as e:
        logger.warning(f"FTS5 消息搜索失败 (query={query[:50]}): {e}")
        return []

    rows = result.fetchall()

    return [
        FTSResult(
            message_id=row[0],
            conversation_id=row[1],
            role=row[2],
            text_content=row[3],
            rank=row[4],
        )
        for row in rows
    ]


async def search_messages_count(
    session: AsyncSession,
    query: str,
    conversation_id: Optional[str] = None,
    role: Optional[str] = None,
) -> int:
    """
    获取搜索结果总数

    Args:
        session: 数据库会话
        query: FTS5 搜索查询
        conversation_id: 限定对话 ID
        role: 限定角色

    Returns:
        匹配的消息数量
    """
    if not query or not query.strip():
        return 0

    from infra.local_store.generic_fts import GenericFTS5

    sanitized = GenericFTS5._sanitize_query(query)
    if not sanitized:
        return 0

    conditions = ["messages_fts MATCH :query"]
    params: dict = {"query": sanitized}

    if conversation_id:
        conditions.append("conversation_id = :cid")
        params["cid"] = conversation_id

    if role:
        conditions.append("role = :role")
        params["role"] = role

    where_clause = " AND ".join(conditions)

    sql = f"SELECT COUNT(*) FROM messages_fts WHERE {where_clause}"
    try:
        result = await session.execute(text(sql), params)
        return result.scalar() or 0
    except Exception as e:
        logger.warning(f"FTS5 消息计数失败: {e}")
        return 0


async def rebuild_fts_index(session: AsyncSession):
    """
    重建 FTS5 索引（从 messages 表全量同步）

    适用场景：
    - 数据库迁移后
    - 索引损坏修复
    - 首次从其他存储导入数据
    """
    logger.info("开始重建 FTS5 索引...")

    # 清空现有索引
    await session.execute(text("DELETE FROM messages_fts"))

    # 从 messages 表全量同步
    # 注意：content 列存储的是 JSON 字符串，需要提取 text 类型的内容
    result = await session.execute(
        text("SELECT id, conversation_id, role, content FROM messages")
    )
    rows = result.fetchall()

    count = 0
    for row in rows:
        message_id, conversation_id, role, content_json = row

        # 解析 content JSON，提取纯文本
        import json

        try:
            blocks = json.loads(content_json) if isinstance(content_json, str) else []
        except (json.JSONDecodeError, TypeError):
            blocks = []

        text_parts = [
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text_content = "\n".join(text_parts)

        if text_content.strip():
            await session.execute(
                text("""
                    INSERT INTO messages_fts(message_id, conversation_id, role, text_content)
                    VALUES (:mid, :cid, :role, :text)
                """),
                {
                    "mid": message_id,
                    "cid": conversation_id,
                    "role": role,
                    "text": text_content,
                },
            )
            count += 1

    await session.commit()
    logger.info(f"FTS5 索引重建完成，共索引 {count} 条消息")
