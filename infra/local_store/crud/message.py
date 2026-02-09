"""
本地消息 CRUD 操作

与 infra/database/crud/message.py 接口对齐，
底层使用 SQLite + TEXT(JSON) 存储。

每次 create/update 消息后自动同步 FTS5 索引。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.local_store.fts import delete_message_from_fts, sync_message_to_fts
from infra.local_store.models import LocalConversation, LocalMessage, _to_json


def _parse_content(content: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """解析 content 为 list 格式"""
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, list) else [{"type": "text", "text": content}]
        except json.JSONDecodeError:
            return [{"type": "text", "text": content}]
    return []


def _parse_metadata(metadata: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    """解析 metadata 为 dict 格式"""
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_text(content_blocks: List[Dict[str, Any]]) -> str:
    """从 content blocks 中提取纯文本"""
    text_parts = [
        block.get("text", "")
        for block in content_blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(text_parts) if text_parts else ""


async def create_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: Union[str, List[Dict[str, Any]]],
    message_id: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Union[str, Dict[str, Any]]] = None,
) -> LocalMessage:
    """
    创建消息

    自动同步 FTS5 索引。

    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        role: 角色（user/assistant/system）
        content: 消息内容（JSON 字符串或 list）
        message_id: 消息 ID（可选）
        status: 状态（可选）
        metadata: 元数据（JSON 字符串或 dict）

    Returns:
        创建的消息对象
    """
    parsed_content = _parse_content(content)
    mid = message_id or str(uuid4())

    msg = LocalMessage(
        id=mid,
        conversation_id=conversation_id,
        role=role,
        content_json=_to_json(parsed_content),
        status=status,
        created_at=datetime.now(),
        metadata_json=_to_json(_parse_metadata(metadata)),
    )

    session.add(msg)

    # 同步更新会话的 updated_at
    conv = await session.get(LocalConversation, conversation_id)
    if conv:
        conv.updated_at = datetime.now()

    # 同步 FTS5 索引
    text_content = _extract_text(parsed_content)
    await sync_message_to_fts(session, mid, conversation_id, role, text_content)

    await session.commit()
    await session.refresh(msg)
    return msg


async def get_message(
    session: AsyncSession,
    message_id: str,
) -> Optional[LocalMessage]:
    """获取消息"""
    return await session.get(LocalMessage, message_id)


async def update_message(
    session: AsyncSession,
    message_id: str,
    content: Optional[Union[str, List[Dict[str, Any]]]] = None,
    status: Optional[str] = None,
    metadata: Optional[Union[str, Dict[str, Any]]] = None,
) -> Optional[LocalMessage]:
    """
    更新消息

    自动同步 FTS5 索引。

    Args:
        session: 数据库会话
        message_id: 消息 ID
        content: 消息内容
        status: 状态
        metadata: 元数据（增量合并）

    Returns:
        更新后的消息对象
    """
    msg = await get_message(session, message_id)
    if not msg:
        return None

    if content is not None:
        parsed = _parse_content(content)
        msg.content_json = _to_json(parsed)

        # 同步 FTS5
        text_content = _extract_text(parsed)
        await sync_message_to_fts(
            session, message_id, msg.conversation_id, msg.role, text_content
        )

    if status is not None:
        msg.status = status

    if metadata is not None:
        # 深度合并 metadata
        existing = _parse_metadata(msg.metadata_json)
        new_meta = _parse_metadata(metadata)

        for key, value in new_meta.items():
            if key in existing and isinstance(existing[key], dict) and isinstance(value, dict):
                existing[key].update(value)
            else:
                existing[key] = value

        msg.metadata_json = _to_json(existing)

    # 同步更新会话的 updated_at
    conv = await session.get(LocalConversation, msg.conversation_id)
    if conv:
        conv.updated_at = datetime.now()

    await session.commit()
    await session.refresh(msg)
    return msg


async def list_messages(
    session: AsyncSession,
    conversation_id: str,
    limit: int = 1000,
    offset: int = 0,
    order: str = "asc",
    before_cursor: Optional[str] = None,
) -> List[LocalMessage]:
    """
    获取对话的消息列表

    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        limit: 返回数量
        offset: 偏移量
        order: 排序方式（asc/desc）
        before_cursor: 游标（message_id），获取此消息之前的消息

    Returns:
        消息列表
    """
    query = select(LocalMessage).where(LocalMessage.conversation_id == conversation_id)

    if before_cursor:
        cursor_msg = await session.get(LocalMessage, before_cursor)
        if cursor_msg:
            query = query.where(LocalMessage.created_at < cursor_msg.created_at)
    elif offset > 0:
        query = query.offset(offset)

    if order == "desc":
        query = query.order_by(LocalMessage.created_at.desc())
    else:
        query = query.order_by(LocalMessage.created_at.asc())

    query = query.limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


async def delete_messages_by_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> int:
    """
    删除对话的所有消息（含 FTS 索引）

    Args:
        session: 数据库会话
        conversation_id: 对话 ID

    Returns:
        删除的消息数量
    """
    # 先清理 FTS
    from infra.local_store.fts import delete_conversation_from_fts

    await delete_conversation_from_fts(session, conversation_id)

    # 删除消息
    result = await session.execute(
        delete(LocalMessage).where(LocalMessage.conversation_id == conversation_id)
    )
    await session.commit()
    return result.rowcount
