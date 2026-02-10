"""
Memory Closed-Loop E2E Verification

验证记忆系统的完整闭环链路（不是单模块测试，是跨模块集成验证）：

链路 1（写入闭环）：
    remember() → MEMORY.md 写入 → FTS5 索引同步 → recall() 可搜到

链路 2（读取闭环 — 注入路径）：
    UserMemoryInjector → MEMORY.md 读取 + Mem0 读取 → 融合注入

链路 3（读取闭环 — 工具路径）：
    MemoryRecallTool.execute(mode="full") → 读到 MEMORY.md 完整内容
    MemoryRecallTool.execute(mode="search") → recall() 融合搜索

链路 4（外部编辑同步）：
    手动修改 MEMORY.md → get_memory_context() → FTS5 重新索引 → recall() 搜到新内容

链路 5（flush 写入全链路）：
    flush(session, messages) → 提取记忆 → remember() → MEMORY.md + FTS5

运行方式：
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    python scripts/verify_memory_closedloop.py
"""

import asyncio
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = 0
FAIL = 0
WARNINGS = []


def check(label: str, condition: bool, detail: str = ""):
    """Single assertion with tracking."""
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        msg = f"  ❌ {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)
        WARNINGS.append(label)


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _contains_cjk(haystack: str, needle: str) -> bool:
    """Check if needle chars are in haystack, ignoring FTS5 tokenizer spaces.

    FTS5 unicode61 tokenizer inserts spaces between CJK characters in
    snippets (e.g. "学 习 日 语" for "学习日语").  Strip spaces for
    comparison so recall results are still considered a match.
    """
    return needle.replace(" ", "") in haystack.replace(" ", "")


# ==============================================================
# Chain 1: Write Closed Loop
# remember() → MEMORY.md + FTS5 → recall()
# ==============================================================

async def test_chain1_write_closedloop():
    """写入闭环：remember → MEMORY.md + FTS5 → recall 搜到"""
    section("链路 1: 写入闭环 (remember → MEMORY.md + FTS5 → recall)")

    from core.memory.instance_memory import InstanceMemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "memory"
        mgr = InstanceMemoryManager(
            base_dir=base,
            user_id="test_closedloop",
            mem0_enabled=False,  # FTS5-only, no external deps
        )

        # Step 1: remember() writes to MEMORY.md + FTS5
        await mgr.remember("喜欢用 Vim 编辑器", category="preference")
        await mgr.remember("用户是产品经理", category="fact")
        await mgr.remember("偏好 Markdown 格式输出", category="style")

        # Step 2: Verify MEMORY.md has content
        ctx = await mgr.get_memory_context()
        check("MEMORY.md 包含 Vim", "Vim" in ctx)
        check("MEMORY.md 包含产品经理", "产品经理" in ctx)
        check("MEMORY.md 包含 Markdown", "Markdown" in ctx)

        # Step 3: recall() fusion search finds it
        results = await mgr.recall("编辑器偏好", limit=5)
        contents = [r["content"] for r in results]
        found_vim = any(_contains_cjk(c, "Vim") for c in contents)
        check(
            "recall('编辑器偏好') 搜到 Vim",
            found_vim,
            f"实际结果: {contents}",
        )

        results2 = await mgr.recall("用户职业", limit=5)
        contents2 = [r["content"] for r in results2]
        found_pm = any(_contains_cjk(c, "产品经理") for c in contents2)
        check(
            "recall('用户职业') 搜到产品经理",
            found_pm,
            f"实际结果: {contents2}",
        )

        print(f"  📄 MEMORY.md 内容预览:\n{ctx[:300]}...")


# ==============================================================
# Chain 2: Read Closed Loop — Injector Path
# UserMemoryInjector → MEMORY.md + Mem0 → fused injection
# ==============================================================

async def test_chain2_injector_reads_markdown():
    """读取闭环（注入路径）：UserMemoryInjector 能读到 MEMORY.md"""
    section("链路 2: 注入路径闭环 (UserMemoryInjector 读 MEMORY.md)")

    from core.memory.instance_memory import InstanceMemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "memory"
        mgr = InstanceMemoryManager(
            base_dir=base,
            user_id="test_injector",
            mem0_enabled=False,
        )

        # Pre-populate MEMORY.md
        await mgr.remember("写作风格：简洁直白", category="style")
        await mgr.remember("常用工具：VS Code", category="tool")

        # Simulate what UserMemoryInjector._fetch_from_markdown does
        content = await mgr.get_memory_context()
        check("get_memory_context() 返回非空", bool(content and len(content) > 20))
        check("内容包含写作风格", "简洁直白" in content)
        check("内容包含 VS Code", "VS Code" in content)

        # Verify the _trim_markdown_memory static method
        from core.context.injectors.phase2.user_memory import (
            UserMemoryInjector,
        )

        trimmed = UserMemoryInjector._trim_markdown_memory(content, 200)
        check(
            "_trim_markdown_memory 不超过预算",
            len(trimmed) <= 200,
            f"实际长度: {len(trimmed)}",
        )
        check(
            "trimmed 仍包含有效内容",
            len(trimmed) > 10,
        )


# ==============================================================
# Chain 3: Read Closed Loop — Tool Path
# MemoryRecallTool → recall() / get_memory_context()
# ==============================================================

async def test_chain3_tool_reads_memory():
    """读取闭环（工具路径）：MemoryRecallTool 能读到记忆"""
    section("链路 3: 工具路径闭环 (MemoryRecallTool 读取记忆)")

    from core.memory.instance_memory import InstanceMemoryManager
    from core.tool.types import ToolContext
    from tools.memory_recall import MemoryRecallTool

    with tempfile.TemporaryDirectory() as tmpdir:
        # Pre-populate
        base = Path(tmpdir) / "memory"
        mgr = InstanceMemoryManager(
            base_dir=base,
            user_id="test_tool",
            mem0_enabled=False,
        )
        await mgr.remember("周末喜欢跑步", category="preference")
        await mgr.remember("开会偏好用腾讯会议", category="tool")

        # Create tool and inject pre-initialized manager
        tool = MemoryRecallTool()
        tool._memory_manager = mgr  # Bypass lazy init for test

        ctx = ToolContext(
            session_id="test_sess",
            user_id="test_tool",
        )

        # Test mode="full"
        result = await tool.execute(
            {"query": "all", "mode": "full"}, ctx
        )
        check("mode=full 返回成功", result.get("success") is True)
        memory_text = result.get("memory", "")
        check("full mode 包含跑步", "跑步" in memory_text)
        check("full mode 包含腾讯会议", "腾讯会议" in memory_text)

        # Test mode="search"
        result2 = await tool.execute(
            {"query": "运动爱好", "mode": "search", "limit": 5}, ctx
        )
        check("mode=search 返回成功", result2.get("success") is True)
        search_results = result2.get("results", [])
        found = any(_contains_cjk(r.get("content", ""), "跑步") for r in search_results)
        check(
            "search('运动爱好') 搜到跑步",
            found,
            f"实际结果: {[r.get('content') for r in search_results]}",
        )


# ==============================================================
# Chain 4: External Edit Sync
# Manual MEMORY.md edit → get_memory_context() → FTS5 re-index
# ==============================================================

async def test_chain4_external_edit_sync():
    """外部编辑同步：手动改 MEMORY.md → FTS5 自动重新索引"""
    section("链路 4: 外部编辑同步 (手动改 MEMORY.md → FTS5 re-index)")

    from core.memory.instance_memory import InstanceMemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "memory"
        mgr = InstanceMemoryManager(
            base_dir=base,
            user_id="test_sync",
            mem0_enabled=False,
        )

        # Initial write via remember()
        await mgr.remember("喜欢喝咖啡", category="preference")

        # Read once to establish baseline hash
        ctx1 = await mgr.get_memory_context()
        check("初始 MEMORY.md 包含咖啡", "咖啡" in ctx1)

        # Simulate external edit: user adds a new line directly
        import aiofiles
        md_path = mgr._file_layer.memory_file
        async with aiofiles.open(md_path, "r", encoding="utf-8") as f:
            original = await f.read()

        new_content = original + "\n- 最近在学习日语\n"
        async with aiofiles.open(md_path, "w", encoding="utf-8") as f:
            await f.write(new_content)

        # Read again — should trigger sync
        ctx2 = await mgr.get_memory_context()
        check("编辑后 MEMORY.md 包含日语", "日语" in ctx2)

        # Recall should now find the externally added content
        results = await mgr.recall("语言学习", limit=5)
        contents = [r["content"] for r in results]
        found_jp = any(_contains_cjk(c, "日语") for c in contents)
        check(
            "recall('语言学习') 搜到日语（外部编辑内容）",
            found_jp,
            f"实际结果: {contents}",
        )


# ==============================================================
# Chain 5: Flush Full Chain
# flush() → extract → remember() → MEMORY.md + FTS5
# ==============================================================

async def test_chain5_flush_chain():
    """Flush 全链路：会话结束 → 提取 → 写入 → 可搜到"""
    section("链路 5: Flush 全链路 (flush → MEMORY.md + FTS5)")

    from core.memory.instance_memory import InstanceMemoryManager

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "memory"
        mgr = InstanceMemoryManager(
            base_dir=base,
            user_id="test_flush",
            mem0_enabled=False,
        )

        # Simulate a conversation with explicit preferences
        messages = [
            {"role": "user", "content": "我是一名数据科学家，平时用 Python 和 R 做分析"},
            {"role": "assistant", "content": "了解！作为数据科学家，Python 和 R 是非常好的选择。"},
            {"role": "user", "content": "对，我特别喜欢用 pandas 处理数据，可视化用 matplotlib"},
            {"role": "assistant", "content": "pandas + matplotlib 是经典组合！"},
        ]

        start = time.time()
        await mgr.flush("test_flush_session_001", messages)
        elapsed = time.time() - start

        # Check MEMORY.md was written
        ctx = await mgr.get_memory_context()
        check(
            "flush 后 MEMORY.md 不为空",
            len(ctx) > 50,
            f"实际长度: {len(ctx)}",
        )

        # Check daily log was written
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        log = await mgr._file_layer.read_daily_log(today)
        check(
            "每日日志已写入",
            len(log) > 0,
            f"日志长度: {len(log)}",
        )
        check(
            "日志包含会话信息",
            "test_flush" in log or "数据科学" in log,
        )

        check(
            f"flush 耗时合理 ({elapsed:.1f}s)",
            elapsed < 30,
            f"实际: {elapsed:.1f}s",
        )

        print(f"  📄 flush 后 MEMORY.md 预览:\n{ctx[:400]}...")


# ==============================================================
# Chain 6: Module Import Verification
# All new/modified modules import correctly
# ==============================================================

async def test_chain6_imports():
    """模块导入验证：所有新增/修改的模块可正常导入"""
    section("链路 6: 模块导入验证")

    # memory_recall tool
    try:
        from tools.memory_recall import MemoryRecallTool
        tool = MemoryRecallTool()
        check("MemoryRecallTool 导入成功", True)
        check("MemoryRecallTool.name == 'memory_recall'", tool.name == "memory_recall")
        check("MemoryRecallTool.input_schema 有 query", "query" in str(tool.input_schema))
        check("MemoryRecallTool.input_schema 有 mode", "mode" in str(tool.input_schema))
    except Exception as e:
        check("MemoryRecallTool 导入", False, str(e))

    # UserMemoryInjector
    try:
        from core.context.injectors.phase2.user_memory import UserMemoryInjector
        injector = UserMemoryInjector()
        check("UserMemoryInjector 导入成功", True)
        check("UserMemoryInjector.name == 'user_memory'", injector.name == "user_memory")
        check(
            "UserMemoryInjector 有 _fetch_fused_memory 方法",
            hasattr(injector, "_fetch_fused_memory"),
        )
        check(
            "UserMemoryInjector 有 _fetch_from_markdown 方法",
            hasattr(injector, "_fetch_from_markdown"),
        )
    except Exception as e:
        check("UserMemoryInjector 导入", False, str(e))

    # InstanceMemoryManager sync method
    try:
        from core.memory.instance_memory import InstanceMemoryManager
        check(
            "InstanceMemoryManager 有 _sync_markdown_to_fts5",
            hasattr(InstanceMemoryManager, "_sync_markdown_to_fts5"),
        )
        check(
            "InstanceMemoryManager 有 _section_to_category",
            hasattr(InstanceMemoryManager, "_section_to_category"),
        )
    except Exception as e:
        check("InstanceMemoryManager 新方法", False, str(e))

    # capabilities.yaml has memory_recall
    try:
        import yaml
        with open("config/capabilities.yaml", "r") as f:
            data = yaml.safe_load(f)
        # Structure: {tool_classification: ..., capabilities: [...]}
        caps_list = data.get("capabilities", []) if isinstance(data, dict) else data
        names = [
            c["name"] for c in (caps_list or [])
            if isinstance(c, dict) and "name" in c
        ]
        check(
            "capabilities.yaml 包含 memory_recall",
            "memory_recall" in names,
            f"注册的工具: {names[:10]}...",
        )
    except Exception as e:
        check("capabilities.yaml 解析", False, str(e))


# ==============================================================
# Main
# ==============================================================

async def main():
    print("\n" + "=" * 60)
    print("  记忆系统闭环验证 (Memory Closed-Loop E2E)")
    print("  验证跨模块集成，不是单模块功能测试")
    print("=" * 60)

    await test_chain6_imports()
    await test_chain1_write_closedloop()
    await test_chain2_injector_reads_markdown()
    await test_chain3_tool_reads_memory()
    await test_chain4_external_edit_sync()
    await test_chain5_flush_chain()

    # Summary
    total = PASS + FAIL
    print(f"\n{'=' * 60}")
    print(f"  结果: {PASS}/{total} 通过")
    if FAIL:
        print(f"  ❌ 失败 {FAIL} 项:")
        for w in WARNINGS:
            print(f"     - {w}")
    else:
        print("  🎉 全部通过 — 记忆系统闭环完整")
    print(f"{'=' * 60}\n")

    return FAIL == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
