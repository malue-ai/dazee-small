"""
Memory optimization E2E verification.

Verifies all 5 optimization points:
1. P0: Mem0 concurrent write fix (threading.Lock)
2. P1: Error handling (_mem0_add returns bool, degraded logging)
3. P1: Ephemeral instruction filtering + dedup script
4. P2: Fusion search (weighted scoring + Jaccard dedup)
5. P2: Embedding warmup + remember_batch

Usage:
    python3 scripts/verify_memory_optimization.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AGENT_INSTANCE", "xiaodazi")

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


# ============================================================
# Test 1: threading.Lock exists on SqliteVecVectorStore
# ============================================================
def test_write_lock():
    print("\n=== Test 1: SqliteVecVectorStore write lock ===")
    import threading

    from core.memory.mem0.sqlite_vec_store import SqliteVecVectorStore

    # Check class has _write_lock in __init__
    import inspect
    source = inspect.getsource(SqliteVecVectorStore.__init__)
    check(
        "_write_lock created in __init__",
        "_write_lock" in source and "threading.Lock" in source,
    )

    # Check write methods use the lock
    for method_name in ("insert", "update", "delete"):
        method_source = inspect.getsource(getattr(SqliteVecVectorStore, method_name))
        check(
            f"{method_name}() uses self._write_lock",
            "self._write_lock" in method_source,
        )


# ============================================================
# Test 2: _mem0_add returns bool
# ============================================================
def test_mem0_add_returns_bool():
    print("\n=== Test 2: _mem0_add returns bool ===")
    import inspect

    from core.memory.instance_memory import InstanceMemoryManager

    sig = inspect.signature(InstanceMemoryManager._mem0_add)
    return_annotation = sig.return_annotation

    check(
        "_mem0_add return annotation is bool",
        return_annotation is bool or str(return_annotation) == "<class 'bool'>",
        f"got {return_annotation}",
    )

    source = inspect.getsource(InstanceMemoryManager._mem0_add)
    check(
        "_mem0_add has 'return True' path",
        "return True" in source,
    )
    check(
        "_mem0_add has 'return False' path",
        "return False" in source,
    )


# ============================================================
# Test 3: Ephemeral instruction filter
# ============================================================
def test_ephemeral_filter():
    print("\n=== Test 3: Ephemeral instruction filter ===")
    from core.memory.instance_memory import _is_ephemeral

    # Should be filtered (ephemeral)
    check(
        "filters '这三个文件必须保持一致...'",
        _is_ephemeral("这三个文件必须保持一致，如果某个文件修改失败，请把其他已修改的文件也恢复原样。"),
    )
    check(
        "filters '请直接修改这些文件'",
        _is_ephemeral("请直接修改这些文件"),
    )
    check(
        "filters '给我恢复到之前的'",
        _is_ephemeral("给我恢复到之前的"),
    )

    # Should NOT be filtered (real memories)
    check(
        "keeps '偏好工具: Excel'",
        not _is_ephemeral("偏好工具: Excel"),
    )
    check(
        "keeps '沟通风格: professional'",
        not _is_ephemeral("沟通风格: professional"),
    )
    check(
        "keeps '目标: 完成数据分析'",
        not _is_ephemeral("目标: 完成数据分析"),
    )


# ============================================================
# Test 4: Dedup script logic
# ============================================================
def test_dedup_script():
    print("\n=== Test 4: Dedup script ===")
    from scripts.deduplicate_memory import process_memory_text

    test_md = """# Test Memory

## 偏好

### 写作风格
- 沟通风格: professional
- 沟通风格: professional
- 沟通风格: professional
- 沟通风格: casual
- 请直接修改这些文件
- 这三个文件必须保持一致

### 工作习惯
- 偏好工具: Excel
- 偏好工具: Excel
- 偏好工具: Excel
- 偏好输出格式: structured

## 历史经验

### 需要改进
- 情绪状态: frustrated
- 情绪状态: frustrated
- 情绪状态: frustrated
- 情绪状态: frustrated
- 情绪状态: frustrated
- 情绪状态: stressed
"""

    cleaned, stats = process_memory_text(test_md)

    check(
        f"entries reduced: {stats['entries_before']} -> {stats['entries_after']}",
        stats["entries_after"] < stats["entries_before"],
    )
    check(
        "noise removed ('请直接修改' gone)",
        "请直接修改" not in cleaned,
    )
    check(
        "noise removed ('保持一致' gone)",
        "保持一致" not in cleaned,
    )
    check(
        "duplicates merged (professional appears once)",
        cleaned.count("沟通风格: professional") == 1,
    )
    check(
        "emotion capped (frustrated max 2)",
        cleaned.count("情绪状态: frustrated") <= 2,
    )
    check(
        "unique entries preserved (casual kept)",
        "沟通风格: casual" in cleaned,
    )
    check(
        "unique entries preserved (structured kept)",
        "偏好输出格式: structured" in cleaned,
    )


# ============================================================
# Test 5: Fusion search — weighted scoring + Jaccard dedup
# ============================================================
def test_fusion_search():
    print("\n=== Test 5: Fusion search logic ===")
    from core.memory.instance_memory import InstanceMemoryManager

    # Check weight constants exist
    check(
        "FTS5 weight defined",
        hasattr(InstanceMemoryManager, "_WEIGHT_FTS5"),
    )
    check(
        "Mem0 weight defined",
        hasattr(InstanceMemoryManager, "_WEIGHT_MEM0"),
    )
    check(
        "Mem0 weight > FTS5 weight (semantic boost)",
        InstanceMemoryManager._WEIGHT_MEM0 > InstanceMemoryManager._WEIGHT_FTS5,
    )

    # Test Jaccard similarity
    sim = InstanceMemoryManager._jaccard_similarity("hello world", "hello world")
    check(f"Jaccard identical = {sim:.2f} == 1.0", abs(sim - 1.0) < 0.01)

    sim = InstanceMemoryManager._jaccard_similarity("abc", "xyz")
    check(f"Jaccard disjoint = {sim:.2f} == 0.0", abs(sim) < 0.01)

    sim = InstanceMemoryManager._jaccard_similarity(
        "偏好工具: Excel", "偏好工具: Excel 分析"
    )
    check(f"Jaccard similar = {sim:.2f} > 0.5", sim > 0.5)

    # Test dedup logic
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = InstanceMemoryManager(
            base_dir=Path(tmpdir), user_id="test", mem0_enabled=False
        )
        results = [
            {"content": "偏好工具: Excel", "score": 0.9, "source": "fts5", "category": "preference"},
            {"content": "偏好工具: Excel", "score": 0.8, "source": "mem0", "category": "preference"},
            {"content": "沟通风格: professional", "score": 0.7, "source": "fts5", "category": "style"},
        ]
        deduped = mgr._deduplicate_results(results)
        check(
            f"Jaccard dedup: 3 -> {len(deduped)} (removed exact dup)",
            len(deduped) == 2,
        )
        # The higher-scored entry should win
        excel_entry = [r for r in deduped if "Excel" in r["content"]][0]
        check(
            f"higher score wins: {excel_entry['score']}",
            excel_entry["score"] == 0.9,
        )


# ============================================================
# Test 6: remember_batch exists and flush uses it
# ============================================================
def test_remember_batch():
    print("\n=== Test 6: remember_batch + flush integration ===")
    import inspect

    from core.memory.instance_memory import InstanceMemoryManager

    check(
        "remember_batch() method exists",
        hasattr(InstanceMemoryManager, "remember_batch"),
    )

    flush_source = inspect.getsource(InstanceMemoryManager.flush)
    check(
        "flush() calls remember_batch",
        "remember_batch" in flush_source,
    )


# ============================================================
# Test 7: Embedding warmup method exists
# ============================================================
def test_embedding_warmup():
    print("\n=== Test 7: Embedding warmup ===")
    from core.knowledge.embeddings import GGUFEmbeddingProvider

    check(
        "GGUFEmbeddingProvider has warmup() method",
        hasattr(GGUFEmbeddingProvider, "warmup"),
    )

    import inspect
    warmup_source = inspect.getsource(GGUFEmbeddingProvider.warmup)
    check(
        "warmup() calls _ensure_model()",
        "_ensure_model" in warmup_source,
    )

    # Check main.py has warmup call
    main_py = (ROOT / "main.py").read_text()
    check(
        "main.py calls _warmup_embedding_model()",
        "_warmup_embedding_model" in main_py,
    )


# ============================================================
# Test 8: Health check endpoint registered
# ============================================================
def test_health_endpoint():
    print("\n=== Test 8: Memory health check endpoint ===")
    from routers.settings import router

    # APIRouter stores routes without prefix; look for the suffix
    route_paths = [getattr(r, "path", "") for r in router.routes]
    found = any("/memory/health" in p for p in route_paths)
    check(
        "/memory/health route registered",
        found,
        f"routes: {route_paths}" if not found else "",
    )


# ============================================================
# Test 9: Full remember() + recall() round-trip (no LLM needed)
# ============================================================
async def test_round_trip():
    print("\n=== Test 9: remember() + recall() round-trip ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        from core.memory.instance_memory import InstanceMemoryManager

        mgr = InstanceMemoryManager(
            base_dir=Path(tmpdir), user_id="test_roundtrip", mem0_enabled=False
        )

        # Write some memories
        await mgr.remember("用户偏好 Python 编程", "preference")
        await mgr.remember("常用工具: VS Code", "tool")
        await mgr.remember("沟通风格: professional", "style")

        # Ephemeral should be filtered
        await mgr.remember("请直接修改这些文件", "preference")

        # Check MEMORY.md content
        ctx = await mgr.get_memory_context()
        check("Python 偏好写入 MEMORY.md", "Python" in ctx)
        check("VS Code 写入 MEMORY.md", "VS Code" in ctx)
        check("professional 写入 MEMORY.md", "professional" in ctx)
        check("临时指令被过滤", "请直接修改" not in ctx)

        # FTS5 recall
        results = await mgr.recall("Python 编程")
        check(
            f"recall('Python') returns {len(results)} results",
            len(results) > 0,
        )
        contents = [r["content"] for r in results]
        check(
            "recall result contains Python",
            any("Python" in c for c in contents),
        )


# ============================================================
# Test 10: Batch writes via remember_batch()
# ============================================================
async def test_batch_writes():
    print("\n=== Test 10: Batch writes ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        from core.memory.instance_memory import InstanceMemoryManager

        mgr = InstanceMemoryManager(
            base_dir=Path(tmpdir), user_id="test_batch", mem0_enabled=False
        )

        # Write 20 memories via batch (sequential internally, safe)
        batch = [
            {"content": f"测试记忆条目 #{i}", "category": "fact"}
            for i in range(20)
        ]
        await mgr.remember_batch(batch)

        # Verify all written
        ctx = await mgr.get_memory_context()
        written_count = sum(1 for i in range(20) if f"#{i}" in ctx)
        check(
            f"batch writes: {written_count}/20 succeeded",
            written_count == 20,
        )


# ============================================================
# Main
# ============================================================
async def async_main():
    await test_round_trip()
    await test_batch_writes()


def main():
    print("=" * 60)
    print("Memory Optimization E2E Verification")
    print("=" * 60)

    # Sync tests
    test_write_lock()
    test_mem0_add_returns_bool()
    test_ephemeral_filter()
    test_dedup_script()
    test_fusion_search()
    test_remember_batch()
    test_embedding_warmup()
    test_health_endpoint()

    # Async tests
    asyncio.run(async_main())

    # Summary
    total = passed + failed
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll checks passed.")


if __name__ == "__main__":
    main()
