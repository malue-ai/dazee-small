"""
sqlite-vec NullPool 修复验证脚本

验证目标：NullPool 下，每次数据库操作都能正确加载 sqlite-vec 扩展。
复现场景：知识库向量搜索报 "no such module: vec0"

测试矩阵：
  1. 引擎初始化 + 扩展探测
  2. 向量表创建（第 1 个连接）
  3. 向量写入（第 2 个连接）
  4. 向量搜索（第 3 个连接）← 之前失败的操作
  5. 连续 5 次独立搜索（验证每次新连接都能用 vec0）
  6. _load_vec_on_connect 适配器拆包验证

用法：
  cd zenflux_agent
  python scripts/verify_vec_fix.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIMENSIONS = 4
TEST_TABLE = "_vec_fix_verify"


async def main():
    results = []

    def record(name: str, passed: bool, detail: str = ""):
        status = "PASS" if passed else "FAIL"
        results.append((name, passed, detail))
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    print("=" * 60)
    print("sqlite-vec NullPool 修复验证")
    print("=" * 60)

    # ── Step 0: 检查 sqlite-vec 是否已安装 ──
    print("\n[Step 0] 检查 sqlite-vec 依赖")
    try:
        import sqlite_vec
        vec_path = sqlite_vec.loadable_path()
        record("sqlite-vec 已安装", True, f"path={vec_path}")
    except ImportError:
        record("sqlite-vec 已安装", False, "未安装，pip install sqlite-vec")
        print("\n⚠ sqlite-vec 未安装，无法继续验证。")
        return 1

    # ── Step 1: 引擎初始化 + 扩展探测 ──
    print("\n[Step 1] 引擎初始化 + 扩展探测")
    import infra.local_store.engine as engine_mod
    from infra.local_store.engine import get_local_engine, is_vec_available

    engine = await get_local_engine()
    record("引擎初始化", engine is not None)
    record("is_vec_available()", is_vec_available())
    vec_path = engine_mod._vec_loadable_path
    record(
        "_vec_loadable_path 已设置",
        vec_path is not None,
        f"path={vec_path}",
    )

    if not is_vec_available():
        print("\n⚠ sqlite-vec 探测失败，检查 init_vector_extension 日志。")
        return 1

    # ── Step 2: 向量表创建（连接 A） ──
    print("\n[Step 2] 向量表创建（连接 A）")
    from infra.local_store.vector import (
        create_vector_table,
        upsert_vector,
        search_vectors,
        delete_vector,
        count_vectors,
    )

    ok = await create_vector_table(engine, table_name=TEST_TABLE, dimensions=DIMENSIONS)
    record("CREATE VIRTUAL TABLE", ok)

    # ── Step 3: 向量写入（连接 B — NullPool 新连接） ──
    print("\n[Step 3] 向量写入（连接 B）")
    from infra.local_store.engine import get_local_session

    test_vectors = [
        ("doc-1", [1.0, 0.0, 0.0, 0.0], {"title": "Python 教程"}),
        ("doc-2", [0.0, 1.0, 0.0, 0.0], {"title": "Rust 指南"}),
        ("doc-3", [0.0, 0.0, 1.0, 0.0], {"title": "Go 入门"}),
    ]

    try:
        async for session in get_local_session():
            for vid, emb, meta in test_vectors:
                await upsert_vector(
                    session, TEST_TABLE, vid, emb, json.dumps(meta, ensure_ascii=False)
                )
            await session.commit()
        record("INSERT 3 条向量", True)
    except Exception as e:
        record("INSERT 3 条向量", False, str(e))

    # ── Step 4: 向量搜索（连接 C — 复现原始错误） ──
    print("\n[Step 4] 向量搜索（连接 C — 复现原始错误路径）")
    try:
        async for session in get_local_session():
            hits = await search_vectors(
                session, TEST_TABLE, [0.9, 0.1, 0.0, 0.0], limit=3
            )
            found = len(hits)
            record(
                "SELECT ... WHERE embedding MATCH",
                found > 0,
                f"返回 {found} 条，最近: {hits[0].id if hits else 'N/A'}",
            )
            if hits:
                record(
                    "最近邻正确性",
                    hits[0].id == "doc-1",
                    f"期望 doc-1，实际 {hits[0].id}",
                )
    except Exception as e:
        record("SELECT ... WHERE embedding MATCH", False, str(e))

    # ── Step 5: 连续 5 次独立搜索（验证 NullPool 每次都行） ──
    print("\n[Step 5] 连续 5 次独立搜索（每次 NullPool 新连接）")
    success_count = 0
    for i in range(5):
        try:
            async for session in get_local_session():
                hits = await search_vectors(
                    session, TEST_TABLE, [0.0, 0.0, 0.9, 0.1], limit=1
                )
                if hits:
                    success_count += 1
        except Exception:
            pass
    record(
        f"5 次连续搜索",
        success_count == 5,
        f"{success_count}/5 成功",
    )

    # ── Step 6: _load_vec_on_connect 适配器拆包验证 ──
    print("\n[Step 6] _load_vec_on_connect 适配器拆包验证")
    from infra.local_store.engine import _load_vec_on_connect

    try:
        async for session in get_local_session():
            conn = await session.connection()
            raw = await conn.get_raw_connection()
            dbapi_conn = raw.dbapi_connection

            aio = getattr(dbapi_conn, "_connection", None)
            record("dbapi_conn._connection 可访问", aio is not None, f"type={type(aio).__name__}")

            if aio:
                raw_sqlite3 = getattr(aio, "_conn", None)
                record(
                    "aiosqlite._conn 可访问",
                    raw_sqlite3 is not None,
                    f"type={type(raw_sqlite3).__name__}" if raw_sqlite3 else "",
                )
                has_method = hasattr(raw_sqlite3, "enable_load_extension")
                record("sqlite3.Connection.enable_load_extension 存在", has_method)
    except Exception as e:
        record("适配器拆包", False, str(e))

    # ── Step 7: count 验证 ──
    print("\n[Step 7] count 验证")
    try:
        async for session in get_local_session():
            cnt = await count_vectors(session, TEST_TABLE)
            record("COUNT(*)", cnt == 3, f"期望 3，实际 {cnt}")
    except Exception as e:
        record("COUNT(*)", False, str(e))

    # ── Cleanup ──
    print("\n[Cleanup] 清理测试表")
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {TEST_TABLE}"))
        record("DROP TABLE", True)
    except Exception as e:
        record("DROP TABLE", False, str(e))

    # ── Summary ──
    total = len(results)
    passed = sum(1 for _, p, _ in results if p)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"结果: {passed}/{total} 通过", end="")
    if failed:
        print(f", {failed} 失败:")
        for name, p, detail in results:
            if not p:
                print(f"  ✗ {name}: {detail}")
    else:
        print(" ✓ 全部通过")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
