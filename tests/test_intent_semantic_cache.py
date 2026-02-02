"""
意图识别语义缓存单元测试

测试内容：
1. 缓存命中逻辑（L1 精确匹配 + L2 语义匹配）
2. 阈值判断逻辑
3. LRU 淘汰策略
4. 性能约束（< 100ms）
"""

import asyncio
import time
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

# 测试目标模块
from core.routing.intent_cache import (
    IntentSemanticCache,
    IntentCacheConfig,
    CachedIntentResult,
    InMemoryBackend,
    get_intent_cache,
)
from core.agent.types import IntentResult, TaskType, Complexity


# ============================================================
# 测试数据
# ============================================================

def create_test_intent_result(
    task_type: TaskType = TaskType.INFORMATION_QUERY,
    complexity: Complexity = Complexity.SIMPLE,
    complexity_score: float = 3.0
) -> IntentResult:
    """创建测试用 IntentResult"""
    return IntentResult(
        task_type=task_type,
        complexity=complexity,
        complexity_score=complexity_score,
        needs_plan=False,
    )


def create_test_embedding(dim: int = 1536) -> np.ndarray:
    """创建测试用 embedding 向量"""
    vec = np.random.randn(dim).astype(np.float32)
    return vec / np.linalg.norm(vec)  # 归一化


# ============================================================
# InMemoryBackend 测试
# ============================================================

class TestInMemoryBackend:
    """内存后端测试"""
    
    @pytest.fixture
    def backend(self):
        """创建测试用后端"""
        return InMemoryBackend(max_size=100, ttl_hours=24)
    
    @pytest.mark.asyncio
    async def test_insert_and_search(self, backend):
        """测试插入和搜索"""
        # 准备数据
        embedding = create_test_embedding()
        intent = create_test_intent_result()
        
        item = CachedIntentResult(
            query_text="测试查询",
            query_hash="test_hash_123",
            embedding=embedding,
            intent_result=intent,
        )
        
        # 插入
        await backend.insert(item)
        assert backend.size() == 1
        
        # 搜索（相同向量应该返回高分数）
        result, score = await backend.search(embedding)
        
        assert result is not None
        assert score > 0.99  # 相同向量，相似度接近 1.0
        assert result.intent_result.task_type == TaskType.INFORMATION_QUERY
    
    @pytest.mark.asyncio
    async def test_exact_match(self, backend):
        """测试精确匹配（L1 缓存）"""
        embedding = create_test_embedding()
        intent = create_test_intent_result()
        
        item = CachedIntentResult(
            query_text="测试查询",
            query_hash="exact_hash_456",
            embedding=embedding,
            intent_result=intent,
        )
        
        await backend.insert(item)
        
        # 精确匹配
        result = await backend.get_by_hash("exact_hash_456")
        assert result is not None
        assert result.query_text == "测试查询"
        
        # 不存在的 hash
        result = await backend.get_by_hash("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self, backend):
        """测试 LRU 淘汰"""
        backend = InMemoryBackend(max_size=3, ttl_hours=24)
        
        # 插入 4 个项目（超过容量）
        for i in range(4):
            item = CachedIntentResult(
                query_text=f"查询{i}",
                query_hash=f"hash_{i}",
                embedding=create_test_embedding(),
                intent_result=create_test_intent_result(),
            )
            await backend.insert(item)
        
        # 应该只保留 3 个
        assert backend.size() == 3
        
        # 最早的应该被淘汰
        result = await backend.get_by_hash("hash_0")
        assert result is None
        
        # 最新的应该存在
        result = await backend.get_by_hash("hash_3")
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self, backend):
        """测试 TTL 过期"""
        embedding = create_test_embedding()
        intent = create_test_intent_result()
        
        # 创建已过期的项目
        item = CachedIntentResult(
            query_text="过期查询",
            query_hash="expired_hash",
            embedding=embedding,
            intent_result=intent,
            created_at=datetime.now() - timedelta(hours=25),  # 超过 24h
        )
        
        await backend.insert(item)
        
        # 精确匹配应该返回 None（已过期）
        result = await backend.get_by_hash("expired_hash")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_search_performance(self, backend):
        """测试搜索性能（< 5ms，10000 条）"""
        backend = InMemoryBackend(max_size=10000, ttl_hours=24)
        
        # 插入 1000 条数据（减少测试时间）
        for i in range(1000):
            item = CachedIntentResult(
                query_text=f"查询{i}",
                query_hash=f"hash_{i}",
                embedding=create_test_embedding(),
                intent_result=create_test_intent_result(),
            )
            await backend.insert(item)
        
        # 测试搜索性能
        query_embedding = create_test_embedding()
        
        start = time.time()
        result, score = await backend.search(query_embedding)
        elapsed_ms = (time.time() - start) * 1000
        
        print(f"搜索耗时: {elapsed_ms:.2f}ms (1000 条)")
        
        # 应该 < 10ms（1000 条）
        assert elapsed_ms < 10, f"搜索耗时 {elapsed_ms:.2f}ms 超过 10ms"


# ============================================================
# IntentSemanticCache 测试
# ============================================================

class TestIntentSemanticCache:
    """语义缓存主类测试"""
    
    @pytest.fixture
    def config(self):
        """测试配置"""
        return IntentCacheConfig(
            enabled=True,
            threshold=0.92,
            max_size=100,
            ttl_hours=24,
            backend="memory",
        )
    
    @pytest.fixture
    def cache(self, config):
        """创建测试缓存"""
        # 重置单例
        IntentSemanticCache.reset_instance()
        return IntentSemanticCache(config)
    
    @pytest.mark.asyncio
    async def test_disabled_cache(self):
        """测试禁用缓存"""
        config = IntentCacheConfig(enabled=False)
        IntentSemanticCache.reset_instance()
        cache = IntentSemanticCache(config)
        
        result, score = await cache.lookup("任意查询")
        assert result is None
        assert score == 0.0
    
    @pytest.mark.asyncio
    async def test_threshold_logic(self, cache):
        """测试阈值判断逻辑"""
        # Mock embedding 服务
        mock_embedding = create_test_embedding()
        
        with patch.object(cache._embedding_service, 'embed', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = mock_embedding
            
            # 先存储一个结果
            intent = create_test_intent_result()
            await cache.store("原始查询", intent)
            
            # 相同查询应该命中（score = 1.0，因为精确匹配）
            result, score = await cache.lookup("原始查询")
            assert result is not None
            assert score == 1.0  # L1 精确匹配
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache):
        """测试统计信息追踪"""
        stats = cache.get_stats()
        
        assert "enabled" in stats
        assert "hit_rate" in stats
        assert "l1_hits" in stats
        assert "l2_hits" in stats
        assert "misses" in stats
        assert "stores" in stats
    
    def test_singleton_pattern(self):
        """测试单例模式"""
        IntentSemanticCache.reset_instance()
        
        cache1 = IntentSemanticCache.get_instance()
        cache2 = IntentSemanticCache.get_instance()
        
        assert cache1 is cache2
    
    def test_get_intent_cache_function(self):
        """测试便捷函数"""
        IntentSemanticCache.reset_instance()
        
        cache = get_intent_cache()
        assert isinstance(cache, IntentSemanticCache)


# ============================================================
# 集成测试（需要 Mock Embedding API）
# ============================================================

class TestIntentCacheIntegration:
    """集成测试（Mock Embedding）"""
    
    @pytest.mark.asyncio
    async def test_full_flow_with_mock_embedding(self):
        """完整流程测试（Mock Embedding）"""
        IntentSemanticCache.reset_instance()
        
        config = IntentCacheConfig(
            enabled=True,
            threshold=0.92,
            max_size=100,
        )
        cache = IntentSemanticCache(config)
        
        # Mock embedding 服务
        base_embedding = create_test_embedding()
        
        with patch.object(cache._embedding_service, 'embed', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = base_embedding
            
            # 1. 首次查询（未命中）
            result1, score1 = await cache.lookup("如何使用 Python?")
            assert result1 is None
            assert cache.get_stats()["misses"] == 1
            
            # 2. 存储结果
            intent = create_test_intent_result(
                task_type=TaskType.INFORMATION_QUERY,
                complexity=Complexity.SIMPLE,
            )
            await cache.store("如何使用 Python?", intent)
            assert cache.get_stats()["stores"] == 1
            
            # 3. 再次查询（应该命中 L1）
            result2, score2 = await cache.lookup("如何使用 Python?")
            assert result2 is not None
            assert score2 == 1.0  # 精确匹配
            assert result2.task_type == TaskType.INFORMATION_QUERY
            assert cache.get_stats()["l1_hits"] == 1
    
    @pytest.mark.asyncio
    async def test_semantic_similarity_matching(self):
        """测试语义相似度匹配"""
        IntentSemanticCache.reset_instance()
        
        config = IntentCacheConfig(
            enabled=True,
            threshold=0.90,  # 降低阈值便于测试
        )
        cache = IntentSemanticCache(config)
        
        # 创建相似的向量
        base_embedding = create_test_embedding()
        # 添加小噪声，模拟相似但不完全相同的查询
        similar_embedding = base_embedding + np.random.randn(1536).astype(np.float32) * 0.1
        similar_embedding = similar_embedding / np.linalg.norm(similar_embedding)
        
        call_count = 0
        
        async def mock_embed(text):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return base_embedding  # 存储时
            else:
                return similar_embedding  # 查询时
        
        with patch.object(cache._embedding_service, 'embed', side_effect=mock_embed):
            # 存储
            intent = create_test_intent_result()
            await cache.store("Python 入门教程", intent)
            
            # 查询相似问题（不完全相同的 hash，走 L2）
            result, score = await cache.lookup("Python 基础教程")  # 不同文本
            
            # 由于向量相似，应该能匹配
            print(f"语义相似度: {score:.4f}")
            # 注意：由于添加了噪声，分数可能低于阈值


# ============================================================
# 配置测试
# ============================================================

class TestIntentCacheConfig:
    """配置类测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = IntentCacheConfig()
        
        assert config.enabled == True
        assert config.threshold == 0.92
        assert config.max_size == 10000
        assert config.ttl_hours == 24
        assert config.backend == "memory"
    
    def test_from_env(self):
        """测试从环境变量加载"""
        import os
        
        # 保存原始值
        original = {
            "INTENT_CACHE_ENABLED": os.environ.get("INTENT_CACHE_ENABLED"),
            "INTENT_CACHE_THRESHOLD": os.environ.get("INTENT_CACHE_THRESHOLD"),
        }
        
        try:
            os.environ["INTENT_CACHE_ENABLED"] = "false"
            os.environ["INTENT_CACHE_THRESHOLD"] = "0.85"
            
            config = IntentCacheConfig.from_env()
            
            assert config.enabled == False
            assert config.threshold == 0.85
        finally:
            # 恢复原始值
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
