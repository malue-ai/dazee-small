"""
Message 表 CRUD 操作
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models import Message
from infra.database.crud.base import get_by_id


def generate_message_id() -> str:
    """生成消息 ID"""
    return f"msg_{uuid4().hex[:24]}"


async def create_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    message_id: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Message:
    """创建消息"""
    msg = Message(
        id=message_id or generate_message_id(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        status=status,
        created_at=datetime.now(),
    )
    if metadata:
        msg._metadata = metadata
    
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_message(
    session: AsyncSession,
    message_id: str
) -> Optional[Message]:
    """获取消息"""
    return await get_by_id(session, Message, message_id)


async def update_message(
    session: AsyncSession,
    message_id: str,
    content: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Message]:
    """更新消息"""
    msg = await get_message(session, message_id)
    if not msg:
        return None
    
    if content is not None:
        msg.content = content
    if status is not None:
        msg.status = status
    if metadata is not None:
        # 深度合并 metadata（对齐文档规范）
        existing = msg._metadata or {}
        merged = _deep_merge_metadata(existing, metadata)
        msg._metadata = merged
    
    await session.commit()
    await session.refresh(msg)
    return msg


def _deep_merge_metadata(existing: dict, new: dict) -> dict:
    """
    深度合并 metadata（对齐文档规范）
    
    Args:
        existing: 现有 metadata
        new: 新 metadata
        
    Returns:
        合并后的 metadata
    """
    result = existing.copy()
    for key, value in new.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_metadata(result[key], value)
        else:
            result[key] = value
    return result


async def list_messages(
    session: AsyncSession,
    conversation_id: str,
    limit: int = 1000,
    order: str = "asc"
) -> List[Message]:
    """获取对话的消息列表"""
    query = select(Message).where(Message.conversation_id == conversation_id)
    
    if order == "desc":
        query = query.order_by(Message.created_at.desc())
    else:
        query = query.order_by(Message.created_at.asc())
    
    query = query.limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_messages_before_cursor(
    session: AsyncSession,
    conversation_id: str,
    cursor_message_id: str,
    limit: int = 50
) -> List[Message]:
    """
    基于游标的分页查询（对齐文档规范）
    
    获取指定消息 ID 之前的 N 条消息（用于向上滚动加载）
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        cursor_message_id: 游标消息 ID（获取此消息之前的消息）
        limit: 返回数量
        
    Returns:
        消息列表（按创建时间倒序，从新到旧）
    """
    # 先获取游标消息的创建时间
    cursor_msg = await get_message(session, cursor_message_id)
    if not cursor_msg:
        # 游标消息不存在，返回空列表
        return []
    
    cursor_time = cursor_msg.created_at
    
    # 查询创建时间早于游标消息的消息
    query = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.created_at < cursor_time
        )
        .order_by(Message.created_at.desc())  # 从新到旧
        .limit(limit)
    )
    
    result = await session.execute(query)
    return list(result.scalars().all())


# 别名：用于 Mem0 更新服务
get_messages_by_conversation = list_messages

