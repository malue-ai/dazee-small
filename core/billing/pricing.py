"""
Pricing 模块 - 模型定价和成本计算

集中管理所有 Claude 模型的定价信息和成本计算逻辑。

价格来源：Anthropic 官方定价（2026-01）
单位：美元 / 百万 tokens
"""

from typing import Dict, Optional, Tuple
from models.usage import CLAUDE_PRICING, get_model_pricing


def get_pricing_for_model(model: str) -> Dict[str, float]:
    """
    获取模型定价（别名，与 models.usage.get_model_pricing 一致）
    
    Args:
        model: 模型名称
        
    Returns:
        定价字典 {input, output, cache_write, cache_read}
    """
    return get_model_pricing(model)


def calculate_cost(
    input_tokens: int = 0,
    output_tokens: int = 0,
    thinking_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    model: str = "claude-sonnet-4.5"
) -> Tuple[float, Dict[str, float]]:
    """
    计算 Token 成本
    
    Args:
        input_tokens: 输入 tokens
        output_tokens: 输出 tokens
        thinking_tokens: Extended Thinking tokens（算作 output 价格）
        cache_read_tokens: 缓存读取 tokens
        cache_write_tokens: 缓存创建 tokens
        model: 模型名称
        
    Returns:
        Tuple[总成本, 成本明细字典]
        
    示例：
        total, details = calculate_cost(
            input_tokens=100000,
            output_tokens=5000,
            model="claude-sonnet-4.5"
        )
        # total = 0.375 (float)
        # details = {
        #     "input_cost": 0.3,       # float
        #     "output_cost": 0.075,    # float
        #     "thinking_cost": 0.0,    # float
        #     "cache_read_cost": 0.0,  # float
        #     "cache_write_cost": 0.0, # float
        #     "total_cost": 0.375      # float
        # }
    """
    pricing = get_model_pricing(model)
    
    # 计算各项成本（USD，float 类型）
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    thinking_cost = (thinking_tokens / 1_000_000) * pricing["output"]  # thinking 用 output 价格
    cache_read_cost = (cache_read_tokens / 1_000_000) * pricing["cache_read"]
    cache_write_cost = (cache_write_tokens / 1_000_000) * pricing["cache_write"]
    
    total_cost = input_cost + output_cost + thinking_cost + cache_read_cost + cache_write_cost
    
    # 所有成本值都是 float，精确到小数点后 6 位
    details = {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "thinking_cost": round(thinking_cost, 6),
        "cache_read_cost": round(cache_read_cost, 6),
        "cache_write_cost": round(cache_write_cost, 6),
        "total_cost": round(total_cost, 6),
    }
    
    return round(total_cost, 6), details


def estimate_monthly_cost(
    daily_requests: int,
    avg_input_tokens_per_request: int = 10000,
    avg_output_tokens_per_request: int = 2000,
    model: str = "claude-sonnet-4.5",
    cache_hit_rate: float = 0.0
) -> Dict[str, float]:
    """
    估算月度成本
    
    用于预算规划和成本预警
    
    Args:
        daily_requests: 每日请求数
        avg_input_tokens_per_request: 每次请求平均输入 tokens
        avg_output_tokens_per_request: 每次请求平均输出 tokens
        model: 模型名称
        cache_hit_rate: 缓存命中率（0.0-1.0）
        
    Returns:
        月度成本估算字典
    """
    pricing = get_model_pricing(model)
    
    # 月度请求数（按30天计算）
    monthly_requests = daily_requests * 30
    
    # 月度 token 消耗
    monthly_input_tokens = avg_input_tokens_per_request * monthly_requests
    monthly_output_tokens = avg_output_tokens_per_request * monthly_requests
    
    # 考虑缓存命中率
    actual_input_tokens = monthly_input_tokens * (1 - cache_hit_rate)
    cache_read_tokens = monthly_input_tokens * cache_hit_rate
    
    # 计算成本
    input_cost = (actual_input_tokens / 1_000_000) * pricing["input"]
    output_cost = (monthly_output_tokens / 1_000_000) * pricing["output"]
    cache_cost = (cache_read_tokens / 1_000_000) * pricing["cache_read"]
    
    total_cost = input_cost + output_cost + cache_cost
    
    # 缓存节省的成本
    saved_by_cache = (cache_read_tokens / 1_000_000) * (pricing["input"] - pricing["cache_read"])
    
    return {
        "model": model,
        "daily_requests": daily_requests,
        "monthly_requests": monthly_requests,
        "monthly_input_tokens": monthly_input_tokens,
        "monthly_output_tokens": monthly_output_tokens,
        "cache_hit_rate": cache_hit_rate,
        "input_cost": round(input_cost, 2),
        "output_cost": round(output_cost, 2),
        "cache_cost": round(cache_cost, 2),
        "total_cost": round(total_cost, 2),
        "saved_by_cache": round(saved_by_cache, 2),
        "currency": "USD",
    }
