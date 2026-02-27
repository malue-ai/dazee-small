"""
RVRBState 和渐进式失败引导的单元测试

覆盖本次改动的核心逻辑，不依赖 LLM / 网络 / 数据库。

运行命令：
    /Users/liuyi/Documents/langchain/liuy/bin/python -m pytest \
        tests/core/agent/execution/test_rvrb_state.py -v
"""

import pytest

from core.agent.execution.rvrb import RVRBExecutor, RVRBState


# ===========================================================================
# RVRBState.record_tool_outcome / get_tool_failure_streak
# ===========================================================================


class TestToolFailureStreak:
    """同工具连续失败计数逻辑"""

    def test_initial_streak_is_zero(self):
        state = RVRBState(session_id="s1")
        assert state.get_tool_failure_streak("any_tool") == 0

    def test_first_failure_sets_streak_to_one(self):
        state = RVRBState(session_id="s1")
        state.record_tool_outcome("tool_x", success=False)
        assert state.get_tool_failure_streak("tool_x") == 1

    def test_consecutive_failures_increment(self):
        state = RVRBState(session_id="s1")
        for _ in range(3):
            state.record_tool_outcome("tool_x", success=False)
        assert state.get_tool_failure_streak("tool_x") == 3

    def test_success_resets_streak_to_zero(self):
        state = RVRBState(session_id="s1")
        state.record_tool_outcome("tool_x", success=False)
        state.record_tool_outcome("tool_x", success=False)
        state.record_tool_outcome("tool_x", success=True)
        assert state.get_tool_failure_streak("tool_x") == 0

    def test_success_then_failure_starts_fresh(self):
        state = RVRBState(session_id="s1")
        state.record_tool_outcome("tool_x", success=False)
        state.record_tool_outcome("tool_x", success=True)
        state.record_tool_outcome("tool_x", success=False)
        assert state.get_tool_failure_streak("tool_x") == 1

    def test_different_tools_are_independent(self):
        state = RVRBState(session_id="s1")
        state.record_tool_outcome("tool_a", success=False)
        state.record_tool_outcome("tool_b", success=False)
        state.record_tool_outcome("tool_b", success=False)
        assert state.get_tool_failure_streak("tool_a") == 1
        assert state.get_tool_failure_streak("tool_b") == 2

    def test_tool_a_success_does_not_affect_tool_b(self):
        state = RVRBState(session_id="s1")
        state.record_tool_outcome("tool_a", success=False)
        state.record_tool_outcome("tool_b", success=False)
        state.record_tool_outcome("tool_a", success=True)
        assert state.get_tool_failure_streak("tool_a") == 0
        assert state.get_tool_failure_streak("tool_b") == 1


# ===========================================================================
# RVRBExecutor._build_progressive_hint
# ===========================================================================


class TestBuildProgressiveHint:
    """渐进式失败引导的三级文案及副作用隔离"""

    def setup_method(self):
        self.executor = RVRBExecutor()
        self.state = RVRBState(session_id="s1")

    # --- Level 0: 未失败过，无引导 ---

    def test_returns_none_when_no_failure(self):
        hint = self.executor._build_progressive_hint("tool_x", "err", self.state)
        assert hint is None

    # --- Level 1: 首次失败 ---

    def test_level1_hint_on_first_failure(self):
        self.state.record_tool_outcome("tool_x", success=False)
        hint = self.executor._build_progressive_hint("tool_x", "permission denied", self.state)
        assert hint is not None
        assert "工具失败提醒" in hint
        assert "tool_x" in hint
        assert "permission denied" in hint

    def test_level1_truncates_long_error_msg(self):
        self.state.record_tool_outcome("tool_x", success=False)
        long_err = "x" * 300
        hint = self.executor._build_progressive_hint("tool_x", long_err, self.state)
        assert hint is not None
        # 错误信息应截断到 150 字符以内
        assert long_err not in hint

    # --- Level 2: 连续失败 2 次 ---

    def test_level2_hint_on_second_failure(self):
        self.state.record_tool_outcome("tool_x", success=False)
        self.state.record_tool_outcome("tool_x", success=False)
        hint = self.executor._build_progressive_hint("tool_x", "error", self.state)
        assert hint is not None
        assert "系统约束" in hint
        assert "连续失败 2 次" in hint

    def test_level2_includes_failed_approaches(self):
        self.state.record_tool_outcome("tool_x", success=False)
        self.state.record_failed_approach("tool_x", "params={a:1}", "权限不足")
        self.state.record_tool_outcome("tool_x", success=False)
        hint = self.executor._build_progressive_hint("tool_x", "error", self.state)
        assert "params={a:1}" in hint

    # --- Level 3: 连续失败 3 次+ ---

    def test_level3_hint_on_third_failure(self):
        for _ in range(3):
            self.state.record_tool_outcome("tool_x", success=False)
        hint = self.executor._build_progressive_hint("tool_x", "error", self.state)
        assert hint is not None
        assert "强制转向" in hint
        assert "连续失败 3 次" in hint

    def test_level3_hint_does_not_add_to_pruned_tools(self):
        """_build_progressive_hint 本身不应产生 pruned_tools 副作用（由调用方负责）"""
        for _ in range(3):
            self.state.record_tool_outcome("tool_x", success=False)
        self.executor._build_progressive_hint("tool_x", "error", self.state)
        assert "tool_x" not in self.state.pruned_tools

    def test_level3_hint_on_fourth_failure_still_works(self):
        for _ in range(4):
            self.state.record_tool_outcome("tool_x", success=False)
        hint = self.executor._build_progressive_hint("tool_x", "error", self.state)
        assert "强制转向" in hint


# ===========================================================================
# pruned_tools 动态裁剪逻辑（调用方写入，符合无副作用设计）
# ===========================================================================


class TestPrunedTools:
    """动态裁剪集合的写入和重置"""

    def test_caller_adds_to_pruned_tools_at_streak_3(self):
        state = RVRBState(session_id="s1")
        executor = RVRBExecutor()
        for _ in range(3):
            state.record_tool_outcome("tool_x", success=False)
        hint = executor._build_progressive_hint("tool_x", "error", state)
        # 模拟调用方逻辑（处理器中的 if streak >= 3: state.pruned_tools.add(tn)）
        if state.get_tool_failure_streak("tool_x") >= 3:
            state.pruned_tools.add("tool_x")
        assert "tool_x" in state.pruned_tools
        assert hint is not None

    def test_pruned_tools_reset_on_hitl_retry(self):
        state = RVRBState(session_id="s1")
        for _ in range(3):
            state.record_tool_outcome("tool_x", success=False)
        state.pruned_tools.add("tool_x")

        # 模拟用户点击"换个思路再试试"后的重置逻辑
        state.backtrack_count = 0
        state.pruned_tools.clear()
        state._tool_failure_streak.clear()

        assert len(state.pruned_tools) == 0
        assert state.get_tool_failure_streak("tool_x") == 0

    def test_pruned_tools_does_not_affect_other_tools(self):
        state = RVRBState(session_id="s1")
        state.pruned_tools.add("tool_x")
        assert "tool_y" not in state.pruned_tools


# ===========================================================================
# RVRBState 默认字段完整性
# ===========================================================================


class TestRVRBStateDefaults:
    """确认新增字段的默认值正确"""

    def test_tool_failure_streak_default_empty(self):
        state = RVRBState(session_id="s1")
        assert state._tool_failure_streak == {}

    def test_pruned_tools_default_empty_set(self):
        state = RVRBState(session_id="s1")
        assert state.pruned_tools == set()

    def test_total_backtrack_tokens_default_zero(self):
        state = RVRBState(session_id="s1")
        assert state.total_backtrack_tokens == 0

    def test_two_states_have_independent_streak_dicts(self):
        s1 = RVRBState(session_id="s1")
        s2 = RVRBState(session_id="s2")
        s1.record_tool_outcome("tool_x", success=False)
        assert s2.get_tool_failure_streak("tool_x") == 0
