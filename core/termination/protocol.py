"""
终止策略协议 - Termination Protocol

定义执行器何时停止的接口，供自适应终止器等实现。
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext


class TerminationAction(str, Enum):
    """终止后的动作"""

    STOP = "stop"  # 正常停止
    ASK_USER = "ask_user"  # 询问用户是否继续（长任务确认）
    ROLLBACK_OPTIONS = "rollback_options"  # 提供回滚选项


@dataclass
class TerminationDecision:
    """
    终止决策结果

    Attributes:
        should_stop: 是否应停止执行
        reason: 停止原因（用于日志和事件）
        action: 终止后动作（stop / ask_user / rollback_options）
    """

    should_stop: bool
    reason: str = ""
    action: TerminationAction = TerminationAction.STOP


class BaseTerminator:
    """
    终止策略基类协议

    执行器在每轮循环末尾调用 evaluate(ctx)，根据返回值决定是否继续。
    """

    def evaluate(self, ctx: "RuntimeContext", **kwargs: Any) -> TerminationDecision:
        """
        评估是否应终止

        Args:
            ctx: 运行时上下文（turn、duration、stop_reason、consecutive_failures 等）
            **kwargs: 扩展参数（如 stop_event、config）

        Returns:
            TerminationDecision
        """
        raise NotImplementedError
