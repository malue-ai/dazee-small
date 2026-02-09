"""
意图识别语义缓存 - IntentSemanticCache

🆕 V9.3: 通过向量相似度匹配减少 LLM 调用，降低延迟和成本

设计原则：
1. 性能约束：缓存查询 < 100ms（包含 Embedding + 相似度计算）
2. 返回 Top-1 + Score
3. 预留向量库扩展接口

架构：
┌─────────────────────────────────────────────────────────┐
│ IntentSemanticCache                                      │
│ ├── L1: 精确匹配（hash）         < 0.1ms               │
│ └── L2: 语义匹配（embedding）    < 60ms                 │
│     ├── Embedding 服务           ~50ms (OpenAI API)    │
│     └── 相似度计算               ~5ms  (numpy/内存)    │
└─────────────────────────────────────────────────────────┘

使用方式：
    cache = IntentSemanticCache.get_instance()

    # 查询
    result, score = await cache.lookup(query)
    if result and score >= 0.95:
        return result  # 缓存命中

    # 未命中，调用 LLM
    result = await intent_analyzer.analyze(messages)

    # 异步存储
    await cache.store(query, result)
"""

import asyncio
import hashlib
import os
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.routing.types import Complexity, IntentResult
from logger import get_logger

logger = get_logger("intent_cache")


# ============================================================
# 配置
# ============================================================


@dataclass
class IntentCacheConfig:
    """
    意图缓存配置

    默认 hash-only 模式（精准 100%，仅匹配完全相同的查询）。
    语义匹配需显式开启（INTENT_CACHE_SEMANTIC_ENABLED=true），
    启用后阈值极高（0.95）以保证不误匹配。

    空间估算（max_size=10000 时）:
    - hash_only: ~1KB/条目，约 10MB
    - full（含语义）: ~5KB/条目（含 1024-dim float32），约 50MB
    """

    enabled: bool = True  # 是否启用缓存
    semantic_enabled: bool = False  # L2 语义匹配（默认关闭，hash-only）
    threshold: float = 0.95  # L2 语义阈值（极高保证精准，仅 semantic_enabled 时生效）
    max_size: int = 10000  # 最大缓存条目数（LRU）
    ttl_hours: int = 24  # 缓存 TTL（小时）
    backend: str = "memory"  # 存储后端：memory | vectordb
    embedding_model: str = "bge-m3-Q4_K_M"  # Embedding 模型（本地 GGUF）
    embedding_dim: int = 1024  # 向量维度（BGE-M3）

    @classmethod
    def from_env(cls) -> "IntentCacheConfig":
        """从环境变量加载配置"""
        return cls(
            enabled=os.getenv("INTENT_CACHE_ENABLED", "true").lower() == "true",
            semantic_enabled=os.getenv("INTENT_CACHE_SEMANTIC_ENABLED", "false").lower()
            == "true",
            threshold=float(os.getenv("INTENT_CACHE_THRESHOLD", "0.95")),
            max_size=int(os.getenv("INTENT_CACHE_MAX_SIZE", "10000")),
            ttl_hours=int(os.getenv("INTENT_CACHE_TTL_HOURS", "24")),
            backend=os.getenv("INTENT_CACHE_BACKEND", "memory"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "bge-m3-Q4_K_M"),
        )


# ============================================================
# 缓存数据结构
# ============================================================


@dataclass
class CachedIntentResult:
    """缓存的意图结果"""

    query_text: str  # 原始查询文本
    query_hash: str  # 查询文本的 hash（用于精确匹配）
    embedding: Optional[np.ndarray]  # 向量（模型不可用时为 None，仅 hash 精确匹配）
    intent_result: IntentResult  # 意图分析结果
    created_at: datetime = field(default_factory=datetime.now)
    hit_count: int = 0  # 命中次数

    def is_expired(self, ttl_hours: int) -> bool:
        """检查是否过期"""
        return datetime.now() - self.created_at > timedelta(hours=ttl_hours)


# ============================================================
# 缓存后端抽象接口
# ============================================================


class IntentCacheBackend(ABC):
    """
    缓存后端抽象接口

    预留向量库扩展：实现 VectorDBBackend 继承此接口
    """

    @abstractmethod
    async def search(self, embedding: np.ndarray) -> Tuple[Optional[CachedIntentResult], float]:
        """
        向量相似度搜索

        Args:
            embedding: 查询向量

        Returns:
            (Top-1 结果, 相似度分数)，未命中返回 (None, 0.0)
        """
        pass

    @abstractmethod
    async def insert(self, item: CachedIntentResult) -> None:
        """插入缓存项"""
        pass

    @abstractmethod
    async def get_by_hash(self, query_hash: str) -> Optional[CachedIntentResult]:
        """精确匹配（L1 缓存）"""
        pass

    @abstractmethod
    def size(self) -> int:
        """当前缓存大小"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """清空缓存"""
        pass


# ============================================================
# 内存后端实现（默认）
# ============================================================


class InMemoryBackend(IntentCacheBackend):
    """
    内存后端实现

    使用 numpy 余弦相似度计算，O(n) 遍历
    10000 条缓存约 2-3ms
    """

    def __init__(self, max_size: int = 10000, ttl_hours: int = 24):
        self.max_size = max_size
        self.ttl_hours = ttl_hours
        self._cache: OrderedDict[str, CachedIntentResult] = OrderedDict()
        self._lock = Lock()

        # 预分配向量矩阵（优化相似度计算）
        self._embeddings: Optional[np.ndarray] = None
        self._hash_to_idx: Dict[str, int] = {}
        self._idx_to_hash: Dict[int, str] = {}
        self._next_idx: int = 0

    async def search(self, embedding: np.ndarray) -> Tuple[Optional[CachedIntentResult], float]:
        """
        向量相似度搜索（返回 Top-1）

        使用 numpy 批量计算余弦相似度，约 2-3ms
        """
        if not self._cache:
            return None, 0.0

        start_time = time.time()

        with self._lock:
            # 清理过期条目
            self._cleanup_expired()

            if not self._cache:
                return None, 0.0

            # 构建向量矩阵（如果需要，hash-only 条目不参与）
            if self._embeddings is None:
                self._rebuild_matrix()

            # 全部为 hash-only 条目，无可用向量
            if self._embeddings is None or self._embeddings.shape[0] == 0:
                return None, 0.0

            # 归一化查询向量
            query_norm = embedding / (np.linalg.norm(embedding) + 1e-10)

            # 批量计算余弦相似度
            similarities = np.dot(self._embeddings, query_norm)

            # 找到最大值
            max_idx = np.argmax(similarities)
            max_score = float(similarities[max_idx])

            # 获取对应的缓存项
            if max_idx in self._idx_to_hash:
                query_hash = self._idx_to_hash[max_idx]
                if query_hash in self._cache:
                    result = self._cache[query_hash]
                    result.hit_count += 1

                    elapsed_ms = (time.time() - start_time) * 1000
                    logger.debug(
                        f"🔍 语义搜索完成: score={max_score:.4f}, "
                        f"elapsed={elapsed_ms:.1f}ms, size={len(self._cache)}"
                    )

                    return result, max_score

        return None, 0.0

    async def insert(self, item: CachedIntentResult) -> None:
        """插入缓存项"""
        with self._lock:
            # LRU 淘汰
            while len(self._cache) >= self.max_size:
                oldest_hash, _ = self._cache.popitem(last=False)
                if oldest_hash in self._hash_to_idx:
                    idx = self._hash_to_idx.pop(oldest_hash)
                    self._idx_to_hash.pop(idx, None)

            # 插入新项
            self._cache[item.query_hash] = item

            # 更新向量索引（仅有 embedding 的条目参与语义搜索）
            if item.embedding is not None:
                idx = self._next_idx
                self._next_idx += 1
                self._hash_to_idx[item.query_hash] = idx
                self._idx_to_hash[idx] = item.query_hash
                # 有新向量，标记矩阵需要重建
                self._embeddings = None

    async def get_by_hash(self, query_hash: str) -> Optional[CachedIntentResult]:
        """精确匹配（L1 缓存）"""
        with self._lock:
            if query_hash in self._cache:
                result = self._cache[query_hash]
                if not result.is_expired(self.ttl_hours):
                    result.hit_count += 1
                    # 移动到末尾（LRU）
                    self._cache.move_to_end(query_hash)
                    return result
                else:
                    # 过期，删除
                    self._remove_item(query_hash)
        return None

    def size(self) -> int:
        """当前缓存大小"""
        return len(self._cache)

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._embeddings = None
            self._hash_to_idx.clear()
            self._idx_to_hash.clear()
            self._next_idx = 0

    def _cleanup_expired(self) -> None:
        """清理过期条目"""
        expired = [h for h, item in self._cache.items() if item.is_expired(self.ttl_hours)]
        for h in expired:
            self._remove_item(h)

    def _remove_item(self, query_hash: str) -> None:
        """删除缓存项"""
        if query_hash in self._cache:
            del self._cache[query_hash]
            if query_hash in self._hash_to_idx:
                idx = self._hash_to_idx.pop(query_hash)
                self._idx_to_hash.pop(idx, None)
            self._embeddings = None

    def _rebuild_matrix(self) -> None:
        """重建向量矩阵（跳过 hash-only 条目，不参与语义搜索）"""
        if not self._cache:
            self._embeddings = None
            return

        # 重建索引映射
        self._hash_to_idx.clear()
        self._idx_to_hash.clear()

        embeddings = []
        for query_hash, item in self._cache.items():
            if item.embedding is None:
                continue  # hash-only 条目，仅支持 L1 精确匹配
            # 归一化向量
            norm = np.linalg.norm(item.embedding) + 1e-10
            embeddings.append(item.embedding / norm)
            idx = len(embeddings) - 1
            self._hash_to_idx[query_hash] = idx
            self._idx_to_hash[idx] = query_hash

        if embeddings:
            self._embeddings = np.array(embeddings)
        else:
            self._embeddings = None  # 全部为 hash-only 条目
        self._next_idx = len(embeddings)


# ============================================================
# 向量库后端（预留接口）
# ============================================================


class VectorDBBackend(IntentCacheBackend):
    """
    向量库后端（预留实现）

    复用 infra/vector/ 基础设施
    """

    def __init__(self, collection_name: str = "intent_cache"):
        self.collection_name = collection_name
        self._vector_store = None
        logger.info(f"📦 VectorDBBackend 初始化（预留）: collection={collection_name}")

    async def _get_vector_store(self):
        """延迟初始化向量库"""
        if self._vector_store is None:
            try:
                from infra.vector.factory import get_vector_store

                self._vector_store = await get_vector_store()
            except ImportError:
                # TODO: 迁移到 local_store
                logger.warning("⚠️ 向量库模块不可用，VectorDBBackend 功能已禁用")
                raise NotImplementedError("向量库模块已删除，请使用 InMemoryBackend")
        return self._vector_store

    async def search(self, embedding: np.ndarray) -> Tuple[Optional[CachedIntentResult], float]:
        """向量库搜索（预留实现）"""
        # TODO: 实现向量库搜索
        raise NotImplementedError("VectorDBBackend.search() 尚未实现")

    async def insert(self, item: CachedIntentResult) -> None:
        """插入向量库（预留实现）"""
        # TODO: 实现向量库插入
        raise NotImplementedError("VectorDBBackend.insert() 尚未实现")

    async def get_by_hash(self, query_hash: str) -> Optional[CachedIntentResult]:
        """精确匹配（预留实现）"""
        # TODO: 实现精确匹配
        return None

    def size(self) -> int:
        """当前缓存大小"""
        return 0

    def clear(self) -> None:
        """清空缓存"""
        pass


# ============================================================
# Embedding 服务
# ============================================================


class EmbeddingService:
    """
    Embedding 服务（优雅降级）

    使用本地 GGUF 模型（BGE-M3），复用 core/knowledge/embeddings 的 provider。
    模型未下载时返回 None，调用方自行降级为关键词/hash 匹配。
    """

    def __init__(self, model: str = "bge-m3-Q4_K_M"):
        self.model = model
        self._provider = None
        self._unavailable = False  # True = model not downloaded, skip silently

    async def _get_provider(self):
        """Lazy-init embedding provider. Returns None if model not available."""
        if self._unavailable:
            return None

        if self._provider is None:
            try:
                from core.knowledge.embeddings import create_embedding_provider

                self._provider = await create_embedding_provider("auto")
                logger.info(
                    f"IntentCache embedding provider: {self._provider.provider_id} "
                    f"(dim={self._provider.dimensions})"
                )
            except Exception:
                # Model not downloaded or no provider available → silent degradation
                self._unavailable = True
                logger.debug(
                    "Embedding model not available, "
                    "intent cache will use hash-only matching"
                )
                return None

        return self._provider

    async def embed(self, text: str) -> Optional[np.ndarray]:
        """
        Get embedding vector for text.

        Returns None if model not available (graceful degradation).

        Args:
            text: input text

        Returns:
            1024-dim vector or None
        """
        provider = await self._get_provider()
        if provider is None:
            return None

        start_time = time.time()
        embedding = await provider.embed(text[:8000])
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(f"Embedding done: dim={len(embedding)}, elapsed={elapsed_ms:.1f}ms")

        return embedding


# ============================================================
# 主类：IntentSemanticCache
# ============================================================


class IntentSemanticCache:
    """
    意图识别语义缓存（单例）

    两层缓存策略：
    - L1: 精确匹配（hash）< 0.1ms
    - L2: 语义匹配（embedding）< 60ms

    使用方式：
        cache = IntentSemanticCache.get_instance()

        # 查询
        result, score = await cache.lookup(query)
        if result and score >= cache.config.threshold:
            return result

        # 未命中，调用 LLM 后存储
        await cache.store(query, intent_result)
    """

    _instance: Optional["IntentSemanticCache"] = None
    _lock = Lock()

    def __init__(self, config: Optional[IntentCacheConfig] = None):
        self.config = config or IntentCacheConfig.from_env()

        # 初始化后端
        if self.config.backend == "vectordb":
            self._backend: IntentCacheBackend = VectorDBBackend()
        else:
            self._backend = InMemoryBackend(
                max_size=self.config.max_size, ttl_hours=self.config.ttl_hours
            )

        # Embedding 服务（仅 semantic_enabled 时初始化，hash-only 模式不加载模型）
        self._embedding_service: Optional[EmbeddingService] = None
        if self.config.semantic_enabled:
            self._embedding_service = EmbeddingService(model=self.config.embedding_model)

        # 统计指标
        self._stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "stores": 0,
            "hash_only_stores": 0,  # 无 embedding 的存储次数
        }

        # 降级日志标记（仅记录一次，避免刷屏）
        self._hash_only_logged = False

        mode = (
            "hash_only"
            if not self.config.semantic_enabled
            else f"full (threshold={self.config.threshold})"
        )
        logger.info(
            f"IntentSemanticCache 初始化: "
            f"enabled={self.config.enabled}, "
            f"mode={mode}, "
            f"max_size={self.config.max_size}"
        )

    @classmethod
    def get_instance(cls, config: Optional[IntentCacheConfig] = None) -> "IntentSemanticCache":
        """获取单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（测试用）"""
        with cls._lock:
            if cls._instance:
                cls._instance._backend.clear()
            cls._instance = None

    async def lookup(self, query: str) -> Tuple[Optional[IntentResult], float]:
        """
        查询语义缓存

        Args:
            query: 用户查询文本

        Returns:
            (IntentResult, 相似度分数)，未命中返回 (None, 0.0)

        耗时预算:
        - L1 精确匹配: < 0.1ms
        - L2 语义匹配: < 60ms (Embedding 50ms + 相似度 5ms)
        """
        if not self.config.enabled:
            return None, 0.0

        start_time = time.time()

        # L1: 精确匹配（hash）
        query_hash = self._compute_hash(query)
        cached = await self._backend.get_by_hash(query_hash)
        if cached:
            self._stats["l1_hits"] += 1
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(f"✅ L1 精确命中: hash={query_hash[:8]}..., " f"elapsed={elapsed_ms:.2f}ms")
            return cached.intent_result, 1.0

        # L2: 语义匹配（仅 semantic_enabled 时执行，默认跳过）
        if not self.config.semantic_enabled or self._embedding_service is None:
            self._stats["misses"] += 1
            return None, 0.0

        try:
            embedding = await self._embedding_service.embed(query)
            if embedding is None:
                # 模型不可用 → 静默降级，仅 L1 hash 精确匹配
                # 精准优先：未命中走正常 LLM 意图识别，不做模糊猜测
                if not self._hash_only_logged:
                    logger.info(
                        "IntentCache 语义匹配降级为 hash-only"
                        "（embedding 模型不可用，仅精确匹配，未命中走 LLM）"
                    )
                    self._hash_only_logged = True
                self._stats["misses"] += 1
                return None, 0.0

            cached, score = await self._backend.search(embedding)

            elapsed_ms = (time.time() - start_time) * 1000

            if cached and score >= self.config.threshold:
                self._stats["l2_hits"] += 1
                logger.info(
                    f"L2 semantic hit: score={score:.4f}, "
                    f"threshold={self.config.threshold}, "
                    f"elapsed={elapsed_ms:.1f}ms"
                )
                return cached.intent_result, score

            self._stats["misses"] += 1
            logger.debug(
                f"Cache miss: score={score:.4f}, "
                f"threshold={self.config.threshold}, "
                f"elapsed={elapsed_ms:.1f}ms"
            )
            return None, score

        except Exception as e:
            self._stats["misses"] += 1
            logger.warning(f"Semantic cache lookup failed: {e}")
            return None, 0.0

    async def store(self, query: str, result: IntentResult) -> None:
        """
        存储意图结果到缓存

        Args:
            query: 用户查询文本
            result: 意图分析结果

        注意: 此方法应异步调用，不阻塞主流程
        """
        if not self.config.enabled:
            return

        try:
            # 获取 embedding（hash-only 模式或模型不可用时为 None）
            embedding = None
            if self.config.semantic_enabled and self._embedding_service is not None:
                embedding = await self._embedding_service.embed(query)

            # 创建缓存项（embedding=None 时仅支持 L1 hash 精确匹配）
            item = CachedIntentResult(
                query_text=query,
                query_hash=self._compute_hash(query),
                embedding=embedding,
                intent_result=result,
            )

            # 存储
            await self._backend.insert(item)
            self._stats["stores"] += 1
            if embedding is None:
                self._stats["hash_only_stores"] += 1

            logger.debug(
                f"Cache stored: hash={item.query_hash[:8]}..., "
                f"has_embedding={embedding is not None}, "
                f"size={self._backend.size()}"
            )

        except Exception as e:
            logger.warning(f"Cache store failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._stats["l1_hits"] + self._stats["l2_hits"] + self._stats["misses"]
        hit_rate = (self._stats["l1_hits"] + self._stats["l2_hits"]) / max(total, 1)

        # 判断当前模式
        if not self.config.semantic_enabled:
            mode = "hash_only"  # 配置默认
        elif self._embedding_service and not self._embedding_service._unavailable:
            mode = "full"  # 语义匹配可用
        else:
            mode = "hash_only_degraded"  # 配置为 semantic 但模型不可用

        # 空间估算：hash-only ~1KB/条目，full ~5KB/条目（含 1024-dim float32 向量）
        size = self._backend.size()
        kb_per_entry = 5.0 if mode == "full" else 1.0

        return {
            "enabled": self.config.enabled,
            "mode": mode,  # "full"=L1+L2, "hash_only"=仅 L1 精确匹配
            "backend": self.config.backend,
            "threshold": self.config.threshold,
            "size": size,
            "max_size": self.config.max_size,
            "l1_hits": self._stats["l1_hits"],
            "l2_hits": self._stats["l2_hits"],
            "misses": self._stats["misses"],
            "stores": self._stats["stores"],
            "hash_only_stores": self._stats["hash_only_stores"],
            "hit_rate": hit_rate,
            "estimated_memory_mb": round(size * kb_per_entry / 1024, 2),
        }

    @staticmethod
    def _compute_hash(text: str) -> str:
        """计算文本 hash"""
        return hashlib.md5(text.encode()).hexdigest()


# ============================================================
# 便捷函数
# ============================================================


def get_intent_cache(config: Optional[IntentCacheConfig] = None) -> IntentSemanticCache:
    """获取意图缓存实例"""
    return IntentSemanticCache.get_instance(config)
