"""
动态上下文窗口单元测试

Tests:
- ModelPricing tiered pricing (estimate_cost with long_context_threshold)
- ContextStrategy model-aware (get_context_strategy with model_name)
- ContextWindowManager state machine (check/apply/decline)
"""

import pytest
from unittest.mock import patch, MagicMock

from core.context.compaction import ContextStrategy
from core.context.window_manager import ContextWindowManager


class TestModelPricingTiers:
    """验证阶梯计价 estimate_cost() 的分段计费正确性"""

    def test_standard_pricing_below_threshold(self):
        """200K 以内: 标准价"""
        from core.llm.model_registry import ModelPricing

        pricing = ModelPricing(
            input_per_million=15.0,
            output_per_million=75.0,
            long_context_threshold=200_000,
            long_context_input_per_million=30.0,
            long_context_output_per_million=112.5,
        )
        cost = pricing.estimate_cost(input_tokens=150_000, output_tokens=5000)
        expected = 150_000 * 15.0 / 1_000_000 + 5000 * 75.0 / 1_000_000
        assert cost == pytest.approx(expected)

    def test_long_context_pricing_above_threshold(self):
        """超过 200K: 全会话按长上下文费率"""
        from core.llm.model_registry import ModelPricing

        pricing = ModelPricing(
            input_per_million=15.0,
            output_per_million=75.0,
            long_context_threshold=200_000,
            long_context_input_per_million=30.0,
            long_context_output_per_million=112.5,
        )
        cost = pricing.estimate_cost(input_tokens=500_000, output_tokens=10000)
        expected = 500_000 * 30.0 / 1_000_000 + 10000 * 112.5 / 1_000_000
        assert cost == pytest.approx(expected)

    def test_no_threshold_flat_pricing(self):
        """无阶梯的模型: 全部走标准价"""
        from core.llm.model_registry import ModelPricing

        pricing = ModelPricing(
            input_per_million=1.20,
            output_per_million=6.0,
        )
        cost = pricing.estimate_cost(input_tokens=500_000, output_tokens=10000)
        expected = 500_000 * 1.20 / 1_000_000 + 10000 * 6.0 / 1_000_000
        assert cost == pytest.approx(expected)

    def test_free_pricing_returns_none(self):
        """免费模型返回 None"""
        from core.llm.model_registry import ModelPricing

        pricing = ModelPricing()
        assert pricing.estimate_cost(input_tokens=100000) is None

    def test_gpt54_full_session_billing(self):
        """GPT-5.4: 超过 272K 后全会话加价"""
        from core.llm.model_registry import ModelPricing

        pricing = ModelPricing(
            input_per_million=2.50,
            output_per_million=15.0,
            long_context_threshold=272_000,
            long_context_input_per_million=5.0,
            long_context_output_per_million=22.5,
        )
        cost = pricing.estimate_cost(input_tokens=300_000, output_tokens=5000)
        expected = 300_000 * 5.0 / 1_000_000 + 5000 * 22.5 / 1_000_000
        assert cost == pytest.approx(expected)


class TestModelCapabilitiesExtended:
    """验证 max_extended_input_tokens 字段"""

    def test_claude_has_extended(self):
        from core.llm.model_registry import ModelCapabilities

        caps = ModelCapabilities(
            max_input_tokens=200_000,
            max_extended_input_tokens=1_000_000,
        )
        assert caps.max_extended_input_tokens == 1_000_000

    def test_qwen_no_extended(self):
        from core.llm.model_registry import ModelCapabilities

        caps = ModelCapabilities(max_input_tokens=258_048)
        assert caps.max_extended_input_tokens is None


class TestContextStrategy:
    """验证 get_context_strategy 按模型名返回正确策略"""

    def test_model_aware_budget(self):
        """指定模型名时从 ModelRegistry 获取 token_budget"""
        with patch("core.llm.model_registry.ModelRegistry") as mock_reg:
            mock_cfg = MagicMock()
            mock_cfg.capabilities.max_input_tokens = 200_000
            mock_cfg.capabilities.max_extended_input_tokens = 1_000_000
            mock_reg.get.return_value = mock_cfg

            from core.context.compaction import get_context_strategy

            strategy = get_context_strategy(model_name="claude-opus-4-6")
            assert strategy.token_budget == 200_000
            assert strategy.max_expandable_budget == 1_000_000
            assert strategy.model_name == "claude-opus-4-6"

    def test_fallback_when_model_not_found(self):
        """模型未找到时回退到 QoS 默认值"""
        with patch("core.llm.model_registry.ModelRegistry") as mock_reg:
            mock_reg.get.return_value = None

            from core.context.compaction import get_context_strategy

            strategy = get_context_strategy(model_name="unknown-model")
            assert strategy.token_budget == 200_000  # QOS_TOKEN_BUDGETS[PRO]
            assert strategy.max_expandable_budget is None


class TestContextWindowManager:
    """验证 ContextWindowManager 状态机"""

    def _make_manager(self, budget=200_000, expandable=1_000_000, threshold=0.90):
        strategy = ContextStrategy(
            token_budget=budget,
            max_expandable_budget=expandable,
            expansion_hitl_threshold=threshold,
            model_name="claude-opus-4-6",
        )
        return ContextWindowManager(strategy), strategy

    def test_expansion_trigger_at_threshold(self):
        """90% 使用率触发扩展信号"""
        mgr, _ = self._make_manager()
        result = mgr.check_expansion_needed(180_000)
        assert result is not None
        assert result.current_tokens == 180_000
        assert result.expanded_budget == 1_000_000

    def test_no_trigger_below_threshold(self):
        """低于 90% 不触发"""
        mgr, _ = self._make_manager()
        assert mgr.check_expansion_needed(170_000) is None

    def test_no_expansion_if_unsupported(self):
        """不支持扩展的模型不触发"""
        mgr, _ = self._make_manager(expandable=None)
        assert mgr.check_expansion_needed(195_000) is None

    def test_apply_updates_budget(self):
        """apply_expansion 更新 token_budget"""
        mgr, strategy = self._make_manager()
        mgr.apply_expansion()
        assert strategy.token_budget == 1_000_000
        assert strategy.is_expanded is True

    def test_no_repeat_ask_after_decline(self):
        """拒绝后不重复询问"""
        mgr, _ = self._make_manager()
        mgr.decline_expansion()
        assert mgr.check_expansion_needed(195_000) is None

    def test_no_repeat_ask_after_apply(self):
        """同意后不重复询问"""
        mgr, _ = self._make_manager()
        mgr.apply_expansion()
        assert mgr.check_expansion_needed(900_000) is None

    def test_can_expand_property(self):
        """can_expand 属性"""
        mgr, _ = self._make_manager()
        assert mgr.can_expand is True
        mgr.decline_expansion()
        assert mgr.can_expand is False
