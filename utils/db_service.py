"""
数据库服务层

提供用户、对话和消息的 CRUD 操作
"""

import logging
from typing import List, Optional
from datetime import datetime
from uuid import uuid4

from models.database import User, Conversation, Message
from utils.database import db_manager, serialize_metadata, deserialize_metadata

logger = logging.getLogger(__name__)


class UserService:
    """用户服务"""
    
    @staticmethod
    async def create_user(username: str, email: Optional[str] = None, metadata: Optional[dict] = None) -> User:
        """
        创建用户
        
        Args:
            username: 用户名
            email: 邮箱
            metadata: 元数据
            
        Returns:
            创建的用户对象
        """
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO users (username, email, metadata)
                VALUES (?, ?, ?)
                """,
                (username, email, serialize_metadata(metadata))
            )
            await db.commit()
            user_id = cursor.lastrowid
            
            logger.info(f"创建用户成功: user_id={user_id}, username={username}")
            
            return User(
                id=user_id,
                username=username,
                email=email,
                created_at=datetime.now(),
                metadata=metadata or {}
            )
    
    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return User(
                        id=row[0],
                        username=row[1],
                        email=row[2],
                        created_at=datetime.fromisoformat(row[3]) if row[3] else None,
                        metadata=deserialize_metadata(row[4])
                    )
                return None
    
    @staticmethod
    async def get_user_by_username(username: str) -> Optional[User]:
        """根据用户名获取用户"""
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return User(
                        id=row[0],
                        username=row[1],
                        email=row[2],
                        created_at=datetime.fromisoformat(row[3]) if row[3] else None,
                        metadata=deserialize_metadata(row[4])
                    )
                return None


class ConversationService:
    """对话服务"""
    
    @staticmethod
    async def create_conversation(
        user_id: str,
        id: Optional[str] = None,
        title: str = "新对话",
        metadata: Optional[dict] = None
    ) -> Conversation:
        """
        创建对话
        
        Args:
            user_id: 用户ID
            id: 对话ID（可选，不提供则自动生成 UUID）
            title: 对话标题
            metadata: 元数据
            
        Returns:
            创建的对话对象
        """
        # 如果没有提供 id，生成 UUID
        if not id:
            id = f"conv_{uuid4().hex[:24]}"
        
        async with db_manager.get_connection() as db:
            await db.execute(
                """
                INSERT INTO conversations (id, user_id, title, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (id, user_id, title, serialize_metadata(metadata))
            )
            await db.commit()
            
            logger.info(f"创建对话成功: id={id}, user_id={user_id}")
            
            return Conversation(
                id=id,
                user_id=user_id,
                title=title,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                metadata=metadata or {}
            )
    
    @staticmethod
    async def get_conversation(conversation_id: str) -> Optional[Conversation]:
        """根据 id 获取对话"""
        async with db_manager.get_connection() as db:
            async with db.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conversation_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    # 表结构: id, user_id, title, created_at, updated_at, metadata
                    return Conversation(
                        id=row[0],
                        user_id=row[1],
                        title=row[2],
                        created_at=datetime.fromisoformat(row[3]) if row[3] else None,
                        updated_at=datetime.fromisoformat(row[4]) if row[4] else None,
                        metadata=deserialize_metadata(row[5])
                    )
                return None
    
    @staticmethod
    async def update_conversation_metadata(
        conversation_id: str,
        **metadata_updates
    ) -> bool:
        """
        更新对话的 metadata 字段（合并更新）
        
        Args:
            conversation_id: 对话ID
            **metadata_updates: 要更新的 metadata 字段（如 compression=...）
            
        Returns:
            是否更新成功
        """
        async with db_manager.get_connection() as db:
            # 1. 读取现有 metadata
            async with db.execute(
                "SELECT metadata FROM conversations WHERE id = ?",
                (conversation_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    logger.error(f"对话不存在: conversation_id={conversation_id}")
                    return False
                
                current_metadata = deserialize_metadata(row[0])
            
            # 2. 合并更新
            current_metadata.update(metadata_updates)
            
            # 3. 写回数据库
            await db.execute(
                """
                UPDATE conversations 
                SET metadata = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (serialize_metadata(current_metadata), conversation_id)
            )
            await db.commit()
            
            logger.info(f"更新对话 metadata 成功: conversation_id={conversation_id}")
            return True
    
    @staticmethod
    async def get_user_conversations(user_id: str, limit: int = 50) -> List[Conversation]:
        """获取用户的所有对话"""
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT * FROM conversations 
                WHERE user_id = ? 
                ORDER BY updated_at DESC 
                LIMIT ?
                """,
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    Conversation(
                        id=row[0],
                        user_id=row[1],
                        title=row[2],
                        created_at=datetime.fromisoformat(row[3]) if row[3] else None,
                        updated_at=datetime.fromisoformat(row[4]) if row[4] else None,
                        metadata=deserialize_metadata(row[5])
                    )
                    for row in rows
                ]
    
    @staticmethod
    async def update_conversation_title(conversation_id: str, title: str):
        """更新对话标题"""
        async with db_manager.get_connection() as db:
            await db.execute(
                """
                UPDATE conversations 
                SET title = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
                """,
                (title, conversation_id)
            )
            await db.commit()
            logger.info(f"更新对话标题: id={conversation_id}, title={title}")
    
    @staticmethod
    async def update_conversation_timestamp(conversation_id: str):
        """更新对话时间戳（有新消息时调用）"""
        async with db_manager.get_connection() as db:
            await db.execute(
                """
                UPDATE conversations 
                SET updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
                """,
                (conversation_id,)
            )
            await db.commit()


class MessageService:
    """消息服务"""
    
    @staticmethod
    async def create_message(
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> Message:
        """
        创建消息
        
        Args:
            conversation_id: 对话ID
            role: 角色 (user/assistant/system)
            content: 消息内容
            metadata: 元数据
            
        Returns:
            创建的消息对象
        """
        async with db_manager.get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO messages (conversation_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, serialize_metadata(metadata))
            )
            await db.commit()
            message_id = cursor.lastrowid
            
            # 更新对话时间戳
            await ConversationService.update_conversation_timestamp(conversation_id)
            
            logger.debug(f"创建消息: id={message_id}, conversation_id={conversation_id}, role={role}")
            
            return Message(
                id=message_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_at=datetime.now(),
                metadata=metadata or {}
            )
    
    @staticmethod
    async def get_conversation_messages(
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Message]:
        """
        获取对话的所有消息
        
        Args:
            conversation_id: 对话ID
            limit: 限制返回数量
            
        Returns:
            消息列表
        """
        async with db_manager.get_connection() as db:
            if limit:
                query = """
                    SELECT * FROM messages 
                    WHERE conversation_id = ? 
                    ORDER BY created_at ASC 
                    LIMIT ?
                """
                params = (conversation_id, limit)
            else:
                query = """
                    SELECT * FROM messages 
                    WHERE conversation_id = ? 
                    ORDER BY created_at ASC
                """
                params = (conversation_id,)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    Message(
                        id=row[0],
                        conversation_id=row[1],
                        role=row[2],
                        content=row[3],
                        created_at=datetime.fromisoformat(row[4]) if row[4] else None,
                        metadata=deserialize_metadata(row[5])
                    )
                    for row in rows
                ]
    
    @staticmethod
    async def get_recent_messages(
        conversation_id: str,
        limit: int = 10
    ) -> List[Message]:
        """获取最近的N条消息"""
        async with db_manager.get_connection() as db:
            async with db.execute(
                """
                SELECT * FROM messages 
                WHERE conversation_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
                """,
                (conversation_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                # 反转顺序，使最早的消息在前
                messages = [
                    Message(
                        id=row[0],
                        conversation_id=row[1],
                        role=row[2],
                        content=row[3],
                        created_at=datetime.fromisoformat(row[4]) if row[4] else None,
                        metadata=deserialize_metadata(row[5])
                    )
                    for row in rows
                ]
                return list(reversed(messages))

