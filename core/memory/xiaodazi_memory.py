"""
小搭子记忆管理器 - XiaodaziMemoryManager

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

logger = get_logger("memory.xiaodazi")

# 小搭子记忆分类 → Mem0 分类映射
_CATEGORY_MAP = {
    "preference": "preference",
    "fact": "fact",
    "workflow": "preference",  # 工作习惯归入偏好
    "style": "preference",  # 风格归入偏好
    "general": "other",
}

# 小搭子记忆分类 → MEMORY.md 段落映射
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


class XiaodaziMemoryManager:
    """
    小搭子记忆管理器（三层架构）

    Layer 1: 文件层 — MEMORY.md（用户可见可编辑）+ 每日日志
    Layer 2: 索引层 — FTS5 全文搜索（零配置）
    Layer 3: 智能层 — Mem0 语义搜索 + 冲突检测 + 记忆提取
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        user_id: str = "default",
        mem0_enabled: bool = True,
    ):
        """
        Args:
            base_dir: 记忆根目录，默认 ~/.xiaodazi
            user_id: 用户标识（Mem0 隔离用）
            mem0_enabled: 是否启用 Mem0 智能层
        """
        from core.memory.markdown_layer import MarkdownMemoryLayer

        self._base_dir = Path(base_dir or Path.home() / ".xiaodazi")
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

        # Layer 3: 从对话提取记忆碎片
        if self._mem0_enabled:
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

    async def _ensure_fts(self) -> None:
        """延迟初始化 FTS5 索引表"""
        if self._fts_initialized:
            return

        try:
            from infra.local_store.engine import get_local_engine
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

            engine = await get_local_engine()
            await self._fts.ensure_table(engine, self._fts_config)
            self._fts_initialized = True
            logger.debug("记忆 FTS5 索引表已就绪: memory_fts")
        except Exception as e:
            logger.warning(f"FTS5 初始化失败（降级到文件层搜索）: {e}")

    async def _fts5_recall(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """FTS5 全文搜索"""
        await self._ensure_fts()
        if not self._fts_initialized:
            # 降级：直接搜索 MEMORY.md 文本
            return await self._file_layer_search(query, limit)

        try:
            from infra.local_store.engine import get_local_session

            async for session in get_local_session():
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
        """将记忆条目写入 FTS5 索引"""
        await self._ensure_fts()
        if not self._fts_initialized:
            return

        try:
            import uuid

            from infra.local_store.engine import get_local_session

            entry_id = f"mem_{uuid.uuid4().hex[:12]}"
            section = _SECTION_MAP.get(category, "")

            async for session in get_local_session():
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
                    "source": "xiaodazi_remember",
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
            conflicts = await self._quality_ctrl.detect_conflicts(
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
        使用 FragmentExtractor 从对话提取记忆碎片

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

        extracted = []
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not content or len(content) < 10:
                continue

            try:
                fragment = await self._extractor.extract(
                    user_id=self._user_id,
                    session_id=session_id,
                    message=content,
                )
                if fragment and fragment.has_content():
                    # 将 FragmentMemory 转为简单字典
                    for pref in fragment.preferences or []:
                        extracted.append({
                            "content": pref,
                            "category": "preference",
                        })
                    for fact in fragment.facts or []:
                        extracted.append({
                            "content": fact,
                            "category": "fact",
                        })
            except Exception as e:
                logger.debug(f"记忆提取跳过（非致命）: {e}")
                continue

        logger.info(f"从对话提取 {len(extracted)} 条记忆碎片")
        return extracted

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
