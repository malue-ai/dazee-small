"""
知识检索 E2E 全流程测试

测试目标：
1. GGUF 本地模型加载 + embedding 正确性
2. 文件索引（docs/ 目录，多种 .md/.txt 文件）
3. FTS5 关键词搜索（中文/英文/混合）
4. 语义搜索（同义词匹配、跨语言理解）
5. 混合搜索加权合并（去重、排序、分数归一化）
6. BM25 归一化 + 最小分数阈值
7. 增量索引（hash check）

运行方式：
    python scripts/test_knowledge_e2e.py
"""

import asyncio
import sys
import time
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use isolated test database (avoid corrupting production DB)
import os
import tempfile

_test_db_dir = tempfile.mkdtemp(prefix="knowledge_e2e_")
os.environ["LOCAL_STORE_DIR"] = _test_db_dir


# ==================== Test Config ====================

# Use docs/ as test corpus
DOCS_DIR = Path(__file__).parent.parent / "docs"
PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️ WARN"


class TestResult:
    """Accumulate test results."""

    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.details: list[str] = []

    def check(self, name: str, condition: bool, detail: str = ""):
        self.total += 1
        if condition:
            self.passed += 1
            self.details.append(f"  {PASS} {name}")
        else:
            self.failed += 1
            msg = f"  {FAIL} {name}"
            if detail:
                msg += f" — {detail}"
            self.details.append(msg)

    def warn(self, name: str, detail: str = ""):
        self.warnings += 1
        msg = f"  {WARN} {name}"
        if detail:
            msg += f" — {detail}"
        self.details.append(msg)

    def print_summary(self):
        print("\n" + "=" * 60)
        print("Test Results")
        print("=" * 60)
        for d in self.details:
            print(d)
        print("-" * 60)
        print(
            f"Total: {self.total} | "
            f"Passed: {self.passed} | "
            f"Failed: {self.failed} | "
            f"Warnings: {self.warnings}"
        )
        if self.failed == 0:
            print(f"\n{PASS} ALL TESTS PASSED")
        else:
            print(f"\n{FAIL} {self.failed} TEST(S) FAILED")
        print("=" * 60)


results = TestResult()


# ==================== Phase 1: Embedding Model ====================


async def test_embedding_model():
    """Test GGUF embedding model load + basic embedding correctness."""
    print("\n📦 Phase 1: Embedding Model")
    print("-" * 40)

    from core.knowledge.embeddings import (
        GGUFEmbeddingProvider,
        create_embedding_provider,
        get_models_dir,
        normalize_l2,
    )
    import numpy as np

    # 1.1 Model file exists
    model_path = get_models_dir() / "bge-m3-Q4_K_M.gguf"
    results.check("Model file exists", model_path.exists(), str(model_path))

    # 1.2 Create provider via auto detection
    t0 = time.time()
    provider = await create_embedding_provider("auto")
    init_ms = (time.time() - t0) * 1000
    results.check(
        f"Auto provider = GGUF (init {init_ms:.0f}ms)",
        provider.provider_id == "local-gguf",
        f"Got {provider.provider_id}",
    )
    results.check("Dimensions = 1024", provider.dimensions == 1024)

    # 1.3 Single embedding
    t0 = time.time()
    vec = await provider.embed("如何优化系统性能")
    embed_ms = (time.time() - t0) * 1000
    results.check(
        f"Single embed OK ({embed_ms:.0f}ms)",
        vec.shape == (1024,) and np.all(np.isfinite(vec)),
    )
    results.check(
        "L2 normalized (|vec|≈1.0)",
        abs(np.linalg.norm(vec) - 1.0) < 0.01,
        f"norm={np.linalg.norm(vec):.6f}",
    )

    # 1.4 Batch embedding
    texts = ["Python 编程", "机器学习", "数据库优化"]
    t0 = time.time()
    vecs = await provider.embed_batch(texts)
    batch_ms = (time.time() - t0) * 1000
    results.check(
        f"Batch embed 3 texts ({batch_ms:.0f}ms)",
        len(vecs) == 3 and all(v.shape == (1024,) for v in vecs),
    )

    # 1.5 Semantic similarity check
    v_python = await provider.embed("Python 编程语言")
    v_java = await provider.embed("Java 编程语言")
    v_weather = await provider.embed("今天天气怎么样")

    sim_same = float(np.dot(v_python, v_java))
    sim_diff = float(np.dot(v_python, v_weather))
    results.check(
        f"Semantic: Python~Java ({sim_same:.3f}) > Python~Weather ({sim_diff:.3f})",
        sim_same > sim_diff,
        f"Δ={sim_same - sim_diff:.3f}",
    )

    # 1.6 Chinese-English cross-lingual
    v_cn = await provider.embed("性能优化")
    v_en = await provider.embed("performance optimization")
    v_food = await provider.embed("红烧肉的做法")

    sim_cross = float(np.dot(v_cn, v_en))
    sim_unrelated = float(np.dot(v_cn, v_food))
    results.check(
        f"Cross-lingual: 性能优化~perf opt ({sim_cross:.3f}) > 性能优化~红烧肉 ({sim_unrelated:.3f})",
        sim_cross > sim_unrelated,
        f"Δ={sim_cross - sim_unrelated:.3f}",
    )

    return provider


# ==================== Phase 2: Indexing ====================


async def test_indexing():
    """Test file indexing with docs/ directory."""
    print("\n📁 Phase 2: File Indexing")
    print("-" * 40)

    from core.knowledge.local_search import LocalKnowledgeManager
    from core.knowledge.file_indexer import FileIndexer

    # 2.1 Initialize with semantic enabled
    km = LocalKnowledgeManager(
        fts5_enabled=True,
        semantic_enabled=True,
        embedding_provider="auto",
    )
    await km.initialize()

    stats = await km.get_stats()
    results.check("KM initialized", stats["fts5_enabled"])
    results.check(
        "Semantic enabled",
        stats["semantic_enabled"],
        f"provider={stats.get('embedding_provider', 'N/A')}",
    )

    # 2.2 Index docs/ directory
    indexer = FileIndexer(km)
    t0 = time.time()
    count = await indexer.index_directory(DOCS_DIR, extensions=[".md", ".txt"])
    index_ms = (time.time() - t0) * 1000
    results.check(
        f"Indexed {count} files from docs/ ({index_ms:.0f}ms)",
        count >= 5,
        "Need at least 5 files",
    )

    # 2.3 Stats after indexing
    stats = await km.get_stats()
    results.check(
        f"Total docs in index: {stats['total_docs']}",
        stats["total_docs"] > 0,
    )

    # 2.4 Incremental indexing (re-index should skip)
    t0 = time.time()
    count2 = await indexer.index_directory(DOCS_DIR, extensions=[".md", ".txt"])
    reindex_ms = (time.time() - t0) * 1000
    results.check(
        f"Incremental re-index ({reindex_ms:.0f}ms) — skipped unchanged files",
        count2 == count,
        f"Expected {count}, got {count2}",
    )

    return km


# ==================== Phase 3: FTS5 Keyword Search ====================


async def test_fts5_search(km):
    """Test FTS5 full-text search with various queries."""
    print("\n🔍 Phase 3: FTS5 Keyword Search")
    print("-" * 40)

    # 3.1 Chinese keyword search
    r = await km._fts5_search("知识库", limit=10)
    results.check(
        f"FTS5 '知识库': {len(r)} results",
        len(r) > 0,
        "Should match docs mentioning 知识库",
    )

    # 3.2 English keyword search
    r = await km._fts5_search("FTS5", limit=10)
    results.check(
        f"FTS5 'FTS5': {len(r)} results",
        len(r) > 0,
        "Should match docs mentioning FTS5",
    )

    # 3.3 BM25 score normalization
    if r:
        scores = [x.score for x in r]
        results.check(
            f"BM25 scores normalized [0,1]: {[f'{s:.3f}' for s in scores[:3]]}",
            all(0 <= s <= 1 for s in scores),
            f"Range: [{min(scores):.3f}, {max(scores):.3f}]",
        )

    # 3.4 Mixed language query
    r = await km._fts5_search("SQLite 搜索", limit=10)
    results.check(
        f"FTS5 mixed 'SQLite 搜索': {len(r)} results",
        len(r) > 0,
    )

    # 3.5 No results for gibberish
    r = await km._fts5_search("xyzabc123nonsense", limit=10)
    results.check(
        f"FTS5 gibberish query: {len(r)} results",
        len(r) == 0,
        "Should return 0 for nonsense",
    )


# ==================== Phase 4: Semantic Search ====================


async def test_semantic_search(km):
    """Test vector-based semantic search."""
    print("\n🧠 Phase 4: Semantic Search")
    print("-" * 40)

    # 4.1 Exact concept match
    r = await km._semantic_search("全文检索引擎", limit=10)
    results.check(
        f"Semantic '全文检索引擎': {len(r)} results",
        len(r) > 0,
        "Should find FTS5-related docs",
    )

    # 4.2 Synonym match — THE KEY VALUE OF SEMANTIC SEARCH
    # "项目架构" should find docs about "系统设计", "架构设计" etc.
    r = await km._semantic_search("项目整体架构是什么样的", limit=10)
    results.check(
        f"Semantic synonym '项目整体架构': {len(r)} results",
        len(r) > 0,
        "Should find architecture-related docs by meaning",
    )

    # 4.3 English query on Chinese docs
    r = await km._semantic_search("how does the knowledge retrieval work", limit=10)
    results.check(
        f"Semantic cross-lang (EN→CN): {len(r)} results",
        len(r) > 0,
        "Should find 知识检索-related docs via English query",
    )

    # 4.4 Scores in [0, 1]
    if r:
        scores = [x.score for x in r]
        results.check(
            f"Semantic scores [0,1]: {[f'{s:.3f}' for s in scores[:3]]}",
            all(0 <= s <= 1 for s in scores),
        )

    # 4.5 Abstract concept
    r = await km._semantic_search("如何提升用户体验", limit=5)
    results.check(
        f"Semantic abstract '用户体验': {len(r)} results",
        len(r) > 0,
        "Should find UX-related content by meaning",
    )


# ==================== Phase 5: Hybrid Search ====================


async def test_hybrid_search(km):
    """Test hybrid search (FTS5 + vector weighted merge)."""
    print("\n⚡ Phase 5: Hybrid Search (Weighted Merge)")
    print("-" * 40)

    # 5.1 Basic hybrid search
    r = await km.search("知识库搜索优化", limit=10)
    results.check(
        f"Hybrid '知识库搜索优化': {len(r)} results",
        len(r) > 0,
    )

    # 5.2 Scores should be weighted combination
    if r:
        scores = [x.score for x in r]
        results.check(
            f"Hybrid scores [0,1]: top={scores[0]:.3f}",
            all(0 <= s <= 1 for s in scores),
        )
        # Verify approximate descending order (allow small floating-point ties)
        is_approx_desc = all(
            scores[i] >= scores[i + 1] - 0.001 for i in range(len(scores) - 1)
        )
        results.check(
            "Hybrid scores approximately descending",
            is_approx_desc,
            f"Scores: {[f'{s:.4f}' for s in scores[:5]]}",
        )

    # 5.3 Deduplication: same doc shouldn't appear twice
    doc_ids = [x.doc_id for x in r]
    results.check(
        "No duplicate doc_ids",
        len(doc_ids) == len(set(doc_ids)),
        f"Total={len(doc_ids)}, unique={len(set(doc_ids))}",
    )

    # 5.4 Semantic advantage: query by meaning, not keywords
    # "怎样让搜索更智能" has no exact keyword match with FTS5,
    # but semantic search should find knowledge-related docs
    fts_only = await km._fts5_search("怎样让搜索更智能", limit=5)
    hybrid = await km.search("怎样让搜索更智能", limit=5)
    results.check(
        f"Hybrid beats FTS5 for vague query: hybrid={len(hybrid)} >= fts={len(fts_only)}",
        len(hybrid) >= len(fts_only),
        "Semantic should add results FTS5 misses",
    )

    # 5.5 min_score filtering
    r_strict = await km.search("知识库", limit=10, min_score=0.5)
    r_loose = await km.search("知识库", limit=10, min_score=0.01)
    results.check(
        f"min_score filter: strict({len(r_strict)}) <= loose({len(r_loose)})",
        len(r_strict) <= len(r_loose),
    )

    # 5.6 Custom weights
    r_vec_heavy = await km.search(
        "怎样优化系统", limit=5, vector_weight=0.9, text_weight=0.1
    )
    r_text_heavy = await km.search(
        "怎样优化系统", limit=5, vector_weight=0.1, text_weight=0.9
    )
    results.check(
        f"Custom weights: vec-heavy={len(r_vec_heavy)}, text-heavy={len(r_text_heavy)}",
        True,  # Both should work without error
    )

    # 5.7 File type filter
    r_md = await km.search("协议", limit=10, file_type=".md")
    if r_md:
        all_md = all(x.file_type == ".md" for x in r_md)
        results.check(
            f"File type filter .md: {len(r_md)} results, all .md={all_md}",
            all_md,
        )
    else:
        results.warn("File type filter .md: no results (may be ok if no match)")

    # 5.8 FTS snippet has highlighting
    r_snippet = await km.search("FTS5", limit=3)
    if r_snippet:
        has_highlight = any("<b>" in x.snippet for x in r_snippet)
        results.check(
            "FTS5 snippets have <b> highlighting",
            has_highlight,
            f"Snippets: {[x.snippet[:50] for x in r_snippet[:2]]}",
        )


# ==================== Phase 6: Edge Cases ====================


async def test_edge_cases(km):
    """Test edge cases and robustness."""
    print("\n🛡️ Phase 6: Edge Cases")
    print("-" * 40)

    # 6.1 Empty query
    r = await km.search("", limit=10)
    results.check("Empty query returns empty", len(r) == 0)

    # 6.2 Very long query (truncation)
    long_q = "知识库搜索 " * 500  # ~3000 chars
    r = await km.search(long_q, limit=5)
    results.check("Long query doesn't crash", True)  # No exception = pass

    # 6.3 Special characters
    r = await km.search('查找 "FTS5" 相关文档', limit=5)
    results.check("Query with quotes OK", True)

    r = await km.search("C++ AND Python", limit=5)
    results.check("Query with AND operator OK", True)

    # 6.4 Unicode edge
    r = await km.search("日本語テスト", limit=5)
    results.check("Japanese query doesn't crash", True)


# ==================== Main ====================


async def main():
    print("=" * 60)
    print("Knowledge Retrieval E2E Test")
    print(f"Test corpus: {DOCS_DIR}")
    print("=" * 60)

    t_start = time.time()

    # Phase 1: Embedding Model
    provider = await test_embedding_model()

    # Phase 2: Indexing
    km = await test_indexing()

    # Phase 3: FTS5
    await test_fts5_search(km)

    # Phase 4: Semantic
    await test_semantic_search(km)

    # Phase 5: Hybrid
    await test_hybrid_search(km)

    # Phase 6: Edge Cases
    await test_edge_cases(km)

    total_s = time.time() - t_start
    print(f"\nTotal time: {total_s:.1f}s")

    results.print_summary()

    return results.failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())

    # Cleanup temp DB
    import shutil
    shutil.rmtree(_test_db_dir, ignore_errors=True)
    print(f"\nCleaned up temp DB: {_test_db_dir}")

    sys.exit(0 if ok else 1)
