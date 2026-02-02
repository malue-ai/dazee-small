"""
Usage 响应模型 - 统一的 Token 使用和成本信息

参考 Dify 平台的计费响应格式，提供：
- Token 统计（input/output/thinking/cache）
- 成本计算（基于模型定价）
- 性能指标（延迟、调用次数）

架构位置：models/usage.py（定价表） + core/billing/models.py（UsageResponse）
使用场景：
- API 响应中返回计费信息
- SSE 事件流结束时发送 usage 事件
- 前端展示 token 消耗和成本
"""

from typing import Any, Dict, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

# 重导出 UsageResponse（统一使用 core/billing 版本）
from core.billing.models import UsageResponse, LLMCallRecord

# 从独立的定价数据模块导入（避免循环导入）
from core.billing.pricing_data import CLAUDE_PRICING, get_model_pricing

if TYPE_CHECKING:
    from core.billing.tracker import EnhancedUsageTracker


# ============================================================
# 重导出定价数据（向后兼容）
# ============================================================
__all__ = [
    "UsageResponse",
    "LLMCallRecord",
    "UsageSummary",
    "CLAUDE_PRICING",
    "get_model_pricing",
    "from_usage_tracker_helper",
]


# ========== 便捷方法（向后兼容）==========

def from_usage_tracker_helper(
    tracker: 'EnhancedUsageTracker',
    model: str = "claude-sonnet-4",
    latency: Optional[float] = None,
) -> UsageResponse:
    """
    从 EnhancedUsageTracker 创建 UsageResponse（便捷方法）
    
    内部调用 UsageResponse.from_tracker()，统一使用新版实现
    
    Args:
        tracker: EnhancedUsageTracker 实例
        model: 模型名称（用于设置主模型，如果 tracker 为空）
        latency: 总延迟（秒）
        
    Returns:
        UsageResponse 实例
    """
    return UsageResponse.from_tracker(tracker, latency=latency or 0.0)


# 添加到 UsageResponse 类的静态方法（向后兼容）
UsageResponse.from_usage_tracker = staticmethod(from_usage_tracker_helper)


class UsageSummary(BaseModel):
    """
    使用量摘要（用于统计页面）
    """
    
    period: str = Field(..., description="统计周期（如 'daily', 'weekly', 'monthly'）")
    start_time: str = Field(..., description="开始时间（ISO 格式）")
    end_time: str = Field(..., description="结束时间（ISO 格式）")
    
    # Token 累计
    total_prompt_tokens: int = Field(0)
    total_completion_tokens: int = Field(0)
    total_thinking_tokens: int = Field(0)
    total_cache_read_tokens: int = Field(0)
    total_cache_write_tokens: int = Field(0)
    total_tokens: int = Field(0)
    
    # 成本累计
    total_cost: str = Field("0")
    currency: str = Field("USD")
    
    # 调用统计
    total_requests: int = Field(0)
    total_llm_calls: int = Field(0)
    
    # 效率指标
    average_latency: Optional[float] = Field(None)
    cache_hit_rate: float = Field(0.0)
    average_tokens_per_request: float = Field(0.0)
