"""
定价数据 - Claude 模型价格表

将定价数据独立出来，避免循环导入
架构：core.billing.pricing_data（数据） → models.usage 和 core.billing.pricing（使用）
"""

from typing import Dict

# ============================================================
# 计费价格表（2026-01 Claude 4.5 定价，$/百万tokens）
# ============================================================

CLAUDE_PRICING: Dict[str, Dict[str, float]] = {
    # Opus 系列
    "claude-opus-4.5": {
        "input": 5.0,
        "output": 25.0,
        "cache_write": 6.25,
        "cache_read": 0.5
    },
    
    # Sonnet 系列
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.1
    },
    "claude-sonnet-4.5": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.1
    },
    "claude-sonnet-4": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.1
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    "claude-3-5-sonnet-20240620": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3
    },
    
    # Haiku 系列
    "claude-haiku-4-5-20251001": {  # 完整版本号
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.05
    },
    "claude-haiku-4.5": {  # 短名称（兼容）
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.05
    },
    "claude-3-5-haiku-20241022": {
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.1
    },
    "claude-3-haiku-20240307": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.3,
        "cache_read": 0.03
    },
    
    # 默认（用于未知模型）
    "default": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.1
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
