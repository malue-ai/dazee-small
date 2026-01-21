"""
Billing 模块 - 统一的 Token 计费管理

V7.5 重大重构：支持多模型调用记录和价格明细

模块结构：
- models.py: 计费数据模型（LLMCallRecord, UsageResponse）
- tracker.py: 增强的 UsageTracker（支持多模型 + Message ID 去重）
- pricing.py: 模型定价表和成本计算（统一来源）

使用示例：
    from core.billing import (
        EnhancedUsageTracker,
        UsageResponse,
        LLMCallRecord,
        get_pricing_for_model,
        calculate_cost
    )
    
    # 创建 tracker
    tracker = EnhancedUsageTracker()
    
    # 记录意图识别调用（Haiku）
    tracker.record_call(
        llm_response=intent_response,
        model="claude-haiku-4.5",
        purpose="intent_analysis"
    )
    
    # 记录主对话调用（Sonnet）
    tracker.record_call(
        llm_response=main_response,
        model="claude-sonnet-4.5",
        purpose="main_response"
    )
    
    # 生成响应（自动包含所有调用明细）
    usage = UsageResponse.from_tracker(tracker, latency=4.0)
"""

# 🆕 V7.5 新模块
from core.billing.models import LLMCallRecord, UsageResponse
from core.billing.tracker import EnhancedUsageTracker

# 定价和成本计算
from core.billing.pricing import (
    calculate_cost,
    get_pricing_for_model,
    estimate_monthly_cost,
)

# 定价数据
from core.billing.pricing_data import CLAUDE_PRICING, get_model_pricing

# 🔄 向后兼容：重导出旧接口
from utils.usage_tracker import UsageTracker, create_usage_tracker

__all__ = [
    # 🆕 V7.5 新接口（推荐）
    "LLMCallRecord",
    "UsageResponse",
    "EnhancedUsageTracker",
    # Pricing
    "CLAUDE_PRICING",
    "get_model_pricing",
    "get_pricing_for_model",
    "calculate_cost",
    "estimate_monthly_cost",
    # 🔄 旧接口（向后兼容）
    "UsageTracker",
    "create_usage_tracker",
]

