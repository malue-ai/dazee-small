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

if TYPE_CHECKING:
    from utils.usage_tracker import UsageTracker


# ============================================================
# 计费价格表（2026-01 Claude 4.5 定价，$/百万tokens）
# 与 core/monitoring/token_audit.py 保持一致
# ============================================================

CLAUDE_PRICING = {
    # Opus 系列
    "claude-opus-4.5": {
        "input": 5.0,
        "output": 25.0,
        "cache_write": 6.25,
        "cache_read": 0.5
    },
    "claude-opus-4-5-20251101": {  # 完整模型名
        "input": 5.0,
        "output": 25.0,
        "cache_write": 6.25,
        "cache_read": 0.5
    },
    "claude-opus-4.1": {
        "input": 15.0,
        "output": 75.0,
        "cache_write": 18.75,
        "cache_read": 1.5
    },
    "claude-opus-4": {
        "input": 15.0,
        "output": 75.0,
        "cache_write": 18.75,
        "cache_read": 1.5
    },
    "claude-opus-3": {  # deprecated
        "input": 15.0,
        "output": 75.0,
        "cache_write": 18.75,
        "cache_read": 1.5
    },
    # Sonnet 系列
    "claude-sonnet-4.5": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    "claude-sonnet-4-5-20250929": {  # 完整模型名
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    "claude-sonnet-4": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    "claude-sonnet-3.7": {  # deprecated
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    # Haiku 系列
    "claude-haiku-4.5": {
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.1
    },
    "claude-haiku-3.5": {
        "input": 0.8,
        "output": 4.0,
        "cache_write": 1.0,
        "cache_read": 0.08
    },
    "claude-haiku-3": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.3,
        "cache_read": 0.03
    },
    # 默认（Sonnet）
    "default": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    }
}


def get_model_pricing(model: str) -> Dict[str, float]:
    """
    获取模型定价
    
    Args:
        model: 模型名称
        
    Returns:
        定价字典 {input, output, cache_write, cache_read}
    """
    # 尝试精确匹配
    if model in CLAUDE_PRICING:
        return CLAUDE_PRICING[model]
    
    # 尝试模糊匹配
    model_lower = model.lower()
    for key, pricing in CLAUDE_PRICING.items():
        if key in model_lower or model_lower in key:
            return pricing
    
    # 返回默认价格
    return CLAUDE_PRICING["default"]


# ========== 便捷方法（向后兼容）==========

def from_usage_tracker_helper(
    tracker: 'UsageTracker',
    model: str = "claude-sonnet-4",
    latency: Optional[float] = None,
) -> UsageResponse:
    """
    从 UsageTracker 创建 UsageResponse（便捷方法）
    
    内部调用 UsageResponse.from_tracker()，统一使用新版实现
    
    Args:
        tracker: UsageTracker 实例
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
