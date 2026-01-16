"""
Usage 响应模型 - 统一的 Token 使用和成本信息

参考 Dify 平台的计费响应格式，提供：
- Token 统计（input/output/thinking/cache）
- 成本计算（基于模型定价）
- 性能指标（延迟、调用次数）

架构位置：models/usage.py
使用场景：
- API 响应中返回计费信息
- SSE 事件流结束时发送 usage 事件
- 前端展示 token 消耗和成本
"""

from typing import Any, Dict, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from utils.usage_tracker import UsageTracker


# ============================================================
# 计费价格表（2026-01 Claude 4.5 定价，$/百万tokens）
# 与 core/monitoring/token_audit.py 保持一致
# ============================================================

CLAUDE_PRICING = {
    "claude-opus-4.5": {
        "input": 5.0,
        "output": 25.0,
        "cache_write": 6.25,
        "cache_read": 0.5
    },
    "claude-sonnet-4.5": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    "claude-haiku-4.5": {
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.1
    },
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


class UsageResponse(BaseModel):
    """
    统一的 Token 使用响应模型
    
    参考 Dify 平台格式，包含：
    - Token 统计（prompt/completion/thinking/cache）
    - 成本信息（单价、总价）
    - 性能指标（延迟、调用次数）
    
    示例响应：
    {
        "prompt_tokens": 229304,
        "completion_tokens": 684,
        "thinking_tokens": 0,
        "cache_read_tokens": 50000,
        "cache_write_tokens": 0,
        "total_tokens": 229988,
        "prompt_price": "0.687912",
        "completion_price": "0.01026",
        "cache_read_price": "0.015",
        "cache_write_price": "0",
        "total_price": "0.713172",
        "prompt_unit_price": "3",
        "completion_unit_price": "15",
        "price_unit": "0.000001",
        "currency": "USD",
        "latency": 8.117,
        "llm_calls": 3
    }
    """
    
    # ==================== Token 统计 ====================
    prompt_tokens: int = Field(0, description="输入 tokens（prompt）")
    completion_tokens: int = Field(0, description="输出 tokens（completion）")
    thinking_tokens: int = Field(0, description="Extended Thinking tokens")
    cache_read_tokens: int = Field(0, description="缓存读取 tokens")
    cache_write_tokens: int = Field(0, description="缓存创建 tokens")
    total_tokens: int = Field(0, description="总 tokens")
    
    # ==================== 成本信息（字符串格式，保留精度）====================
    prompt_price: str = Field("0", description="输入成本（美元）")
    completion_price: str = Field("0", description="输出成本（美元）")
    cache_read_price: str = Field("0", description="缓存读取成本（美元）")
    cache_write_price: str = Field("0", description="缓存写入成本（美元）")
    total_price: str = Field("0", description="总成本（美元）")
    
    # ==================== 单价信息 ====================
    prompt_unit_price: str = Field("3", description="输入单价（$/百万tokens）")
    completion_unit_price: str = Field("15", description="输出单价（$/百万tokens）")
    price_unit: str = Field("0.000001", description="价格精度单位")
    currency: str = Field("USD", description="货币单位")
    
    # ==================== 性能指标 ====================
    latency: Optional[float] = Field(None, description="响应延迟（秒）")
    llm_calls: int = Field(1, description="LLM 调用次数")
    
    # ==================== 元数据 ====================
    model: str = Field("claude-sonnet-4.5", description="使用的模型")
    
    @computed_field
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        total_input = self.prompt_tokens + self.cache_read_tokens
        if total_input == 0:
            return 0.0
        return round(self.cache_read_tokens / total_input, 4)
    
    @computed_field
    @property
    def cost_saved_by_cache(self) -> str:
        """缓存节省的成本（美元）"""
        # 如果没有缓存命中，成本应该是原价
        # 缓存价格是 input 价格的 10%，所以节省了 90%
        pricing = get_model_pricing(self.model)
        saved = (self.cache_read_tokens / 1_000_000) * (pricing["input"] - pricing["cache_read"])
        return f"{saved:.6f}"
    
    @staticmethod
    def from_usage_tracker(
        tracker: 'UsageTracker',
        model: str = "claude-sonnet-4.5",
        latency: Optional[float] = None,
        thinking_tokens: int = 0
    ) -> 'UsageResponse':
        """
        从 UsageTracker 创建响应
        
        Args:
            tracker: UsageTracker 实例
            model: 模型名称
            latency: 响应延迟（秒）
            thinking_tokens: Extended Thinking tokens
            
        Returns:
            UsageResponse 实例
        """
        stats = tracker.get_stats()
        pricing = get_model_pricing(model)
        
        # 提取 token 统计
        prompt_tokens = stats.get("total_input_tokens", 0)
        completion_tokens = stats.get("total_output_tokens", 0)
        cache_read = stats.get("total_cache_read_tokens", 0)
        cache_write = stats.get("total_cache_creation_tokens", 0)
        llm_calls = stats.get("llm_calls", 1)
        thinking = stats.get("total_thinking_tokens", thinking_tokens)
        
        # 计算成本（美元）
        prompt_price = (prompt_tokens / 1_000_000) * pricing["input"]
        completion_price = (completion_tokens / 1_000_000) * pricing["output"]
        cache_read_price = (cache_read / 1_000_000) * pricing["cache_read"]
        cache_write_price = (cache_write / 1_000_000) * pricing["cache_write"]
        total_price = prompt_price + completion_price + cache_read_price + cache_write_price
        
        return UsageResponse(
            # Token 统计
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            thinking_tokens=thinking,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            total_tokens=prompt_tokens + completion_tokens + thinking,
            # 成本信息
            prompt_price=f"{prompt_price:.6f}",
            completion_price=f"{completion_price:.6f}",
            cache_read_price=f"{cache_read_price:.6f}",
            cache_write_price=f"{cache_write_price:.6f}",
            total_price=f"{total_price:.6f}",
            # 单价信息
            prompt_unit_price=str(pricing["input"]),
            completion_unit_price=str(pricing["output"]),
            price_unit="0.000001",
            currency="USD",
            # 性能指标
            latency=round(latency, 3) if latency else None,
            llm_calls=llm_calls,
            # 元数据
            model=model
        )
    
    @staticmethod
    def from_dict(
        usage_dict: Dict[str, Any],
        model: str = "claude-sonnet-4.5",
        latency: Optional[float] = None
    ) -> 'UsageResponse':
        """
        从字典创建响应（用于多智能体等场景）
        
        Args:
            usage_dict: 包含 token 统计的字典
            model: 模型名称
            latency: 响应延迟（秒）
            
        Returns:
            UsageResponse 实例
        """
        pricing = get_model_pricing(model)
        
        # 提取 token 统计
        prompt_tokens = usage_dict.get("input_tokens", 0) or usage_dict.get("prompt_tokens", 0)
        completion_tokens = usage_dict.get("output_tokens", 0) or usage_dict.get("completion_tokens", 0)
        thinking_tokens = usage_dict.get("thinking_tokens", 0)
        cache_read = usage_dict.get("cache_read_tokens", 0)
        cache_write = usage_dict.get("cache_write_tokens", 0) or usage_dict.get("cache_creation_tokens", 0)
        llm_calls = usage_dict.get("llm_calls", 1)
        
        # 计算成本
        prompt_price = (prompt_tokens / 1_000_000) * pricing["input"]
        completion_price = (completion_tokens / 1_000_000) * pricing["output"]
        cache_read_price = (cache_read / 1_000_000) * pricing["cache_read"]
        cache_write_price = (cache_write / 1_000_000) * pricing["cache_write"]
        total_price = prompt_price + completion_price + cache_read_price + cache_write_price
        
        return UsageResponse(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            thinking_tokens=thinking_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            total_tokens=prompt_tokens + completion_tokens + thinking_tokens,
            prompt_price=f"{prompt_price:.6f}",
            completion_price=f"{completion_price:.6f}",
            cache_read_price=f"{cache_read_price:.6f}",
            cache_write_price=f"{cache_write_price:.6f}",
            total_price=f"{total_price:.6f}",
            prompt_unit_price=str(pricing["input"]),
            completion_unit_price=str(pricing["output"]),
            price_unit="0.000001",
            currency="USD",
            latency=round(latency, 3) if latency else None,
            llm_calls=llm_calls,
            model=model
        )
    
    def to_sse_event(self) -> Dict[str, Any]:
        """
        转换为 SSE 事件格式
        
        Returns:
            SSE 事件数据
        """
        return {
            "event": "usage",
            "data": self.model_dump()
        }
    
    def to_metadata(self) -> Dict[str, Any]:
        """
        转换为 metadata 格式（用于存储到数据库）
        
        Returns:
            metadata 字典
        """
        return {
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "thinking_tokens": self.thinking_tokens,
                "cache_read_tokens": self.cache_read_tokens,
                "cache_write_tokens": self.cache_write_tokens,
                "total_tokens": self.total_tokens,
                "total_price": self.total_price,
                "currency": self.currency,
                "model": self.model,
                "llm_calls": self.llm_calls
            }
        }


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
