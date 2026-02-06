"""
Prompt 选择器

职责：根据意图分析结果返回合适的系统提示词
- 需要 Plan（needs_plan=True 或 complex）→ full prompt（含 plan 规则）
- 否则按 simple / standard 分层以节省 token

这段逻辑放在 prompts 层，保持 Agent 框架的通用性。
"""

from typing import Callable, Dict

from prompts.simple_prompt import get_simple_prompt
from prompts.standard_prompt import get_standard_prompt


def select_prompt(
    prompt_level: str,
    complexity: str,
    needs_plan: bool,
    build_full_prompt: Callable[[], str],
) -> Dict[str, object]:
    """
    返回系统提示词及元信息。

    Args:
        prompt_level: simple|standard|full（Haiku 预测）
        complexity: simple|medium|complex（Haiku 预测）
        needs_plan: 是否需要 Plan（Haiku 预测）
        build_full_prompt: 构造 full prompt 的回调（包含动态注入）

    Returns:
        {
            "system_prompt": str,
            "prompt_name": str,
            "enable_thinking": bool,
            "level": "simple|standard|full"
        }
    """
    # 需要 Plan → 强制 full prompt（含 plan 规则）
    if needs_plan or prompt_level == "full" or complexity == "complex":
        return {
            "system_prompt": build_full_prompt(),
            "prompt_name": "universal_agent_prompt",
            "enable_thinking": True,
            "level": "full",
        }

    # simple：最省 token
    if prompt_level == "simple" or complexity == "simple":
        return {
            "system_prompt": get_simple_prompt(),
            "prompt_name": "simple_prompt",
            "enable_thinking": False,
            "level": "simple",
        }

    # standard：默认中等
    return {
        "system_prompt": get_standard_prompt(),
        "prompt_name": "standard_prompt",
        "enable_thinking": True,
        "level": "standard",
    }

