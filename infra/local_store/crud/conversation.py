"""
本地会话 CRUD 操作

与 infra/database/crud/conversation.py 接口对齐，
底层使用 SQLite + TEXT(JSON) 存储。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from infra.local_store.fts import delete_conversation_from_fts
from infra.local_store.models import LocalConversation, LocalMessage, _to_json


def _normalize_user_id(_: str) -> str:
    """
    Normalize all conversation ownership to a single local user.

    The desktop app currently runs in single-user mode. For consistency across
    web, gateway channels, and local tasks, conversation rows are always stored
    and queried under user_id="local".
    """
    return "local"


async def create_conversation(
    session: AsyncSession,
    user_id: str,
    title: str = "新对话",
    metadata: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[str] = None,
) -> LocalConversation:
    """
    创建会话

    Args:
        session: 数据库会话
        user_id: 用户 ID
        title: 会话标题
        metadata: 元数据
        conversation_id: 可选的会话 ID

    Returns:
        创建的会话对象
    """
    normalized_user_id = _normalize_user_id(user_id)
    now = datetime.now()
    conv = LocalConversation(
        id=conversation_id or str(uuid4()),
        user_id=normalized_user_id,
        title=title,
        created_at=now,
        updated_at=now,
        metadata_json=_to_json(metadata or {}),
    )

    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def get_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> Optional[LocalConversation]:
    """获取会话"""
    return await session.get(LocalConversation, conversation_id)


async def get_or_create_conversation(
    session: AsyncSession,
    user_id: str,
    conversation_id: Optional[str] = None,
    title: str = "新对话",
    metadata: Optional[Dict[str, Any]] = None,
) -> tuple[LocalConversation, bool]:
    """
    获取或创建会话

    Args:
        session: 数据库会话
        user_id: 用户 ID
        conversation_id: 会话 ID（可选）
        title: 标题（仅创建时使用）
        metadata: 元数据（仅创建时使用）

    Returns:
        (conversation, is_new)
    """
    normalized_user_id = _normalize_user_id(user_id)
    if not conversation_id:
        conv = await create_conversation(session, normalized_user_id, title, metadata)
        return conv, True

    conv = await get_conversation(session, conversation_id)
    if conv:
        return conv, False

    conv = await create_conversation(
        session, normalized_user_id, title, metadata, conversation_id
    )
    return conv, True


async def update_conversation(
    session: AsyncSession,
    conversation_id: str,
    title: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[LocalConversation]:
    """更新会话"""
    conv = await get_conversation(session, conversation_id)
    if not conv:
        return None

    if title is not None:
        conv.title = title
    if status is not None:
        conv.status = status
    if metadata is not None:
        conv.metadata_json = _to_json(metadata)
    conv.updated_at = datetime.now()

    await session.commit()
    await session.refresh(conv)
    return conv


async def list_conversations(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    exclude_hidden: bool = True,
    agent_id: Optional[str] = None,
) -> List[LocalConversation]:
    """
    获取用户的会话列表

    Args:
        session: 数据库会话
        user_id: 用户 ID
        limit: 每页数量
        offset: 偏移量
        exclude_hidden: 是否排除 hidden 会话
        agent_id: 可选，按 agent_id 过滤（metadata.agent_id）
    """
    normalized_user_id = _normalize_user_id(user_id)
    query = (
        select(LocalConversation)
        .where(LocalConversation.user_id == normalized_user_id)
    )
    if exclude_hidden:
        query = query.where(
            text("COALESCE(json_extract(metadata, '$.hidden'), 0) != 1")
        )
    if agent_id is not None:
        query = query.where(
            text("json_extract(metadata, '$.agent_id') = :agent_id")
        ).params(agent_id=agent_id)
    query = (
        query
        .order_by(LocalConversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_conversations(
    session: AsyncSession,
    user_id: str,
    exclude_hidden: bool = True,
    agent_id: Optional[str] = None,
) -> int:
    """
    统计用户的会话数量

    Args:
        session: 数据库会话
        user_id: 用户 ID
        exclude_hidden: 是否排除 hidden 会话
        agent_id: 可选，按 agent_id 过滤（metadata.agent_id）
    """
    normalized_user_id = _normalize_user_id(user_id)
    query = select(func.count(LocalConversation.id)).where(
        LocalConversation.user_id == normalized_user_id
    )
    if exclude_hidden:
        query = query.where(
            text("COALESCE(json_extract(metadata, '$.hidden'), 0) != 1")
        )
    if agent_id is not None:
        query = query.where(
            text("json_extract(metadata, '$.agent_id') = :agent_id")
        ).params(agent_id=agent_id)
    result = await session.execute(query)
    return result.scalar() or 0


async def delete_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> bool:
    """
    删除会话（级联删除消息 + FTS 索引）

    Args:
        session: 数据库会话
        conversation_id: 会话 ID

    Returns:
        是否删除成功
    """
    conv = await get_conversation(session, conversation_id)
    if not conv:
        return False

    # 清理 FTS 索引
    await delete_conversation_from_fts(session, conversation_id)

    # 删除消息
    await session.execute(
        delete(LocalMessage).where(LocalMessage.conversation_id == conversation_id)
    )

    # 删除会话
    await session.delete(conv)
    await session.commit()
    return True
