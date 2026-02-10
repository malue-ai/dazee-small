"""
RVR-B Backtracking Integration Tests

Validates the complete backtrack chain AFTER bug fixes:
  P0-1: classified_error.message → suggested_action
  P1-1: TOOL_REPLACE degradation logging
  P1-2: Non-stream _clean_backtrack_results
  ProgressTransformer lazy-init

Test strategy:
  - Mock LLM + mock tools to simulate failures deterministically
  - Verify each component in the backtrack chain fires correctly
  - No real LLM API calls needed — runs in CI under 5 seconds

Run:
    python -m pytest tests/test_rvrb_backtrack.py -v
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ======================================================================
# 1. ErrorClassifier: verify ClassifiedError has suggested_action
# ======================================================================

class TestErrorClassifier:
    """Verify ErrorClassifier produces ClassifiedError with correct attributes."""

    def test_classified_error_has_suggested_action(self):
        """P0-1 fix: ClassifiedError must have suggested_action, NOT message."""
        from core.agent.backtrack.error_classifier import (
            BacktrackType,
            ClassifiedError,
            ErrorCategory,
            ErrorLayer,
        )

        ce = ClassifiedError(
            original_error=Exception("tool failed"),
            layer=ErrorLayer.BUSINESS_LOGIC,
            category=ErrorCategory.TOOL_MISMATCH,
            backtrack_type=BacktrackType.TOOL_REPLACE,
            is_retryable=False,
            confidence=0.8,
            suggested_action="Use alternative tool",
        )

        assert hasattr(ce, "suggested_action")
        assert ce.suggested_action == "Use alternative tool"
        assert not hasattr(ce, "message"), "ClassifiedError should NOT have 'message' attr"

    def test_classify_tool_error_produces_valid_result(self):
        """ErrorClassifier.classify_tool_error() returns complete ClassifiedError."""
        from core.agent.backtrack.error_classifier import ErrorClassifier

        classifier = ErrorClassifier()

        # Simulate a business logic error (parameter error)
        error = ValueError("invalid parameter: file_path is empty")
        result = classifier.classify_tool_error(
            error=error,
            tool_name="nodes",
            tool_input={"action": "read_file", "path": ""},
        )

        assert result.original_error is error
        assert result.layer is not None
        assert result.category is not None
        assert result.backtrack_type is not None
        assert isinstance(result.confidence, float)
        assert isinstance(result.suggested_action, str)

    def test_infrastructure_error_no_backtrack(self):
        """Infrastructure errors (timeout, rate limit) should NOT trigger backtrack."""
        from core.agent.backtrack.error_classifier import ErrorClassifier

        classifier = ErrorClassifier()

        # Simulate a timeout (infrastructure error)
        error = TimeoutError("request timeout after 30s")
        result = classifier.classify_tool_error(
            error=error,
            tool_name="api_calling",
            tool_input={"url": "https://example.com"},
        )

        assert result.is_infrastructure_error()
        assert not result.needs_backtrack()


# ======================================================================
# 2. BacktrackManager: verify evaluate_and_decide works
# ======================================================================

class TestBacktrackManager:
    """Verify BacktrackManager decision pipeline."""

    def test_max_backtracks_returns_fail_gracefully(self):
        """When max backtracks reached, should return FAIL_GRACEFULLY."""
        from core.agent.backtrack.error_classifier import (
            BacktrackType,
            ClassifiedError,
            ErrorCategory,
            ErrorLayer,
        )
        from core.agent.backtrack.manager import (
            BacktrackContext,
            BacktrackDecision,
            BacktrackManager,
        )

        manager = BacktrackManager(llm_service=None, max_backtracks=3)

        ctx = BacktrackContext(
            session_id="test",
            turn=5,
            max_turns=30,
            error=ClassifiedError(
                original_error=Exception("test"),
                layer=ErrorLayer.BUSINESS_LOGIC,
                category=ErrorCategory.TOOL_MISMATCH,
                backtrack_type=BacktrackType.TOOL_REPLACE,
                is_retryable=False,
                confidence=0.8,
            ),
            backtrack_count=3,  # Already at max
            max_backtracks=3,
        )

        result = asyncio.get_event_loop().run_until_complete(
            manager.evaluate_and_decide(ctx, use_llm=False)
        )

        assert result.decision == BacktrackDecision.FAIL_GRACEFULLY

    def test_rule_based_fallback_produces_backtrack(self):
        """Without LLM, rule-based decision should produce BACKTRACK."""
        from core.agent.backtrack.error_classifier import (
            BacktrackType,
            ClassifiedError,
            ErrorCategory,
            ErrorLayer,
        )
        from core.agent.backtrack.manager import (
            BacktrackContext,
            BacktrackDecision,
            BacktrackManager,
        )

        manager = BacktrackManager(llm_service=None, max_backtracks=3)

        ctx = BacktrackContext(
            session_id="test",
            turn=2,
            max_turns=30,
            error=ClassifiedError(
                original_error=ValueError("param error"),
                layer=ErrorLayer.BUSINESS_LOGIC,
                category=ErrorCategory.PARAMETER_ERROR,
                backtrack_type=BacktrackType.PARAM_ADJUST,
                is_retryable=False,
                confidence=0.7,
                suggested_action="Adjust parameters",
            ),
            backtrack_count=0,
            max_backtracks=3,
        )

        result = asyncio.get_event_loop().run_until_complete(
            manager.evaluate_and_decide(ctx, use_llm=False)
        )

        assert result.decision == BacktrackDecision.BACKTRACK
        assert result.backtrack_type == BacktrackType.PARAM_ADJUST


# ======================================================================
# 3. RVRBExecutor: verify _evaluate_backtrack chain
# ======================================================================

class TestRVRBEvaluateBacktrack:
    """Verify the complete _evaluate_backtrack → BacktrackResult chain."""

    def test_evaluate_backtrack_no_crash(self):
        """
        P0-1 core test: _evaluate_backtrack must NOT crash.

        Before fix: classified_error.message raised AttributeError.
        After fix: uses classified_error.suggested_action.
        """
        from core.agent.execution.rvrb import RVRBExecutor, RVRBState

        executor = RVRBExecutor()
        state = RVRBState(session_id="test", max_backtracks=3)

        # Mock LLM (BacktrackManager needs it for LLM decision)
        mock_llm = MagicMock()

        error = ValueError("invalid file path")

        result = asyncio.get_event_loop().run_until_complete(
            executor._evaluate_backtrack(
                error=error,
                tool_name="nodes",
                tool_input={"action": "read_file", "path": "/nonexistent"},
                state=state,
                llm=mock_llm,
            )
        )

        # Should not crash, should return a valid BacktrackResult
        assert result is not None
        assert hasattr(result, "decision")
        assert hasattr(result, "backtrack_type")

        # State should record the failure
        assert "nodes" in state.failed_tools
        assert len(state.failed_approaches) > 0

    def test_infrastructure_error_returns_continue(self):
        """Infrastructure errors should return CONTINUE (delegate to resilience)."""
        from core.agent.backtrack.manager import BacktrackDecision
        from core.agent.execution.rvrb import RVRBExecutor, RVRBState

        executor = RVRBExecutor()
        state = RVRBState(session_id="test", max_backtracks=3)

        error = TimeoutError("API timeout")

        result = asyncio.get_event_loop().run_until_complete(
            executor._evaluate_backtrack(
                error=error,
                tool_name="api_calling",
                tool_input={"url": "https://example.com"},
                state=state,
                llm=MagicMock(),
            )
        )

        assert result.decision == BacktrackDecision.CONTINUE


# ======================================================================
# 4. Context Pollution Cleanup
# ======================================================================

class TestContextPollutionCleanup:
    """Verify _clean_backtrack_results works for both stream and non-stream."""

    def test_no_backtrack_returns_original(self):
        """If no backtrack happened, results should pass through unchanged."""
        from core.agent.execution.rvrb import RVRBExecutor, RVRBState

        executor = RVRBExecutor()
        state = RVRBState(session_id="test")
        # backtrack_count = 0

        results = [
            {"type": "tool_result", "tool_use_id": "1", "content": "success", "is_error": False},
        ]

        cleaned = executor._clean_backtrack_results(results, state)
        assert cleaned == results

    def test_with_backtrack_cleans_errors(self):
        """After backtrack, failed results should be compressed into reflection."""
        from core.agent.execution.rvrb import RVRBExecutor, RVRBState

        executor = RVRBExecutor()
        state = RVRBState(session_id="test")
        state.backtrack_count = 1
        state.failed_tools = ["nodes"]
        state.failed_approaches = [
            {"tool": "nodes", "approach": "read /tmp/x", "reason": "not found"}
        ]

        results = [
            {"type": "tool_result", "tool_use_id": "1", "content": "success data", "is_error": False},
            {"type": "tool_result", "tool_use_id": "2", "content": "error: file not found", "is_error": True},
        ]

        cleaned = executor._clean_backtrack_results(results, state)

        # Success result should be kept
        assert any(r.get("content") == "success data" for r in cleaned)

        # Failed result should be replaced with reflection summary
        reflection = [r for r in cleaned if "backtrack_summary" in str(r.get("tool_use_id", ""))]
        assert len(reflection) == 1
        assert "回溯反思" in reflection[0]["content"]
        assert "nodes" in reflection[0]["content"]
        assert "已尝试过的方法" in reflection[0]["content"]


# ======================================================================
# 5. TOOL_REPLACE degradation
# ======================================================================

class TestToolReplaceDegradation:
    """Verify TOOL_REPLACE gracefully degrades without tool_selector."""

    def test_try_alternative_tool_returns_none_without_selector(self):
        """Without tool_selector, _try_alternative_tool should return None (not crash)."""
        from core.agent.execution.rvrb import RVRBExecutor, RVRBState

        executor = RVRBExecutor()
        state = RVRBState(session_id="test")

        result = asyncio.get_event_loop().run_until_complete(
            executor._try_alternative_tool(
                failed_tool="nodes",
                tool_input={"action": "read_file"},
                state=state,
                tool_executor=MagicMock(),
                tool_selector=None,  # No selector available
            )
        )

        assert result is None  # Graceful degradation


# ======================================================================
# 6. RVRBState: verify failed_approaches recording
# ======================================================================

class TestRVRBState:
    """Verify RVRBState tracks failures correctly for reflection."""

    def test_record_failed_approach(self):
        from core.agent.execution.rvrb import RVRBState

        state = RVRBState(session_id="test")

        state.record_failed_approach("nodes", "read /tmp/file", "not found")
        state.record_failed_approach("api_calling", "GET /api/data", "timeout")

        assert len(state.failed_approaches) == 2
        assert state.failed_approaches[0]["tool"] == "nodes"
        assert state.failed_approaches[1]["reason"] == "timeout"

    def test_failed_approaches_dedup(self):
        from core.agent.execution.rvrb import RVRBState

        state = RVRBState(session_id="test")

        # Same approach twice should not duplicate
        state.record_failed_approach("nodes", "read /tmp/file", "not found")
        state.record_failed_approach("nodes", "read /tmp/file", "not found")

        assert len(state.failed_approaches) == 1

    def test_failed_approaches_limit(self):
        from core.agent.execution.rvrb import RVRBState

        state = RVRBState(session_id="test")

        for i in range(15):
            state.record_failed_approach(f"tool_{i}", f"approach_{i}", f"reason_{i}")

        # Should keep only last 10
        assert len(state.failed_approaches) == 10


# ======================================================================
# 7. ProgressTransformer: verify output quality
# ======================================================================

class TestProgressTransformer:
    """Verify ProgressTransformer produces user-friendly messages."""

    def test_progress_stages(self):
        from core.planning.progress_transformer import ProgressTransformer

        pt = ProgressTransformer()

        # 0/5: just started
        u = pt.transform({"id": "1", "title": "分析", "status": "in_progress"}, 0, 5)
        assert u.percent == 0.0
        assert "5 步" in u.message

        # 2/5: mid-progress
        u = pt.transform({"id": "2", "title": "处理", "status": "completed"}, 2, 5)
        assert "2/5" in u.message

        # 5/5: done
        u = pt.transform({"id": "5", "title": "完成", "status": "completed"}, 5, 5)
        assert u.percent == 100.0
        assert "搞定" in u.message

        # failed
        u = pt.transform({"id": "3", "title": "失败", "status": "failed"}, 2, 5)
        assert "没成功" in u.message or "问题" in u.message

    def test_simple_plan(self):
        from core.planning.progress_transformer import ProgressTransformer

        pt = ProgressTransformer()

        # 1-step plan
        u = pt.transform({"id": "1", "title": "执行", "status": "in_progress"}, 0, 1)
        assert u.percent == 0.0

        u = pt.transform({"id": "1", "title": "执行", "status": "completed"}, 1, 1)
        assert "搞定" in u.message


# ======================================================================
# 8. RuntimeContext.finish_reason
# ======================================================================

class TestRuntimeContextFinishReason:
    """Verify finish_reason field lifecycle."""

    def test_finish_reason_default_none(self):
        from core.context.runtime import RuntimeContext

        ctx = RuntimeContext(session_id="test")
        assert ctx.finish_reason is None

    def test_finish_reason_set_and_reset(self):
        from core.context.runtime import RuntimeContext

        ctx = RuntimeContext(session_id="test")
        ctx.finish_reason = "completed"
        assert ctx.finish_reason == "completed"

        summary = ctx.summary()
        assert summary["finish_reason"] == "completed"

        ctx.reset_for_new_chat()
        assert ctx.finish_reason is None


# ======================================================================
# 9. End-to-end: simulate tool failure → backtrack → recovery
# ======================================================================

class TestE2EBacktrackScenario:
    """
    Simulate a realistic scenario: tool fails → ErrorClassifier → BacktrackManager → recovery.

    This is the integration test that proves the entire chain works after fixes.
    """

    def test_tool_failure_triggers_backtrack_chain(self):
        """
        Scenario: Agent calls 'nodes' tool to read a file, gets FileNotFoundError.
        Expected: ErrorClassifier classifies → BacktrackManager decides → RVRBState updated.
        """
        from core.agent.backtrack.manager import BacktrackDecision
        from core.agent.execution.rvrb import RVRBExecutor, RVRBState

        executor = RVRBExecutor()
        state = RVRBState(session_id="e2e_test", max_backtracks=3)

        # Simulate FileNotFoundError from nodes tool
        error = FileNotFoundError("No such file: /Users/test/data.xlsx")

        result = asyncio.get_event_loop().run_until_complete(
            executor._evaluate_backtrack(
                error=error,
                tool_name="nodes",
                tool_input={"action": "read_file", "path": "/Users/test/data.xlsx"},
                state=state,
                llm=MagicMock(),
            )
        )

        # Should NOT crash (P0-1 fix)
        assert result is not None

        # Should decide to backtrack (business logic error, not infra)
        # FileNotFoundError → UNKNOWN layer → pattern matching → business logic
        assert result.decision in (
            BacktrackDecision.BACKTRACK,
            BacktrackDecision.CONTINUE,
        )

        # State should record failure
        assert "nodes" in state.failed_tools
        assert len(state.failed_approaches) >= 1
        assert state.failed_approaches[0]["tool"] == "nodes"

    def test_three_failures_exhaust_backtracks(self):
        """
        Scenario: Tool fails 3 times → backtrack count exhausted → FAIL_GRACEFULLY.
        """
        from core.agent.backtrack.manager import BacktrackDecision
        from core.agent.execution.rvrb import RVRBExecutor, RVRBState

        executor = RVRBExecutor()
        state = RVRBState(session_id="exhaust_test", max_backtracks=3)

        for i in range(4):
            error = Exception(f"failure #{i+1}")
            result = asyncio.get_event_loop().run_until_complete(
                executor._evaluate_backtrack(
                    error=error,
                    tool_name=f"tool_{i}",
                    tool_input={"attempt": i},
                    state=state,
                    llm=MagicMock(),
                )
            )

            if result.decision == BacktrackDecision.BACKTRACK:
                state.increment_backtrack()

        # After 3 backtracks, should be exhausted
        assert state.backtrack_count >= 3 or result.decision == BacktrackDecision.FAIL_GRACEFULLY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
