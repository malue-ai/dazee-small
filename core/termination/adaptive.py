"""
自适应终止器 - Adaptive Terminator

五维度终止判断：
1. LLM 自主终止（stop_reason == "end_turn"）
2. HITL 人工干预（危险操作确认）
3. 用户主动停止（stop event）
4. 安全兜底（max_turns、max_duration、idle_timeout、连续失败上限）
5. 长任务用户确认

安全增强：
- idle_timeout 空闲检测（通过 RuntimeContext.idle_seconds）
- 连续失败触发回滚选项（联动状态一致性层）
- HITL 危险操作确认列表
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Optional

from core.termination.protocol import (
    BaseTerminator,
    TerminationAction,
    TerminationDecision,
)
from logger import get_logger

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext

logger = get_logger(__name__)


@dataclass
class HITLConfig:
    """HITL 人工干预配置"""

    enabled: bool = True
    # 需要确认的危险操作列表
    require_confirmation: List[str] = field(
        default_factory=lambda: [
            "delete",
            "overwrite",
            "send_email",
            "publish",
            "payment",
        ]
    )
    # 用户拒绝后的处理
    on_rejection: str = "ask_rollback"  # stop / rollback / ask_rollback
    # 异常时显示回滚选项
    show_rollback_on_error: bool = True


@dataclass
class AdaptiveTerminatorConfig:
    """自适应终止器配置"""

    # 安全兜底
    max_turns: int = 100
    max_duration_seconds: int = 1800
    idle_timeout_seconds: int = 120
    consecutive_failure_limit: int = 5

    # 长任务确认
    long_running_confirm_after_turns: int = 20

    # HITL 人工干预
    hitl: HITLConfig = field(default_factory=HITLConfig)


class AdaptiveTerminator(BaseTerminator):
    """
    自适应终止器

    结合 LLM 完成信号、HITL 干预、用户停止、安全兜底与长任务确认。
    连续失败超限时联动状态一致性层提供回滚选项。
    """

    def __init__(self, config: Optional[AdaptiveTerminatorConfig] = None):
        self.config = config or AdaptiveTerminatorConfig()
        # 长任务确认状态（避免重复询问）
        self._long_running_confirmed: bool = False

    def evaluate(
        self,
        ctx: "RuntimeContext",
        stop_requested: bool = False,
        last_stop_reason: Optional[str] = None,
        pending_tool_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> TerminationDecision:
        """
        评估是否应终止

        Args:
            ctx: 运行时上下文
            stop_requested: 用户是否已请求停止
            last_stop_reason: 上一轮 LLM 响应的 stop_reason
            pending_tool_names: 待执行的工具名称列表（用于 HITL 检查）
        """
        # === 1. 用户主动停止 ===
        if stop_requested:
            logger.info("终止决策: 用户主动停止")
            return TerminationDecision(
                should_stop=True,
                reason="user_stop",
                action=TerminationAction.STOP,
            )

        # === 2. HITL 危险操作确认 ===
        hitl_decision = self._check_hitl(pending_tool_names)
        if hitl_decision is not None:
            return hitl_decision

        # === 3. LLM 自主终止 ===
        if last_stop_reason == "end_turn":
            logger.info("终止决策: LLM 自主完成 (end_turn)")
            return TerminationDecision(
                should_stop=True,
                reason="end_turn",
                action=TerminationAction.STOP,
            )

        # === 4. 安全兜底：最大轮次 ===
        if ctx.current_turn >= self.config.max_turns:
            logger.warning(
                f"终止决策: 达到最大轮次 {ctx.current_turn}/{self.config.max_turns}"
            )
            return TerminationDecision(
                should_stop=True,
                reason="max_turns",
                action=TerminationAction.STOP,
            )

        # === 5. 安全兜底：最大时长 ===
        duration = ctx.duration_seconds
        if duration >= self.config.max_duration_seconds:
            logger.warning(
                f"终止决策: 达到最大时长 {duration:.0f}s/{self.config.max_duration_seconds}s"
            )
            return TerminationDecision(
                should_stop=True,
                reason="max_duration",
                action=TerminationAction.STOP,
            )

        # === 6. 安全兜底：空闲超时 ===
        idle = getattr(ctx, "idle_seconds", 0) or 0
        if idle >= self.config.idle_timeout_seconds:
            logger.warning(
                f"终止决策: 空闲超时 {idle:.0f}s/{self.config.idle_timeout_seconds}s"
            )
            return TerminationDecision(
                should_stop=True,
                reason="idle_timeout",
                action=TerminationAction.STOP,
            )

        # === 7. 安全兜底：连续失败 → 提供回滚选项 ===
        consecutive_failures = ctx.consecutive_failures
        if consecutive_failures >= self.config.consecutive_failure_limit:
            logger.warning(
                f"终止决策: 连续失败 {consecutive_failures}/{self.config.consecutive_failure_limit}, "
                f"提供回滚选项"
            )
            return TerminationDecision(
                should_stop=True,
                reason="consecutive_failures",
                action=TerminationAction.ROLLBACK_OPTIONS,
            )

        # === 8. 长任务确认 ===
        if (
            not self._long_running_confirmed
            and ctx.current_turn >= self.config.long_running_confirm_after_turns
        ):
            logger.info(
                f"终止决策: 长任务确认 (turn={ctx.current_turn} >= "
                f"{self.config.long_running_confirm_after_turns})"
            )
            return TerminationDecision(
                should_stop=False,
                reason="long_running_confirm",
                action=TerminationAction.ASK_USER,
            )

        return TerminationDecision(should_stop=False, reason="")

    def confirm_long_running(self) -> None:
        """用户确认继续长任务后调用，避免重复询问"""
        self._long_running_confirmed = True
        logger.info("长任务确认: 用户选择继续执行")

    def reset(self) -> None:
        """重置状态（新任务开始时调用）"""
        self._long_running_confirmed = False

    # ==================== HITL 检查（私有方法）====================

    def _check_hitl(
        self, pending_tool_names: Optional[List[str]]
    ) -> Optional[TerminationDecision]:
        """
        检查待执行工具是否需要 HITL 确认

        Args:
            pending_tool_names: 待执行的工具名称列表

        Returns:
            如需确认则返回 TerminationDecision，否则 None
        """
        if not self.config.hitl.enabled:
            return None
        if not pending_tool_names:
            return None

        dangerous = self.config.hitl.require_confirmation
        for tool_name in pending_tool_names:
            # 检查工具名是否在危险列表中，或包含危险关键词（如 delete_file 匹配 delete）
            if tool_name in dangerous:
                logger.info(f"HITL 拦截: 工具 '{tool_name}' 需要用户确认")
                return TerminationDecision(
                    should_stop=False,
                    reason=f"hitl_confirm:{tool_name}",
                    action=TerminationAction.ASK_USER,
                )
            for kw in dangerous:
                if kw in (tool_name or "").lower():
                    logger.info(f"HITL 拦截: 工具 '{tool_name}' 含危险关键词 '{kw}'，需用户确认")
                    return TerminationDecision(
                        should_stop=False,
                        reason=f"hitl_confirm:{tool_name}",
                        action=TerminationAction.ASK_USER,
                    )

        return None
