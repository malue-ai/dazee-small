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

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("memory.instance")

# ==================== Ephemeral instruction filter ====================
# These are session-scoped commands that should NOT be persisted as long-term
# memory.  The patterns are pure format checks (allowed by LLM-First rules).

_EPHEMERAL_PATTERNS = [
    re.compile(r"这.*文件.*保持一致", re.I),
    re.compile(r"请直接修改", re.I),
    re.compile(r"给我恢复", re.I),
    re.compile(r"帮我.*吧$", re.I),
]


def _is_ephemeral(content: str) -> bool:
    """Return True if *content* looks like a transient instruction."""
    return any(p.search(content) for p in _EPHEMERAL_PATTERNS)


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
    "identity": "基本信息",
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
        enabled: bool = True,
    ):
        """
        Args:
            base_dir: 记忆根目录（优先级最高，直接传入）
            user_id: 用户标识（Mem0 隔离用）
            mem0_enabled: 是否启用 Mem0 智能层
            instance_name: 实例名称（用于按实例隔离存储路径）
            enabled: 是否启用记忆功能（False 时 recall/remember/flush 全部跳过）
        """
        import os

        from core.memory.markdown_layer import MarkdownMemoryLayer

        self._enabled = enabled

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

    # Source weights for fusion ranking.
    # Semantic (Mem0) results get a boost because they capture meaning
    # even when surface keywords differ.
    _WEIGHT_FTS5 = 1.0
    _WEIGHT_MEM0 = 1.2

    async def recall(
        self,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recall relevant memories (fusion search).

        Strategy:
        1. FTS5 full-text search (BM25 keyword matching)
        2. Mem0 semantic search (vector similarity)
        3. Weighted merge + semantic deduplication

        Args:
            query: search query
            project_id: optional project scope
            limit: max results

        Returns:
            [{"content": str, "score": float, "source": str, "category": str}, ...]
        """
        if not self._enabled:
            return []

        results: List[Dict[str, Any]] = []

        # Layer 2: FTS5 full-text search (weight 1.0)
        fts_results = await self._fts5_recall(query, limit=limit)
        for hit in fts_results:
            results.append({
                "content": hit.get("content", ""),
                "score": hit.get("score", 0.0) * self._WEIGHT_FTS5,
                "source": "fts5",
                "category": hit.get("category", "general"),
            })

        # Layer 3: Mem0 semantic search (weight 1.2)
        if self._mem0_enabled:
            mem0_results = await self._mem0_recall(query, limit=limit)
            for mem in mem0_results:
                results.append({
                    "content": mem.get("content", ""),
                    "score": mem.get("score", 0.0) * self._WEIGHT_MEM0,
                    "source": "mem0",
                    "category": mem.get("category", "general"),
                })

        # Semantic dedup + weighted sort
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
        Remember new information (dual-write strategy).

        1. Conflict detection (Mem0 QualityController) with last-write-wins
        2. Write to MEMORY.md section (Layer 1)
        3. Update FTS5 index (Layer 2)
        4. Write to Mem0 vector store (Layer 3)

        Identity detection is handled upstream by FragmentExtractor's
        identity_hint dimension (LLM-driven), not by keyword patterns here.

        Args:
            content: Memory content
            category: Category (identity/preference/fact/workflow/style/general)
            project_id: Project ID (optional)
        """
        if not self._enabled:
            return

        if not content or not content.strip():
            return

        # Skip ephemeral instructions (session-scoped commands)
        if _is_ephemeral(content):
            logger.debug(f"跳过临时指令: {content[:50]}")
            return

        # Layer 3: 冲突检测（如果 Mem0 启用）+ last-write-wins
        if self._mem0_enabled:
            conflicts = await self._check_conflicts(content, category)
            if conflicts:
                logger.info(
                    f"记忆冲突检测: {len(conflicts)} 个冲突，"
                    f"采用 last-write-wins 策略覆盖旧记忆"
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
        mem0_ok = False
        if self._mem0_enabled:
            mem0_ok = await self._mem0_add(content, category)

        # Log with layer status — "degraded" means Mem0 was expected but failed
        degraded = self._mem0_enabled and not mem0_ok
        logger.info(
            f"记忆已保存: [{category}] {content[:50]}... "
            f"(fts5=ok, mem0={'ok' if mem0_ok else 'skip' if not self._mem0_enabled else 'FAIL'})"
        )
        if degraded:
            logger.warning(
                "Mem0 向量写入失败，语义搜索降级运行"
            )

    async def remember_batch(
        self, memories: List[Dict[str, str]]
    ) -> None:
        """
        Batch-write multiple memories with fast/slow path separation.

        Each item is ``{"content": str, "category": str}``.

        Strategy (optimized for multi-turn latency):
        - Phase 1 (fast): Write to MEMORY.md + FTS5 for each fragment
        - Phase 2 (slow, optional): Single Mem0 add() for all fragments combined
          Mem0 is best-effort — failures are logged and skipped.

        This reduces 16× Mem0 add() calls (each ~5s) to a single call (~5s).
        """
        if not memories:
            return

        # Filter valid, non-ephemeral entries
        valid: List[Dict[str, str]] = []
        for mem in memories:
            content = mem.get("content", "")
            category = mem.get("category", "general")
            if content and content.strip() and not _is_ephemeral(content):
                valid.append({"content": content.strip(), "category": category})

        if not valid:
            return

        # Phase 1: Fast writes (L1 file + L2 FTS5) — sequential, ~1ms each
        ok = 0
        for mem in valid:
            content = mem["content"]
            category = mem["category"]
            section = _SECTION_MAP.get(category, "历史经验")
            try:
                await self._file_layer.append_to_section(section, content)
                await self._fts5_index_entry(content, category)
                ok += 1
            except Exception as e:
                logger.warning(f"L1/L2 写入失败（跳过）: {e}")

        # Phase 2: Mem0 batch write (optional, best-effort)
        # Combine all fragments into one message for a single Mem0 add() call.
        # This turns 16× (embedding + LLM + DB) into 1× — ~5s instead of ~80s.
        mem0_ok = False
        if self._mem0_enabled and valid:
            try:
                combined = "\n".join(m["content"] for m in valid)
                mem0_ok = await self._mem0_add(combined, "general")
            except Exception as e:
                logger.warning(f"Mem0 批量写入失败（非致命）: {e}")

        logger.info(
            f"批量记忆写入: {ok}/{len(memories)} 条成功"
            f" (mem0={'ok' if mem0_ok else 'skip'})"
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
        3. 对通过阈值的记忆调用 remember_batch() 双写
        4. 写入每日日志（Layer 1）

        Args:
            session_id: 会话 ID
            messages: 本次对话消息列表
        """
        if not self._enabled:
            return

        if not messages:
            return

        # Extract memory fragments (uses LLM, independent of Mem0)
        # mem0_enabled only controls whether Mem0 vector store is written to,
        # extraction itself always runs (uses FragmentExtractor + LLM Profile)
        extracted = await self._extract_from_conversation(
            session_id, messages
        )
        await self.remember_batch(extracted)

        # Layer 1: 写入每日日志
        user_msgs = [
            (m.get("content", "") if isinstance(m, dict) else getattr(m, "content", ""))
            for m in messages
            if (m.get("role") if isinstance(m, dict) else getattr(m, "role", "")) == "user"
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

        Side effect: triggers FTS5 sync if file has changed since last index.

        Returns:
            MEMORY.md 的完整 Markdown 内容
        """
        content = await self._file_layer.read_global_memory()

        # Opportunistic sync: re-index if MEMORY.md changed externally
        await self._sync_markdown_to_fts5(content)

        return content

    # ==================== MEMORY.md → FTS5 sync ====================

    _last_md_hash: str = ""

    async def _sync_markdown_to_fts5(self, md_content: str) -> None:
        """
        Detect if MEMORY.md was externally edited and re-index to FTS5.

        Uses a simple content hash to detect changes.
        Only re-indexes when the hash differs from last sync.
        Uses a SINGLE session for all writes (pool_size=1 safe).
        """
        if not md_content or not self._enabled:
            return

        import hashlib
        current_hash = hashlib.md5(md_content.encode()).hexdigest()

        if current_hash == self._last_md_hash:
            return  # No changes

        self._last_md_hash = current_hash

        # Parse entries and batch-index in a single session
        try:
            entries = self._file_layer._parse_memory_entries(
                md_content, "MEMORY.md"
            )
            if not entries:
                return

            await self._ensure_fts()
            if not self._fts_initialized:
                return

            import uuid

            indexed = 0
            async with await self._get_fts_session() as session:
                for entry in entries:
                    # Skip template placeholders
                    if entry.content.startswith("（") and entry.content.endswith("）"):
                        continue
                    entry_id = f"mem_{uuid.uuid4().hex[:12]}"
                    category = self._section_to_category(entry.section)
                    section = _SECTION_MAP.get(category, "")
                    await self._fts.upsert(
                        session,
                        self._fts_config,
                        doc_id=entry_id,
                        title=section,
                        content=entry.content,
                        category=category,
                        source="md_sync",
                    )
                    indexed += 1
                await session.commit()

            if indexed > 0:
                logger.info(
                    f"MEMORY.md → FTS5 同步完成: {indexed} 条条目已索引"
                )

        except Exception as e:
            logger.warning(f"MEMORY.md → FTS5 同步失败（非致命）: {e}")

    @staticmethod
    def _section_to_category(section: str) -> str:
        """Map MEMORY.md section name back to category."""
        section_lower = section.lower()
        for cat, sec in _SECTION_MAP.items():
            if sec.lower() in section_lower or section_lower in sec.lower():
                return cat
        return "general"

    # ==================== Layer 2: FTS5 内部方法 ====================

    _FTS_MAX_RETRIES = 3

    # Class-level cache: reuse SQLite engine across instances with the same DB path
    _fts_engine_cache: dict = {}

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
            #
            # NullPool: 避免 aiosqlite + QueuePool(size=1) 在 async
            # 上下文切换时连接未归还导致的死锁。
            # SQLite WAL 模式保证并发读写安全。
            # 参考: https://www.sqlite.org/wal.html
            fts_db_dir = str(self._base_dir.parent / "store")
            cache_key = f"{fts_db_dir}:memory_fts.db"
            engine = InstanceMemoryManager._fts_engine_cache.get(cache_key)
            if engine is None:
                engine = create_local_engine(
                    db_dir=fts_db_dir, db_name="memory_fts.db",
                    use_null_pool=True,
                )
                InstanceMemoryManager._fts_engine_cache[cache_key] = engine
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

    @staticmethod
    def _strip_fts5_highlight(text: str) -> str:
        """Strip HTML highlight tags from FTS5 snippets."""
        return re.sub(r"</?b>", "", text) if "<b>" in text else text

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
                        "content": self._strip_fts5_highlight(
                            h.snippet or h.title
                        ),
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

    async def _mem0_add(self, content: str, category: str) -> bool:
        """Write to Mem0 vector store. Returns True on success."""
        self._ensure_mem0()
        if not self._mem0_pool:
            return False

        try:
            mem0_category = _CATEGORY_MAP.get(category, "other")
            result = self._mem0_pool.add(
                user_id=self._user_id,
                messages=[{"role": "user", "content": content}],
                metadata={
                    "category": mem0_category,
                    "memory_type": "explicit",
                    "source": "instance_remember",
                },
            )
            results_list = result.get("results", [])
            if not results_list:
                # Mem0 returns empty when content is deduplicated or too
                # short to be meaningful.  Not a real error — FTS5 still
                # stores it.  Log at DEBUG to reduce noise.
                logger.debug(
                    f"Mem0 向量去重跳过: 返回空结果, "
                    f"content={content[:50]}, category={category}"
                )
                return False
            return True
        except Exception as e:
            logger.error(
                f"Mem0 写入异常: {e}, "
                f"content={content[:50]}, category={category}",
                exc_info=True,
            )
            return False

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

            # ── LLM-driven memory persistence ──
            # The LLM decides what's worth remembering long-term via the
            # `long_term_memories` field. No hardcoded dimension filtering
            # in code — the semantic judgment of "is this worth keeping
            # across sessions?" is made by the LLM at extraction time.
            #
            # This avoids the noise problem where session-scoped data
            # (task descriptions, goals, emotions) floods MEMORY.md.

            extracted: List[Dict[str, Any]] = []
            long_term = fragment.metadata.get("long_term_memories", [])

            valid_categories = set(_SECTION_MAP.keys())
            for mem in long_term:
                if not isinstance(mem, dict):
                    continue
                content = mem.get("content", "").strip()
                category = mem.get("category", "general")
                if not content:
                    continue
                # Normalize unknown categories to "general"
                if category not in valid_categories:
                    category = "general"
                extracted.append({
                    "content": content,
                    "category": category,
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

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        """Character-level Jaccard similarity (fast, no dependencies)."""
        set_a = set(a.lower())
        set_b = set(b.lower())
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def _deduplicate_results(
        self,
        results: List[Dict[str, Any]],
        similarity_threshold: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """
        Semantic deduplication using character-level Jaccard similarity.

        When two results are > 80% similar, the higher-scored one wins.
        This catches rephrased duplicates that simple prefix matching misses.
        """
        if not results:
            return []

        deduped: List[Dict[str, Any]] = []
        for r in results:
            content = r["content"]
            is_dup = False
            for i, existing in enumerate(deduped):
                sim = self._jaccard_similarity(content, existing["content"])
                if sim > similarity_threshold:
                    # Keep the higher-scored entry
                    if r["score"] > existing["score"]:
                        deduped[i] = r
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(r)

        return deduped
