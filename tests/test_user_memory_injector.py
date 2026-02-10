"""
UserMemoryInjector 重构测试

验证范围：
1. 融合路径正确性：MEMORY.md + Mem0 + 分类召回三路并行
2. skip_memory=True 时完全跳过
3. skip_memory=False 时三路全部执行
4. 单路失败不影响其他路
5. Mem0 异步包装（asyncio.to_thread）不阻塞
6. 预算控制和截断
7. prompt_builder 不再预加载用户画像

Run:
    python -m pytest tests/test_user_memory_injector.py -v
"""

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ======================================================================
# Fixtures: Mock InjectionContext
# ======================================================================

@dataclass
class MockIntent:
    """Mock IntentResult for testing."""
    skip_memory: bool = False
    complexity: str = "medium"
    confidence: float = 0.8


@dataclass
class MockInjectionContext:
    """Minimal mock of InjectionContext for UserMemoryInjector tests."""
    user_id: Optional[str] = "test_user"
    user_query: Optional[str] = "帮我写一篇关于咖啡文化的文章"
    intent: Optional[MockIntent] = None
    _data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.intent is None:
            self.intent = MockIntent()

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value


# ======================================================================
# 1. should_inject: skip_memory 信号
# ======================================================================

class TestShouldInject:
    """验证 should_inject 对 skip_memory 的响应。"""

    @pytest.mark.asyncio
    async def test_skip_memory_true_returns_false(self):
        """skip_memory=True 时应该跳过注入。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext(intent=MockIntent(skip_memory=True))
        assert await injector.should_inject(ctx) is False

    @pytest.mark.asyncio
    async def test_skip_memory_false_returns_true(self):
        """skip_memory=False 时应该注入。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext(intent=MockIntent(skip_memory=False))
        assert await injector.should_inject(ctx) is True

    @pytest.mark.asyncio
    async def test_no_user_id_returns_false(self):
        """没有 user_id 时应该跳过。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext(user_id=None)
        assert await injector.should_inject(ctx) is False

    @pytest.mark.asyncio
    async def test_no_intent_returns_true(self):
        """intent 为 None 时默认注入（保守策略）。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext(intent=None, user_id="test_user")
        # intent=None 时 should_inject 应该返回 True（有 user_id）
        assert await injector.should_inject(ctx) is True


# ======================================================================
# 2. 融合路径：三路并行
# ======================================================================

class TestFusedMemoryPath:
    """验证 inject() 始终走融合路径，三路并行。"""

    @pytest.mark.asyncio
    async def test_all_three_sources_called(self):
        """三路数据源都被调用。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value="## 记忆档案\n- Python 偏好") as md_mock,
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=["老张是项目负责人"]) as mem0_mock,
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=["毒舌风格"]) as style_mock,
        ):
            result = await injector.inject(ctx)

            md_mock.assert_awaited_once()
            mem0_mock.assert_awaited_once()
            style_mock.assert_awaited_once()
            assert result.content is not None
            assert "Python 偏好" in result.content
            assert "老张是项目负责人" in result.content
            assert "毒舌风格" in result.content

    @pytest.mark.asyncio
    async def test_no_preload_shortcut(self):
        """即使 context 中有 user_profile，也不会短路——始终走融合。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()
        # 模拟旧代码可能设置的 pre-load 数据
        ctx.set("user_profile", "这是旧的预加载数据，不应被使用")

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value="## 新鲜的 MEMORY.md") as md_mock,
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=[]),
        ):
            result = await injector.inject(ctx)

            md_mock.assert_awaited_once()
            # 应该使用融合路径的结果，而不是预加载数据
            assert "新鲜的 MEMORY.md" in result.content
            assert "旧的预加载数据" not in result.content

    @pytest.mark.asyncio
    async def test_only_markdown_available(self):
        """只有 MEMORY.md 有数据时也能正常返回。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value="## 记忆\n- 使用 FastAPI"),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=[]),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            assert "FastAPI" in result.content

    @pytest.mark.asyncio
    async def test_only_mem0_available(self):
        """只有 Mem0 有数据时也能正常返回。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=["用户喜欢简洁代码"]),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=[]),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            assert "用户喜欢简洁代码" in result.content

    @pytest.mark.asyncio
    async def test_only_style_available(self):
        """只有分类召回有数据时也能正常返回。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=["毒舌风格"]),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            assert "毒舌风格" in result.content
            assert "始终生效" in result.content

    @pytest.mark.asyncio
    async def test_all_empty_returns_empty(self):
        """三路全空时返回空结果。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=[]),
        ):
            result = await injector.inject(ctx)
            assert result.content is None


# ======================================================================
# 3. 容错：单路失败不影响其他
# ======================================================================

class TestFaultTolerance:
    """验证 asyncio.gather(return_exceptions=True) 的容错性。"""

    @pytest.mark.asyncio
    async def test_markdown_fails_others_work(self):
        """MEMORY.md 读取失败时，Mem0 和分类召回正常返回。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, side_effect=RuntimeError("文件不存在")),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=["记忆内容A"]),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=["风格B"]),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            assert "记忆内容A" in result.content
            assert "风格B" in result.content

    @pytest.mark.asyncio
    async def test_mem0_fails_others_work(self):
        """Mem0 搜索失败时，MEMORY.md 和分类召回正常返回。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value="## 记忆\n- 偏好X"),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, side_effect=ConnectionError("Mem0 不可用")),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=["风格Y"]),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            assert "偏好X" in result.content
            assert "风格Y" in result.content

    @pytest.mark.asyncio
    async def test_style_fails_others_work(self):
        """分类召回失败时，MEMORY.md 和 Mem0 正常返回。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value="## 记忆\n- 偏好Z"),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=["记忆W"]),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, side_effect=RuntimeError("FTS5 挂了")),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            assert "偏好Z" in result.content
            assert "记忆W" in result.content

    @pytest.mark.asyncio
    async def test_all_fail_returns_empty(self):
        """三路全部失败时返回空结果，不抛异常。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, side_effect=RuntimeError("err1")),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, side_effect=RuntimeError("err2")),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, side_effect=RuntimeError("err3")),
        ):
            result = await injector.inject(ctx)
            assert result.content is None


# ======================================================================
# 4. 预算控制
# ======================================================================

class TestBudgetControl:
    """验证预算截断逻辑。"""

    @pytest.mark.asyncio
    async def test_truncation_at_max_chars(self):
        """超过 MAX_INJECT_CHARS 时截断并追加省略号。"""
        from core.context.injectors.phase2.user_memory import (
            MAX_INJECT_CHARS,
            UserMemoryInjector,
        )

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        # 生成超长内容
        long_content = "## 记忆\n" + "- 很长的记忆条目\n" * 200
        assert len(long_content) > MAX_INJECT_CHARS

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value=long_content),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=[]),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            # 截断后加 "\n..." 总长度应略大于 MAX_INJECT_CHARS
            assert len(result.content) <= MAX_INJECT_CHARS + 10

    @pytest.mark.asyncio
    async def test_within_budget_no_truncation(self):
        """未超预算时不截断。"""
        from core.context.injectors.phase2.user_memory import (
            MAX_INJECT_CHARS,
            UserMemoryInjector,
        )

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        short_content = "## 记忆\n- 简短内容"
        assert len(short_content) < MAX_INJECT_CHARS

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value=short_content),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=[]),
        ):
            result = await injector.inject(ctx)
            assert "..." not in result.content


# ======================================================================
# 5. 去重逻辑
# ======================================================================

class TestDeduplication:
    """验证分类召回与 Mem0 结果的去重。"""

    @pytest.mark.asyncio
    async def test_style_deduped_against_mem0(self):
        """分类召回中与 Mem0 重复的条目应被去除。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=["毒舌风格", "偏好简洁"]),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=["毒舌风格", "喜欢咖啡"]),
        ):
            result = await injector.inject(ctx)
            assert result.content is not None
            # "毒舌风格" 应只出现在 Mem0 部分，不重复出现在风格部分
            # 风格部分只有 "喜欢咖啡"
            style_section = result.content.split("始终生效")
            if len(style_section) > 1:
                assert "喜欢咖啡" in style_section[1]
                assert "毒舌风格" not in style_section[1]


# ======================================================================
# 6. Mem0 异步包装
# ======================================================================

class TestMem0Async:
    """验证 Mem0 搜索通过 asyncio.to_thread 异步执行。"""

    @pytest.mark.asyncio
    async def test_mem0_uses_to_thread(self):
        """_fetch_from_mem0 应该通过 asyncio.to_thread 调用 pool.search。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        mock_pool = MagicMock()
        mock_pool.search.return_value = [
            {"memory": "记忆1"},
            {"memory": "记忆2"},
        ]

        with (
            patch("core.context.injectors.phase2.user_memory.asyncio.to_thread", new_callable=AsyncMock) as to_thread_mock,
            patch("core.memory.mem0.pool.get_mem0_pool", return_value=mock_pool),
        ):
            to_thread_mock.return_value = mock_pool.search.return_value
            result = await injector._fetch_from_mem0(ctx)

            # 验证 to_thread 被调用
            to_thread_mock.assert_awaited_once()
            # 验证返回了正确的记忆列表
            assert result is not None
            assert "记忆1" in result
            assert "记忆2" in result

    @pytest.mark.asyncio
    async def test_mem0_no_user_query_returns_none(self):
        """没有 user_query 时应该直接返回 None。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext(user_query=None)

        result = await injector._fetch_from_mem0(ctx)
        assert result is None

    @pytest.mark.asyncio
    async def test_mem0_no_user_id_returns_none(self):
        """没有 user_id 时应该直接返回 None。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext(user_id=None)

        result = await injector._fetch_from_mem0(ctx)
        assert result is None


# ======================================================================
# 7. prompt_builder 不再预加载
# ======================================================================

class TestPromptBuilderCleanup:
    """验证 prompt_builder 已移除 fetch_user_profile 和预加载逻辑。"""

    def test_fetch_user_profile_removed_from_prompt_builder(self):
        """prompt_builder 不再导出 fetch_user_profile。"""
        import core.agent.context.prompt_builder as pb

        assert not hasattr(pb, "fetch_user_profile"), (
            "fetch_user_profile 应已从 prompt_builder 中删除"
        )

    def test_fetch_user_profile_removed_from_init(self):
        """__init__.py 不再导出 fetch_user_profile。"""
        import core.agent.context as ctx_module

        assert "fetch_user_profile" not in ctx_module.__all__, (
            "fetch_user_profile 应已从 __all__ 中删除"
        )

    def test_profile_cache_removed(self):
        """prompt_builder 不再有 _profile_cache。"""
        import core.agent.context.prompt_builder as pb

        assert not hasattr(pb, "_profile_cache"), (
            "_profile_cache 应已从 prompt_builder 中删除"
        )

    def test_no_preload_in_source(self):
        """prompt_builder 源码中不再出现 user_profile 预加载。"""
        import inspect
        import core.agent.context.prompt_builder as pb

        source = inspect.getsource(pb)
        assert 'context.set("user_profile"' not in source, (
            "prompt_builder 不应再有 context.set('user_profile') 预加载"
        )
        assert "fetch_user_profile" not in source, (
            "prompt_builder 不应再引用 fetch_user_profile"
        )


# ======================================================================
# 8. _fetch_user_profile 从 universal_agent_prompt 删除
# ======================================================================

class TestUniversalPromptCleanup:
    """验证 universal_agent_prompt 已删除 _fetch_user_profile。"""

    def test_fetch_user_profile_removed(self):
        """universal_agent_prompt 不再有 _fetch_user_profile。"""
        from prompts import universal_agent_prompt as uap

        assert not hasattr(uap, "_fetch_user_profile"), (
            "_fetch_user_profile 应已从 universal_agent_prompt 中删除"
        )

    @pytest.mark.asyncio
    async def test_get_prompt_no_mem0_call(self):
        """get_universal_agent_prompt 不再调用 Mem0。"""
        from prompts.universal_agent_prompt import get_universal_agent_prompt

        # 即使传了 user_id 和 user_query，也不应触发 Mem0 搜索
        with patch("core.memory.mem0.pool.get_mem0_pool") as pool_mock:
            prompt = await get_universal_agent_prompt(
                user_id="test_user",
                user_query="测试查询",
            )
            pool_mock.assert_not_called()
            assert isinstance(prompt, str)
            assert len(prompt) > 0


# ======================================================================
# 9. XML tag 和 injector 元数据
# ======================================================================

class TestInjectorMetadata:
    """验证 injector 属性和输出格式。"""

    def test_injector_properties(self):
        """验证 injector 名称、Phase、优先级。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        assert injector.name == "user_memory"
        assert injector.priority == 90

    @pytest.mark.asyncio
    async def test_xml_tag_is_user_memory(self):
        """输出的 xml_tag 应为 'user_memory'。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()
        ctx = MockInjectionContext()

        with (
            patch.object(injector, "_fetch_from_markdown", new_callable=AsyncMock, return_value="## 记忆\n- 内容"),
            patch.object(injector, "_fetch_from_mem0", new_callable=AsyncMock, return_value=None),
            patch.object(injector, "_recall_by_category", new_callable=AsyncMock, return_value=[]),
        ):
            result = await injector.inject(ctx)
            assert result.xml_tag == "user_memory"


# ======================================================================
# 10. trim_markdown_memory 单元测试
# ======================================================================

class TestTrimMarkdownMemory:
    """验证 MEMORY.md 智能裁剪。"""

    def test_short_content_unchanged(self):
        """短内容不裁剪。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        content = "## 偏好\n- Python"
        result = UserMemoryInjector._trim_markdown_memory(content, 1000)
        assert result == content

    def test_placeholder_lines_skipped_during_trim(self):
        """裁剪时模板占位符行被跳过，有效内容得到保留。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        # 用很小的预算触发裁剪逻辑
        content = "## 偏好\n（小搭子还不了解你的偏好）\n- Python\n- FastAPI"
        result = UserMemoryInjector._trim_markdown_memory(content, 30)
        # 占位符行被跳过，有效内容优先保留
        assert "小搭子" not in result
        assert "偏好" in result

    def test_blockquote_lines_skipped_during_trim(self):
        """裁剪时引用说明行被跳过，有效内容得到保留。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        content = "## 偏好\n> 这是说明文字\n- Python\n- FastAPI"
        result = UserMemoryInjector._trim_markdown_memory(content, 30)
        assert "说明文字" not in result
        assert "偏好" in result

    def test_truncation_respects_budget(self):
        """裁剪遵守预算限制。"""
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        content = "## 标题\n" + "- 很长的条目内容\n" * 100
        result = UserMemoryInjector._trim_markdown_memory(content, 100)
        assert len(result) <= 120  # 允许最后一行略超
