"""
智能护栏模块

V8.0 新增

职责：
- 自适应资源限制（max_turns, max_tools, token_budget）
- 根据任务复杂度和用户等级动态调整
- 运行时监控和干预

设计原则：
- 护栏是安全阀，不是刚性限制
- 根据上下文智能调整
- 提供预警而非直接阻断
"""

from core.guardrails.adaptive import (
    AdaptiveGuardrails,
    GuardrailAction,
    GuardrailCheckResult,
    GuardrailConfig,
    create_adaptive_guardrails,
)

__all__ = [
    "AdaptiveGuardrails",
    "GuardrailConfig",
    "GuardrailAction",
    "GuardrailCheckResult",
    "create_adaptive_guardrails",
]
