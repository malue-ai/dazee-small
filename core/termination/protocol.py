"""
终止策略协议 - Termination Protocol

V12 更新：
- 新增 FinishReason 枚举，统一终止原因
- 终止原因从散落的字符串统一为枚举，便于前端展示和数据分析

定义执行器何时停止的接口，供自适应终止器等实现。
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext


class FinishReason(str, Enum):
    """
    终止原因枚举（V12）

    统一所有终止原因，便于前端展示和数据分析。
    """

    # 正常完成
    COMPLETED = "completed"  # LLM 自主完成（end_turn）
    AGENT_DECISION = "agent_decision"  # Agent 自主决定结束

    # 用户触发
    USER_STOP = "user_stop"  # 用户主动停止
    USER_ABORT = "user_abort"  # 用户中止（HITL 拒绝）

    # 安全兜底
    MAX_TURNS = "max_turns"  # 达到最大轮次
    MAX_DURATION = "max_duration"  # 达到最大时长
    IDLE_TIMEOUT = "idle_timeout"  # 空闲超时
    COST_LIMIT = "cost_limit"  # 费用超限

    # 错误恢复
    CONSECUTIVE_FAILURES = "consecutive_failures"  # 连续失败
    BACKTRACK_EXHAUSTED = "backtrack_exhausted"  # 回溯耗尽

    # 交互
    HITL_CONFIRM = "hitl_confirm"  # HITL 危险操作确认
    LONG_RUNNING_CONFIRM = "long_running_confirm"  # 长任务确认
    INTENT_CLARIFY = "intent_clarify"  # 意图澄清（回溯升级）


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
        finish_reason: 结构化终止原因枚举（V12）
        action: 终止后动作（stop / ask_user / rollback_options）
    """

    should_stop: bool
    reason: str = ""
    finish_reason: Optional[FinishReason] = None
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

    def confirm_long_running(self) -> None:
        """用户确认继续长任务后调用（子类可覆盖）"""

    def confirm_cost_continue(self, level: str = "confirm") -> None:
        """用户确认费用后继续执行（子类可覆盖）"""
