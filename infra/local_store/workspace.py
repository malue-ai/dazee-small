"""
Workspace 管理器 - 本地存储统一入口

整合 SQLite 存储层的所有组件：
┌───────────────────────────────────────────────────────────────────────┐
│                    存储层（100% 本地）                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │
│  │ SQLite      │ │ SQLite FTS5 │ │ sqlite-vec  │ │ Skills 缓存 │      │
│  │ (消息/会话) │ │ (全文索引)   │ │ (可选向量)  │ │ (延迟加载)  │      │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │
└───────────────────────────────────────────────────────────────────────┘

职责：
- 生命周期管理（初始化 / 关闭）
- 提供上层统一的存储 API
- 管理各子组件的协作
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from logger import get_logger

logger = get_logger("local_store.workspace")


class LocalWorkspace:
    """
    本地 Workspace 管理器

    统一管理 SQLite 引擎、FTS5、sqlite-vec、Skills 缓存。
    桌面端实例的全部持久化操作通过此入口完成。

    使用示例:
        workspace = LocalWorkspace(instance_id="dazee_agent")
        await workspace.start()

        # 会话 & 消息
        conv = await workspace.create_conversation(user_id="u1")
        msg = await workspace.create_message(conv.id, "user", "你好")

        # 全文搜索
        results = await workspace.search("天气")

        # Skills 缓存
        skill = await workspace.get_skill("excel-analyzer")

        await workspace.shutdown()
    """

    def __init__(
        self,
        instance_id: str,
        db_dir: Optional[str] = None,
        db_name: Optional[str] = None,
        skills_dir: Optional[str] = None,
    ):
        """
        初始化 Workspace

        Args:
            instance_id: 实例 ID（如 "dazee_agent"）
            db_dir: SQLite 数据库目录
            db_name: 数据库文件名
            skills_dir: Skills 目录路径
        """
        self.instance_id = instance_id
        self._db_dir = db_dir
        self._db_name = db_name
        self._skills_dir = Path(skills_dir) if skills_dir else None

        self._engine = None
        self._session_factory = None
        self._vec_available = False
        self._running = False

    async def start(self):
        """
        启动 Workspace（初始化 SQLite 引擎、建表、加载扩展）
        """
        if self._running:
            logger.warning("Workspace 已在运行")
            return

        from infra.local_store.engine import (
            create_local_engine,
            create_local_session_factory,
            init_local_database,
            init_vector_extension,
        )

        logger.info(f"启动 LocalWorkspace: instance={self.instance_id}")

        # 创建引擎
        self._engine = create_local_engine(
            db_dir=self._db_dir,
            db_name=self._db_name or f"{self.instance_id}.db",
        )

        # 建表 + FTS5
        await init_local_database(self._engine)

        # 可选：加载 sqlite-vec
        self._vec_available = await init_vector_extension(self._engine)

        # 创建会话工厂
        self._session_factory = create_local_session_factory(self._engine)

        self._running = True
        logger.info(
            f"LocalWorkspace 已启动: vec={'可用' if self._vec_available else '不可用'}"
        )

    async def shutdown(self):
        """关闭 Workspace"""
        if not self._running:
            return

        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

        self._running = False
        logger.info("LocalWorkspace 已关闭")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def vec_available(self) -> bool:
        return self._vec_available

    # ==================== 会话上下文 ====================

    def session(self) -> AsyncSession:
        """Get an async session context manager.

        Usage:
            async with workspace.session() as session:
                ...

        Raises:
            RuntimeError: If workspace is not started.
        """
        if self._session_factory is None:
            raise RuntimeError("Workspace 未启动，请先调用 start()")
        return self._session_factory()

    async def _get_session(self) -> AsyncSession:
        """获取数据库会话（内部使用）"""
        if not self._running or self._session_factory is None:
            raise RuntimeError("Workspace 未启动，请先调用 start()")
        return self._session_factory()

    # ==================== 会话操作 ====================

    async def create_conversation(
        self,
        user_id: str,
        title: str = "新对话",
        metadata: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
    ):
        """创建会话"""
        from infra.local_store.crud.conversation import create_conversation

        async with self._session_factory() as session:
            return await create_conversation(
                session, user_id, title, metadata, conversation_id
            )

    async def get_conversation(self, conversation_id: str):
        """获取会话"""
        from infra.local_store.crud.conversation import get_conversation

        async with self._session_factory() as session:
            return await get_conversation(session, conversation_id)

    async def get_or_create_conversation(
        self,
        user_id: str,
        conversation_id: Optional[str] = None,
        title: str = "新对话",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """获取或创建会话"""
        from infra.local_store.crud.conversation import get_or_create_conversation

        async with self._session_factory() as session:
            return await get_or_create_conversation(
                session, user_id, conversation_id, title, metadata
            )

    async def list_conversations(
        self, user_id: str, limit: int = 50, offset: int = 0
    ):
        """获取用户的会话列表"""
        from infra.local_store.crud.conversation import list_conversations

        async with self._session_factory() as session:
            return await list_conversations(session, user_id, limit, offset)

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除会话"""
        from infra.local_store.crud.conversation import delete_conversation

        async with self._session_factory() as session:
            return await delete_conversation(session, conversation_id)

    # ==================== 消息操作 ====================

    async def create_message(
        self,
        conversation_id: str,
        role: str,
        content: Union[str, List[Dict[str, Any]]],
        message_id: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """创建消息（自动同步 FTS5 索引）"""
        from infra.local_store.crud.message import create_message

        async with self._session_factory() as session:
            return await create_message(
                session, conversation_id, role, content, message_id, status, metadata
            )

    async def get_message(self, message_id: str):
        """获取消息"""
        from infra.local_store.crud.message import get_message

        async with self._session_factory() as session:
            return await get_message(session, message_id)

    async def update_message(
        self,
        message_id: str,
        content: Optional[Union[str, List[Dict[str, Any]]]] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """更新消息（自动同步 FTS5 索引）"""
        from infra.local_store.crud.message import update_message

        async with self._session_factory() as session:
            return await update_message(session, message_id, content, status, metadata)

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 1000,
        offset: int = 0,
        order: str = "asc",
    ):
        """获取对话的消息列表"""
        from infra.local_store.crud.message import list_messages

        async with self._session_factory() as session:
            return await list_messages(session, conversation_id, limit, offset, order)

    # ==================== 全文搜索 ====================

    async def search(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 20,
    ):
        """
        全文搜索消息

        Args:
            query: 搜索关键词（支持 FTS5 语法）
            conversation_id: 限定对话
            role: 限定角色
            limit: 返回数量

        Returns:
            FTSResult 列表
        """
        from infra.local_store.fts import search_messages

        async with self._session_factory() as session:
            return await search_messages(
                session, query, conversation_id, role, limit
            )

    async def rebuild_search_index(self):
        """重建全文搜索索引"""
        from infra.local_store.fts import rebuild_fts_index

        async with self._session_factory() as session:
            await rebuild_fts_index(session)

    # ==================== 向量搜索（可选）====================

    async def vector_search(
        self,
        query_embedding: List[float],
        table_name: str = "message_vectors",
        limit: int = 10,
    ):
        """
        向量相似度搜索（需要 sqlite-vec 扩展）

        Args:
            query_embedding: 查询向量
            table_name: 向量表名
            limit: 返回数量

        Returns:
            VectorSearchResult 列表（sqlite-vec 不可用时返回空列表）
        """
        if not self._vec_available:
            logger.debug("sqlite-vec 不可用，跳过向量搜索")
            return []

        from infra.local_store.vector import search_vectors

        async with self._session_factory() as session:
            return await search_vectors(session, table_name, query_embedding, limit)

    # ==================== Skills 缓存 ====================

    async def get_skill(self, skill_name: str) -> Optional[str]:
        """
        获取 Skill 内容（延迟加载 + 缓存）

        Args:
            skill_name: Skill 名称

        Returns:
            Skill 内容文本
        """
        if not self._skills_dir:
            logger.warning("未配置 skills_dir，无法加载 Skill")
            return None

        from infra.local_store.skills_cache import get_cached_skill

        async with self._session_factory() as session:
            return await get_cached_skill(
                session, self.instance_id, skill_name, self._skills_dir
            )

    async def get_skills_batch(self, skill_names: List[str]) -> Dict[str, str]:
        """
        批量获取 Skill 内容

        Args:
            skill_names: Skill 名称列表

        Returns:
            {skill_name: content}
        """
        if not self._skills_dir:
            return {}

        from infra.local_store.skills_cache import get_cached_skills_batch

        async with self._session_factory() as session:
            return await get_cached_skills_batch(
                session, self.instance_id, skill_names, self._skills_dir
            )

    async def invalidate_skill_cache(self, skill_name: Optional[str] = None):
        """使 Skill 缓存失效"""
        from infra.local_store.skills_cache import invalidate_skill_cache

        async with self._session_factory() as session:
            await invalidate_skill_cache(session, self.instance_id, skill_name)

    # ==================== 统计信息 ====================

    async def get_stats(self) -> Dict[str, Any]:
        """获取 Workspace 统计信息"""
        from sqlalchemy import text as sql_text

        from infra.local_store.skills_cache import get_cache_stats

        stats = {
            "instance_id": self.instance_id,
            "running": self._running,
            "vec_available": self._vec_available,
        }

        if not self._running:
            return stats

        async with self._session_factory() as session:
            # 会话数量
            result = await session.execute(
                sql_text("SELECT COUNT(*) FROM conversations")
            )
            stats["conversation_count"] = result.scalar() or 0

            # 消息数量
            result = await session.execute(
                sql_text("SELECT COUNT(*) FROM messages")
            )
            stats["message_count"] = result.scalar() or 0

            # FTS 索引数量
            try:
                result = await session.execute(
                    sql_text("SELECT COUNT(*) FROM messages_fts")
                )
                stats["fts_indexed_count"] = result.scalar() or 0
            except Exception:
                stats["fts_indexed_count"] = 0

            # Skills 缓存统计
            stats["skills_cache"] = await get_cache_stats(session, self.instance_id)

        return stats


# ==================== 全局实例管理 ====================

_workspaces: Dict[str, LocalWorkspace] = {}


async def get_workspace(
    instance_id: str,
    db_dir: Optional[str] = None,
    skills_dir: Optional[str] = None,
) -> LocalWorkspace:
    """
    获取或创建 Workspace 实例（按 instance_id 单例）

    Args:
        instance_id: 实例 ID
        db_dir: 数据库目录
        skills_dir: Skills 目录

    Returns:
        LocalWorkspace 实例
    """
    if instance_id not in _workspaces:
        ws = LocalWorkspace(
            instance_id=instance_id,
            db_dir=db_dir,
            skills_dir=skills_dir,
        )
        await ws.start()
        _workspaces[instance_id] = ws

    return _workspaces[instance_id]


async def close_all_workspaces():
    """关闭所有 Workspace 实例（应用退出时调用）"""
    for ws in _workspaces.values():
        await ws.shutdown()
    _workspaces.clear()
    logger.info("所有 LocalWorkspace 已关闭")
