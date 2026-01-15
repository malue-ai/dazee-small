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
    """生成消息 ID（纯 UUID）"""
    return uuid4().hex


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
        msg.extra_data = metadata
    
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
        # 合并 metadata
        existing = msg.extra_data
        existing.update(metadata)
        msg.extra_data = existing
    
    await session.commit()
    await session.refresh(msg)
    return msg


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


# 别名：用于 Mem0 更新服务
get_messages_by_conversation = list_messages

