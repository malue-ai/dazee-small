"""
Backtrack 回溯模块

职责：
- 错误层级分类（基础设施层 vs 业务逻辑层）
- 回溯决策管理
- 策略调整和重规划
"""

from core.agent.backtrack.error_classifier import (
    BacktrackType,
    ClassifiedError,
    ErrorCategory,
    ErrorClassifier,
    ErrorLayer,
    get_error_classifier,
)
from core.agent.backtrack.manager import (
    BacktrackContext,
    BacktrackDecision,
    BacktrackManager,
    BacktrackResult,
    get_backtrack_manager,
)

__all__ = [
    # 错误分类
    "ErrorClassifier",
    "ErrorLayer",
    "ErrorCategory",
    "ClassifiedError",
    "BacktrackType",
    "get_error_classifier",
    # 回溯管理
    "BacktrackManager",
    "BacktrackContext",
    "BacktrackDecision",
    "BacktrackResult",
    "get_backtrack_manager",
]
