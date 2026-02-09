"""
实例记忆管理器 - InstanceMemoryManager

三层架构入口：
- Layer 1 文件层：MarkdownMemoryLayer（MEMORY.md + 每日日志）
- Layer 2 索引层：GenericFTS5（全文搜索，零配置）
- Layer 3 智能层：Mem0MemoryPool + QualityController + FragmentExtractor（复用已有）

核心方法：
- recall(query)：融合搜索（FTS5 全文 + Mem0 语义）
- remember(content, category)：双写（MEMORY.md + Mem0 向量存储）
- flush(session_id, messages)：会话结束刷新（提取记忆 + 写入日志）
- get_memory_context()：读取 MEMORY.md 全文（供系统提示词注入）
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("memory.instance")

# 记忆分类 → Mem0 分类映射
_CATEGORY_MAP = {
    "preference": "preference",
    "fact": "fact",
    "workflow": "preference",  # 工作习惯归入偏好
    "style": "preference",  # 风格归入偏好
    "general": "other",
}

# 记忆分类 → MEMORY.md 段落映射
_SECTION_MAP = {
    "preference": "偏好",
    "fact": "关于你",
    "workflow": "偏好/工作习惯",
    "style": "偏好/写作风格",
    "tool": "常用工具",
    "success": "历史经验/成功案例",
    "improvement": "历史经验/需要改进",
    "general": "历史经验",
}


class InstanceMemoryManager:
    """
    实例记忆管理器（三层架构）

    Layer 1: 文件层 — MEMORY.md（用户可见可编辑）+ 每日日志
    Layer 2: 索引层 — FTS5 全文搜索（零配置）
    Layer 3: 智能层 — Mem0 语义搜索 + 冲突检测 + 记忆提取
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        user_id: str = "default",
        mem0_enabled: bool = True,
        instance_name: Optional[str] = None,
    ):
        """
        Args:
            base_dir: 记忆根目录（优先级最高，直接传入）
            user_id: 用户标识（Mem0 隔离用）
            mem0_enabled: 是否启用 Mem0 智能层
            instance_name: 实例名称（用于按实例隔离存储路径）
        """
        import os

        from core.memory.markdown_layer import MarkdownMemoryLayer

        if base_dir:
            self._base_dir = Path(base_dir)
        else:
            from utils.app_paths import get_instance_memory_dir
            _inst = instance_name or os.getenv("AGENT_INSTANCE", "default")
            self._base_dir = get_instance_memory_dir(_inst)
        self._user_id = user_id
        self._mem0_enabled = mem0_enabled

        # Layer 1: 文件层
        self._file_layer = MarkdownMemoryLayer(self._base_dir)

        # Layer 2: FTS5 索引层（延迟初始化）
        self._fts_initialized = False

        # Layer 3: Mem0 智能层（延迟初始化，仅在启用时）
        self._mem0_pool = None
        self._quality_ctrl = None
        self._extractor = None

    # ==================== recall（融合搜索）====================

    async def recall(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        回忆相关记忆（融合搜索）

        搜索策略：
        1. FTS5 全文搜索 MEMORY.md 索引（BM25）
        2. Mem0 语义搜索（向量相似度）
        3. 合并去重 + 加权排序

        Args:
            query: 搜索查询
            project_id: 项目 ID（可选，限定项目记忆）
            limit: 返回数量

        Returns:
            [{"content": str, "score": float, "source": str, "category": str}, ...]
        """
        results: List[Dict[str, Any]] = []

        # Layer 2: FTS5 全文搜索
        fts_results = await self._fts5_recall(query, limit=limit)
        for hit in fts_results:
            results.append({
                "content": hit.get("content", ""),
                "score": hit.get("score", 0.0),
                "source": "fts5",
                "category": hit.get("category", "general"),
            })

        # Layer 3: Mem0 语义搜索
        if self._mem0_enabled:
            mem0_results = await self._mem0_recall(query, limit=limit)
            for mem in mem0_results:
                results.append({
                    "content": mem.get("content", ""),
                    "score": mem.get("score", 0.0),
                    "source": "mem0",
                    "category": mem.get("category", "general"),
                })

        # 合并去重（按内容相似度去重）+ 按 score 降序排序
        results = self._deduplicate_results(results)
        results.sort(key=lambda x: x["score"], reverse=True)

        return results[:limit]

    # ==================== remember（双写）====================

    async def remember(
        self,
        content: str,
        category: str = "general",
        project_id: Optional[str] = None,
    ) -> None:
        """
        记住新信息（双写策略）

        1. 冲突检测（Mem0 QualityController）
        2. 写入 MEMORY.md 对应段落（Layer 1）
        3. 更新 FTS5 索引（Layer 2）
        4. 写入 Mem0 向量存储（Layer 3）

        Args:
            content: 记忆内容
            category: 分类（preference/fact/workflow/style/general）
            project_id: 项目 ID（可选）
        """
        if not content or not content.strip():
            return

        # Layer 3: 冲突检测（如果 Mem0 启用）
        if self._mem0_enabled:
            conflicts = await self._check_conflicts(content, category)
            if conflicts:
                logger.info(
                    f"记忆冲突检测: {len(conflicts)} 个冲突，自动解决"
                )

        # Layer 1: 写入 MEMORY.md
        section = _SECTION_MAP.get(category, "历史经验")
        if project_id:
            await self._file_layer.append_project_memory(
                project_id, section, content
            )
        else:
            await self._file_layer.append_to_section(section, content)

        # Layer 2: 更新 FTS5 索引
        await self._fts5_index_entry(content, category)

        # Layer 3: 写入 Mem0 向量存储
        if self._mem0_enabled:
            await self._mem0_add(content, category)

        logger.info(
            f"记忆已保存: [{category}] {content[:50]}..."
        )

    # ==================== flush（会话结束刷新）====================

    async def flush(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
    ) -> None:
        """
        会话结束时刷新记忆

        1. 使用 FragmentExtractor 从对话提取记忆碎片（Layer 3）
        2. QualityController 过滤 + 冲突检测
        3. 对通过阈值的记忆调用 remember() 双写
        4. 写入每日日志（Layer 1）

        Args:
            session_id: 会话 ID
            messages: 本次对话消息列表
        """
        if not messages:
            return

        # Extract memory fragments (uses LLM, independent of Mem0)
        # mem0_enabled only controls whether Mem0 vector store is written to,
        # extraction itself always runs (uses FragmentExtractor + LLM Profile)
        extracted = await self._extract_from_conversation(
            session_id, messages
        )
        for memory in extracted:
            await self.remember(
                content=memory.get("content", ""),
                category=memory.get("category", "general"),
            )

        # Layer 1: 写入每日日志
        user_msgs = [
            m.get("content", "")
            for m in messages
            if m.get("role") == "user"
        ]
        if user_msgs:
            summary = f"对话 {session_id[:8]}... — 用户主题: {user_msgs[0][:100]}"
            await self._file_layer.append_daily_log(summary)

        logger.info(
            f"记忆刷新完成: session={session_id[:8]}..., "
            f"messages={len(messages)}"
        )

    # ==================== 上下文注入 ====================

    async def get_memory_context(self) -> str:
        """
        读取 MEMORY.md 全文（供系统提示词注入）

        Returns:
            MEMORY.md 的完整 Markdown 内容
        """
        return await self._file_layer.read_global_memory()

    # ==================== Layer 2: FTS5 内部方法 ====================

    _FTS_MAX_RETRIES = 3

    async def _ensure_fts(self) -> None:
        """
        Lazy-init FTS5 index table with retry.

        Uses a DEDICATED engine (memory_fts.db) separate from the main
        zenflux.db to avoid lock contention and silent degradation.
        """
        if self._fts_initialized:
            return

        # Retry on transient failures (DB locked, I/O contention)
        if not hasattr(self, "_fts_retry_count"):
            self._fts_retry_count = 0

        if self._fts_retry_count >= self._FTS_MAX_RETRIES:
            return  # Exhausted retries, stay degraded

        try:
            from infra.local_store.engine import create_local_engine
            from infra.local_store.generic_fts import (
                FTS5TableConfig,
                GenericFTS5,
            )

            self._fts = GenericFTS5()
            self._fts_config = FTS5TableConfig(
                table_name="memory_fts",
                id_column="entry_id",
                title_column="section",
                content_column="content",
                extra_columns=["category", "source"],
            )

            # Dedicated DB for memory FTS5 — uses instance store directory
            # self._base_dir is already instance-scoped
            # Put FTS5 in sibling "store/" directory
            fts_db_dir = str(self._base_dir.parent / "store")
            engine = create_local_engine(
                db_dir=fts_db_dir, db_name="memory_fts.db"
            )
            self._fts_engine = engine
            self._fts_session_factory = None  # lazy

            await self._fts.ensure_table(engine, self._fts_config)
            self._fts_initialized = True
            logger.info("记忆 FTS5 索引表已就绪: memory_fts.db")
        except Exception as e:
            self._fts_retry_count += 1
            remaining = self._FTS_MAX_RETRIES - self._fts_retry_count
            logger.error(
                f"FTS5 初始化失败（降级到文件层搜索，剩余重试 {remaining} 次）: {e}",
                exc_info=True,
            )

    async def _get_fts_session(self):
        """Get a session for the dedicated FTS5 engine."""
        if self._fts_session_factory is None:
            from sqlalchemy.ext.asyncio import async_sessionmaker
            self._fts_session_factory = async_sessionmaker(
                self._fts_engine, expire_on_commit=False
            )
        return self._fts_session_factory()

    async def _fts5_recall(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """FTS5 全文搜索"""
        await self._ensure_fts()
        if not self._fts_initialized:
            return await self._file_layer_search(query, limit)

        try:
            async with await self._get_fts_session() as session:
                hits = await self._fts.search(
                    session, self._fts_config, query, limit=limit
                )
                return [
                    {
                        "content": h.snippet or h.title,
                        "score": abs(h.rank) if h.rank else 0.0,
                        "category": h.extra.get("category", "general"),
                    }
                    for h in hits
                ]
        except Exception as e:
            logger.warning(f"FTS5 搜索失败: {e}")
            return await self._file_layer_search(query, limit)

        return []

    async def _fts5_index_entry(
        self, content: str, category: str
    ) -> None:
        """Write memory entry to FTS5 index (dedicated DB)."""
        await self._ensure_fts()
        if not self._fts_initialized:
            return

        try:
            import uuid

            entry_id = f"mem_{uuid.uuid4().hex[:12]}"
            section = _SECTION_MAP.get(category, "")

            async with await self._get_fts_session() as session:
                await self._fts.upsert(
                    session,
                    self._fts_config,
                    doc_id=entry_id,
                    title=section,
                    content=content,
                    category=category,
                    source="remember",
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"FTS5 索引写入失败: {e}")

    async def _file_layer_search(
        self, query: str, limit: int
    ) -> List[Dict[str, Any]]:
        """降级搜索：直接在 MEMORY.md 内容中匹配"""
        entries = await self._file_layer.read_all_memories()
        query_lower = query.lower()
        results = []
        for entry in entries:
            if query_lower in entry.content.lower():
                results.append({
                    "content": entry.content,
                    "score": 1.0,
                    "category": "general",
                })
            if len(results) >= limit:
                break
        return results

    # ==================== Layer 3: Mem0 内部方法 ====================

    def _ensure_mem0(self) -> None:
        """延迟初始化 Mem0 组件"""
        if self._mem0_pool is not None:
            return

        try:
            from core.memory.mem0 import get_mem0_pool
            from core.memory.mem0.update.quality_control import (
                get_quality_controller,
            )

            self._mem0_pool = get_mem0_pool()
            self._quality_ctrl = get_quality_controller()
            logger.debug("Mem0 智能层已初始化")
        except Exception as e:
            logger.warning(f"Mem0 初始化失败（智能层不可用）: {e}")
            self._mem0_enabled = False

    async def _mem0_recall(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Mem0 语义搜索"""
        self._ensure_mem0()
        if not self._mem0_pool:
            return []

        try:
            results = self._mem0_pool.search(
                user_id=self._user_id,
                query=query,
                limit=limit,
            )
            return [
                {
                    "content": r.get("memory", ""),
                    "score": r.get("score", 0.0),
                    "category": (r.get("metadata") or {}).get(
                        "category", "general"
                    ),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"Mem0 语义搜索失败: {e}")
            return []

    async def _mem0_add(self, content: str, category: str) -> None:
        """写入 Mem0 向量存储"""
        self._ensure_mem0()
        if not self._mem0_pool:
            return

        try:
            mem0_category = _CATEGORY_MAP.get(category, "other")
            self._mem0_pool.add(
                user_id=self._user_id,
                messages=[{"role": "user", "content": content}],
                metadata={
                    "category": mem0_category,
                    "memory_type": "explicit",
                    "source": "instance_remember",
                },
            )
        except Exception as e:
            logger.warning(f"Mem0 写入失败: {e}")

    async def _check_conflicts(
        self, content: str, category: str
    ) -> List[Dict[str, Any]]:
        """使用 QualityController 检测冲突"""
        self._ensure_mem0()
        if not self._quality_ctrl:
            return []

        try:
            mem0_category = _CATEGORY_MAP.get(category, "other")
            # detect_conflicts() is synchronous (no await needed)
            conflicts = self._quality_ctrl.detect_conflicts(
                user_id=self._user_id,
                new_memory=content,
                memory_type=mem0_category,
            )
            return conflicts or []
        except Exception as e:
            logger.warning(f"冲突检测失败: {e}")
            return []

    async def _extract_from_conversation(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Session-level memory extraction: one LLM call for the full conversation.

        Concatenates all messages into a single conversation text, sends to
        FragmentExtractor once, and converts 10-dimension hints into flat
        (content, category) pairs for downstream remember() calls.

        Returns:
            [{"content": str, "category": str}, ...]
        """
        if not self._extractor:
            try:
                from core.memory.mem0.extraction.extractor import (
                    FragmentExtractor,
                )
                self._extractor = FragmentExtractor()
            except Exception as e:
                logger.warning(f"FragmentExtractor 初始化失败: {e}")
                return []

        # Concatenate full conversation for single LLM call
        conversation_text = "\n".join(
            f"[{m.get('role', 'unknown')}] {m.get('content', '')}"
            for m in messages
            if m.get("content")
        )

        if not conversation_text or len(conversation_text) < 20:
            return []

        try:
            fragment = await self._extractor.extract(
                user_id=self._user_id,
                session_id=session_id,
                message=conversation_text,
            )
            if not fragment:
                return []

            # Convert FragmentMemory hints → flat (content, category)
            extracted: List[Dict[str, Any]] = []

            if fragment.task_hint and fragment.task_hint.content:
                extracted.append({
                    "content": fragment.task_hint.content,
                    "category": "fact",
                })
            if fragment.preference_hint:
                ph = fragment.preference_hint
                if ph.response_format:
                    extracted.append({
                        "content": f"偏好输出格式: {ph.response_format}",
                        "category": "preference",
                    })
                if ph.communication_style:
                    extracted.append({
                        "content": f"沟通风格: {ph.communication_style}",
                        "category": "style",
                    })
                for tool in ph.preferred_tools or []:
                    extracted.append({
                        "content": f"偏好工具: {tool}",
                        "category": "preference",
                    })
                # Verbatim preferences: preserve user's exact words
                for vp in ph.verbatim_preferences or []:
                    extracted.append({
                        "content": vp,
                        "category": "preference",
                    })
            if fragment.tool_hint and fragment.tool_hint.tools_mentioned:
                for tool in fragment.tool_hint.tools_mentioned:
                    extracted.append({
                        "content": f"使用工具: {tool}",
                        "category": "tool",
                    })
            if fragment.emotion_hint and fragment.emotion_hint.signal != "neutral":
                extracted.append({
                    "content": f"情绪状态: {fragment.emotion_hint.signal}",
                    "category": "general",
                })
            if fragment.relation_hint and fragment.relation_hint.mentioned:
                for person in fragment.relation_hint.mentioned:
                    extracted.append({
                        "content": f"提到人物: {person}",
                        "category": "fact",
                    })
            if fragment.goal_hint and fragment.goal_hint.goals:
                for goal in fragment.goal_hint.goals:
                    extracted.append({
                        "content": f"目标: {goal}",
                        "category": "fact",
                    })

            logger.info(
                f"会话级记忆提取: {len(extracted)} 条碎片, "
                f"1 次 LLM 调用, 对话长度={len(conversation_text)} 字符"
            )
            return extracted

        except Exception as e:
            logger.warning(f"记忆提取失败（非致命）: {e}")
            return []

    # ==================== 工具方法 ====================

    def _deduplicate_results(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """简单去重：按内容前 50 字符去重"""
        seen = set()
        deduped = []
        for r in results:
            key = r["content"][:50].lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped
