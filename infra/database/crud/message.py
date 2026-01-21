"""
Message 表 CRUD 操作

支持 PostgreSQL JSONB 类型：
- content: List[Dict] 或 JSON 字符串
- metadata: Dict 或 JSON 字符串
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import uuid4
import json

from sqlalchemy import select 
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models import Message, Conversation
from infra.database.crud.base import get_by_id


def generate_message_id() -> str:
    """生成消息 ID（纯 UUID）"""
    return uuid4().hex


def _parse_content(content: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    解析 content 为 list 格式
    
    Args:
        content: JSON 字符串或 list
        
    Returns:
        content blocks 列表
    """
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
    """
    解析 metadata 为 dict 格式
    
    Args:
        metadata: JSON 字符串或 dict
        
    Returns:
        metadata 字典
    """
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


async def create_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: Union[str, List[Dict[str, Any]]],
    message_id: Optional[str] = None,
    status: Optional[str] = None,
    metadata: Optional[Union[str, Dict[str, Any]]] = None
) -> Message:
    """
    创建消息
    
    Args:
        session: 数据库会话
        conversation_id: 对话 ID
        role: 角色（user/assistant/system）
        content: 消息内容（JSON 字符串或 list）
        message_id: 消息 ID（可选）
        status: 状态（可选）
        metadata: 元数据（JSON 字符串或 dict）
    """
    msg = Message(
        id=message_id or generate_message_id(),
        conversation_id=conversation_id,
        role=role,
        content=_parse_content(content),
        status=status,
        created_at=datetime.now(),
        extra_data=_parse_metadata(metadata)
    )
    
    session.add(msg)
    
    # 同步更新对话的 updated_at（保证活跃对话在列表中上浮）
    conv = await session.get(Conversation, conversation_id)
    if conv:
        conv.updated_at = datetime.now()
    
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
    content: Optional[Union[str, List[Dict[str, Any]]]] = None,
    status: Optional[str] = None,
    metadata: Optional[Union[str, Dict[str, Any]]] = None
) -> Optional[Message]:
    """
    更新消息
    
    Args:
        session: 数据库会话
        message_id: 消息 ID
        content: 消息内容（JSON 字符串或 list）
        status: 状态
        metadata: 元数据（增量合并）
    """
    msg = await get_message(session, message_id)
    if not msg:
        return None
    
    if content is not None:
        msg.content = _parse_content(content)
    if status is not None:
        msg.status = status
    if metadata is not None:
        # 深度合并 extra_data（JSONB 支持直接操作）
        # 🔥 修复：确保 existing 是字典（可能从数据库读取为字符串）
        existing = msg.extra_data or {}
        if isinstance(existing, str):
            # 如果是字符串，尝试解析为字典
            try:
                existing = json.loads(existing)
            except json.JSONDecodeError:
                existing = {}
        elif not isinstance(existing, dict):
            existing = {}
        
        new_metadata = _parse_metadata(metadata)
        
        # 深度合并：对于嵌套的 dict，递归合并
        for key, value in new_metadata.items():
            if key in existing and isinstance(existing[key], dict) and isinstance(value, dict):
                existing[key].update(value)
            else:
                existing[key] = value
        
        msg.extra_data = existing
    
    # 同步更新对话的 updated_at（保证活跃对话在列表中上浮）
    conv = await session.get(Conversation, msg.conversation_id)
    if conv:
        conv.updated_at = datetime.now()
    
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

