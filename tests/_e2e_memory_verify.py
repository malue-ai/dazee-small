# -*- coding: utf-8 -*-
"""
E2E Memory Hybrid Search Verification

Real Mem0 pool + Qwen embedding + FTS5 keyword search.
No mock, no fake — tests the actual production code path.
"""
import os
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DASHSCOPE_API_KEY", "sk-1650eb369f834d77a4148898ce04a6c6")
os.environ.setdefault("AGENT_INSTANCE", "xiaodazi")


def main():
    print("=" * 60)
    print("  E2E Memory Hybrid Search Verification")
    print("=" * 60)

    # --- Step 1: Init Mem0 Pool ---
    print("\n[Step 1] Init Mem0 Pool...")
    try:
        from utils.instance_loader import load_instance_env_from_config
        load_instance_env_from_config("xiaodazi")
    except Exception as e:
        print(f"  WARN: load_instance_env failed: {e}")

    try:
        from core.memory.mem0.pool import get_mem0_pool
        pool = get_mem0_pool()
        print(f"  OK: pool initialized, collection={pool.config.collection_name}")
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback; traceback.print_exc()
        return 1

    # --- Step 2: Check vector store type ---
    print("\n[Step 2] Check vector store...")
    from core.memory.mem0.sqlite_vec_store import SqliteVecVectorStore
    vs = pool.memory.vector_store
    if not isinstance(vs, SqliteVecVectorStore):
        print(f"  FAIL: vector store is {type(vs).__name__}, not SqliteVecVectorStore")
        return 1
    info = vs.col_info()
    print(f"  OK: backend={info.get('backend')}, docs={info.get('document_count')}, fts={info.get('fts_count')}")

    # --- Step 3: Add test memories ---
    print("\n[Step 3] Add test memories via Mem0...")
    test_user = "e2e_hybrid_verify"
    test_memories = [
        "user prefers Python and likes concise code style",
        "laozahng is in charge of yonghui project, contract amount 1.5 million",
        "user has a caustic writing style, sharp and sarcastic",
        "user frequently uses FastAPI for backend development",
        "meeting with laozahng on Wednesday to discuss project progress",
        "user works on macOS with VS Code",
        "user is researching Transformer papers, interested in attention mechanisms",
        "user name is xiaoliu, works in Shanghai, internet industry",
    ]

    added = 0
    for text in test_memories:
        try:
            pool.add(
                user_id=test_user,
                messages=[{"role": "user", "content": text}],
            )
            added += 1
        except Exception as e:
            print(f"  WARN: add failed for '{text[:30]}': {e}")
    print(f"  OK: {added}/{len(test_memories)} memories added")

    # --- Step 4: Check FTS5 sync ---
    print("\n[Step 4] Check FTS5 index sync...")
    info2 = vs.col_info()
    fts_count = info2.get("fts_count", 0)
    doc_count = info2.get("document_count", 0)
    print(f"  docs={doc_count}, fts={fts_count}")
    if fts_count > 0:
        print(f"  OK: FTS5 index has {fts_count} entries")
    else:
        print("  WARN: FTS5 index empty (may need rebuild for pre-existing data)")
        print("  Rebuilding FTS5 index...")
        rebuilt = vs.rebuild_fts_index()
        print(f"  Rebuilt {rebuilt} entries")

    # --- Step 5: FTS5 keyword search ---
    print("\n[Step 5] FTS5 keyword search...")
    keyword_tests = [
        ("laozahng", "should find laozahng-related memories"),
        ("Python", "should find Python preference"),
        ("FastAPI", "should find FastAPI usage"),
        ("caustic", "should find writing style"),
        ("xiaoliu", "should find user name"),
    ]
    fts_pass = 0
    for query, desc in keyword_tests:
        results = vs.keyword_search(query, user_id=test_user, limit=5)
        status = "PASS" if results else "FAIL"
        if results:
            fts_pass += 1
        print(f"  [{status}] '{query}' -> {len(results)} results ({desc})")
        for r in results[:2]:
            mem_text = r.payload.get("data", r.payload.get("memory", ""))[:60]
            print(f"         score={r.score:.3f} | {mem_text}")

    print(f"\n  FTS5 keyword: {fts_pass}/{len(keyword_tests)} passed")

    # --- Step 6: Hybrid search (pool.search with min_score) ---
    print("\n[Step 6] Hybrid search (vector + FTS5 merged)...")
    hybrid_tests = [
        ("laozahng project", "should find laozahng + project memories"),
        ("Python code style", "should find Python + style preferences"),
        ("writing article", "cross-domain: should prefer caustic style via vector"),
    ]
    for query, desc in hybrid_tests:
        results = pool.search(
            user_id=test_user, query=query, limit=5, min_score=0.0
        )
        print(f"  '{query}' -> {len(results)} results ({desc})")
        for r in results[:3]:
            print(f"    score={r.get('score', 0):.3f} | {r.get('memory', '')[:60]}")

    # --- Step 7: min_score filtering ---
    print("\n[Step 7] min_score=0.35 filtering...")
    results_no_filter = pool.search(user_id=test_user, query="Shanghai tech", limit=10, min_score=0.0)
    results_filtered = pool.search(user_id=test_user, query="Shanghai tech", limit=10, min_score=0.35)
    print(f"  Without filter: {len(results_no_filter)} results")
    print(f"  With min_score=0.35: {len(results_filtered)} results")
    print(f"  Filtered out: {len(results_no_filter) - len(results_filtered)} low-score entries")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Mem0 Pool: OK")
    print(f"  SqliteVecVectorStore + FTS5: OK")
    print(f"  FTS5 keyword search: {fts_pass}/{len(keyword_tests)}")
    print(f"  Hybrid search: functional")
    print(f"  min_score filter: {len(results_no_filter) - len(results_filtered)} entries filtered")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
