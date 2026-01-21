"""
Conversation 服务层 - 对话管理业务逻辑

职责：
1. 业务逻辑编排
2. 异常处理和日志
3. 返回 Pydantic 模型

设计原则：
- Service 层只调用 crud.xxx() 函数
- 不直接写 SQLAlchemy 查询
- 不直接导入数据库模型
"""

import json
from logger import get_logger
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

from models.database import Conversation, Message
from infra.database import AsyncSessionLocal, crud

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
    
    注意：所有数据库操作都通过 crud 层完成
    """
    
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
            创建的对话对象（Pydantic 模型）
        """
        async with AsyncSessionLocal() as session:
            # 确保用户存在
            await crud.get_or_create_user(session, user_id=user_id)
            db_conv = await crud.create_conversation(
                session=session,
                user_id=user_id,
                title=title,
                metadata=metadata
            )
            
            logger.info(f"✅ 对话创建成功: id={db_conv.id}, user_id={user_id}")
            
            # 转换为 Pydantic 模型
            return Conversation(
                id=db_conv.id,
                user_id=db_conv.user_id,
                title=db_conv.title,
                created_at=db_conv.created_at,
                updated_at=db_conv.updated_at,
                metadata=db_conv.extra_data
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
        async with AsyncSessionLocal() as session:
            db_conv = await crud.get_conversation(session, conversation_id)
        
        if not db_conv:
            raise ConversationNotFoundError(f"对话不存在: {conversation_id}")
        
        return Conversation(
            id=db_conv.id,
            user_id=db_conv.user_id,
            title=db_conv.title,
            created_at=db_conv.created_at,
            updated_at=db_conv.updated_at,
            metadata=db_conv.extra_data
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
            {"conversations": [...], "total": int, "limit": int, "offset": int}
        """
        async with AsyncSessionLocal() as session:
            # 获取总数
            total = await crud.count_conversations(session, user_id)
            
            # 获取对话列表（带统计）
            conversations = await crud.list_conversations_with_stats(
                session=session,
                user_id=user_id,
                limit=limit,
                offset=offset
            )
        
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
        async with AsyncSessionLocal() as session:
            db_conv = await crud.update_conversation(
                session=session,
                conversation_id=conversation_id,
                title=title,
                metadata=metadata
            )
            
            if not db_conv:
                raise ConversationNotFoundError(f"对话不存在: {conversation_id}")
            
            logger.info(f"✅ 对话更新成功: id={conversation_id}")
            
            return Conversation(
                id=db_conv.id,
                user_id=db_conv.user_id,
                title=db_conv.title,
                created_at=db_conv.created_at,
                updated_at=db_conv.updated_at,
                metadata=db_conv.extra_data
            )
    
    async def delete_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """
        删除对话（同时删除所有消息）
        
        Args:
            conversation_id: 对话ID
            
        Returns:
            {"conversation_id": str, "deleted": bool, "deleted_messages": int}
            
        Raises:
            ConversationNotFoundError: 对话不存在
        """
        # 先检查对话是否存在
        await self.get_conversation(conversation_id)
        
        async with AsyncSessionLocal() as session:
            # 统计消息数量
            message_count = await crud.count_messages_in_conversation(session, conversation_id)
            
            # 删除对话（消息会被级联删除）
            success = await crud.delete_conversation(session, conversation_id)
        
        logger.info(f"✅ 对话删除成功: id={conversation_id}, deleted_messages={message_count}")
        
        return {
            "conversation_id": conversation_id,
            "deleted": success,
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
            {"conversation_id": str, "messages": [...], "total": int, ...}
            
        Raises:
            ConversationNotFoundError: 对话不存在
        """
        # 先检查对话是否存在
        await self.get_conversation(conversation_id)
        
        async with AsyncSessionLocal() as session:
            # 获取总数
            total = await crud.count_messages_in_conversation(session, conversation_id)
            
            # 获取消息列表
            db_messages = await crud.list_messages(
                session=session,
                conversation_id=conversation_id,
                limit=limit,
                order=order
            )
            
            # 转换为字典列表
            messages = []
            for db_msg in db_messages:
                # content 是 JSONB 类型，ORM 返回 list，无需 json.loads
                content = db_msg.content if db_msg.content else []
                
                messages.append({
                    "id": db_msg.id,
                    "conversation_id": db_msg.conversation_id,
                    "role": db_msg.role,
                    "content": content,
                    "status": db_msg.status,
                    "created_at": db_msg.created_at.isoformat() if db_msg.created_at else None,
                    "metadata": db_msg.extra_data
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
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None
    ) -> Message:
        """
        添加消息到对话
        
        Args:
            conversation_id: 对话ID
            role: 角色（user/assistant/system）
            content: 消息内容（JSON 数组格式）
            status: 消息状态
            metadata: 消息元数据
            message_id: 消息ID（可选）
            
        Returns:
            创建的消息对象
        """
        msg_id = message_id or f"msg_{uuid4().hex[:24]}"
        now = datetime.now()
        
        async with AsyncSessionLocal() as session:
            await crud.create_message(
                session=session,
                conversation_id=conversation_id,
                role=role,
                content=content,
                message_id=msg_id,
                status=status,
                metadata=metadata
            )
            
            # 更新对话的 updated_at
            await crud.update_conversation(
                session=session,
                conversation_id=conversation_id
            )
        
        # 日志
        status_info = f", status={status}" if status else ""
        
        logger.info(
            f"✅ 消息添加成功: id={msg_id}, conversation_id={conversation_id}, "
            f"role={role}{status_info}"
        )
        
        return Message(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            status=status,
            created_at=now,
            metadata=metadata or {}
        )
    
    async def update_message(
        self,
        message_id: str,
        content: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        更新消息内容
        
        Args:
            message_id: 消息ID
            content: 消息内容
            status: 消息状态
            metadata: 元数据（合并更新）
            
        Returns:
            更新后的消息对象
        """
        async with AsyncSessionLocal() as session:
            # 先获取现有消息
            db_msg = await crud.get_message(session, message_id)
            
            if not db_msg:
                raise ValueError(f"消息不存在: id={message_id}")
            
            # 合并 metadata
            existing_metadata = db_msg.extra_data or {}
            if metadata:
                existing_metadata.update(metadata)
            
            # 更新消息
            updated_msg = await crud.update_message(
                session=session,
                message_id=message_id,
                content=content,
                status=status,
                metadata=existing_metadata
            )
        
        # 日志
        status_info = f", status={status}" if status else ""
        
        logger.info(f"✅ 消息更新成功: id={message_id}{status_info}")
        
        # content 是 JSONB（list），需要转换为 JSON 字符串给 Pydantic 模型
        import json
        final_content = content if content is not None else updated_msg.content
        if isinstance(final_content, list):
            final_content = json.dumps(final_content, ensure_ascii=False)
        
        return Message(
            id=updated_msg.id,
            conversation_id=updated_msg.conversation_id,
            role=updated_msg.role,
            content=final_content,
            status=status if status is not None else updated_msg.status,
            created_at=updated_msg.created_at,
            metadata=existing_metadata
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
        async with AsyncSessionLocal() as session:
            summary = await crud.get_conversation_summary(session, conversation_id)
        
        if not summary:
            raise ConversationNotFoundError(f"对话不存在: {conversation_id}")
        
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
