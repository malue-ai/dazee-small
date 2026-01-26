"""
Conversation 表 CRUD 操作

职责：封装所有对话相关的数据库操作
Service 层只调用这里的函数，不直接写 SQLAlchemy 查询
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models import Conversation
from infra.database.models.message import Message
from infra.database.crud.base import get_by_id, delete_by_id


async def create_conversation(
    session: AsyncSession,
    user_id: str,
    title: str = "新对话",
    metadata: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[str] = None
) -> Conversation:
    """
    创建对话
    
    Args:
        session: 数据库会话
        user_id: 用户 ID
        title: 对话标题
        metadata: 对话元数据
        conversation_id: 可选的对话 ID（如果不提供则自动生成）
    
    Returns:
        创建的对话对象
    """
    conv = Conversation(
        id=conversation_id or str(uuid4()),
        user_id=user_id,
        title=title,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    if metadata:
        conv.extra_data = metadata
    
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def get_conversation(
    session: AsyncSession,
    conversation_id: str
) -> Optional[Conversation]:
    """获取对话"""
    return await get_by_id(session, Conversation, conversation_id)


async def update_conversation(
    session: AsyncSession,
    conversation_id: str,
    title: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Conversation]:
    """更新对话"""
    conv = await get_conversation(session, conversation_id)
    if not conv:
        return None
    
    if title is not None:
        conv.title = title
    if metadata is not None:
        conv.extra_data = metadata
    conv.updated_at = datetime.now()
    
    await session.commit()
    await session.refresh(conv)
    return conv


async def list_conversations(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0
) -> List[Conversation]:
    """获取用户的对话列表"""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def count_conversations(
    session: AsyncSession,
    user_id: str
) -> int:
    """统计用户的对话数量"""
    result = await session.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
    )
    return result.scalar() or 0


async def list_conversations_with_stats(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    获取用户的对话列表（带消息统计）
    
    使用子查询优化，避免 N+1 查询问题
    
    返回字典列表，包含 message_count 和 last_message
    """
    from sqlalchemy import literal_column
    from sqlalchemy.orm import selectinload
    
    # 子查询：每个对话的消息数量
    msg_count_subq = (
        select(
            Message.conversation_id,
            func.count(Message.id).label("message_count")
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    
    # 子查询：每个对话的最后一条消息（使用 DISTINCT ON 或 ROW_NUMBER）
    # PostgreSQL 支持 DISTINCT ON，更简洁
    last_msg_subq = (
        select(
            Message.conversation_id,
            Message.content.label("last_content"),
            Message.created_at.label("last_message_at")
        )
        .distinct(Message.conversation_id)
        .order_by(Message.conversation_id, Message.created_at.desc())
        .subquery()
    )
    
    # 主查询：JOIN 对话表和子查询
    query = (
        select(
            Conversation,
            func.coalesce(msg_count_subq.c.message_count, 0).label("message_count"),
            last_msg_subq.c.last_content,
            last_msg_subq.c.last_message_at
        )
        .outerjoin(msg_count_subq, Conversation.id == msg_count_subq.c.conversation_id)
        .outerjoin(last_msg_subq, Conversation.id == last_msg_subq.c.conversation_id)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    result = await session.execute(query)
    rows = result.all()
    
    # 辅助函数：确保 metadata 是字典
    def _ensure_dict(value):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                import json
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return {}
    
    return [
        {
            "id": row.Conversation.id,
            "user_id": row.Conversation.user_id,
            "title": row.Conversation.title,
            "status": row.Conversation.status,
            "created_at": row.Conversation.created_at.isoformat() if row.Conversation.created_at else None,
            "updated_at": row.Conversation.updated_at.isoformat() if row.Conversation.updated_at else None,
            "metadata": _ensure_dict(row.Conversation.extra_data),
            "message_count": row.message_count,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "last_message": row.last_content
        }
        for row in rows
    ]


async def get_conversation_summary(
    session: AsyncSession,
    conversation_id: str
) -> Optional[Dict[str, Any]]:
    """
    获取对话摘要（含消息统计）
    
    Returns:
        包含 message_count, user_message_count, assistant_message_count, last_message 的字典
    """
    conv = await get_conversation(session, conversation_id)
    if not conv:
        return None
    
    # 总消息数
    total_result = await session.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    total = total_result.scalar() or 0
    
    # 用户消息数
    user_result = await session.execute(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation_id,
            Message.role == 'user'
        )
    )
    user_count = user_result.scalar() or 0
    
    # 助手消息数
    assistant_result = await session.execute(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation_id,
            Message.role == 'assistant'
        )
    )
    assistant_count = assistant_result.scalar() or 0
    
    # 最后一条消息
    last_msg_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()
    
    last_message = None
    if last_msg:
        last_message = {
            "role": last_msg.role,
            "content": last_msg.content,
            "created_at": last_msg.created_at.isoformat() if last_msg.created_at else None
        }
    
    return {
        "conversation_id": conversation_id,
        "title": conv.title,
        "message_count": total,
        "user_message_count": user_count,
        "assistant_message_count": assistant_count,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        "last_message": last_message
    }


async def delete_conversation(
    session: AsyncSession,
    conversation_id: str
) -> bool:
    """删除对话（级联删除消息）"""
    return await delete_by_id(session, Conversation, conversation_id)


async def get_conversations_since(
    session: AsyncSession,
    since: datetime,
    user_id: Optional[str] = None,
    limit: int = 1000
) -> List[Conversation]:
    """
    获取指定时间之后有更新的会话列表（用于 Mem0 增量更新）
    
    包括：新创建的对话 OR 有新消息的对话（updated_at 更新）
    
    Args:
        session: 数据库会话
        since: 开始时间
        user_id: 用户 ID（可选，不指定则获取所有用户）
        limit: 最大返回数量
        
    Returns:
        会话列表
    """
    
    # 同时检查 created_at 和 updated_at，捕获所有活跃对话
    query = select(Conversation).where(
        or_(
            Conversation.created_at >= since,
            Conversation.updated_at >= since
        )
    )
    
    if user_id:
        query = query.where(Conversation.user_id == user_id)
    
    query = query.order_by(Conversation.updated_at.asc()).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_messages_in_conversation(
    session: AsyncSession,
    conversation_id: str
) -> int:
    """统计对话中的消息数量"""
    result = await session.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    return result.scalar() or 0

