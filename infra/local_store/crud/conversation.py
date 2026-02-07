"""
本地会话 CRUD 操作

与 infra/database/crud/conversation.py 接口对齐，
底层使用 SQLite + TEXT(JSON) 存储。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.local_store.fts import delete_conversation_from_fts
from infra.local_store.models import LocalConversation, LocalMessage, _to_json


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
    now = datetime.now()
    conv = LocalConversation(
        id=conversation_id or str(uuid4()),
        user_id=user_id,
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
    if not conversation_id:
        conv = await create_conversation(session, user_id, title, metadata)
        return conv, True

    conv = await get_conversation(session, conversation_id)
    if conv:
        return conv, False

    conv = await create_conversation(session, user_id, title, metadata, conversation_id)
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
) -> List[LocalConversation]:
    """获取用户的会话列表"""
    result = await session.execute(
        select(LocalConversation)
        .where(LocalConversation.user_id == user_id)
        .order_by(LocalConversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def count_conversations(
    session: AsyncSession,
    user_id: str,
) -> int:
    """统计用户的会话数量"""
    result = await session.execute(
        select(func.count(LocalConversation.id)).where(
            LocalConversation.user_id == user_id
        )
    )
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
