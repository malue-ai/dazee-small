"""
本地知识管理器 - LocalKnowledgeManager

以文件为中心的本地知识检索：
- Level 1: SQLite FTS5 全文搜索（零配置，内置）
- Level 2: sqlite-vec 语义搜索（可选，支持 OpenAI / 本地模型）

搜索策略：混合搜索（FTS5 + 向量并行 → 加权合并去重）。
"""

import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("knowledge.local_search")

# 知识库向量表名
KNOWLEDGE_VECTOR_TABLE = "knowledge_vectors"

# ==================== 混合搜索参数 ====================

# 混合搜索权重（向量:关键词），和为 1.0
DEFAULT_VECTOR_WEIGHT = 0.6
DEFAULT_TEXT_WEIGHT = 0.4

# 最小分数阈值（低于此分数的结果被过滤）
DEFAULT_MIN_SCORE = 0.05


@dataclass
class SearchResult:
    """搜索结果"""

    doc_id: str
    title: str
    snippet: str  # 匹配片段（带高亮）
    score: float  # 归一化分数 [0, 1]
    file_path: str = ""
    file_type: str = ""
    chunk_index: int = 0


class LocalKnowledgeManager:
    """
    本地知识管理器

    管理用户指定文件夹中的文档索引和搜索。
    搜索策略：FTS5 + 向量并行搜索 → 加权合并去重。
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        fts5_enabled: bool = True,
        semantic_enabled: bool = False,
        embedding_provider: str = "auto",
        embedding_model: Optional[str] = None,
    ):
        """
        Args:
            db_path: 索引数据库路径（默认复用 local_store 引擎）
            fts5_enabled: 是否启用 FTS5 全文搜索
            semantic_enabled: 是否启用语义搜索
            embedding_provider: Embedding 提供商 ('auto'|'openai'|'local')
            embedding_model: 覆盖模型名称（None 使用默认值）
        """
        self._fts5_enabled = fts5_enabled
        self._semantic_enabled = semantic_enabled
        self._embedding_provider_type = embedding_provider
        self._embedding_model = embedding_model
        self._fts_initialized = False
        self._vec_initialized = False
        self._fts = None
        self._fts_config = None
        self._embedding_provider = None

    async def initialize(self) -> None:
        """
        初始化搜索引擎（FTS5 表 + 可选向量表）

        应在首次使用前调用。
        """
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
                table_name="knowledge_fts",
                id_column="doc_id",
                title_column="title",
                content_column="content",
                extra_columns=["file_path", "file_type", "chunk_index"],
            )

            engine = await get_local_engine()
            await self._fts.ensure_table(engine, self._fts_config)
            self._fts_initialized = True
            logger.info("知识检索 FTS5 索引已就绪: knowledge_fts")
        except Exception as e:
            logger.error(f"知识检索初始化失败: {e}", exc_info=True)

        # 初始化 sqlite-vec 向量表
        if self._semantic_enabled:
            await self._init_vector_table()

    async def search(
        self,
        query: str,
        limit: int = 10,
        file_type: Optional[str] = None,
        min_score: float = DEFAULT_MIN_SCORE,
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
        text_weight: float = DEFAULT_TEXT_WEIGHT,
    ) -> List[SearchResult]:
        """
        混合搜索知识库

        策略：
        1. FTS5 + 向量搜索并行执行
        2. 分数归一化到 [0, 1]
        3. 加权合并去重
        4. 最小分数阈值过滤

        Args:
            query: 搜索查询
            limit: 返回数量
            file_type: 过滤文件类型（如 ".md"）
            min_score: 最小分数阈值，低于此分数的结果被过滤
            vector_weight: 向量搜索权重（默认 0.6）
            text_weight: 关键词搜索权重（默认 0.4）

        Returns:
            SearchResult 列表（按加权分数降序排列）
        """
        # 并行搜索：FTS5 + 语义
        fts_task = self._fts5_search(query, limit * 2, file_type)

        if self._semantic_enabled and self._vec_initialized:
            vec_task = self._semantic_search(query, limit * 2, file_type)
            fts_results, vec_results = await asyncio.gather(
                fts_task, vec_task, return_exceptions=True
            )

            # Handle exceptions from gather
            if isinstance(fts_results, Exception):
                logger.warning(f"FTS5 搜索异常: {fts_results}")
                fts_results = []
            if isinstance(vec_results, Exception):
                logger.warning(f"语义搜索异常: {vec_results}")
                vec_results = []

            # 混合合并
            merged = self._merge_hybrid_results(
                vec_results=vec_results,
                fts_results=fts_results,
                vector_weight=vector_weight,
                text_weight=text_weight,
            )
        else:
            # 仅 FTS5
            fts_results = await fts_task
            merged = fts_results

        # 最小分数过滤
        filtered = [r for r in merged if r.score >= min_score]

        return filtered[:limit]

    async def add_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        file_path: str = "",
        file_type: str = "",
        chunk_index: int = 0,
        embedding: Optional[List[float]] = None,
    ) -> None:
        """
        添加文档到索引

        Args:
            doc_id: 文档唯一标识（如 file_path:chunk_index）
            title: 文档标题
            content: 文档内容
            file_path: 源文件路径
            file_type: 文件类型
            chunk_index: 分块索引
            embedding: 预计算的向量嵌入（可选，语义搜索用）
        """
        await self.initialize()
        if not self._fts or not self._fts_config:
            return

        try:
            from infra.local_store.engine import get_local_session

            async for session in get_local_session():
                await self._fts.upsert(
                    session,
                    self._fts_config,
                    doc_id=doc_id,
                    title=title,
                    content=content,
                    file_path=file_path,
                    file_type=file_type,
                    chunk_index=str(chunk_index),
                )

                # 存储向量嵌入（如果提供）
                if embedding and self._vec_initialized:
                    await self._upsert_vector(
                        session,
                        doc_id=doc_id,
                        embedding=embedding,
                        title=title,
                        content=content[:200],
                        file_path=file_path,
                        file_type=file_type,
                        chunk_index=chunk_index,
                    )

                await session.commit()
        except Exception as e:
            logger.error(f"文档添加失败: {doc_id} - {e}", exc_info=True)

    async def remove_document(self, doc_id: str) -> None:
        """
        从索引中移除文档

        Args:
            doc_id: 文档唯一标识
        """
        if not self._fts or not self._fts_config:
            return

        try:
            from infra.local_store.engine import get_local_session

            async for session in get_local_session():
                await self._fts.delete(session, self._fts_config, doc_id)

                # 同步删除向量
                if self._vec_initialized:
                    from infra.local_store.vector import delete_vector
                    await delete_vector(session, KNOWLEDGE_VECTOR_TABLE, doc_id)

                await session.commit()
        except Exception as e:
            logger.error(f"文档移除失败: {doc_id} - {e}", exc_info=True)

    async def remove_by_file_path(self, file_path: str) -> int:
        """
        移除某个文件的所有索引块

        Args:
            file_path: 源文件路径

        Returns:
            移除的块数
        """
        if not self._fts_config:
            return 0

        try:
            from sqlalchemy import text as sa_text

            from infra.local_store.engine import get_local_session

            async for session in get_local_session():
                result = await session.execute(
                    sa_text(
                        f"SELECT {self._fts_config.id_column} "
                        f"FROM {self._fts_config.table_name} "
                        f"WHERE file_path = :fp"
                    ),
                    {"fp": file_path},
                )
                doc_ids = [row[0] for row in result.fetchall()]

                for doc_id in doc_ids:
                    await self._fts.delete(
                        session, self._fts_config, doc_id
                    )

                    # 同步删除向量
                    if self._vec_initialized:
                        from infra.local_store.vector import delete_vector
                        await delete_vector(
                            session, KNOWLEDGE_VECTOR_TABLE, doc_id
                        )

                await session.commit()
                return len(doc_ids)
        except Exception as e:
            logger.error(f"文件索引移除失败: {file_path} - {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取索引统计

        Returns:
            {"total_docs": int, "fts5_enabled": bool, "semantic_enabled": bool, ...}
        """
        stats: Dict[str, Any] = {
            "fts5_enabled": self._fts5_enabled,
            "semantic_enabled": self._semantic_enabled,
            "total_docs": 0,
        }

        # Embedding provider info
        if self._embedding_provider:
            stats["embedding_provider"] = self._embedding_provider.provider_id
            stats["embedding_model"] = self._embedding_provider.model_name
            stats["embedding_dimensions"] = self._embedding_provider.dimensions

        if self._fts and self._fts_config:
            try:
                from infra.local_store.engine import get_local_session

                async for session in get_local_session():
                    fts_stats = await self._fts.get_stats(
                        session, self._fts_config
                    )
                    stats["total_docs"] = fts_stats.get("total_docs", 0)
            except Exception:
                pass

        return stats

    # ==================== 混合搜索核心 ====================

    @staticmethod
    def bm25_rank_to_score(rank: float) -> float:
        """
        BM25 rank → 归一化分数 [0, 1]

        FTS5 BM25 rank 是负数（越小越相关），转换为 [0, 1] 分数。
        公式：abs(rank) / (1 + abs(rank))
        - rank=-10 → 0.909（高相关）
        - rank=-5  → 0.833
        - rank=-1  → 0.500
        - rank=-0.1 → 0.091（低相关）
        - rank=0   → 0.000

        保证：更相关的文档（rank 绝对值更大）得分更高。

        Args:
            rank: FTS5 BM25 rank（通常为负数）

        Returns:
            归一化分数 [0, 1]
        """
        if rank is None or not math.isfinite(rank):
            return 0.0
        a = abs(rank)
        return a / (1.0 + a)

    @staticmethod
    def _merge_hybrid_results(
        vec_results: List[SearchResult],
        fts_results: List[SearchResult],
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
        text_weight: float = DEFAULT_TEXT_WEIGHT,
    ) -> List[SearchResult]:
        """
        混合搜索加权合并去重

        借鉴 OpenClaw hybrid.ts 实现：
        1. 以 doc_id 为 key 去重
        2. 同 doc_id 合并分数
        3. 加权排序：score = vector_weight * vec_score + text_weight * fts_score

        Args:
            vec_results: 向量搜索结果（score 已归一化到 [0, 1]）
            fts_results: FTS5 搜索结果（score 已归一化到 [0, 1]）
            vector_weight: 向量搜索权重
            text_weight: 关键词搜索权重

        Returns:
            合并后的结果列表（按加权分数降序）
        """
        by_id: Dict[str, Dict[str, Any]] = {}

        # Process vector results first
        for r in vec_results:
            by_id[r.doc_id] = {
                "title": r.title,
                "snippet": r.snippet,
                "file_path": r.file_path,
                "file_type": r.file_type,
                "chunk_index": r.chunk_index,
                "vec_score": r.score,
                "text_score": 0.0,
            }

        # Process FTS results, merge if same doc_id
        for r in fts_results:
            if r.doc_id in by_id:
                entry = by_id[r.doc_id]
                entry["text_score"] = r.score
                # Prefer FTS snippet (has keyword highlighting)
                if r.snippet:
                    entry["snippet"] = r.snippet
            else:
                by_id[r.doc_id] = {
                    "title": r.title,
                    "snippet": r.snippet,
                    "file_path": r.file_path,
                    "file_type": r.file_type,
                    "chunk_index": r.chunk_index,
                    "vec_score": 0.0,
                    "text_score": r.score,
                }

        # Weighted scoring and sort
        merged: List[SearchResult] = []
        for doc_id, entry in by_id.items():
            weighted_score = (
                vector_weight * entry["vec_score"]
                + text_weight * entry["text_score"]
            )
            merged.append(
                SearchResult(
                    doc_id=doc_id,
                    title=entry["title"],
                    snippet=entry["snippet"],
                    score=weighted_score,
                    file_path=entry["file_path"],
                    file_type=entry["file_type"],
                    chunk_index=entry["chunk_index"],
                )
            )

        # Sort by score descending
        merged.sort(key=lambda x: x.score, reverse=True)
        return merged

    # ==================== 内部搜索方法 ====================

    async def _fts5_search(
        self,
        query: str,
        limit: int,
        file_type: Optional[str] = None,
    ) -> List[SearchResult]:
        """FTS5 全文搜索（分数已归一化到 [0, 1]）"""
        await self.initialize()
        if not self._fts or not self._fts_config:
            return []

        try:
            from infra.local_store.engine import get_local_session

            where = {"file_type": file_type} if file_type else None

            async for session in get_local_session():
                hits = await self._fts.search(
                    session,
                    self._fts_config,
                    query,
                    limit=limit,
                    where=where,
                )
                return [
                    SearchResult(
                        doc_id=h.doc_id,
                        title=h.title,
                        snippet=h.snippet,
                        # P0: BM25 归一化到 [0, 1]
                        score=self.bm25_rank_to_score(h.rank),
                        file_path=h.extra.get("file_path", ""),
                        file_type=h.extra.get("file_type", ""),
                        chunk_index=int(
                            h.extra.get("chunk_index", 0) or 0
                        ),
                    )
                    for h in hits
                ]
        except Exception as e:
            logger.error(f"FTS5 搜索失败: {e}", exc_info=True)
            return []

    async def _semantic_search(
        self,
        query: str,
        limit: int,
        file_type: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        语义搜索（基于 sqlite-vec 向量相似度）

        流程：查询文本 → embedding → sqlite-vec MATCH → SearchResult
        分数已归一化到 [0, 1]。
        """
        if not self._vec_initialized:
            return []

        try:
            provider = await self._get_embedding_provider()
            query_embedding = await provider.embed(query)
            query_list = query_embedding.tolist()

            from infra.local_store.engine import get_local_session
            from infra.local_store.vector import search_vectors

            async for session in get_local_session():
                vec_results = await search_vectors(
                    session,
                    KNOWLEDGE_VECTOR_TABLE,
                    query_list,
                    limit=limit,
                )

                results = []
                for vr in vec_results:
                    meta = json.loads(vr.metadata_json)

                    # 按 file_type 过滤
                    if file_type and meta.get("file_type") != file_type:
                        continue

                    # 余弦距离转相似度（sqlite-vec 返回 distance）
                    similarity = max(0.0, 1.0 - vr.distance)

                    results.append(SearchResult(
                        doc_id=vr.id,
                        title=meta.get("title", ""),
                        snippet=meta.get("snippet", ""),
                        score=similarity,
                        file_path=meta.get("file_path", ""),
                        file_type=meta.get("file_type", ""),
                        chunk_index=int(meta.get("chunk_index", 0)),
                    ))

                return results

        except Exception as e:
            logger.warning(f"语义搜索失败，降级到 FTS5: {e}")
            return []

    # ==================== 向量辅助方法 ====================

    async def _init_vector_table(self) -> None:
        """初始化 sqlite-vec 知识向量表"""
        try:
            from infra.local_store.engine import (
                get_local_engine,
                is_vec_available,
            )

            if not is_vec_available():
                logger.info("sqlite-vec 不可用，语义搜索已禁用")
                self._semantic_enabled = False
                return

            # Determine dimensions from embedding provider
            provider = await self._get_embedding_provider()
            dimensions = provider.dimensions

            from infra.local_store.vector import create_vector_table

            engine = await get_local_engine()
            success = await create_vector_table(
                engine,
                table_name=KNOWLEDGE_VECTOR_TABLE,
                dimensions=dimensions,
            )

            if success:
                self._vec_initialized = True
                logger.info(
                    f"知识检索向量表已就绪: {KNOWLEDGE_VECTOR_TABLE} "
                    f"(dim={dimensions}, provider={provider.provider_id})"
                )
            else:
                self._semantic_enabled = False
                logger.warning("向量表创建失败，语义搜索已禁用")

        except Exception as e:
            self._semantic_enabled = False
            logger.warning(f"向量表初始化失败: {e}")

    async def _get_embedding_provider(self):
        """获取 embedding 提供商（懒初始化）"""
        if self._embedding_provider is None:
            from core.knowledge.embeddings import create_embedding_provider
            self._embedding_provider = await create_embedding_provider(
                provider=self._embedding_provider_type,
                model=self._embedding_model,
            )
        return self._embedding_provider

    async def _upsert_vector(
        self,
        session,
        doc_id: str,
        embedding: List[float],
        title: str = "",
        content: str = "",
        file_path: str = "",
        file_type: str = "",
        chunk_index: int = 0,
    ) -> None:
        """存储文档向量"""
        from infra.local_store.vector import upsert_vector

        metadata = json.dumps({
            "title": title,
            "snippet": content[:200],
            "file_path": file_path,
            "file_type": file_type,
            "chunk_index": chunk_index,
        }, ensure_ascii=False)

        await upsert_vector(
            session,
            KNOWLEDGE_VECTOR_TABLE,
            vector_id=doc_id,
            embedding=embedding,
            metadata=metadata,
        )
