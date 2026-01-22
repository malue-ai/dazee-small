"""
Usage Tracking 端到端测试

测试内容：
1. UsageTracker 基础功能
2. UsageResponse 模型
3. 成本计算
4. thinking_tokens 跟踪
5. 多智能体场景
"""

import pytest
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock


# ============================================================
# 1. UsageTracker 测试
# ============================================================

class TestUsageTracker:
    """UsageTracker 单元测试"""
    
    def test_init(self):
        """测试初始化"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        stats = tracker.get_stats()
        
        assert stats["total_input_tokens"] == 0
        assert stats["total_output_tokens"] == 0
        assert stats["total_thinking_tokens"] == 0
        assert stats["total_cache_read_tokens"] == 0
        assert stats["total_cache_creation_tokens"] == 0
        assert stats["llm_calls"] == 0
    
    def test_accumulate(self):
        """测试累积 usage"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        # 模拟 LLM 响应
        mock_response = MagicMock()
        mock_response.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 20,
            "cache_read_tokens": 30,
            "cache_creation_tokens": 10
        }
        
        tracker.accumulate(mock_response)
        
        stats = tracker.get_stats()
        assert stats["total_input_tokens"] == 100
        assert stats["total_output_tokens"] == 50
        assert stats["total_thinking_tokens"] == 20
        assert stats["total_cache_read_tokens"] == 30
        assert stats["total_cache_creation_tokens"] == 10
        assert stats["llm_calls"] == 1
    
    def test_accumulate_multiple(self):
        """测试多次累积"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        for i in range(3):
            mock_response = MagicMock()
            mock_response.usage = {
                "input_tokens": 100,
                "output_tokens": 50,
                "thinking_tokens": 10
            }
            tracker.accumulate(mock_response)
        
        stats = tracker.get_stats()
        assert stats["total_input_tokens"] == 300
        assert stats["total_output_tokens"] == 150
        assert stats["total_thinking_tokens"] == 30
        assert stats["llm_calls"] == 3
    
    def test_accumulate_from_dict(self):
        """测试从字典累积"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        tracker.accumulate_from_dict({
            "input_tokens": 200,
            "output_tokens": 100,
            "thinking_tokens": 50,
            "cache_read_tokens": 80
        })
        
        stats = tracker.get_stats()
        assert stats["total_input_tokens"] == 200
        assert stats["total_output_tokens"] == 100
        assert stats["total_thinking_tokens"] == 50
        assert stats["total_cache_read_tokens"] == 80
    
    def test_get_total_tokens(self):
        """测试总 token 计算"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        mock_response = MagicMock()
        mock_response.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 30
        }
        tracker.accumulate(mock_response)
        
        # 总 token = input + output + thinking
        assert tracker.get_total_tokens() == 180
    
    def test_get_cost_estimate(self):
        """测试成本估算"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        mock_response = MagicMock()
        mock_response.usage = {
            "input_tokens": 1_000_000,  # 1M tokens
            "output_tokens": 1_000_000,  # 1M tokens
        }
        tracker.accumulate(mock_response)
        
        # Claude Sonnet 4.5: $3/M input + $15/M output = $18
        cost = tracker.get_cost_estimate()
        assert cost == pytest.approx(18.0, rel=0.01)
    
    def test_snapshot(self):
        """测试快照"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        mock_response = MagicMock()
        mock_response.usage = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_tokens": 200
        }
        tracker.accumulate(mock_response)
        
        snapshot = tracker.snapshot()
        
        assert "total_tokens" in snapshot
        assert "estimated_cost_usd" in snapshot
        assert "average_input_per_call" in snapshot
        assert "average_output_per_call" in snapshot
        assert "cache_hit_rate" in snapshot
    
    def test_reset(self):
        """测试重置"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        mock_response = MagicMock()
        mock_response.usage = {"input_tokens": 100, "output_tokens": 50}
        tracker.accumulate(mock_response)
        
        tracker.reset()
        
        stats = tracker.get_stats()
        assert stats["total_input_tokens"] == 0
        assert stats["llm_calls"] == 0
    
    def test_to_usage_response(self):
        """测试转换为 UsageResponse"""
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        mock_response = MagicMock()
        mock_response.usage = {
            "input_tokens": 10000,
            "output_tokens": 5000,
            "thinking_tokens": 1000
        }
        tracker.accumulate(mock_response)
        
        usage_response = tracker.to_usage_response(
            model="claude-sonnet-4.5",
            latency=5.5
        )
        
        assert usage_response.prompt_tokens == 10000
        assert usage_response.completion_tokens == 5000
        assert usage_response.thinking_tokens == 1000
        assert usage_response.latency == 5.5
        assert float(usage_response.total_price) > 0


# ============================================================
# 2. UsageResponse 测试
# ============================================================

class TestUsageResponse:
    """UsageResponse 模型测试"""
    
    def test_from_usage_tracker(self):
        """测试从 UsageTracker 创建"""
        from models.usage import UsageResponse
        from utils.usage_tracker import UsageTracker
        
        tracker = UsageTracker()
        
        mock_response = MagicMock()
        mock_response.usage = {
            "input_tokens": 229304,
            "output_tokens": 684,
            "cache_read_tokens": 50000
        }
        tracker.accumulate(mock_response)
        
        usage = UsageResponse.from_tracker(
            tracker=tracker,
            latency=8.117
        )
        
        assert usage.prompt_tokens == 229304
        assert usage.completion_tokens == 684
        assert usage.total_tokens == 229988
        assert usage.currency == "USD"
        assert usage.latency == 8.117
        assert float(usage.prompt_price) > 0
        assert float(usage.completion_price) > 0
        assert float(usage.total_price) > 0
    
    def test_from_dict(self):
        """测试从字典创建"""
        from models.usage import UsageResponse
        
        usage = UsageResponse.from_dict({
            "input_tokens": 10000,
            "output_tokens": 5000,
            "thinking_tokens": 1000
        })
        
        assert usage.prompt_tokens == 10000
        assert usage.completion_tokens == 5000
        assert usage.thinking_tokens == 1000
    
    def test_cache_hit_rate(self):
        """测试缓存命中率计算"""
        from models.usage import UsageResponse
        
        usage = UsageResponse(
            prompt_tokens=80000,
            completion_tokens=5000,
            cache_read_tokens=20000,  # 20%
            total_tokens=105000
        )
        
        # cache_hit_rate = 20000 / (80000 + 20000) = 0.2
        assert usage.cache_hit_rate == pytest.approx(0.2, rel=0.01)
    
    def test_to_sse_event(self):
        """测试转换为 SSE 事件"""
        from models.usage import UsageResponse
        
        usage = UsageResponse(
            prompt_tokens=10000,
            completion_tokens=5000,
            total_tokens=15000,
            total_price="0.105"
        )
        
        event = usage.to_sse_event()
        
        assert event["event"] == "usage"
        assert event["data"]["prompt_tokens"] == 10000
        assert event["data"]["total_price"] == "0.105"
    
    def test_to_metadata(self):
        """测试转换为 metadata"""
        from models.usage import UsageResponse
        
        usage = UsageResponse(
            prompt_tokens=10000,
            completion_tokens=5000,
            total_tokens=15000,
            total_price="0.105",
            model="claude-sonnet-4.5"
        )
        
        metadata = usage.to_metadata()
        
        assert "usage" in metadata
        assert metadata["usage"]["prompt_tokens"] == 10000
        assert metadata["usage"]["model"] == "claude-sonnet-4.5"


# ============================================================
# 3. Pricing 测试
# ============================================================

class TestPricing:
    """定价和成本计算测试"""
    
    def test_get_model_pricing(self):
        """测试获取模型定价"""
        from models.usage import get_model_pricing
        
        pricing = get_model_pricing("claude-sonnet-4.5")
        
        assert pricing["input"] == 3.0
        assert pricing["output"] == 15.0
        assert pricing["cache_read"] == 0.3
        assert pricing["cache_write"] == 3.75
    
    def test_get_model_pricing_default(self):
        """测试默认定价"""
        from models.usage import get_model_pricing
        
        pricing = get_model_pricing("unknown-model")
        
        # 默认使用 Sonnet 价格
        assert pricing["input"] == 3.0
        assert pricing["output"] == 15.0
    
    def test_calculate_cost(self):
        """测试成本计算"""
        from core.billing.pricing import calculate_cost
        
        total, details = calculate_cost(
            input_tokens=1_000_000,
            output_tokens=100_000,
            model="claude-sonnet-4.5"
        )
        
        # $3 + $1.5 = $4.5
        assert total == pytest.approx(4.5, rel=0.01)
        assert details["input_cost"] == pytest.approx(3.0, rel=0.01)
        assert details["output_cost"] == pytest.approx(1.5, rel=0.01)
    
    def test_calculate_cost_with_cache(self):
        """测试带缓存的成本计算"""
        from core.billing.pricing import calculate_cost
        
        total, details = calculate_cost(
            input_tokens=500_000,
            output_tokens=100_000,
            cache_read_tokens=500_000,  # 50% 缓存命中
            model="claude-sonnet-4.5"
        )
        
        # input: 500K * $3/M = $1.5
        # output: 100K * $15/M = $1.5
        # cache_read: 500K * $0.3/M = $0.15
        # total = $3.15
        assert total == pytest.approx(3.15, rel=0.01)
        assert details["cache_read_cost"] == pytest.approx(0.15, rel=0.01)
    
    def test_estimate_monthly_cost(self):
        """测试月度成本估算"""
        from core.billing.pricing import estimate_monthly_cost
        
        estimate = estimate_monthly_cost(
            daily_requests=1000,
            avg_input_tokens_per_request=10000,
            avg_output_tokens_per_request=2000,
            model="claude-sonnet-4.5",
            cache_hit_rate=0.0
        )
        
        assert estimate["model"] == "claude-sonnet-4.5"
        assert estimate["monthly_requests"] == 30000
        assert estimate["total_cost"] > 0
        assert estimate["currency"] == "USD"


# ============================================================
# 4. 集成测试
# ============================================================

class TestIntegration:
    """集成测试"""
    
    def test_billing_module_imports(self):
        """测试 billing 模块导入"""
        from core.billing import (
            UsageTracker,
            create_usage_tracker,
            UsageResponse,
            UsageSummary,
            CLAUDE_PRICING,
            get_model_pricing,
            calculate_cost,
            estimate_monthly_cost,
        )
        
        # 验证导入成功
        assert UsageTracker is not None
        assert create_usage_tracker is not None
        assert UsageResponse is not None
        assert CLAUDE_PRICING is not None
    
    def test_full_workflow(self):
        """测试完整工作流"""
        from core.billing import (
            create_usage_tracker,
            UsageResponse,
            calculate_cost
        )
        
        # 1. 创建 tracker
        tracker = create_usage_tracker()
        
        # 2. 模拟多次 LLM 调用
        for i in range(3):
            mock_response = MagicMock()
            mock_response.usage = {
                "input_tokens": 10000 + i * 1000,
                "output_tokens": 2000 + i * 500,
                "thinking_tokens": 500 if i == 1 else 0,  # 只有第二次有 thinking
                "cache_read_tokens": 5000 if i > 0 else 0  # 后两次有缓存
            }
            tracker.accumulate(mock_response)
        
        # 3. 生成 UsageResponse
        usage = UsageResponse.from_tracker(
            tracker=tracker,
            latency=15.5
        )
        
        # 4. 验证结果
        assert usage.prompt_tokens == 33000  # 10000 + 11000 + 12000
        assert usage.completion_tokens == 7500  # 2000 + 2500 + 3000
        assert usage.thinking_tokens == 500
        assert usage.cache_read_tokens == 10000  # 0 + 5000 + 5000
        assert usage.llm_calls == 3
        assert usage.latency == 15.5
        assert float(usage.total_price) > 0
        
        # 5. 验证 SSE 事件
        event = usage.to_sse_event()
        assert event["event"] == "usage"
        
        # 6. 验证 metadata
        metadata = usage.to_metadata()
        assert metadata["usage"]["llm_calls"] == 3


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
