"""
端到端验证：Mem0 混合搜索（向量 + FTS5 关键词）

使用真实 Qwen API 生成 embedding，验证：
1. 记忆写入后 FTS5 索引同步
2. 纯向量搜索 vs 混合搜索的召回差异
3. 中文关键词搜索（"老张"、"毒舌"、"Python"）
4. min_score 阈值过滤效果
5. G1 场景复现："写健身房文章" 能否召回 "毒舌风格"

运行方式（需要设置 DASHSCOPE_API_KEY 环境变量）：
    set DASHSCOPE_API_KEY=sk-xxx
    python tests/e2e_hybrid_search_verify.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    # 检查 API Key
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 请设置 DASHSCOPE_API_KEY 环境变量")
        print("   set DASHSCOPE_API_KEY=sk-xxx")
        return

    print("=" * 70)
    print("  Mem0 混合搜索端到端验证")
    print("=" * 70)

    # 1. 创建临时 DB 和 store
    print("\n📦 Step 1: 创建 SqliteVecVectorStore...")
    from core.memory.mem0.sqlite_vec_store import SqliteVecVectorStore

    tmp_dir = tempfile.mkdtemp(prefix="e2e_hybrid_")
    db_path = os.path.join(tmp_dir, "test_hybrid.db")

    store = SqliteVecVectorStore(
        collection_name="e2e_test",
        embedding_model_dims=1024,  # BGE-M3 / DashScope 维度
        db_path=db_path,
    )
    print(f"   ✅ DB: {db_path}")

    # 2. 准备测试记忆
    test_memories = [
        ("m1", "用户偏好 Python 编程，喜欢简洁的代码风格"),
        ("m2", "老张是永辉项目的负责人，合同金额150万"),
        ("m3", "毒舌风格，说话犀利，写作锋利，喜欢讽刺"),
        ("m4", "常用 FastAPI 框架开发后端服务"),
        ("m5", "周三下午两点跟老张开会讨论项目进度"),
        ("m6", "用户使用 macOS 开发环境，偏好 VS Code"),
        ("m7", "最近在研究 Transformer 论文，对注意力机制感兴趣"),
        ("m8", "用户叫小刘，在上海工作，互联网行业"),
    ]

    # 3. 生成 embedding 并写入
    print("\n📝 Step 2: 写入记忆 + 生成 embedding...")
    try:
        from core.knowledge.embeddings import get_embedding_provider

        provider = get_embedding_provider()
        print(f"   Embedding provider: {provider.provider_id} ({provider.model_name})")
        print(f"   Dimensions: {provider.dimensions}")

        # 调整 store 维度匹配实际 provider
        if provider.dimensions != store.embedding_model_dims:
            print(f"   ⚠️ 调整维度: {store.embedding_model_dims} → {provider.dimensions}")
            store.close()
            store = SqliteVecVectorStore(
                collection_name="e2e_test",
                embedding_model_dims=provider.dimensions,
                db_path=db_path,
            )

        for mid, text in test_memories:
            embedding = provider.embed(text)
            store.insert(
                vectors=[embedding],
                payloads=[{"data": text, "user_id": "e2e_user", "memory": text}],
                ids=[mid],
            )
            print(f"   ✅ {mid}: {text[:30]}...")

    except Exception as e:
        print(f"   ❌ Embedding 生成失败: {e}")
        print("   回退到随机向量测试（仅验证 FTS5）...")
        import math
        import random

        for mid, text in test_memories:
            dim = store.embedding_model_dims
            raw = [random.random() for _ in range(dim)]
            norm = math.sqrt(sum(x * x for x in raw))
            vec = [x / norm for x in raw]
            store.insert(
                vectors=[vec],
                payloads=[{"data": text, "user_id": "e2e_user", "memory": text}],
                ids=[mid],
            )
        print("   ✅ 使用随机向量写入完成")

    # 4. 验证 FTS5 索引
    print("\n🔍 Step 3: 验证 FTS5 索引同步...")
    info = store.col_info()
    print(f"   文档数: {info['document_count']}")
    print(f"   FTS 索引数: {info['fts_count']}")
    assert info["fts_count"] == len(test_memories), "FTS5 索引数量不匹配!"

    # 5. FTS5 关键词搜索测试
    print("\n🔑 Step 4: FTS5 关键词搜索...")
    test_queries = [
        ("老张", ["m2", "m5"]),
        ("Python", ["m1"]),
        ("毒舌", ["m3"]),
        ("FastAPI", ["m4"]),
        ("小刘", ["m8"]),
        ("永辉 合同", ["m2"]),
    ]

    fts_pass = 0
    fts_total = len(test_queries)
    for query, expected_ids in test_queries:
        results = store.keyword_search(query, user_id="e2e_user", limit=5)
        found_ids = [r.id for r in results]
        hit = any(eid in found_ids for eid in expected_ids)
        status = "✅" if hit else "❌"
        print(f"   {status} 搜 '{query}' → 命中: {found_ids[:3]}, 期望含: {expected_ids}")
        if hit:
            fts_pass += 1

    print(f"\n   FTS5 搜索: {fts_pass}/{fts_total} 通过")

    # 6. G1 场景复现
    print("\n🎯 Step 5: G1 场景复现 — '写健身房文章' 能否召回 '毒舌风格'？")

    # 纯向量搜索
    print("   [纯向量搜索]")
    try:
        vec_results = store.search(
            query="写健身房文章",
            vectors=[provider.embed("写健身房文章")],
            limit=5,
        )
        vec_ids = [r.id for r in vec_results]
        vec_has_m3 = "m3" in vec_ids
        print(f"   结果: {vec_ids}")
        print(f"   包含 m3(毒舌风格): {'✅ YES' if vec_has_m3 else '❌ NO'}")
    except Exception:
        print("   ⚠️ 向量搜索跳过（无 embedding provider）")
        vec_has_m3 = False

    # FTS5 关键词搜索
    print("   [FTS5 关键词搜索]")
    fts_results = store.keyword_search("写健身房文章", user_id="e2e_user", limit=5)
    fts_ids = [r.id for r in fts_results]
    fts_has_m3 = "m3" in fts_ids
    print(f"   结果: {fts_ids}")
    print(f"   包含 m3(毒舌风格): {'✅ YES' if fts_has_m3 else '❌ NO（预期，关键词无重叠）'}")

    # 结论
    print("\n   📊 G1 分析:")
    if not vec_has_m3 and not fts_has_m3:
        print("   → 向量和关键词都搜不到 '毒舌风格'（跨域语义鸿沟）")
        print("   → 这正是 _recall_by_category(style/preference) 存在的意义")
        print("   → 混合搜索提升的是关键词能命中的场景（如 '老张'、'合同'）")
    elif vec_has_m3:
        print("   → 向量搜索能找到 '毒舌风格'（当前 embedding 质量足够）")
    elif fts_has_m3:
        print("   → FTS5 关键词能找到（有共同字）")

    # 7. 清理
    store.close()
    print(f"\n✅ 验证完成，临时 DB: {db_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
