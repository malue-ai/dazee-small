"""
SqliteVecVectorStore FTS5 集成测试（真实 SQLite 文件）

使用真实 sqlite-vec + FTS5，不依赖 mock。
重点验证：
1. FTS5 表创建和同步
2. insert/update/delete 正确维护 FTS5 索引
3. keyword_search BM25 搜索
4. rebuild_fts_index 索引重建
5. 多线程并发写入不死锁
6. 多线程读写混合不死锁
7. FTS5 搜索 + 向量搜索独立性（FTS5 挂了不影响向量）

Run:
    python -m pytest tests/test_sqlite_vec_fts5_integration.py -v
"""

import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.memory.mem0.sqlite_vec_store import SqliteVecVectorStore


@pytest.fixture
def store(tmp_path):
    """创建临时 SqliteVecVectorStore 实例。"""
    db_path = str(tmp_path / "test_mem0.db")
    s = SqliteVecVectorStore(
        collection_name="test_memories",
        embedding_model_dims=4,  # 使用小维度加速测试
        db_path=db_path,
    )
    yield s
    s.close()


def _make_vector(dim=4, seed=0.1):
    """生成测试用向量（L2 归一化）"""
    import math
    raw = [seed + i * 0.1 for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


# ======================================================================
# 1. FTS5 表创建
# ======================================================================

class TestFtsTableCreation:
    """验证 FTS5 表在初始化时被正确创建。"""

    def test_fts_table_exists(self, store):
        """FTS5 虚拟表应在初始化后存在。"""
        cursor = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE name = ?",
            (store._fts_table_name,),
        )
        row = cursor.fetchone()
        assert row is not None, f"FTS5 表 {store._fts_table_name} 不存在"

    def test_fts_table_name_correct(self, store):
        """FTS5 表名应为 collection_name + '_fts'。"""
        assert store._fts_table_name == "test_memories_fts"


# ======================================================================
# 2. insert → FTS5 同步
# ======================================================================

class TestInsertFtsSync:
    """验证 insert 操作同步写入 FTS5。"""

    def test_insert_syncs_to_fts(self, store):
        """insert 后 FTS5 表应有对应条目。"""
        payload = {"data": "用户偏好 Python 编程", "user_id": "u1"}
        store.insert(
            vectors=[_make_vector()],
            payloads=[payload],
            ids=["mem_001"],
        )

        cursor = store._conn.execute(
            f"SELECT id, memory, user_id FROM [{store._fts_table_name}]"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "mem_001"
        assert "Python" in rows[0][1]
        assert rows[0][2] == "u1"

    def test_insert_multiple(self, store):
        """批量 insert 后 FTS5 条目数正确。"""
        payloads = [
            {"data": f"记忆内容 {i}", "user_id": "u1"}
            for i in range(5)
        ]
        vectors = [_make_vector(seed=0.1 * i) for i in range(5)]
        ids = [f"mem_{i:03d}" for i in range(5)]

        store.insert(vectors=vectors, payloads=payloads, ids=ids)

        cursor = store._conn.execute(
            f"SELECT COUNT(*) FROM [{store._fts_table_name}]"
        )
        assert cursor.fetchone()[0] == 5

    def test_insert_idempotent_upsert(self, store):
        """重复 insert 同一 id 不应产生重复的 FTS5 条目。"""
        payload = {"data": "版本1", "user_id": "u1"}
        store.insert(
            vectors=[_make_vector()], payloads=[payload], ids=["mem_dup"]
        )
        # 重复插入（更新内容）
        payload2 = {"data": "版本2", "user_id": "u1"}
        store.insert(
            vectors=[_make_vector(seed=0.2)], payloads=[payload2], ids=["mem_dup"]
        )

        cursor = store._conn.execute(
            f"SELECT COUNT(*) FROM [{store._fts_table_name}] WHERE id = 'mem_dup'"
        )
        assert cursor.fetchone()[0] == 1

        # 通过 keyword_search 验证能搜到最新内容
        results = store.keyword_search("版本2", user_id="u1", limit=5)
        assert any(r.id == "mem_dup" for r in results)

    def test_insert_empty_memory_skipped(self, store):
        """空 memory 不应写入 FTS5。"""
        payload = {"data": "", "user_id": "u1"}
        store.insert(
            vectors=[_make_vector()], payloads=[payload], ids=["mem_empty"]
        )

        cursor = store._conn.execute(
            f"SELECT COUNT(*) FROM [{store._fts_table_name}]"
        )
        assert cursor.fetchone()[0] == 0


# ======================================================================
# 3. update → FTS5 同步
# ======================================================================

class TestUpdateFtsSync:
    """验证 update 操作同步更新 FTS5。"""

    def test_update_payload_syncs_fts(self, store):
        """update payload 后 FTS5 内容应更新。"""
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "旧内容", "user_id": "u1"}],
            ids=["mem_upd"],
        )
        store.update(
            vector_id="mem_upd",
            payload={"data": "新内容全新", "user_id": "u1"},
        )

        # 通过 keyword_search 验证更新后能搜到新内容中的特有词
        # 使用新内容独有的"全新"来验证更新生效
        results = store.keyword_search("全新", user_id="u1", limit=5)
        assert any(r.id == "mem_upd" for r in results)

    def test_update_vector_only_no_fts_change(self, store):
        """只 update 向量不传 payload 时 FTS5 不变。"""
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "原始内容", "user_id": "u1"}],
            ids=["mem_vec"],
        )
        store.update(
            vector_id="mem_vec",
            vector=_make_vector(seed=0.5),  # 只更新向量
        )

        # 通过 keyword_search 验证原始内容仍可搜到
        results = store.keyword_search("原始内容", user_id="u1", limit=5)
        assert any(r.id == "mem_vec" for r in results)


# ======================================================================
# 4. delete → FTS5 同步
# ======================================================================

class TestDeleteFtsSync:
    """验证 delete 操作同步删除 FTS5。"""

    def test_delete_removes_fts_entry(self, store):
        """delete 后 FTS5 条目应被移除。"""
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "待删除", "user_id": "u1"}],
            ids=["mem_del"],
        )
        store.delete("mem_del")

        cursor = store._conn.execute(
            f"SELECT COUNT(*) FROM [{store._fts_table_name}] WHERE id = 'mem_del'"
        )
        assert cursor.fetchone()[0] == 0

    def test_delete_nonexistent_no_error(self, store):
        """删除不存在的 id 不应报错。"""
        store.delete("nonexistent_id")  # Should not raise


# ======================================================================
# 5. keyword_search
# ======================================================================

class TestKeywordSearch:
    """验证 FTS5 关键词搜索。"""

    def _seed_memories(self, store):
        """填充测试数据。"""
        memories = [
            ("m1", "用户偏好 Python 编程，喜欢简洁代码风格"),
            ("m2", "老张是永辉项目的负责人，合同金额150万"),
            ("m3", "毒舌风格，说话犀利，写作锋利"),
            ("m4", "常用 FastAPI 框架开发后端服务"),
            ("m5", "周三下午两点跟老张开会讨论项目进度"),
        ]
        for mid, text in memories:
            store.insert(
                vectors=[_make_vector(seed=hash(mid) % 100 * 0.01)],
                payloads=[{"data": text, "user_id": "u1"}],
                ids=[mid],
            )

    def test_exact_keyword_match(self, store):
        """精确关键词搜索应命中。"""
        self._seed_memories(store)
        results = store.keyword_search("老张", user_id="u1", limit=5)
        ids = [r.id for r in results]
        assert "m2" in ids or "m5" in ids  # 两条都含"老张"

    def test_phrase_match(self, store):
        """短语搜索应命中。"""
        self._seed_memories(store)
        results = store.keyword_search("Python 编程", user_id="u1", limit=5)
        assert any(r.id == "m1" for r in results)

    def test_no_match_returns_empty(self, store):
        """无匹配时返回空列表。"""
        self._seed_memories(store)
        results = store.keyword_search("量子计算", user_id="u1", limit=5)
        assert results == []

    def test_user_id_filter(self, store):
        """不同 user_id 的记忆不应被搜到。"""
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "用户A的Python记忆", "user_id": "userA"}],
            ids=["ma"],
        )
        store.insert(
            vectors=[_make_vector(seed=0.5)],
            payloads=[{"data": "用户B的Python记忆", "user_id": "userB"}],
            ids=["mb"],
        )
        results = store.keyword_search("Python", user_id="userA", limit=5)
        ids = [r.id for r in results]
        assert "ma" in ids
        assert "mb" not in ids

    def test_score_is_normalized(self, store):
        """返回的 score 应在 [0, 1] 范围内。"""
        self._seed_memories(store)
        results = store.keyword_search("Python", user_id="u1", limit=5)
        for r in results:
            assert 0.0 <= r.score <= 1.0

    def test_empty_query_returns_empty(self, store):
        """空查询返回空列表。"""
        self._seed_memories(store)
        results = store.keyword_search("", user_id="u1", limit=5)
        assert results == []

    def test_fallback_to_or_search(self, store):
        """短语搜索无结果时回退到逐词 OR 搜索。"""
        self._seed_memories(store)
        # "毒舌 Python" 作为短语不存在，但逐词 OR 应该能匹配
        results = store.keyword_search("毒舌 Python", user_id="u1", limit=5)
        ids = [r.id for r in results]
        # 应该能找到 m3 (毒舌) 或 m1 (Python)
        assert len(ids) > 0


# ======================================================================
# 6. rebuild_fts_index
# ======================================================================

class TestRebuildFtsIndex:
    """验证 FTS5 索引重建。"""

    def test_rebuild_from_meta(self, store):
        """从 _meta 表重建 FTS5 索引。"""
        # 直接往 _meta 表插数据（模拟旧数据没有 FTS5 索引的情况）
        store._conn.execute(
            f"INSERT OR REPLACE INTO [{store.collection_name}_meta](id, payload) "
            f"VALUES (?, ?)",
            ("legacy_1", json.dumps({"data": "旧记忆没有FTS索引", "user_id": "u1"})),
        )
        store._conn.execute(
            f"INSERT OR REPLACE INTO [{store.collection_name}_meta](id, payload) "
            f"VALUES (?, ?)",
            ("legacy_2", json.dumps({"data": "另一条旧记忆", "user_id": "u1"})),
        )
        store._conn.commit()

        count = store.rebuild_fts_index()
        assert count == 2

        # 重建后应该能搜到
        results = store.keyword_search("旧记忆", user_id="u1", limit=5)
        assert len(results) > 0

    def test_rebuild_clears_old_index(self, store):
        """重建前清空旧索引。"""
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "正常插入", "user_id": "u1"}],
            ids=["normal"],
        )
        # 手动往 FTS5 插垃圾数据
        store._conn.execute(
            f"INSERT INTO [{store._fts_table_name}](id, memory, user_id) "
            f"VALUES ('ghost', '幽灵数据', 'u1')"
        )
        store._conn.commit()

        store.rebuild_fts_index()

        # 幽灵数据应被清除（因为 _meta 表里没有它）
        results = store.keyword_search("幽灵数据", user_id="u1", limit=5)
        assert len(results) == 0

        # 正常数据应还在
        results = store.keyword_search("正常插入", user_id="u1", limit=5)
        assert len(results) > 0


# ======================================================================
# 7. 多线程并发写入不死锁
# ======================================================================

class TestConcurrency:
    """验证多线程安全和无死锁。"""

    def test_concurrent_inserts_no_deadlock(self, store):
        """多线程并发 insert 不应死锁。"""
        errors = []

        def worker(thread_id):
            try:
                for i in range(10):
                    mid = f"t{thread_id}_m{i}"
                    store.insert(
                        vectors=[_make_vector(seed=thread_id * 0.1 + i * 0.01)],
                        payloads=[{"data": f"线程{thread_id}记忆{i}", "user_id": "u1"}],
                        ids=[mid],
                    )
            except Exception as e:
                errors.append((thread_id, e))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"线程出错: {errors}"

        # 验证数据完整性
        cursor = store._conn.execute(
            f"SELECT COUNT(*) FROM [{store.collection_name}_meta]"
        )
        meta_count = cursor.fetchone()[0]
        assert meta_count == 40  # 4 threads * 10 inserts

        cursor = store._conn.execute(
            f"SELECT COUNT(*) FROM [{store._fts_table_name}]"
        )
        fts_count = cursor.fetchone()[0]
        assert fts_count == 40  # FTS5 应完全同步

    def test_concurrent_read_write_no_deadlock(self, store):
        """读写混合并发不应死锁。"""
        # 先写入一些数据
        for i in range(20):
            store.insert(
                vectors=[_make_vector(seed=i * 0.05)],
                payloads=[{"data": f"预置记忆{i}", "user_id": "u1"}],
                ids=[f"pre_{i}"],
            )

        errors = []
        read_results = []

        def writer(thread_id):
            try:
                for i in range(10):
                    mid = f"w{thread_id}_m{i}"
                    store.insert(
                        vectors=[_make_vector(seed=thread_id * 0.1 + i * 0.01)],
                        payloads=[{"data": f"写入{thread_id}_{i}", "user_id": "u1"}],
                        ids=[mid],
                    )
            except Exception as e:
                errors.append(("writer", thread_id, e))

        def reader(thread_id):
            try:
                for _ in range(10):
                    results = store.keyword_search("记忆", user_id="u1", limit=5)
                    read_results.append(len(results))
                    time.sleep(0.01)  # 模拟读间隔
            except Exception as e:
                errors.append(("reader", thread_id, e))

        threads = []
        for t in range(2):
            threads.append(threading.Thread(target=writer, args=(t,)))
        for t in range(2):
            threads.append(threading.Thread(target=reader, args=(t,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"线程出错: {errors}"
        # 读操作应返回结果（不一定每次都有，但不应报错）
        assert len(read_results) > 0

    def test_concurrent_insert_delete_no_deadlock(self, store):
        """并发插入和删除不死锁。"""
        # 先写入数据
        for i in range(20):
            store.insert(
                vectors=[_make_vector(seed=i * 0.05)],
                payloads=[{"data": f"初始数据{i}", "user_id": "u1"}],
                ids=[f"init_{i}"],
            )

        errors = []

        def inserter():
            try:
                for i in range(20):
                    store.insert(
                        vectors=[_make_vector(seed=0.5 + i * 0.01)],
                        payloads=[{"data": f"新增{i}", "user_id": "u1"}],
                        ids=[f"new_{i}"],
                    )
            except Exception as e:
                errors.append(("inserter", e))

        def deleter():
            try:
                for i in range(20):
                    store.delete(f"init_{i}")
            except Exception as e:
                errors.append(("deleter", e))

        t1 = threading.Thread(target=inserter)
        t2 = threading.Thread(target=deleter)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"线程出错: {errors}"


# ======================================================================
# 8. col_info 包含 FTS 统计
# ======================================================================

class TestColInfo:
    """验证 col_info 包含 FTS5 索引信息。"""

    def test_col_info_includes_fts_count(self, store):
        """col_info 应返回 fts_count。"""
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "测试", "user_id": "u1"}],
            ids=["info_test"],
        )
        info = store.col_info()
        assert "fts_count" in info
        assert info["fts_count"] == 1
        assert info["backend"] == "sqlite-vec + fts5"


# ======================================================================
# 9. reset 清理 FTS5
# ======================================================================

class TestReset:
    """验证 reset 清理 FTS5 表。"""

    def test_reset_clears_fts(self, store):
        """reset 后 FTS5 表应被重建（清空）。"""
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "重置前数据", "user_id": "u1"}],
            ids=["rst_test"],
        )
        store.reset()

        cursor = store._conn.execute(
            f"SELECT COUNT(*) FROM [{store._fts_table_name}]"
        )
        assert cursor.fetchone()[0] == 0

        # 重置后应能正常插入
        store.insert(
            vectors=[_make_vector()],
            payloads=[{"data": "重置后数据", "user_id": "u1"}],
            ids=["rst_after"],
        )
        results = store.keyword_search("重置后", user_id="u1", limit=5)
        assert len(results) > 0
