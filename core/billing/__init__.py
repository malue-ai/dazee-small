"""
Billing 模块 - 统一的 Token 计费管理

核心功能：
- 记录每次 LLM 调用（model, tokens, price）
- 支持多模型调用追踪
- 自动计算价格（包含缓存）
- Message ID 去重
- 生成聚合统计报告

模块结构：
- models.py: 计费数据模型（LLMCallRecord, UsageResponse）
- tracker.py: EnhancedUsageTracker（统一实现）
- pricing.py: 模型定价表和成本计算

使用示例：
    from core.billing import EnhancedUsageTracker, UsageResponse
    
    # 创建 tracker
    tracker = EnhancedUsageTracker()
    
    # 记录调用
    tracker.record_call(
        llm_response=response,
        model="claude-sonnet-4",
        purpose="main_response",
        message_id=response.id
    )
    
    # 生成响应（包含调用明细）
    usage = UsageResponse.from_tracker(tracker, latency=4.0)
"""

from core.billing.models import LLMCallRecord, UsageResponse
from core.billing.tracker import EnhancedUsageTracker, create_enhanced_usage_tracker
from core.billing.pricing import (
    calculate_cost,
    get_pricing_for_model,
    estimate_monthly_cost,
)

# 重导出定价表（延迟导入以避免循环依赖）
def get_model_pricing(model: str):
    """获取模型定价（延迟导入）"""
    from models.usage import get_model_pricing as _get_model_pricing
    return _get_model_pricing(model)

def get_claude_pricing():
    """获取 CLAUDE_PRICING（延迟导入）"""
    from models.usage import CLAUDE_PRICING as _CLAUDE_PRICING
    return _CLAUDE_PRICING

CLAUDE_PRICING = None  # 占位，实际使用时调用 get_claude_pricing()

# 统一别名
UsageTracker = EnhancedUsageTracker
create_usage_tracker = create_enhanced_usage_tracker

__all__ = [
    # 数据模型
    "LLMCallRecord",
    "UsageResponse",
    # Tracker
    "EnhancedUsageTracker",
    "UsageTracker",
    "create_enhanced_usage_tracker",
    "create_usage_tracker",
    # 定价
    "CLAUDE_PRICING",
    "get_model_pricing",
    "get_pricing_for_model",
    "calculate_cost",
    "estimate_monthly_cost",
]
