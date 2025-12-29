"""
Conversation 服务层 - 对话管理业务逻辑

职责：
1. 对话 CRUD 业务逻辑
2. 历史消息查询和管理
3. 对话统计和摘要
4. 数据库操作封装

设计原则：
- 单一职责：只管理 Conversation 和 Message
- 数据持久化到 SQLite
- 返回 Pydantic 模型
"""

from logger import get_logger
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

from models.database import Conversation, Message
from utils.database import db_manager, serialize_metadata, deserialize_metadata

logger = get_logger("conversation_service")


class ConversationServiceError(Exception):
    """对话服务异常基类"""
    pass


class ConversationNotFoundError(ConversationServiceError):
    """对话不存在异常"""
    pass


class ConversationService:
    """
    对话服务
    
    提供对话和消息的完整生命周期管理
    """
    
    def __init__(self):
        """初始化对话服务"""
        self.db = db_manager
    
    # ==================== 对话 CRUD ====================
    
    async def create_conversation(
        self,
        user_id: str,
        title: str = "新对话",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Conversation:
        """
        创建新对话
        
        Args:
            user_id: 用户ID
            title: 对话标题
            metadata: 对话元数据
            
        Returns:
            创建的对话对象
        """
        conversation_id = f"conv_{uuid4().hex[:24]}"
        now = datetime.now()
        
        async with self.db.get_connection() as db:
            await db.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    user_id,
                    title,
                    now.isoformat(),
                    now.isoformat(),
                    serialize_metadata(metadata)
                )
            )
            await db.commit()
        
        logger.info(f"✅ 对话创建成功: id={conversation_id}, user_id={user_id}")
        
        return Conversation(
            id=conversation_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
    
    async def get_conversation(self, conversation_id: str) -> Conversation:
        """
        获取对话详情
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            对话对象
            
        Raises:
            ConversationNotFoundError: 对话不存在
        """
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, title, created_at, updated_at, metadata
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,)
            )
            row = await cursor.fetchone()
        
        if not row:
            raise ConversationNotFoundError(f"对话不存在: {conversation_id}")
        
        return Conversation(
            id=row[0],
            user_id=row[1],
            title=row[2],
            created_at=datetime.fromisoformat(row[3]) if row[3] else None,
            updated_at=datetime.fromisoformat(row[4]) if row[4] else None,
            metadata=deserialize_metadata(row[5])
        )
    
    async def list_conversations(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取用户的对话列表（带统计信息）
        
        Args:
            user_id: 用户ID
            limit: 每页数量
            offset: 偏移量
            
        Returns:
            {
                "conversations": [对话列表],
                "total": 总数,
                "limit": 每页数量,
                "offset": 偏移量
            }
        """
        async with self.db.get_connection() as db:
            # 获取总数
            cursor = await db.execute(
                "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
                (user_id,)
            )
            total = (await cursor.fetchone())[0]
            
            # 获取对话列表（带消息统计）
            cursor = await db.execute(
                """
                SELECT 
                    c.id,
                    c.user_id,
                    c.title,
                    c.created_at,
                    c.updated_at,
                    c.metadata,
                    COUNT(m.id) as message_count,
                    MAX(m.created_at) as last_message_at,
                    (SELECT content FROM messages WHERE conversation_id = c.id 
                     ORDER BY created_at DESC LIMIT 1) as last_message
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.user_id = ?
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset)
            )
            rows = await cursor.fetchall()
        
        conversations = []
        for row in rows:
            conversations.append({
                "id": row[0],
                "user_id": row[1],
                "title": row[2],
                "created_at": row[3],
                "updated_at": row[4],
                "metadata": deserialize_metadata(row[5]),
                "message_count": row[6] or 0,
                "last_message_at": row[7],
                "last_message": row[8]
            })
        
        logger.info(f"✅ 获取对话列表: user_id={user_id}, total={total}, returned={len(conversations)}")
        
        return {
            "conversations": conversations,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    async def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Conversation:
        """
        更新对话信息
        
        Args:
            conversation_id: 对话ID
            title: 新标题（可选）
            metadata: 新元数据（可选）
            
        Returns:
            更新后的对话对象
            
        Raises:
            ConversationNotFoundError: 对话不存在
        """
        # 先检查对话是否存在
        await self.get_conversation(conversation_id)
        
        now = datetime.now()
        update_fields = ["updated_at = ?"]
        params = [now.isoformat()]
        
        if title is not None:
            update_fields.append("title = ?")
            params.append(title)
        
        if metadata is not None:
            update_fields.append("metadata = ?")
            params.append(serialize_metadata(metadata))
        
        params.append(conversation_id)
        
        async with self.db.get_connection() as db:
            await db.execute(
                f"""
                UPDATE conversations
                SET {', '.join(update_fields)}
                WHERE id = ?
                """,
                params
            )
            await db.commit()
        
        logger.info(f"✅ 对话更新成功: id={conversation_id}")
        
        # 返回更新后的对话
        return await self.get_conversation(conversation_id)
    
    async def delete_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """
        删除对话（同时删除所有消息）
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            {
                "conversation_id": str,
                "deleted": bool,
                "deleted_messages": int
            }
            
        Raises:
            ConversationNotFoundError: 对话不存在
        """
        # 先检查对话是否存在
        await self.get_conversation(conversation_id)
        
        async with self.db.get_connection() as db:
            # 统计消息数量
            cursor = await db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )
            message_count = (await cursor.fetchone())[0]
            
            # 删除所有消息
            await db.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )
            
            # 删除对话
            await db.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            
            await db.commit()
        
        logger.info(f"✅ 对话删除成功: id={conversation_id}, deleted_messages={message_count}")
        
        return {
            "conversation_id": conversation_id,
            "deleted": True,
            "deleted_messages": message_count
        }
    
    # ==================== 历史消息查询 ====================
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
        order: str = "asc"
    ) -> Dict[str, Any]:
        """
        获取对话的历史消息
        
        Args:
            conversation_id: 对话ID
            limit: 每页数量
            offset: 偏移量
            order: 排序方式（asc/desc）
            
        Returns:
            {
                "conversation_id": str,
                "messages": [消息列表],
                "total": 总数,
                "limit": 每页数量,
                "offset": 偏移量,
                "has_more": 是否有更多
            }
            
        Raises:
            ConversationNotFoundError: 对话不存在
        """
        # 先检查对话是否存在
        await self.get_conversation(conversation_id)
        
        order_sql = "ASC" if order == "asc" else "DESC"
        
        async with self.db.get_connection() as db:
            # 获取总数
            cursor = await db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )
            total = (await cursor.fetchone())[0]
            
            # 获取消息列表
            cursor = await db.execute(
                f"""
                SELECT id, conversation_id, role, content, created_at, metadata
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at {order_sql}
                LIMIT ? OFFSET ?
                """,
                (conversation_id, limit, offset)
            )
            rows = await cursor.fetchall()
        
        messages = []
        for row in rows:
            messages.append({
                "id": row[0],
                "conversation_id": row[1],
                "role": row[2],
                "content": row[3],
                "created_at": row[4],
                "metadata": deserialize_metadata(row[5])
            })
        
        has_more = (offset + len(messages)) < total
        
        logger.info(
            f"✅ 获取历史消息: conversation_id={conversation_id}, "
            f"total={total}, returned={len(messages)}, has_more={has_more}"
        )
        
        return {
            "conversation_id": conversation_id,
            "messages": messages,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": has_more
        }
    
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        添加消息到对话
        
        Args:
            conversation_id: 对话ID
            role: 角色（user/assistant/system）
            content: 消息内容
            metadata: 消息元数据
            
        Returns:
            创建的消息对象
        """
        now = datetime.now()
        
        async with self.db.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    role,
                    content,
                    now.isoformat(),
                    serialize_metadata(metadata)
                )
            )
            message_id = cursor.lastrowid
            
            # 更新对话的 updated_at
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now.isoformat(), conversation_id)
            )
            
            await db.commit()
        
        logger.info(f"✅ 消息添加成功: id={message_id}, conversation_id={conversation_id}")
        
        return Message(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now,
            metadata=metadata or {}
        )
    
    async def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """
        获取对话摘要
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            对话摘要信息
            
        Raises:
            ConversationNotFoundError: 对话不存在
        """
        # 获取对话基本信息
        conversation = await self.get_conversation(conversation_id)
        
        async with self.db.get_connection() as db:
            # 获取消息统计
            cursor = await db.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) as user_count,
                    SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) as assistant_count
                FROM messages
                WHERE conversation_id = ?
                """,
                (conversation_id,)
            )
            stats = await cursor.fetchone()
            
            # 获取最后一条消息
            cursor = await db.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (conversation_id,)
            )
            last_message_row = await cursor.fetchone()
        
        last_message = None
        if last_message_row:
            last_message = {
                "role": last_message_row[0],
                "content": last_message_row[1],
                "created_at": last_message_row[2]
            }
        
        summary = {
            "conversation_id": conversation_id,
            "title": conversation.title,
            "message_count": stats[0] or 0,
            "user_message_count": stats[1] or 0,
            "assistant_message_count": stats[2] or 0,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
            "last_message": last_message
        }
        
        logger.info(f"✅ 对话摘要: conversation_id={conversation_id}, message_count={summary['message_count']}")
        
        return summary


# ==================== 便捷函数 ====================

_default_conversation_service: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    """
    获取默认的 Conversation Service 实例（单例）
    
    Returns:
        ConversationService 实例
    """
    global _default_conversation_service
    if _default_conversation_service is None:
        _default_conversation_service = ConversationService()
    return _default_conversation_service

