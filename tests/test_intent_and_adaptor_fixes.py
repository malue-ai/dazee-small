"""
Smoke + functional tests for the intent analyzer and adaptor fixes.

Covers:
- P0-1: _get_conservative_default returns relevant_skill_groups=None
- P0-2: tool_choice structured output (classify_intent tool definition)
- P1-1: orphan tool_use → text summary
- P1-2: follow-up tasks skip simple tool pruning

Run: python -m pytest tests/test_intent_and_adaptor_fixes.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List


# ============================================================
# P0-1: Conservative default — relevant_skill_groups=None
# ============================================================

class TestConservativeDefault:
    """_get_conservative_default must return None (full fallback), not []."""

    def test_conservative_default_skill_groups_is_none(self):
        from core.routing.intent_analyzer import IntentAnalyzer

        analyzer = IntentAnalyzer(llm_service=None, enable_llm=False)
        result = analyzer._get_conservative_default()

        assert result.relevant_skill_groups is None, (
            f"Expected None (full fallback), got {result.relevant_skill_groups!r}"
        )

    def test_conservative_default_complexity_is_medium(self):
        from core.routing.intent_analyzer import IntentAnalyzer
        from core.routing.types import Complexity

        analyzer = IntentAnalyzer(llm_service=None, enable_llm=False)
        result = analyzer._get_conservative_default()

        assert result.complexity == Complexity.MEDIUM

    def test_conservative_default_confidence_is_low(self):
        from core.routing.intent_analyzer import IntentAnalyzer

        analyzer = IntentAnalyzer(llm_service=None, enable_llm=False)
        result = analyzer._get_conservative_default()

        assert result.confidence == 0.3


# ============================================================
# P0-1 supplement: IntentResult type supports None
# ============================================================

class TestIntentResultNone:
    """IntentResult.relevant_skill_groups can be None."""

    def test_intent_result_default_is_none(self):
        from core.routing.types import IntentResult, Complexity

        result = IntentResult(complexity=Complexity.SIMPLE, skip_memory=False)
        assert result.relevant_skill_groups is None

    def test_intent_result_to_dict_handles_none(self):
        from core.routing.types import IntentResult, Complexity

        result = IntentResult(complexity=Complexity.SIMPLE, skip_memory=False)
        d = result.to_dict()
        assert d["relevant_skill_groups"] == []  # serialized as empty list

    def test_intent_result_accepts_list(self):
        from core.routing.types import IntentResult, Complexity

        result = IntentResult(
            complexity=Complexity.MEDIUM,
            skip_memory=False,
            relevant_skill_groups=["app_automation", "file_operations"],
        )
        assert result.relevant_skill_groups == ["app_automation", "file_operations"]


# ============================================================
# P0-2: classify_intent tool definition
# ============================================================

class TestIntentToolDefinition:
    """The classify_intent tool schema must be valid and complete."""

    def test_tool_schema_has_all_required_fields(self):
        from core.routing.intent_analyzer import _INTENT_TOOL

        schema = _INTENT_TOOL["input_schema"]
        required = set(schema["required"])
        expected = {
            "complexity", "skip_memory", "is_follow_up",
            "wants_to_stop", "wants_rollback", "relevant_skill_groups",
        }
        assert required == expected, f"Missing: {expected - required}"

    def test_tool_schema_complexity_enum(self):
        from core.routing.intent_analyzer import _INTENT_TOOL

        props = _INTENT_TOOL["input_schema"]["properties"]
        assert props["complexity"]["enum"] == ["simple", "medium", "complex"]

    def test_tool_name_constant(self):
        from core.routing.intent_analyzer import _INTENT_TOOL, _INTENT_TOOL_NAME

        assert _INTENT_TOOL["name"] == _INTENT_TOOL_NAME
        assert _INTENT_TOOL_NAME == "classify_intent"


# ============================================================
# P0-2: _parse_intent_dict (from tool_call input)
# ============================================================

class TestParseIntentDict:
    """_parse_intent_dict correctly parses structured tool output."""

    def _analyzer(self):
        from core.routing.intent_analyzer import IntentAnalyzer
        return IntentAnalyzer(llm_service=None, enable_llm=False)

    def test_parse_valid_dict(self):
        from core.routing.types import Complexity

        result = self._analyzer()._parse_intent_dict({
            "complexity": "complex",
            "skip_memory": True,
            "is_follow_up": False,
            "wants_to_stop": False,
            "wants_rollback": False,
            "relevant_skill_groups": ["data_analysis", "file_operations"],
        })

        assert result.complexity == Complexity.COMPLEX
        assert result.skip_memory is True
        assert result.relevant_skill_groups == ["data_analysis", "file_operations"]

    def test_parse_invalid_complexity_defaults_to_medium(self):
        from core.routing.types import Complexity

        result = self._analyzer()._parse_intent_dict({
            "complexity": "ultra_hard",
            "skip_memory": False,
            "is_follow_up": False,
            "wants_to_stop": False,
            "wants_rollback": False,
            "relevant_skill_groups": [],
        })

        assert result.complexity == Complexity.MEDIUM

    def test_parse_missing_fields_use_defaults(self):
        result = self._analyzer()._parse_intent_dict({})

        assert result.skip_memory is False
        assert result.is_follow_up is False
        assert result.wants_to_stop is False
        assert result.relevant_skill_groups == []

    def test_parse_non_bool_coerced(self):
        result = self._analyzer()._parse_intent_dict({
            "complexity": "simple",
            "skip_memory": "yes",  # not a bool
            "is_follow_up": 1,     # not a bool
            "wants_to_stop": False,
            "wants_rollback": False,
            "relevant_skill_groups": ["a"],
        })

        assert result.skip_memory is False  # coerced to default
        assert result.is_follow_up is False  # coerced to default


# ============================================================
# P0-2: _supplement_skill_groups skips when None
# ============================================================

class TestSupplementSkillGroups:
    """supplement must skip when relevant_skill_groups is None."""

    def test_skip_when_none(self):
        from core.routing.intent_analyzer import IntentAnalyzer
        from core.routing.types import IntentResult, Complexity

        analyzer = IntentAnalyzer(llm_service=None, enable_llm=False)
        result = IntentResult(
            complexity=Complexity.MEDIUM,
            skip_memory=False,
            relevant_skill_groups=None,
        )

        supplemented = analyzer._supplement_skill_groups(result, "some query")
        assert supplemented.relevant_skill_groups is None  # unchanged


# ============================================================
# P1-1: Orphan tool_use → text summary
# ============================================================

class TestOrphanToolUseSummary:
    """Orphan tool_use blocks should be converted to text summaries."""

    def test_summarize_orphan_tool_use_basic(self):
        from core.llm.adaptor import ClaudeAdaptor

        block = {
            "type": "tool_use",
            "id": "toolu_123",
            "name": "nodes",
            "input": {"action": "run", "command": ["open", "file.xlsx"]},
        }
        summary = ClaudeAdaptor._summarize_orphan_tool_use(block)

        assert "[之前调用了 nodes" in summary
        assert "结果未记录]" in summary
        assert "action=run" in summary

    def test_summarize_orphan_truncates_long_values(self):
        from core.llm.adaptor import ClaudeAdaptor

        block = {
            "type": "tool_use",
            "id": "toolu_456",
            "name": "execute",
            "input": {"code": "x" * 100},
        }
        summary = ClaudeAdaptor._summarize_orphan_tool_use(block)

        # Value should be truncated (40 chars + "...")
        assert len(summary) < 200

    def test_summarize_orphan_empty_input(self):
        from core.llm.adaptor import ClaudeAdaptor

        block = {
            "type": "tool_use",
            "id": "toolu_789",
            "name": "status",
            "input": {},
        }
        summary = ClaudeAdaptor._summarize_orphan_tool_use(block)

        assert summary == "[之前调用了 status，结果未记录]"

    def test_ensure_tool_pairs_keeps_summaries(self):
        """Orphan tool_use should become text summary, not disappear."""
        from core.llm.adaptor import ClaudeAdaptor

        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hello"}],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me help."},
                    {"type": "tool_use", "id": "t1", "name": "nodes", "input": {"action": "run"}},
                ],
            },
            # No tool_result for t1 → orphan
            {
                "role": "user",
                "content": [{"type": "text", "text": "what happened?"}],
            },
        ]

        cleaned = ClaudeAdaptor.ensure_tool_pairs(messages)

        # The assistant message should still exist with text + summary
        assistant_msgs = [m for m in cleaned if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1

        content = assistant_msgs[0]["content"]
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]
        combined = " ".join(texts)

        assert "Let me help" in combined
        assert "之前调用了 nodes" in combined

    def test_ensure_tool_pairs_max_summaries(self):
        """Only the most recent MAX_ORPHAN_SUMMARIES orphans get summaries."""
        from core.llm.adaptor import ClaudeAdaptor

        # Create 15 orphan tool_use blocks (cap is 10)
        blocks = []
        for i in range(15):
            blocks.append({"type": "tool_use", "id": f"t{i}", "name": f"tool_{i}", "input": {}})

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "start"}]},
            {"role": "assistant", "content": blocks},
            {"role": "user", "content": [{"type": "text", "text": "end"}]},
        ]

        cleaned = ClaudeAdaptor.ensure_tool_pairs(messages)

        # Count text blocks containing summaries in assistant messages
        summary_count = 0
        for msg in cleaned:
            if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
                for b in msg["content"]:
                    if isinstance(b, dict) and b.get("type") == "text" and "之前调用了" in b.get("text", ""):
                        summary_count += 1

        assert summary_count == 10, f"Expected 10 summaries (cap), got {summary_count}"


# ============================================================
# P1-2: Follow-up tasks skip tool pruning
# ============================================================

class TestFollowUpNoToolPrune:
    """is_follow_up=True should prevent simple task tool pruning."""

    def test_is_simple_task_false_when_follow_up(self):
        """Simulate the is_simple_task logic from base.py."""
        from core.routing.types import IntentResult, Complexity

        intent = IntentResult(
            complexity=Complexity.SIMPLE,
            skip_memory=False,
            is_follow_up=True,
        )

        # Replicate the condition from core/agent/base.py
        is_simple_task = (
            intent
            and intent.complexity.value == "simple"
            and not intent.needs_plan
            and not None  # plan
            and not intent.is_follow_up
        )

        assert is_simple_task is False, "Follow-up should NOT be pruned"

    def test_is_simple_task_true_when_not_follow_up(self):
        from core.routing.types import IntentResult, Complexity

        intent = IntentResult(
            complexity=Complexity.SIMPLE,
            skip_memory=False,
            is_follow_up=False,
        )

        is_simple_task = (
            intent
            and intent.complexity.value == "simple"
            and not intent.needs_plan
            and not None  # plan
            and not intent.is_follow_up
        )

        assert is_simple_task is True, "Non-follow-up simple should be pruned"


# ============================================================
# P0-2: Claude client tool_choice passthrough
# ============================================================

class TestClaudeToolChoice:
    """Claude client should pass tool_choice from kwargs to request_params."""

    def test_tool_choice_in_request_params(self):
        """Verify tool_choice is included when tools and tool_choice are provided."""
        # This is a code-level verification, not a live API call
        # We check that the code path exists by importing and inspecting
        import inspect
        from core.llm.claude import ClaudeLLMService

        source = inspect.getsource(ClaudeLLMService.create_message_async)
        assert 'tool_choice' in source, "tool_choice handling must exist in create_message_async"
        assert 'kwargs.get("tool_choice")' in source, "tool_choice must be read from kwargs"
