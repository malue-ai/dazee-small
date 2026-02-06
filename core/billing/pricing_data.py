"""
定价数据 - 多厂商 LLM 模型价格表

将定价数据独立出来，避免循环导入
架构：core.billing.pricing_data（数据） → models.usage 和 core.billing.pricing（使用）

支持的模型：
- Claude 系列（Anthropic）
- Qwen 系列（阿里云百炼）
"""

from typing import Dict

# ============================================================
# 计费价格表（$/百万tokens）
# - Claude: 2026-01 官方定价
# - Qwen: 参考价格，需根据官方文档确认
# ============================================================

CLAUDE_PRICING: Dict[str, Dict[str, float]] = {
    # Opus 系列
    "claude-opus-4.5": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.5},
    # Sonnet 系列
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.1,
    },
    "claude-sonnet-4.5": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.1},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.1},
    "claude-3-5-sonnet-20241022": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3,
    },
    "claude-3-5-sonnet-20240620": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.3,
    },
    # Haiku 系列
    "claude-haiku-4-5-20251001": {  # 完整版本号
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.05,
    },
    "claude-haiku-4.5": {  # 短名称（兼容）
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.05,
    },
    "claude-3-5-haiku-20241022": {
        "input": 1.0,
        "output": 5.0,
        "cache_write": 1.25,
        "cache_read": 0.1,
    },
    "claude-3-haiku-20240307": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.3,
        "cache_read": 0.03,
    },
    # ============================================================
    # 千问系列（阿里云百炼 - 国际部署模式）
    # 官方文档：https://help.aliyun.com/zh/model-studio/pricing
    # 价格来源：2026-01-30 官方文档，国际部署模式（新加坡地域）
    # 原始价格单位：人民币（元）/百万Token
    # 转换汇率：1 USD ≈ 7.2 CNY（用于统一计费系统）
    # ⚠️ 注意：用户使用 base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    #           对应国际部署模式，而非中国内地价格
    # ============================================================
    # Qwen3 Max（旗舰模型，对标 claude-sonnet-4-5）
    # 国际价格（阶梯计价，使用第一档 0<Token≤32K 作为默认值）：
    # - 0<Token≤32K：输入 ¥8.807/MTok, 输出 ¥44.035/MTok
    # - 32K<Token≤128K：输入 ¥17.614/MTok, 输出 ¥88.071/MTok
    # - 128K<Token≤252K：输入 ¥22.018/MTok, 输出 ¥110.089/MTok
    # ⚠️ 注意：实际计费按阶梯计价，这里使用第一档作为默认值
    "qwen3-max": {
        "input": 1.223,  # ¥8.807 ÷ 7.2 ≈ $1.223/百万tokens（第一档）
        "output": 6.116,  # ¥44.035 ÷ 7.2 ≈ $6.116/百万tokens（第一档）
        "cache_write": 0.0,  # 千问支持上下文缓存，但暂不在此计费
        "cache_read": 0.0,
    },
    "qwen3-max-2025-09-23": {
        "input": 1.223,  # 与 qwen3-max 稳定版相同
        "output": 6.116,
        "cache_write": 0.0,
        "cache_read": 0.0,
    },
    "qwen3-max-2026-01-23": {
        "input": 1.223,  # 与 qwen3-max 稳定版相同
        "output": 6.116,
        "cache_write": 0.0,
        "cache_read": 0.0,
    },
    "qwen3-max-preview": {
        "input": 1.223,  # 与 qwen3-max 稳定版相同
        "output": 6.116,
        "cache_write": 0.0,
        "cache_read": 0.0,
    },
    # Qwen Max（旧版旗舰模型，对标 claude-sonnet-4-5）
    # 国际价格：输入 ¥11.743/MTok, 输出 ¥46.971/MTok
    "qwen-max": {
        "input": 1.63,  # ¥11.743 ÷ 7.2 ≈ $1.63/百万tokens
        "output": 6.52,  # ¥46.971 ÷ 7.2 ≈ $6.52/百万tokens
        "cache_write": 0.0,  # 千问不支持显式缓存
        "cache_read": 0.0,
    },
    "qwen-max-latest": {"input": 1.63, "output": 6.52, "cache_write": 0.0, "cache_read": 0.0},
    "qwen-max-2025-01-25": {"input": 1.63, "output": 6.52, "cache_write": 0.0, "cache_read": 0.0},
    # Qwen Plus（性价比模型，对标 claude-haiku-4-5）
    # 国际价格：输入 ¥2.936/MTok (0-256K), 输出 ¥8.807/MTok (非思考模式)
    "qwen-plus": {
        "input": 0.41,  # ¥2.936 ÷ 7.2 ≈ $0.41/百万tokens
        "output": 1.22,  # ¥8.807 ÷ 7.2 ≈ $1.22/百万tokens
        "cache_write": 0.0,
        "cache_read": 0.0,
    },
    "qwen-plus-latest": {"input": 0.41, "output": 1.22, "cache_write": 0.0, "cache_read": 0.0},
    # Qwen Turbo（快速模型）
    # 国际价格：输入 ¥0.367/MTok, 输出 ¥1.468/MTok (非思考模式)
    "qwen-turbo": {
        "input": 0.05,  # ¥0.367 ÷ 7.2 ≈ $0.05/百万tokens
        "output": 0.20,  # ¥1.468 ÷ 7.2 ≈ $0.20/百万tokens
        "cache_write": 0.0,
        "cache_read": 0.0,
    },
    "qwen-turbo-latest": {"input": 0.05, "output": 0.20, "cache_write": 0.0, "cache_read": 0.0},
    # 默认（用于未知模型）
    "default": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.1},
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
