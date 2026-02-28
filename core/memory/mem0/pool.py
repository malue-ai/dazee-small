"""
Mem0 全局缓存池

职责：
- 管理 Mem0 Memory 实例
- 提供基于 user_id 的实例缓存
- 支持跨 Session 的用户记忆

设计原则：
- 单例模式：全局唯一的缓存池
- 懒加载：按需创建 Memory 实例
- 线程安全：支持并发访问
- 100% 本地：使用 sqlite-vec，零外部服务依赖
"""

import os
import threading
from typing import Any, Dict, List, Optional

from logger import get_logger

from .config import Mem0Config, get_mem0_config

logger = get_logger("memory.mem0.pool")


class Mem0MemoryPool:
    """
    Mem0 全局缓存池（单例）

    管理所有用户的 Mem0 Memory 实例，支持：
    - 基于 user_id 的实例缓存
    - 跨 Session 的记忆持久化
    - 高效的记忆搜索

    使用示例：
        pool = get_mem0_pool()
        memories = pool.search(user_id="user_123", query="用户偏好")
    """

    _instance: Optional["Mem0MemoryPool"] = None
    _lock = threading.Lock()

    def __new__(cls, config: Optional[Mem0Config] = None) -> "Mem0MemoryPool":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self, config: Optional[Mem0Config] = None) -> None:
        """
        初始化缓存池

        Args:
            config: Mem0 配置（可选，默认从环境变量读取）
        """
        if self._initialized:
            return

        self.config = config or get_mem0_config()
        self._memory: Optional[Any] = None  # Mem0 Memory 实例（懒加载）
        self._memory_lock = threading.Lock()
        self._memory_unavailable = False  # True = 创建失败，不再重试
        self._initialized = True

        logger.info("[Mem0Pool] 缓存池初始化完成")

    @property
    def memory(self) -> Any:
        """
        获取 Mem0 Memory 实例（懒加载）

        Mem0 Memory 是用户无关的，user_id 在调用时传入。
        创建失败时标记 _memory_unavailable，避免每次调用都重试并产生噪音日志。

        Returns:
            Mem0 Memory 实例

        Raises:
            RuntimeError: 当向量记忆不可用时
        """
        if self._memory_unavailable:
            raise RuntimeError("[Mem0Pool] 向量记忆不可用（已在初始化时失败，跳过重试）")

        if self._memory is None:
            with self._memory_lock:
                if self._memory is None:
                    try:
                        self._memory = self._create_memory()
                    except Exception as e:
                        self._memory_unavailable = True
                        logger.warning(
                            f"[Mem0Pool] Memory 创建失败，向量记忆已禁用（本会话不再重试）: {e}"
                        )
                        raise
        return self._memory

    @staticmethod
    def _create_local_embedder():
        """
        Create a Mem0-compatible adapter wrapping our local GGUF embedding provider.

        Returns the adapter if GGUF model is available, None otherwise.
        """
        try:
            from core.knowledge.embeddings import (
                DEFAULT_GGUF_FILE,
                GGUFEmbeddingProvider,
                get_models_dir,
            )

            model_filename = os.getenv("GGUF_MODEL", DEFAULT_GGUF_FILE)
            model_path = get_models_dir() / model_filename
            if not model_path.exists():
                logger.info("[Mem0Pool] 本地 GGUF 模型不存在，回退到云端 embedder")
                return None

            provider = GGUFEmbeddingProvider()
            logger.info("[Mem0Pool] 使用本地 GGUF embedding (BGE-M3, 1024 维)")
            return _GGUFEmbedderAdapter(provider)
        except ImportError:
            logger.debug("[Mem0Pool] llama-cpp-python 未安装，回退到云端 embedder")
            return None
        except Exception as e:
            logger.warning(f"[Mem0Pool] 本地 embedder 初始化失败: {e}，回退到云端")
            return None

    def _create_memory(self) -> Any:
        """
        创建 Mem0 Memory 实例（使用 sqlite-vec 本地向量存储）

        Returns:
            配置好的 Memory 实例
        """
        try:
            from mem0 import Memory  # type: ignore[attr-defined]
            from mem0.configs.base import MemoryConfig as Mem0MemoryConfig  # type: ignore[import-untyped]
            from mem0.embeddings.configs import EmbedderConfig  # type: ignore[import-untyped]
            from mem0.llms.configs import LlmConfig  # type: ignore[import-untyped]
            from mem0.memory.storage import SQLiteManager  # type: ignore[import-untyped]
            from mem0.utils.factory import EmbedderFactory, LlmFactory  # type: ignore[import-untyped]
            from mem0.vector_stores.configs import VectorStoreConfig  # type: ignore[import-untyped]

            from core.memory.mem0.sqlite_vec_store import SqliteVecVectorStore

            logger.info(
                f"[Mem0Pool] 使用 sqlite-vec 本地向量存储 "
                f"(instance={self.config.instance_name})"
            )

            collection_name = self.config.collection_name

            # 1. 创建 Embedder（优先使用本地 GGUF，离线可用）
            #    必须在创建向量存储之前，以确定实际的向量维度
            embedding_config = self.config.embedder.to_dict()
            embedding_model = self._create_local_embedder()

            if embedding_model is not None:
                # 本地 GGUF embedder 可用 — 使用其实际维度
                actual_dims = embedding_model.provider.dimensions
                if actual_dims != self.config.embedding_model_dims:
                    logger.info(
                        f"[Mem0Pool] 向量维度调整: "
                        f"config={self.config.embedding_model_dims} → "
                        f"local_gguf={actual_dims}"
                    )
            else:
                # Fallback: 使用 Mem0 原生 EmbedderFactory（如 OpenAI）
                actual_dims = self.config.embedding_model_dims
                embedding_model = EmbedderFactory.create(
                    self.config.embedder.provider,
                    embedding_config,
                    {"collection_name": collection_name,
                     "embedding_model_dims": actual_dims},
                )

            # 2. 创建 sqlite-vec 向量存储 — 使用实际 embedder 的维度
            vector_store = SqliteVecVectorStore(
                collection_name=collection_name,
                embedding_model_dims=actual_dims,
                db_path=self.config.db_path,
            )

            # 3. 创建 LLM
            llm = LlmFactory.create(
                self.config.llm.provider, self.config.llm.to_dict()
            )

            # 4. 创建 SQLite 历史管理器 — instance-scoped
            db = SQLiteManager(self.config.history_db_name)

            # Enable WAL mode + busy_timeout on Mem0's history DB.
            # SQLiteManager defaults to DELETE journal mode, which causes
            # "database is locked" under concurrent writes from Mem0's
            # internal thread pool during batch memory.add() calls.
            if db.connection is not None:
                db.connection.execute("PRAGMA journal_mode=WAL")
                db.connection.execute("PRAGMA busy_timeout=5000")

            # 5. 创建最小配置对象（供 Memory 内部方法访问）
            #
            # 注意：Mem0 的 MemoryConfig 只支持预定义的 provider（如 "qdrant"），
            # 不支持 "sqlite_vec"。因此使用 qdrant 结构占位，
            # 实际 vector_store 会被替换为 SqliteVecVectorStore 实例。
            minimal_config = Mem0MemoryConfig(
                version=self.config.version,
                vector_store=VectorStoreConfig(
                    provider="qdrant",
                    config={
                        "collection_name": collection_name,
                        "embedding_model_dims": actual_dims,
                        "path": ":memory:",  # 占位，不会实际使用
                    },
                ),
                embedder=EmbedderConfig(
                    provider=self.config.embedder.provider,
                    config=embedding_config,
                ),
                llm=LlmConfig(
                    provider=self.config.llm.provider,
                    config=self.config.llm.to_dict(),
                ),
            )

            # 6. 手动构造 Memory 实例
            #
            # 使用 __new__ 绕过 __init__，手动设置所有属性，
            # 这样可以注入 SqliteVecVectorStore 替代 Qdrant。
            from core.memory.mem0.update.prompts import (
                CUSTOM_FACT_EXTRACTION_PROMPT,
                CUSTOM_UPDATE_MEMORY_PROMPT,
            )

            memory = Memory.__new__(Memory)
            memory.config = minimal_config
            memory.custom_fact_extraction_prompt = CUSTOM_FACT_EXTRACTION_PROMPT
            memory.custom_update_memory_prompt = CUSTOM_UPDATE_MEMORY_PROMPT
            memory.embedding_model = embedding_model
            memory.vector_store = vector_store  # 关键：使用 sqlite-vec
            memory.llm = llm
            memory.db = db
            memory.collection_name = collection_name
            memory.api_version = self.config.version
            memory.reranker = None
            memory.enable_graph = False
            memory.graph = None

            logger.info("[Mem0Pool] Memory 实例创建成功（sqlite-vec）")
            return memory

        except ImportError as e:
            logger.error(f"[Mem0Pool] 依赖模块未安装: {e}")
            raise RuntimeError(
                "依赖模块未安装，请运行: pip install mem0ai sqlite-vec"
            ) from e
        except Exception as e:
            logger.error(f"[Mem0Pool] Memory 创建失败: {e}")
            raise

    def search(
        self,
        user_id: str,
        query: str,
        limit: Optional[int] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        混合搜索用户相关记忆（向量语义 + FTS5 关键词）

        搜索策略：
        1. 向量搜索（Mem0 原生）：语义相似度 top-2K
        2. FTS5 关键词搜索：BM25 精确匹配 top-2K
        3. 加权合并去重：score = 0.6 * vec_score + 0.4 * text_score
        4. min_score 阈值过滤（方向 C：减少噪音）

        Args:
            user_id: 用户 ID
            query: 搜索查询（通常是用户当前问题）
            limit: 返回数量限制（默认使用配置值）
            min_score: 最低分阈值（低于此分数的结果被过滤，默认 0.0 不过滤）

        Returns:
            记忆列表，每个记忆包含：
            - id: 记忆 ID
            - memory: 记忆内容
            - score: 相关性分数（混合加权后）
            - user_id: 用户 ID
            - created_at: 创建时间
            - metadata: 元数据
        """
        if not user_id or not query:
            logger.warning("[Mem0Pool] search: user_id 或 query 为空")
            return []

        # 向量记忆不可用时静默降级（仅首次已 WARNING，后续不再刷屏）
        if self._memory_unavailable:
            return []

        try:
            search_limit = limit or self.config.default_search_limit

            # ── 1. 向量语义搜索（Mem0 原生，取 2 倍量用于合并） ──
            vec_memories = []
            try:
                result = self.memory.search(
                    query=query, user_id=user_id, limit=search_limit * 2
                )
                if isinstance(result, dict) and "results" in result:
                    vec_memories = result["results"]
                elif isinstance(result, list):
                    vec_memories = result
            except Exception as e:
                logger.warning(f"[Mem0Pool] 向量搜索失败 (降级): {e}")

            # ── 2. FTS5 关键词搜索（补充通路） ──
            fts_memories = []
            try:
                from core.memory.mem0.sqlite_vec_store import SqliteVecVectorStore

                vector_store = self.memory.vector_store
                if isinstance(vector_store, SqliteVecVectorStore):
                    fts_results = vector_store.keyword_search(
                        query=query,
                        user_id=user_id,
                        limit=search_limit * 2,
                    )
                    # 转换为 Mem0 标准格式
                    for r in fts_results:
                        fts_memories.append({
                            "id": r.id,
                            "memory": r.payload.get("data", r.payload.get("memory", "")),
                            "score": r.score,
                            "user_id": r.payload.get("user_id", user_id),
                            "created_at": r.payload.get("created_at", ""),
                            "metadata": r.payload.get("metadata", {}),
                        })
            except Exception as e:
                logger.debug(f"[Mem0Pool] FTS5 搜索失败 (non-fatal): {e}")

            # ── 3. 加权合并去重 ──
            memories = self._merge_hybrid_results(
                vec_memories, fts_memories, search_limit
            )

            # ── 4. min_score 阈值过滤（方向 C） ──
            if min_score > 0:
                before_count = len(memories)
                memories = [
                    m for m in memories if m.get("score", 0) >= min_score
                ]
                filtered = before_count - len(memories)
                if filtered > 0:
                    logger.debug(
                        f"[Mem0Pool] min_score={min_score} 过滤了 {filtered} 条低分记忆"
                    )

            logger.info(
                f"[Mem0Pool] 混合搜索完成: user_id={user_id}, "
                f"query={query[:30]}..., "
                f"vec={len(vec_memories)}, fts={len(fts_memories)}, "
                f"merged={len(memories)}"
            )
            return memories

        except Exception as e:
            logger.error(f"[Mem0Pool] 搜索失败: {e}")
            return []

    @staticmethod
    def _merge_hybrid_results(
        vec_memories: List[Dict[str, Any]],
        fts_memories: List[Dict[str, Any]],
        limit: int,
        vector_weight: float = 0.6,
        text_weight: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """
        混合搜索加权合并去重。

        策略（与 knowledge/local_search.py 一致）：
        1. 以 memory id 为 key 去重
        2. 同 id 合并分数：score = vector_weight * vec_score + text_weight * fts_score
        3. 按加权分数降序排列

        Args:
            vec_memories: 向量搜索结果
            fts_memories: FTS5 搜索结果
            limit: 返回数量上限
            vector_weight: 向量搜索权重（默认 0.6）
            text_weight: 关键词搜索权重（默认 0.4）

        Returns:
            合并后的记忆列表（按分数降序）
        """
        by_id: Dict[str, Dict[str, Any]] = {}

        # 向量搜索结果
        for m in vec_memories:
            mid = m.get("id", "")
            if not mid:
                continue
            by_id[mid] = {
                **m,
                "_vec_score": m.get("score", 0),
                "_fts_score": 0.0,
            }

        # FTS5 搜索结果：合并或新增
        for m in fts_memories:
            mid = m.get("id", "")
            if not mid:
                continue
            if mid in by_id:
                by_id[mid]["_fts_score"] = m.get("score", 0)
            else:
                by_id[mid] = {
                    **m,
                    "_vec_score": 0.0,
                    "_fts_score": m.get("score", 0),
                }

        # 加权合并 + 排序
        merged = []
        for mid, entry in by_id.items():
            weighted_score = (
                vector_weight * entry["_vec_score"]
                + text_weight * entry["_fts_score"]
            )
            # 清理内部字段
            result = {k: v for k, v in entry.items() if not k.startswith("_")}
            result["score"] = weighted_score
            merged.append(result)

        merged.sort(key=lambda x: x.get("score", 0), reverse=True)
        return merged[:limit]

    def add(
        self,
        user_id: str,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None,
        memory_type: Optional[str] = None,
        source: Optional[str] = None,
        visibility: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        添加记忆

        Args:
            user_id: 用户 ID
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            metadata: 额外元数据
            memory_type: 记忆类型（explicit/implicit/behavior/emotion/preference）
            source: 记忆来源（user_card/conversation/behavior_analysis 等）
            visibility: 可见性（public/private/filtered）
            ttl_minutes: 过期时间（分钟），None 表示永不过期

        Returns:
            添加结果
        """
        if not user_id or not messages:
            logger.warning("[Mem0Pool] add: user_id 或 messages 为空")
            return {"results": []}

        # 向量记忆不可用时静默降级（仅首次已 WARNING，后续不再刷屏）
        if self._memory_unavailable:
            return {"results": []}

        try:
            # 构建增强的元数据
            enhanced_metadata = metadata or {}
            if memory_type:
                enhanced_metadata["memory_type"] = memory_type
            if source:
                enhanced_metadata["source"] = source
            if visibility:
                enhanced_metadata["visibility"] = visibility
            if ttl_minutes is not None:
                enhanced_metadata["ttl_minutes"] = ttl_minutes
                from datetime import datetime, timedelta

                enhanced_metadata["expires_at"] = (
                    datetime.now() + timedelta(minutes=ttl_minutes)
                ).isoformat()

            result = self.memory.add(
                messages=messages, user_id=user_id, metadata=enhanced_metadata
            )

            results_count = len(result.get("results", []))
            logger.info(
                f"[Mem0Pool] 添加记忆: user_id={user_id}, "
                f"messages={len(messages)}, 新增={results_count}, "
                f"type={memory_type or 'default'}"
            )
            return result

        except Exception as e:
            logger.error(f"[Mem0Pool] 添加记忆失败: {e}")
            return {"results": [], "error": str(e)}

    def get_all(
        self, user_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取用户所有记忆

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        if not user_id:
            return []
        if self._memory_unavailable:
            return []

        try:
            result = self.memory.get_all(user_id=user_id, limit=limit or 100)

            if isinstance(result, dict) and "results" in result:
                memories = result["results"]
            elif isinstance(result, list):
                memories = result
            else:
                memories = []

            logger.info(
                f"[Mem0Pool] 获取所有记忆: user_id={user_id}, 数量={len(memories)}"
            )
            return memories

        except Exception as e:
            logger.error(f"[Mem0Pool] 获取所有记忆失败: {e}")
            return []

    def update(
        self, memory_id: str, data: str, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        更新单条记忆

        Args:
            memory_id: 记忆 ID
            data: 新的记忆内容
            user_id: 用户 ID（可选，用于日志）

        Returns:
            更新结果
        """
        if self._memory_unavailable:
            return {"error": "vector memory unavailable"}

        try:
            result = self.memory.update(memory_id=memory_id, data=data)
            logger.info(
                f"[Mem0Pool] 更新记忆: memory_id={memory_id}, user_id={user_id}"
            )
            return result
        except Exception as e:
            logger.error(f"[Mem0Pool] 更新记忆失败: {e}")
            return {"error": str(e)}

    def delete(self, memory_id: str, user_id: Optional[str] = None) -> bool:
        """
        删除单条记忆

        Args:
            memory_id: 记忆 ID
            user_id: 用户 ID（可选，用于日志）

        Returns:
            是否成功
        """
        if self._memory_unavailable:
            return False

        try:
            self.memory.delete(memory_id=memory_id)
            logger.info(
                f"[Mem0Pool] 删除记忆: memory_id={memory_id}, user_id={user_id}"
            )
            return True
        except Exception as e:
            logger.error(f"[Mem0Pool] 删除记忆失败: {e}")
            return False

    def reset_user(self, user_id: str) -> bool:
        """
        重置用户所有记忆

        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        if self._memory_unavailable:
            return False

        try:
            self.memory.delete_all(user_id=user_id)
            logger.info(f"[Mem0Pool] 重置用户记忆: user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"[Mem0Pool] 重置用户记忆失败: {e}")
            return False

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            健康状态信息
        """
        try:
            _ = self.memory
            return {
                "status": "healthy",
                "vector_store": "sqlite-vec",
                "collection": self.config.collection_name,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# ==================== 全局访问函数 ====================

_pool_instance: Optional[Mem0MemoryPool] = None


def get_mem0_pool(config: Optional[Mem0Config] = None) -> Mem0MemoryPool:
    """
    获取全局 Mem0 缓存池（单例）

    Args:
        config: 可选的配置（仅首次调用生效）

    Returns:
        Mem0MemoryPool 实例

    使用示例：
        from core.memory.mem0 import get_mem0_pool

        pool = get_mem0_pool()
        memories = pool.search(user_id="user_123", query="用户偏好")
    """
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = Mem0MemoryPool(config)
    return _pool_instance


def reset_mem0_pool() -> None:
    """
    重置全局缓存池（用于配置变更后重新初始化）

    同时清除 _memory_unavailable 标志，使下次访问可以重试创建 Memory 实例。
    典型场景：用户在设置页面更换 API Key 后触发。
    """
    global _pool_instance
    if _pool_instance is not None:
        _pool_instance._memory_unavailable = False
        _pool_instance._memory = None
    _pool_instance = None
    Mem0MemoryPool._instance = None


# ==================== GGUF → Mem0 Adapter ====================


class _GGUFEmbedderAdapter:
    """
    Adapter: wraps our GGUFEmbeddingProvider to match Mem0's EmbeddingBase interface.

    Mem0 calls ``embedder.embed(text, memory_action=...)`` expecting ``list[float]``.
    Our GGUF provider is async and returns ``np.ndarray``.
    This adapter bridges the gap with ``asyncio.run`` (Mem0 calls embed synchronously).

    Mem0's telemetry also accesses ``embedder.config.embedding_dims``, so we
    expose a lightweight config object carrying the dimension information.
    """

    def __init__(self, provider):
        import concurrent.futures

        self.provider = provider
        # Trigger lazy model load now so first embed() is fast
        self.provider._ensure_model()

        # Reuse a single worker thread for all embed() calls.
        # Previously each call created a new ThreadPoolExecutor, adding
        # ~50ms overhead per call (thread creation + asyncio.run bootstrap).
        # With 48+ embed calls per memory flush, that's 2-3s of pure waste.
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # Mem0 internally accesses ``embedding_model.config.embedding_dims``
        # (e.g. in telemetry capture_event).  Provide a compatible config object.
        from types import SimpleNamespace

        self.config = SimpleNamespace(
            embedding_dims=provider.dimensions,
            model=getattr(provider, "_model_path", "gguf-local"),
        )

    def embed(self, text, memory_action=None):
        """
        Synchronous embed matching Mem0 interface.

        Mem0 calls this synchronously. Our GGUF provider is async.
        - If already inside a running event loop (FastAPI request):
          run embed in a worker thread with its own event loop.
        - Otherwise: use asyncio.run() directly.

        SQLite safety: this method only calls the embedding provider
        (CPU inference), it does NOT touch SQLite. SQLite reads/writes
        are handled by sqlite_vec_store with its own _write_lock.
        """
        import asyncio

        _in_async = True
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            _in_async = False

        if _in_async:
            # Worker thread gets its own event loop via asyncio.run()
            coro = self.provider.embed(text)
            vec = self._executor.submit(asyncio.run, coro).result()
        else:
            vec = asyncio.run(self.provider.embed(text))

        return vec.tolist()
