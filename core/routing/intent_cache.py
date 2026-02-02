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
    if result and score >= 0.92:
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
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

from logger import get_logger
from core.agent.types import IntentResult, TaskType, Complexity

logger = get_logger("intent_cache")


# ============================================================
# 配置
# ============================================================

@dataclass
class IntentCacheConfig:
    """意图缓存配置"""
    enabled: bool = True                    # 是否启用缓存
    threshold: float = 0.92                 # 相似度阈值（>= 则命中）
    max_size: int = 10000                   # 最大缓存条目数（LRU）
    ttl_hours: int = 24                     # 缓存 TTL（小时）
    backend: str = "memory"                 # 存储后端：memory | vectordb
    embedding_model: str = "text-embedding-3-small"  # Embedding 模型
    embedding_dim: int = 1536               # 向量维度
    
    @classmethod
    def from_env(cls) -> "IntentCacheConfig":
        """从环境变量加载配置"""
        return cls(
            enabled=os.getenv("INTENT_CACHE_ENABLED", "true").lower() == "true",
            threshold=float(os.getenv("INTENT_CACHE_THRESHOLD", "0.92")),
            max_size=int(os.getenv("INTENT_CACHE_MAX_SIZE", "10000")),
            ttl_hours=int(os.getenv("INTENT_CACHE_TTL_HOURS", "24")),
            backend=os.getenv("INTENT_CACHE_BACKEND", "memory"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        )


# ============================================================
# 缓存数据结构
# ============================================================

@dataclass
class CachedIntentResult:
    """缓存的意图结果"""
    query_text: str                         # 原始查询文本
    query_hash: str                         # 查询文本的 hash（用于精确匹配）
    embedding: np.ndarray                   # 向量（1536维）
    intent_result: IntentResult             # 意图分析结果
    created_at: datetime = field(default_factory=datetime.now)
    hit_count: int = 0                      # 命中次数
    
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
    async def search(
        self,
        embedding: np.ndarray
    ) -> Tuple[Optional[CachedIntentResult], float]:
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
    
    async def search(
        self,
        embedding: np.ndarray
    ) -> Tuple[Optional[CachedIntentResult], float]:
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
            
            # 构建向量矩阵（如果需要）
            if self._embeddings is None or len(self._cache) != self._embeddings.shape[0]:
                self._rebuild_matrix()
            
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
            
            # 更新向量索引
            idx = self._next_idx
            self._next_idx += 1
            self._hash_to_idx[item.query_hash] = idx
            self._idx_to_hash[idx] = item.query_hash
            
            # 标记需要重建矩阵
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
        expired = [
            h for h, item in self._cache.items()
            if item.is_expired(self.ttl_hours)
        ]
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
        """重建向量矩阵"""
        if not self._cache:
            self._embeddings = None
            return
        
        # 重建索引映射
        self._hash_to_idx.clear()
        self._idx_to_hash.clear()
        
        embeddings = []
        for idx, (query_hash, item) in enumerate(self._cache.items()):
            # 归一化向量
            norm = np.linalg.norm(item.embedding) + 1e-10
            embeddings.append(item.embedding / norm)
            self._hash_to_idx[query_hash] = idx
            self._idx_to_hash[idx] = query_hash
        
        self._embeddings = np.array(embeddings)
        self._next_idx = len(self._cache)


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
            from infra.vector.factory import get_vector_store
            self._vector_store = await get_vector_store()
        return self._vector_store
    
    async def search(
        self,
        embedding: np.ndarray
    ) -> Tuple[Optional[CachedIntentResult], float]:
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
    Embedding 服务
    
    封装 OpenAI Embedding API 调用
    """
    
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._client = None
    
    async def embed(self, text: str) -> np.ndarray:
        """
        获取文本的 embedding 向量
        
        Args:
            text: 输入文本
            
        Returns:
            1536 维向量（text-embedding-3-small）
            
        耗时: ~50ms（网络延迟主导）
        """
        import httpx
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 环境变量未设置")
        
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                json={
                    "model": self.model,
                    "input": text[:8000]  # 截断过长文本
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            data = response.json()
        
        embedding = np.array(data["data"][0]["embedding"], dtype=np.float32)
        
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(f"🔢 Embedding 完成: dim={len(embedding)}, elapsed={elapsed_ms:.1f}ms")
        
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
                max_size=self.config.max_size,
                ttl_hours=self.config.ttl_hours
            )
        
        # Embedding 服务
        self._embedding_service = EmbeddingService(model=self.config.embedding_model)
        
        # 统计指标
        self._stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "stores": 0,
        }
        
        logger.info(
            f"✅ IntentSemanticCache 初始化: "
            f"enabled={self.config.enabled}, "
            f"threshold={self.config.threshold}, "
            f"backend={self.config.backend}"
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
            logger.info(
                f"✅ L1 精确命中: hash={query_hash[:8]}..., "
                f"elapsed={elapsed_ms:.2f}ms"
            )
            return cached.intent_result, 1.0
        
        # L2: 语义匹配（embedding）
        try:
            embedding = await self._embedding_service.embed(query)
            cached, score = await self._backend.search(embedding)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if cached and score >= self.config.threshold:
                self._stats["l2_hits"] += 1
                logger.info(
                    f"✅ L2 语义命中: score={score:.4f}, "
                    f"threshold={self.config.threshold}, "
                    f"elapsed={elapsed_ms:.1f}ms"
                )
                return cached.intent_result, score
            
            self._stats["misses"] += 1
            logger.debug(
                f"❌ 缓存未命中: score={score:.4f}, "
                f"threshold={self.config.threshold}, "
                f"elapsed={elapsed_ms:.1f}ms"
            )
            return None, score
            
        except Exception as e:
            self._stats["misses"] += 1
            logger.warning(f"⚠️ 语义缓存查询失败: {e}")
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
            # 获取 embedding
            embedding = await self._embedding_service.embed(query)
            
            # 创建缓存项
            item = CachedIntentResult(
                query_text=query,
                query_hash=self._compute_hash(query),
                embedding=embedding,
                intent_result=result,
            )
            
            # 存储
            await self._backend.insert(item)
            self._stats["stores"] += 1
            
            logger.debug(
                f"💾 缓存存储: hash={item.query_hash[:8]}..., "
                f"size={self._backend.size()}"
            )
            
        except Exception as e:
            logger.warning(f"⚠️ 缓存存储失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._stats["l1_hits"] + self._stats["l2_hits"] + self._stats["misses"]
        hit_rate = (self._stats["l1_hits"] + self._stats["l2_hits"]) / max(total, 1)
        
        return {
            "enabled": self.config.enabled,
            "backend": self.config.backend,
            "threshold": self.config.threshold,
            "size": self._backend.size(),
            "max_size": self.config.max_size,
            "l1_hits": self._stats["l1_hits"],
            "l2_hits": self._stats["l2_hits"],
            "misses": self._stats["misses"],
            "stores": self._stats["stores"],
            "hit_rate": hit_rate,
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
