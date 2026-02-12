"""
终止策略模块

提供执行器何时停止的决策接口与实现（如自适应终止器）。
"""

from core.termination.adaptive import (
    AdaptiveTerminator,
    AdaptiveTerminatorConfig,
    HITLConfig,
)
from core.termination.protocol import (
    BaseTerminator,
    TerminationAction,
    TerminationDecision,
)

__all__ = [
    "BaseTerminator",
    "TerminationDecision",
    "TerminationAction",
    "AdaptiveTerminator",
    "AdaptiveTerminatorConfig",
    "HITLConfig",
]
