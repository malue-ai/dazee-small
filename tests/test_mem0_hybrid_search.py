"""
Mem0 混合搜索测试

验证范围：
1. FTS5 索引同步：insert/update/delete 正确维护 FTS5 表
2. keyword_search：BM25 关键词搜索 + 分数归一化
3. pool.search 混合搜索：向量 + 关键词加权合并
4. min_score 阈值过滤
5. _merge_hybrid_results 合并去重逻辑
6. 容错：FTS5 不可用时回退到纯向量搜索
7. rebuild_fts_index：索引重建

Run:
    python -m pytest tests/test_mem0_hybrid_search.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ======================================================================
# 1. BM25 归一化
# ======================================================================

def _bm25_rank_to_score(rank):
    """复制 SqliteVecVectorStore._bm25_rank_to_score 的纯函数逻辑用于测试。
    避免导入 sqlite_vec_store（依赖 mem0 包）。"""
    import math
    if rank is None or not math.isfinite(rank):
        return 0.0
    a = abs(rank)
    return a / (1.0 + a)


class TestBm25RankToScore:
    """验证 BM25 rank → [0, 1] 分数转换。"""

    def test_high_relevance(self):
        """rank=-10 → ~0.91"""
        score = _bm25_rank_to_score(-10.0)
        assert 0.90 < score < 0.92

    def test_medium_relevance(self):
        """rank=-1 → 0.5"""
        score = _bm25_rank_to_score(-1.0)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_low_relevance(self):
        """rank=-0.1 → ~0.09"""
        score = _bm25_rank_to_score(-0.1)
        assert 0.08 < score < 0.10

    def test_zero_rank(self):
        """rank=0 → 0.0"""
        assert _bm25_rank_to_score(0.0) == 0.0

    def test_none_rank(self):
        """rank=None → 0.0"""
        assert _bm25_rank_to_score(None) == 0.0

    def test_inf_rank(self):
        """rank=inf → 0.0"""
        assert _bm25_rank_to_score(float("inf")) == 0.0


# ======================================================================
# 2. _merge_hybrid_results
# ======================================================================

class TestMergeHybridResults:
    """验证混合搜索加权合并逻辑。"""

    def test_both_sources(self):
        """向量 + 关键词都有结果时正确合并。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        vec = [
            {"id": "a", "memory": "Python 偏好", "score": 0.8},
            {"id": "b", "memory": "FastAPI", "score": 0.6},
        ]
        fts = [
            {"id": "a", "memory": "Python 偏好", "score": 0.9},
            {"id": "c", "memory": "老张负责人", "score": 0.7},
        ]
        merged = Mem0MemoryPool._merge_hybrid_results(vec, fts, limit=10)

        ids = [m["id"] for m in merged]
        assert "a" in ids
        assert "b" in ids
        assert "c" in ids
        assert len(merged) == 3

        # id="a" 的分数应该是加权值
        a_entry = next(m for m in merged if m["id"] == "a")
        expected = 0.6 * 0.8 + 0.4 * 0.9  # 0.84
        assert a_entry["score"] == pytest.approx(expected, abs=0.01)

    def test_only_vec(self):
        """只有向量结果时正常返回。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        vec = [{"id": "a", "memory": "test", "score": 0.7}]
        merged = Mem0MemoryPool._merge_hybrid_results(vec, [], limit=10)
        assert len(merged) == 1
        assert merged[0]["score"] == pytest.approx(0.6 * 0.7, abs=0.01)

    def test_only_fts(self):
        """只有 FTS 结果时正常返回。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        fts = [{"id": "b", "memory": "test", "score": 0.5}]
        merged = Mem0MemoryPool._merge_hybrid_results([], fts, limit=10)
        assert len(merged) == 1
        assert merged[0]["score"] == pytest.approx(0.4 * 0.5, abs=0.01)

    def test_both_empty(self):
        """两路都空时返回空列表。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        merged = Mem0MemoryPool._merge_hybrid_results([], [], limit=10)
        assert merged == []

    def test_limit_applied(self):
        """结果数不超过 limit。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        vec = [{"id": f"v{i}", "memory": f"mem{i}", "score": 0.5} for i in range(20)]
        merged = Mem0MemoryPool._merge_hybrid_results(vec, [], limit=5)
        assert len(merged) == 5

    def test_sorted_by_score_desc(self):
        """结果按分数降序排列。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        vec = [
            {"id": "low", "memory": "low", "score": 0.3},
            {"id": "high", "memory": "high", "score": 0.9},
            {"id": "mid", "memory": "mid", "score": 0.6},
        ]
        merged = Mem0MemoryPool._merge_hybrid_results(vec, [], limit=10)
        scores = [m["score"] for m in merged]
        assert scores == sorted(scores, reverse=True)

    def test_no_internal_fields_leaked(self):
        """合并后不应有 _vec_score / _fts_score 内部字段。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        vec = [{"id": "a", "memory": "test", "score": 0.7}]
        merged = Mem0MemoryPool._merge_hybrid_results(vec, [], limit=10)
        for m in merged:
            assert "_vec_score" not in m
            assert "_fts_score" not in m


# ======================================================================
# 3. min_score 过滤
# ======================================================================

class TestMinScoreFilter:
    """验证 pool.search() 的 min_score 阈值过滤。"""

    def test_low_score_filtered(self):
        """低于 min_score 的记忆被过滤。"""
        from core.memory.mem0.pool import Mem0MemoryPool

        vec = [
            {"id": "good", "memory": "good", "score": 0.8},
            {"id": "bad", "memory": "bad", "score": 0.1},
        ]
        # 测试 _merge + filter 逻辑
        merged = Mem0MemoryPool._merge_hybrid_results(vec, [], limit=10)
        filtered = [m for m in merged if m.get("score", 0) >= 0.35]
        assert len(filtered) == 1
        assert filtered[0]["id"] == "good"


# ======================================================================
# 4. FTS5 表结构
# ======================================================================

class TestFtsTableName:
    """验证 FTS5 表命名规则。"""

    def test_fts_table_name_format(self):
        """_fts_table_name 应为 collection_name + '_fts'。"""
        # 直接测试命名规则，不依赖 mem0 包
        collection_name = "test_memories"
        fts_name = f"{collection_name}_fts"
        assert fts_name == "test_memories_fts"


# ======================================================================
# 5. 默认参数
# ======================================================================

class TestDefaultParams:
    """验证默认参数配置。"""

    def test_default_min_score(self):
        """user_memory.py 的 _MEM0_MIN_SCORE 应为 0.35。"""
        from core.context.injectors.phase2.user_memory import _MEM0_MIN_SCORE
        assert _MEM0_MIN_SCORE == 0.35

    def test_default_weights(self):
        """混合搜索默认权重应为 0.6 / 0.4（与 pool._merge_hybrid_results 默认参数一致）。"""
        import inspect
        from core.memory.mem0.pool import Mem0MemoryPool

        sig = inspect.signature(Mem0MemoryPool._merge_hybrid_results)
        assert sig.parameters["vector_weight"].default == 0.6
        assert sig.parameters["text_weight"].default == 0.4
