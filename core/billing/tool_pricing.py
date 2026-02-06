"""
工具定价模块 - Tool Pricing

集中管理所有工具的定价信息和成本计算逻辑。

价格来源：平台提供的工具价格表
单位：美元 / 次调用

设计原则：
1. 价格表可动态更新（通过配置文件或环境变量）
2. 支持免费工具（price = 0.0）
3. 未定价的工具默认免费（避免计费错误）
4. Claude 服务端工具不单独计费（成本已包含在 LLM API 调用中）

计费规则：
- Claude Server-side 工具（web_search, code_execution 等）：$0.00（成本已在 LLM 计费中）
- 第三方 API 工具（exa_search, ragie 等）：按实际调用成本计费
- 内部工具（sandbox_read_file, plan_todo 等）：$0.00（免费）

使用示例：
    from core.billing.tool_pricing import get_tool_pricing, calculate_tool_cost

    # 获取工具价格
    price = get_tool_pricing("web_search")  # 0.0 USD（Claude 服务端工具）
    price = get_tool_pricing("exa_search")  # 0.05 USD（第三方工具）

    # 计算总成本
    total = calculate_tool_cost("exa_search", count=3)  # 0.15 USD
"""

from typing import Any, Dict, Optional

from logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 工具定价表（USD / 次调用）
#
# 价格来源：2026-01-20 平台提供的官方价格表
# 更新说明：根据实际业务需求定期更新
# ============================================================

TOOL_PRICING = {
    # ==================== Claude 服务端工具（不单独计费）====================
    # 这些工具由 Anthropic 服务器执行，成本已包含在 Claude API 调用费用中
    # 🆕 仅保留 code_execution 用于 Skills 功能
    "code_execution": 0.0,  # Claude 代码执行沙箱（Skills 需要）
    # ==================== 内部工具（免费）====================
    "sandbox_read_file": 0.0,  # 沙盒文件读取
    "plan_todo": 0.0,  # 任务规划
    "request_human_confirmation": 0.0,  # 人工确认
    "hitl": 0.0,  # HITL (Human-in-the-Loop)
    "api_calling": 0.0,  # API 调用（通用调用器，实际按 api_name 计费）
    "knowledge_search": 0.0,  # 知识库搜索
    "planning-task": 0.0,  # 规划任务
    # ==================== 搜索类工具 ====================
    "exa_search": 0.05,  # Exa 搜索引擎（第三方工具）
    # ==================== 文档处理类工具 ====================
    "document_partition_tool": 0.05,  # 文档分区解析
    "ppt-generator": 2.0,  # PPT 生成器
    "ppt_generator": 2.0,  # PPT 生成器（别名）
    # ==================== 沙盒执行类工具 ====================
    "sandbox_run_project": 0.05,  # E2B 沙盒运行项目
    "sandbox_exec": 0.05,  # 沙盒执行（通用）
    # ==================== Dify 平台工具 ====================
    "dify_Ontology_TextToChart": 0.5,  # 文本转图表
    "dify_nano_banana": 0.6,  # Nano Banana
    "dify_chatDocuments": 0.001,  # 文档对话
    "dify_text2document": 0.05,  # 文本转文档
    "dify_Perplexity": 0.4,  # Perplexity 搜索
    # ==================== 其他业务工具 ====================
    "ontology-builder": 0.8,  # 本体构建器
    "ontology_builder": 0.8,  # 本体构建器（别名）
    # ==================== 第三方服务/平台 ====================
    # 问数平台（多个别名）
    "问数平台": 0.002,  # 问数数据平台
    "wenshu": 0.002,  # 问数平台（拼音）
    "wenshu_api": 0.002,  # 问数平台（API 名称）
    "wenshu_platform": 0.002,  # 问数平台（英文）
    # 知识检索服务
    "ragie": 0.05,  # Ragie 知识检索服务
    # PPT 渲染服务
    "slidespeak": 0.5,  # SlideSpeak 服务
    "slidespeak_render": 0.5,  # SlideSpeak 渲染（别名）
    # ==================== 备用/遗留工具 ====================
    # 以下工具价格仅供参考，未在官方价格表中
    "arxiv_search": 0.01,  # 学术搜索
    "pdf_parser": 0.02,  # PDF 解析
    "ocr_tool": 0.03,  # OCR 识别
    "code_interpreter": 0.02,  # 代码解释器
    "data_analysis": 0.03,  # 数据分析
    "chart_generator": 0.01,  # 图表生成
    # ==================== 免费工具 ====================
    "get_current_time": 0.0,  # 获取时间
    "calculator": 0.0,  # 计算器
    "text_formatter": 0.0,  # 文本格式化
    "bash": 0.0,  # Shell 命令（Claude 原生）
    "text_editor": 0.0,  # 文本编辑器（Claude 原生）
    # ==================== 默认价格 ====================
    "default": 0.0,  # 默认免费（安全策略）
}


def get_tool_pricing(tool_name: str, params: Optional[Dict[str, Any]] = None) -> float:
    """
    获取工具定价

    Args:
        tool_name: 工具名称
        params: 工具参数（可选，用于 api_calling 等通用工具）

    Returns:
        工具单次调用价格（USD）

    示例：
        price = get_tool_pricing("web_search")  # 0.01
        price = get_tool_pricing("unknown_tool")  # 0.0 (默认免费)

        # api_calling 特殊处理
        price = get_tool_pricing("api_calling", {"api_name": "wenshu_api"})  # 0.002
    """
    # 🔧 特殊处理：api_calling 工具
    # api_calling 是通用调用器，需要通过 params["api_name"] 确定实际服务
    if tool_name == "api_calling" and params:
        api_name = params.get("api_name")
        if api_name:
            # 优先查找 api_name 的价格
            price = TOOL_PRICING.get(api_name)
            if price is not None:
                logger.debug(
                    f"🔑 api_calling 解析: tool_name={tool_name}, "
                    f"api_name={api_name}, price=${price:.6f}"
                )
                return price
            # 如果 api_name 没有配置，使用 api_calling 的默认价格
            logger.debug(f"⚠️ api_name '{api_name}' 未配置价格，使用 api_calling 默认价格")
            return TOOL_PRICING.get("api_calling", 0.0)

    # 精确匹配
    if tool_name in TOOL_PRICING:
        return TOOL_PRICING[tool_name]

    # 模糊匹配（支持工具名变体）
    tool_name_lower = tool_name.lower()
    for key, price in TOOL_PRICING.items():
        if key.lower() in tool_name_lower or tool_name_lower in key.lower():
            return price

    # 未配置的工具默认免费（避免计费错误）
    logger.debug(f"工具 '{tool_name}' 未配置价格，使用默认价格: ${TOOL_PRICING['default']}")
    return TOOL_PRICING["default"]


def calculate_tool_cost(
    tool_name: str, count: int = 1, params: Optional[Dict[str, Any]] = None
) -> float:
    """
    计算工具调用成本

    Args:
        tool_name: 工具名称
        count: 调用次数
        params: 工具参数（可选，用于 api_calling 等通用工具）

    Returns:
        总成本（USD）

    示例：
        cost = calculate_tool_cost("web_search", count=3)
        # 0.03 (0.01 * 3)

        cost = calculate_tool_cost("api_calling", count=2, params={"api_name": "wenshu_api"})
        # 0.004 (0.002 * 2)
    """
    unit_price = get_tool_pricing(tool_name, params=params)
    total_cost = unit_price * count
    return round(total_cost, 6)  # 精确到小数点后 6 位


def update_tool_pricing(pricing_dict: Dict[str, float]) -> None:
    """
    动态更新工具定价表

    用于运行时更新价格（如从配置文件加载）

    Args:
        pricing_dict: 新的定价字典

    示例：
        update_tool_pricing({
            "web_search": 0.02,  # 涨价
            "new_tool": 0.01
        })
    """
    global TOOL_PRICING
    TOOL_PRICING.update(pricing_dict)
    logger.info(f"工具定价已更新: {len(pricing_dict)} 个工具")


async def load_tool_pricing_from_config(config_path: Optional[str] = None) -> None:
    """
    从配置文件加载工具定价

    Args:
        config_path: 配置文件路径（YAML/JSON）

    示例配置文件（YAML）：
        # tool_pricing.yaml
        web_search: 0.01
        document_partition_tool: 0.05
        custom_tool: 0.03
    """
    if config_path is None:
        return

    from pathlib import Path

    import aiofiles
    import yaml

    config_file = Path(config_path)
    if not config_file.exists():
        logger.warning(f"工具定价配置文件不存在: {config_path}")
        return

    try:
        async with aiofiles.open(config_file, "r", encoding="utf-8") as f:
            content = await f.read()
            pricing_dict = yaml.safe_load(content)
            if pricing_dict:
                update_tool_pricing(pricing_dict)
                logger.info(f"✅ 从配置文件加载工具定价: {config_path}")
    except Exception as e:
        logger.error(f"❌ 加载工具定价配置失败: {e}")


# ============================================================
# 导出接口
# ============================================================

__all__ = [
    "TOOL_PRICING",
    "get_tool_pricing",
    "calculate_tool_cost",
    "update_tool_pricing",
    "load_tool_pricing_from_config",
]
