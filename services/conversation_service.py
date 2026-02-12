"""
Conversation 服务层 - 对话管理业务逻辑

职责：
1. 业务逻辑编排
2. 异常处理和日志
3. 返回 Pydantic 模型

设计原则：
- Service 层只调用 local_store.crud.xxx() 函数
- 使用 SQLite 本地存储
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from infra.local_store import get_workspace, crud as local_crud
from infra.local_store.engine import get_local_session_factory
from logger import get_logger
from models.database import Conversation, Message

logger = get_logger(__name__)


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

    注意：所有数据库操作都通过 local_store.crud 层完成
    """

    @staticmethod
    def _parse_metadata(metadata: Any) -> dict:
        """
        解析 metadata 为字典

        Args:
            metadata: 可能是 dict 或 JSON 字符串

        Returns:
            字典对象
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

    # ==================== 对话 CRUD ====================

    async def create_conversation(
        self,
        user_id: str,
        title: str = "新对话",
        metadata: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
    ) -> Conversation:
        """
        创建新对话

        Args:
            user_id: 用户ID
            title: 对话标题
            metadata: 对话元数据
            conversation_id: 可选的对话 ID

        Returns:
            创建的对话对象（Pydantic 模型）
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            db_conv = await local_crud.create_conversation(
                session=session,
                user_id=user_id,
                title=title,
                metadata=metadata,
                conversation_id=conversation_id,
            )

            logger.info(f"✅ 对话创建成功: id={db_conv.id}, user_id={user_id}")

            return Conversation(
                id=db_conv.id,
                user_id=db_conv.user_id,
                title=db_conv.title,
                status=db_conv.status or "active",
                created_at=db_conv.created_at,
                updated_at=db_conv.updated_at,
                metadata=self._parse_metadata(db_conv.metadata_json),
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
        factory = await get_local_session_factory()
        async with factory() as session:
            db_conv = await local_crud.get_conversation(session, conversation_id)

        if not db_conv:
            raise ConversationNotFoundError(f"对话不存在: {conversation_id}")

        return Conversation(
            id=db_conv.id,
            user_id=db_conv.user_id,
            title=db_conv.title,
            status=db_conv.status or "active",
            created_at=db_conv.created_at,
            updated_at=db_conv.updated_at,
            metadata=self._parse_metadata(db_conv.metadata_json),
        )

    async def get_or_create_conversation(
        self,
        user_id: str,
        conversation_id: Optional[str] = None,
        title: str = "新对话",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[Conversation, bool]:
        """
        获取或创建对话

        Args:
            user_id: 用户ID
            conversation_id: 对话ID（可选）
            title: 标题（仅创建时使用）
            metadata: 元数据（仅创建时使用）

        Returns:
            (对话对象, 是否新创建)
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            db_conv, is_new = await local_crud.get_or_create_conversation(
                session=session,
                user_id=user_id,
                conversation_id=conversation_id,
                title=title,
                metadata=metadata,
            )

            if is_new:
                logger.info(f"✅ 对话创建成功: id={db_conv.id}, user_id={user_id}")
            else:
                logger.debug(f"📂 使用已有对话: id={db_conv.id}")

            return Conversation(
                id=db_conv.id,
                user_id=db_conv.user_id,
                title=db_conv.title,
                status=db_conv.status or "active",
                created_at=db_conv.created_at,
                updated_at=db_conv.updated_at,
                metadata=self._parse_metadata(db_conv.metadata_json),
            ), is_new

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取对话列表

        Args:
            user_id: 用户ID
            limit: 每页数量
            offset: 偏移量
            agent_id: 可选，按 agent_id 过滤

        Returns:
            包含 conversations, total, limit, offset 的字典
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            total = await local_crud.count_conversations(
                session, user_id, agent_id=agent_id
            )
            conversations = await local_crud.list_conversations(
                session=session,
                user_id=user_id,
                limit=limit,
                offset=offset,
                agent_id=agent_id,
            )

            items = [
                Conversation(
                    id=conv.id,
                    user_id=conv.user_id,
                    title=conv.title,
                    status=conv.status or "active",
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    metadata=self._parse_metadata(conv.metadata_json),
                )
                for conv in conversations
            ]

            return {
                "conversations": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    async def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Conversation:
        """
        更新对话

        Args:
            conversation_id: 对话ID
            title: 新标题
            status: 新状态
            metadata: 新元数据

        Returns:
            更新后的对话对象
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            db_conv = await local_crud.update_conversation(
                session=session,
                conversation_id=conversation_id,
                title=title,
                status=status,
                metadata=metadata,
            )

        if not db_conv:
            raise ConversationNotFoundError(f"对话不存在: {conversation_id}")

        logger.info(f"✅ 对话更新成功: id={conversation_id}")

        return Conversation(
            id=db_conv.id,
            user_id=db_conv.user_id,
            title=db_conv.title,
            status=db_conv.status or "active",
            created_at=db_conv.created_at,
            updated_at=db_conv.updated_at,
            metadata=self._parse_metadata(db_conv.metadata_json),
        )

    async def delete_conversation(self, conversation_id: str) -> bool:
        """
        删除对话

        Args:
            conversation_id: 对话ID

        Returns:
            是否删除成功
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            success = await local_crud.delete_conversation(session, conversation_id)

        if success:
            logger.info(f"✅ 对话删除成功: id={conversation_id}")
        else:
            logger.warning(f"⚠️ 对话删除失败或不存在: id={conversation_id}")

        return success

    # ==================== 消息 CRUD ====================

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
        order: str = "asc",
    ) -> Dict[str, Any]:
        """
        获取消息列表

        Args:
            conversation_id: 对话ID
            limit: 每页数量
            offset: 偏移量
            order: 排序方式 (asc/desc)

        Returns:
            包含 items, total, limit, offset 的字典
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            messages = await local_crud.list_messages(
                session=session,
                conversation_id=conversation_id,
                limit=limit,
                offset=offset,
                order=order,
            )

            items = []
            for msg in messages:
                # content_json 是 DB 中的原始 JSON 字符串，Message.content 类型为 str
                # 注意：msg.content 是 @property 会解析为 list，不能直接用
                items.append(Message(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    role=msg.role,
                    content=msg.content_json or "[]",
                    status=msg.status or "completed",
                    created_at=msg.created_at,
                    metadata=self._parse_metadata(msg.metadata_json),
                ))

            return {
                "items": items,
                "total": len(items),
                "limit": limit,
                "offset": offset,
            }

    async def create_message(
        self,
        conversation_id: str,
        role: str,
        content: Any,
        message_id: Optional[str] = None,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """
        创建消息

        Args:
            conversation_id: 对话ID
            role: 角色 (user/assistant)
            content: 消息内容
            message_id: 可选的消息ID
            status: 消息状态
            metadata: 元数据

        Returns:
            创建的消息对象
        """
        # 序列化 content
        if isinstance(content, (list, dict)):
            content_str = json.dumps(content, ensure_ascii=False)
        else:
            content_str = str(content) if content else ""

        factory = await get_local_session_factory()
        async with factory() as session:
            db_msg = await local_crud.create_message(
                session=session,
                conversation_id=conversation_id,
                role=role,
                content=content_str,
                message_id=message_id,
                status=status,
                metadata=metadata,
            )

            # 更新对话的 updated_at
            await local_crud.update_conversation(
                session=session,
                conversation_id=conversation_id,
            )

            logger.debug(f"✅ 消息创建成功: id={db_msg.id}, role={role}")

            # content_str 已序列化为 JSON 字符串，Message.content 类型为 str
            return Message(
                id=db_msg.id,
                conversation_id=db_msg.conversation_id,
                role=db_msg.role,
                content=content_str or "[]",
                status=db_msg.status or "completed",
                created_at=db_msg.created_at,
                metadata=self._parse_metadata(db_msg.metadata_json),
            )

    async def update_message(
        self,
        message_id: str,
        content: Optional[Any] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Message]:
        """
        更新消息

        Args:
            message_id: 消息ID
            content: 新内容
            status: 新状态
            metadata: 新元数据

        Returns:
            更新后的消息对象，如果不存在返回 None
        """
        # 序列化 content
        content_str = None
        if content is not None:
            if isinstance(content, (list, dict)):
                content_str = json.dumps(content, ensure_ascii=False)
            else:
                content_str = str(content)

        factory = await get_local_session_factory()
        async with factory() as session:
            db_msg = await local_crud.update_message(
                session=session,
                message_id=message_id,
                content=content_str,
                status=status,
                metadata=metadata,
            )

        if not db_msg:
            logger.warning(f"⚠️ 消息不存在: id={message_id}")
            return None

        logger.debug(f"✅ 消息更新成功: id={message_id}")

        # content_json 是 DB 中的原始 JSON 字符串，Message.content 类型为 str
        # 注意：db_msg.content 是 @property 会解析为 list，不能直接用
        return Message(
            id=db_msg.id,
            conversation_id=db_msg.conversation_id,
            role=db_msg.role,
            content=db_msg.content_json or "[]",
            status=db_msg.status or "completed",
            created_at=db_msg.created_at,
            metadata=self._parse_metadata(db_msg.metadata_json),
        )

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
        order: str = "asc",
        before_cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取对话历史消息（支持游标分页）

        Args:
            conversation_id: 对话ID
            limit: 每页数量
            offset: 偏移量
            order: 排序方式 (asc/desc)
            before_cursor: 游标（message_id），获取此消息之前的消息

        Returns:
            包含 messages, conversation_metadata, total, has_more, next_cursor 的字典
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            # 获取对话信息（同时验证对话是否存在）
            conv = await local_crud.get_conversation(session, conversation_id)
            if not conv:
                raise ConversationNotFoundError(f"对话不存在: {conversation_id}")

            # 多取 1 条用于判断 has_more
            messages = await local_crud.list_messages(
                session=session,
                conversation_id=conversation_id,
                limit=limit + 1,
                offset=offset if not before_cursor else 0,
                order=order,
                before_cursor=before_cursor,
            )

            has_more = len(messages) > limit
            if has_more:
                messages = messages[:limit]

            # before_cursor query returns DESC order (closest to cursor first),
            # reverse to ASC for chronological display
            if before_cursor:
                messages = list(reversed(messages))

            items = [
                Message(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    role=msg.role,
                    content=msg.content_json or "[]",
                    status=msg.status or "completed",
                    created_at=msg.created_at,
                    metadata=self._parse_metadata(msg.metadata_json),
                )
                for msg in messages
            ]

            # next_cursor: oldest message ID in current batch,
            # used by client to load even older messages
            next_cursor = items[0].id if has_more and items else None

            # 构建 conversation_metadata
            conv_metadata = self._parse_metadata(conv.metadata_json)

            return {
                "conversation_id": conversation_id,
                "conversation_metadata": conv_metadata,
                "messages": items,
                "total": len(items),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_cursor": next_cursor,
            }

    async def search_conversations(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        搜索对话（标题匹配 + 消息全文搜索）

        同时搜索对话标题和消息内容，合并去重后返回。

        Args:
            user_id: 用户ID
            query: 搜索关键词
            limit: 返回数量

        Returns:
            包含 conversations 和 total 的字典
        """
        if not query or not query.strip():
            return {"conversations": [], "total": 0}

        factory = await get_local_session_factory()
        async with factory() as session:
            from sqlalchemy import select
            from infra.local_store.models import LocalConversation
            from infra.local_store.fts import search_messages

            # 1. 标题模糊搜索
            keyword = f"%{query.strip()}%"
            title_result = await session.execute(
                select(LocalConversation)
                .where(
                    LocalConversation.user_id == user_id,
                    LocalConversation.title.ilike(keyword),
                )
                .order_by(LocalConversation.updated_at.desc())
                .limit(limit)
            )
            title_matches = list(title_result.scalars().all())

            # 2. 消息内容全文搜索（FTS5）
            fts_results = await search_messages(
                session, query.strip(), limit=limit * 2
            )

            # 按 conversation_id 分组，取每个对话最相关的片段
            fts_conv_map: Dict[str, str] = {}
            for r in fts_results:
                if r.conversation_id not in fts_conv_map:
                    # 截取片段（最多 80 字符）
                    snippet = r.text_content[:80].replace("\n", " ")
                    fts_conv_map[r.conversation_id] = snippet

            # 查询 FTS 命中的对话（只取属于该用户的）
            fts_conv_ids = list(fts_conv_map.keys())
            content_matches = []
            if fts_conv_ids:
                content_result = await session.execute(
                    select(LocalConversation)
                    .where(
                        LocalConversation.id.in_(fts_conv_ids),
                        LocalConversation.user_id == user_id,
                    )
                    .order_by(LocalConversation.updated_at.desc())
                )
                content_matches = list(content_result.scalars().all())

            # 3. 合并去重（标题匹配优先）
            seen_ids = set()
            merged = []

            for conv in title_matches:
                if conv.id not in seen_ids:
                    seen_ids.add(conv.id)
                    merged.append({
                        "conversation": Conversation(
                            id=conv.id,
                            user_id=conv.user_id,
                            title=conv.title,
                            status=conv.status or "active",
                            created_at=conv.created_at,
                            updated_at=conv.updated_at,
                            metadata=self._parse_metadata(conv.metadata_json),
                        ),
                        "match_type": "title",
                        "snippet": None,
                    })

            for conv in content_matches:
                if conv.id not in seen_ids:
                    seen_ids.add(conv.id)
                    merged.append({
                        "conversation": Conversation(
                            id=conv.id,
                            user_id=conv.user_id,
                            title=conv.title,
                            status=conv.status or "active",
                            created_at=conv.created_at,
                            updated_at=conv.updated_at,
                            metadata=self._parse_metadata(conv.metadata_json),
                        ),
                        "match_type": "content",
                        "snippet": fts_conv_map.get(conv.id),
                    })

            return {
                "conversations": merged[:limit],
                "total": len(merged),
            }

    async def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """
        获取对话摘要

        Args:
            conversation_id: 对话ID

        Returns:
            对话摘要信息
        """
        factory = await get_local_session_factory()
        async with factory() as session:
            conv = await local_crud.get_conversation(session, conversation_id)
            if not conv:
                raise ConversationNotFoundError(f"对话不存在: {conversation_id}")

            messages = await local_crud.list_messages(
                session=session,
                conversation_id=conversation_id,
                limit=1000,
                order="asc",
            )

            return {
                "conversation_id": conversation_id,
                "title": conv.title,
                "message_count": len(messages),
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            }


# ==================== 单例 ====================

_conversation_service: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    """获取对话服务单例"""
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
    return _conversation_service
