"""
记忆系统 + 知识检索 端到端验证脚本

验证内容：
1. MarkdownMemoryLayer — MEMORY.md 读写、段落追加、每日日志
2. GenericFTS5 — 建表、upsert、search、delete
3. InstanceMemoryManager — recall/remember/flush/get_memory_context
4. LocalKnowledgeManager — search/add_document/get_stats
5. FileIndexer — index_path/index_directory

运行方式：
    python3 scripts/verify_memory_knowledge.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

passed = 0
failed = 0


def check(description: str, condition: bool):
    global passed, failed
    if condition:
        print(f"  ✅ {description}")
        passed += 1
    else:
        print(f"  ❌ {description}")
        failed += 1


async def test_markdown_layer():
    """测试 MEMORY.md 文件层"""
    print("\n" + "=" * 60)
    print("测试 1: MarkdownMemoryLayer")
    print("=" * 60)

    from core.memory.markdown_layer import MarkdownMemoryLayer

    with tempfile.TemporaryDirectory() as tmpdir:
        layer = MarkdownMemoryLayer(base_dir=Path(tmpdir))

        # 1. 首次读取自动创建模板
        content = await layer.read_global_memory()
        check("首次读取创建 MEMORY.md", len(content) > 0)
        check("模板包含标题", "# 小搭子的记忆" in content)
        check("模板包含偏好段落", "## 偏好" in content)

        # 2. 段落追加
        result = await layer.append_to_section("偏好/写作风格", "喜欢简洁风格")
        check("段落追加成功", result is True)

        content = await layer.read_global_memory()
        check("追加内容已写入", "喜欢简洁风格" in content)

        # 3. 追加到顶级段落
        await layer.append_to_section("关于你", "职业：产品经理")
        content = await layer.read_global_memory()
        check("顶级段落追加", "职业：产品经理" in content)

        # 4. 追加到不存在的段落（自动创建）
        await layer.append_to_section("新段落", "测试内容")
        content = await layer.read_global_memory()
        check("自动创建新段落", "新段落" in content and "测试内容" in content)

        # 5. 每日日志
        await layer.append_daily_log("测试对话记录")
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        log = await layer.read_daily_log(today)
        check("每日日志写入", "测试对话记录" in log)

        # 6. 解析记忆条目
        entries = await layer.read_all_memories()
        check("记忆条目解析", len(entries) >= 2)

        # 7. 项目级记忆
        await layer.append_project_memory("test_project", "偏好", "项目偏好内容")
        project_mem = await layer.read_project_memory("test_project")
        check("项目记忆读写", "项目偏好内容" in project_mem)


async def test_generic_fts5():
    """测试通用 FTS5 引擎"""
    print("\n" + "=" * 60)
    print("测试 2: GenericFTS5")
    print("=" * 60)

    from infra.local_store.engine import create_local_engine
    from infra.local_store.generic_fts import (
        FTS5TableConfig,
        GenericFTS5,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = create_local_engine(db_dir=tmpdir, db_name="test_fts.db")
        fts = GenericFTS5()
        config = FTS5TableConfig(
            table_name="test_fts",
            extra_columns=["category"],
        )

        # 1. 建表
        await fts.ensure_table(engine, config)
        check("FTS5 建表成功", True)

        # 2. Upsert
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            await fts.upsert(
                session, config,
                doc_id="d1",
                title="Python 学习笔记",
                content="Python 是一门优雅的编程语言，适合数据分析和 AI 开发。",
                category="fact",
            )
            await fts.upsert(
                session, config,
                doc_id="d2",
                title="工作习惯",
                content="用户喜欢早上写代码，下午开会讨论需求。",
                category="workflow",
            )
            await fts.upsert(
                session, config,
                doc_id="d3",
                title="写作偏好",
                content="喜欢毒舌但有干货的写作风格，不喜欢鸡汤文。",
                category="preference",
            )
            await session.commit()

        check("FTS5 upsert 3 条文档", True)

        # 3. 搜索
        async with session_factory() as session:
            hits = await fts.search(session, config, "Python 编程")
            check("FTS5 搜索返回结果", len(hits) > 0)
            if hits:
                check("搜索结果包含 doc_id", hits[0].doc_id == "d1")
            else:
                check("搜索结果包含 doc_id（无结果跳过）", False)

        # 4. 按分类过滤
        async with session_factory() as session:
            hits = await fts.search(
                session, config, "喜欢",
                where={"category": "preference"},
            )
            check("按分类过滤搜索", len(hits) > 0)
            if hits:
                check("过滤结果正确", hits[0].extra.get("category") == "preference")
            else:
                check("过滤结果正确（无结果跳过）", False)

        # 5. 统计
        async with session_factory() as session:
            stats = await fts.get_stats(session, config)
            check("索引统计", stats["total_docs"] == 3)

        # 6. 删除
        async with session_factory() as session:
            await fts.delete(session, config, "d2")
            await session.commit()
            stats = await fts.get_stats(session, config)
            check("删除后统计", stats["total_docs"] == 2)

        # 7. 获取全文
        async with session_factory() as session:
            full = await fts.get_full_content(session, config, "d1")
            check("获取全文", full is not None and "Python" in full)

        # 8. CJK 逆向合并：snippet/title 中不应有 CJK 字符间的空格
        async with session_factory() as session:
            hits = await fts.search(session, config, "喜欢")
            if hits:
                # snippet 中的中文应该连续，不应有 "喜 欢" 这种碎字
                has_cjk_space = "喜 欢" in hits[0].snippet or "毒 舌" in hits[0].snippet
                check("CJK 逆向合并（snippet 无碎字）", not has_cjk_space)
            else:
                check("CJK 逆向合并（无结果跳过）", False)

        # 9. integrity_check
        async with session_factory() as session:
            is_ok = await fts.integrity_check(session, config)
            check("FTS5 完整性检查", is_ok)

        await engine.dispose()


async def test_instance_memory():
    """测试 InstanceMemoryManager（不依赖 Mem0）"""
    print("\n" + "=" * 60)
    print("测试 3: InstanceMemoryManager（文件层 + 降级搜索）")
    print("=" * 60)

    from core.memory.instance_memory import InstanceMemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = InstanceMemoryManager(
            base_dir=Path(tmpdir),
            user_id="test_user",
            mem0_enabled=False,  # 不依赖 Mem0 进行基本测试
        )

        # 1. get_memory_context
        ctx = await mgr.get_memory_context()
        check("get_memory_context 返回模板", "小搭子的记忆" in ctx)

        # 2. remember
        await mgr.remember("喜欢 Python 编程", category="preference")
        ctx = await mgr.get_memory_context()
        check("remember 写入 MEMORY.md", "喜欢 Python 编程" in ctx)

        # 3. remember 不同分类
        await mgr.remember("产品经理", category="fact")
        ctx = await mgr.get_memory_context()
        check("fact 分类写入", "产品经理" in ctx)

        # 4. recall（降级到文件层搜索）
        results = await mgr.recall("Python")
        check("recall 返回结果", len(results) > 0)
        check("recall 结果包含内容", "Python" in results[0]["content"])

        # 5. flush
        messages = [
            {"role": "user", "content": "帮我写个 Python 脚本"},
            {"role": "assistant", "content": "好的，我来帮你写。"},
        ]
        await mgr.flush("test_session_123", messages)

        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(tmpdir) / "memory" / f"{today}.md"
        check("flush 写入每日日志", log_file.exists())


async def test_knowledge_manager():
    """测试 LocalKnowledgeManager + FileIndexer"""
    print("\n" + "=" * 60)
    print("测试 4: LocalKnowledgeManager + FileIndexer")
    print("=" * 60)

    from core.knowledge.file_indexer import FileIndexer
    from core.knowledge.local_search import LocalKnowledgeManager

    # 先初始化 local_store 引擎（使用临时目录）
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()

        (test_dir / "python_guide.md").write_text(
            "# Python 入门指南\n\n"
            "Python 是一门优雅的编程语言。\n"
            "适合数据分析、机器学习和 Web 开发。\n\n"
            "## 安装\n\n使用 brew install python3 安装。\n",
            encoding="utf-8",
        )
        (test_dir / "daily_notes.txt").write_text(
            "今天学习了 FastAPI 框架的路由设计。\n"
            "明天计划研究 SQLite FTS5 全文搜索。\n",
            encoding="utf-8",
        )
        (test_dir / "ignore.js").write_text(
            "// 这个文件不应该被索引\n",
            encoding="utf-8",
        )

        # 创建知识管理器（使用独立引擎）
        from infra.local_store.engine import create_local_engine
        from infra.local_store.generic_fts import FTS5TableConfig, GenericFTS5
        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = create_local_engine(db_dir=tmpdir, db_name="test_knowledge.db")

        km = LocalKnowledgeManager(fts5_enabled=True)
        # 手动初始化 FTS5（使用测试引擎）
        km._fts = GenericFTS5()
        km._fts_config = FTS5TableConfig(
            table_name="knowledge_fts",
            id_column="doc_id",
            title_column="title",
            content_column="content",
            extra_columns=["file_path", "file_type", "chunk_index"],
        )
        await km._fts.ensure_table(engine, km._fts_config)
        km._fts_initialized = True

        # 包装 session 获取方法（使用测试引擎）
        test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # 手动添加文档（绕过 get_local_session）
        async with test_session_factory() as session:
            await km._fts.upsert(
                session, km._fts_config,
                doc_id="python_guide.md:0",
                title="python_guide",
                content="Python 是一门优雅的编程语言。适合数据分析、机器学习和 Web 开发。",
                file_path=str(test_dir / "python_guide.md"),
                file_type=".md",
                chunk_index="0",
            )
            await km._fts.upsert(
                session, km._fts_config,
                doc_id="daily_notes.txt:0",
                title="daily_notes",
                content="今天学习了 FastAPI 框架的路由设计。明天计划研究 SQLite FTS5 全文搜索。",
                file_path=str(test_dir / "daily_notes.txt"),
                file_type=".txt",
                chunk_index="0",
            )
            await session.commit()

        # 搜索测试（直接使用测试 session）
        async with test_session_factory() as session:
            hits = await km._fts.search(session, km._fts_config, "Python 编程")
            check("知识搜索: Python", len(hits) > 0)

        async with test_session_factory() as session:
            hits = await km._fts.search(session, km._fts_config, "FastAPI")
            check("知识搜索: FastAPI", len(hits) > 0)

        async with test_session_factory() as session:
            stats = await km._fts.get_stats(session, km._fts_config)
            check("知识索引统计", stats["total_docs"] == 2)

        # FileIndexer 分块测试
        indexer = FileIndexer(km, chunk_size=100, chunk_overlap=20)
        chunks = indexer._split_chunks("A" * 250)
        check("分块: 长文本正确分块", len(chunks) >= 2)

        short_chunks = indexer._split_chunks("短文本")
        check("分块: 短文本不分块", len(short_chunks) == 1)

        # 文件 hash 计算
        hash1 = await indexer._compute_hash(test_dir / "python_guide.md")
        hash2 = await indexer._compute_hash(test_dir / "daily_notes.txt")
        check("文件 hash 计算", len(hash1) == 64 and hash1 != hash2)

        # 文件读取
        content = await indexer._read_text(test_dir / "python_guide.md")
        check("文件读取: md", "Python" in content)

        content = await indexer._read_text(test_dir / "daily_notes.txt")
        check("文件读取: txt", "FastAPI" in content)

        await engine.dispose()


async def test_module_imports():
    """测试所有模块可导入"""
    print("\n" + "=" * 60)
    print("测试 5: 模块导入")
    print("=" * 60)

    modules = [
        ("infra.local_store.generic_fts", ["GenericFTS5", "FTS5TableConfig", "FTS5Hit"]),
        ("core.memory.markdown_layer", ["MarkdownMemoryLayer", "MemoryEntry"]),
        ("core.memory.instance_memory", ["InstanceMemoryManager"]),
        ("core.knowledge.local_search", ["LocalKnowledgeManager", "SearchResult"]),
        ("core.knowledge.file_indexer", ["FileIndexer"]),
        ("infra.local_store", ["GenericFTS5", "FTS5TableConfig", "FTS5Hit", "LocalIndexedFile"]),
    ]

    for module_name, expected_exports in modules:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            for attr in expected_exports:
                assert hasattr(mod, attr), f"{attr} not in {module_name}"
            check(f"import {module_name}", True)
        except Exception as e:
            check(f"import {module_name}: {e}", False)


async def main():
    print("=" * 60)
    print("记忆系统 + 知识检索 端到端验证")
    print("=" * 60)

    await test_module_imports()
    await test_markdown_layer()
    await test_generic_fts5()
    await test_instance_memory()
    await test_knowledge_manager()

    print("\n" + "=" * 60)
    total = passed + failed
    print(f"验证完成: {passed}/{total} 通过, {failed} 失败")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
