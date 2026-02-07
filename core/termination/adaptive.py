"""
自适应终止器 - Adaptive Terminator

V12.1 更新（智能费用感知）：
- 维度 4.5 重构：移除 max_cost_usd 用户配置，改为智能体自主阶梯式 HITL 提醒
- 费用估算基于 ModelRegistry 真实定价，支持 Claude/Qwen/DeepSeek/私有化等不同模型
- 私有化部署（pricing 未知）自动跳过费用检查

V12 更新（回溯↔终止联动 + 费用限制）：
- 新增维度 6.5：回溯感知（回溯耗尽 → HITL 三选一 / 意图澄清）
- 所有决策使用 FinishReason 枚举

八维度终止判断：
1. 用户主动停止（stop event）
2. HITL 人工干预（危险操作确认）
3. LLM 自主终止（stop_reason == "end_turn"）
4. 安全兜底：最大轮次
4.5 智能费用感知：阶梯式 HITL 提醒（V12.1 重构）
5. 安全兜底：最大时长
6. 安全兜底：空闲超时
6.5 回溯感知：回溯耗尽 / 意图澄清（V12 新增）
7. 安全兜底：连续失败 → 回滚选项
8. 长任务用户确认
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Optional

from core.termination.protocol import (
    BaseTerminator,
    FinishReason,
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
class CostAlertConfig:
    """
    智能费用感知配置（V12.1）

    无需用户手动设置 max_cost_usd，智能体自主感知费用并通过 HITL 阶梯式提醒。
    私有化部署（pricing 未知）自动跳过费用检查。

    阶梯阈值（美元）：
    - warn_threshold:  首次提醒（默认 $0.50），仅日志告知
    - confirm_threshold: 二次确认（默认 $2.00），HITL 询问用户是否继续
    - urgent_threshold: 紧急提醒（默认 $10.00），HITL 再次询问，但决定权在用户
    
    注意：所有阶梯都是 HITL 询问，智能体不会主动替用户终止任务！
    """

    warn_threshold: float = 0.50  # 首次提醒阈值（仅日志 + 前端提示）
    confirm_threshold: float = 2.00  # 二次确认阈值（HITL 暂停询问）
    urgent_threshold: float = 10.00  # 紧急提醒阈值（HITL 再次询问，非强制停止）


@dataclass
class AdaptiveTerminatorConfig:
    """自适应终止器配置"""

    # 安全兜底
    max_turns: int = 30  # V12: 对齐 ExecutorConfig.max_turns，避免语义混淆
    max_duration_seconds: int = 1800
    idle_timeout_seconds: int = 120
    consecutive_failure_limit: int = 5

    # V12.1 智能费用感知（阶梯式 HITL 提醒，无需用户配置 max_cost_usd）
    cost_alert: CostAlertConfig = field(default_factory=CostAlertConfig)

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
        # V12.1 费用感知状态（避免重复提醒）
        self._cost_warned: bool = False  # 已触发 warn_threshold
        self._cost_confirmed: bool = False  # 用户已确认 confirm_threshold
        self._cost_urgent_confirmed: bool = False  # 用户已确认 urgent_threshold

    def evaluate(
        self,
        ctx: "RuntimeContext",
        stop_requested: bool = False,
        last_stop_reason: Optional[str] = None,
        pending_tool_names: Optional[List[str]] = None,
        current_cost_usd: Optional[float] = None,
        **kwargs: Any,
    ) -> TerminationDecision:
        """
        评估是否应终止（V12 八维度）

        Args:
            ctx: 运行时上下文
            stop_requested: 用户是否已请求停止
            last_stop_reason: 上一轮 LLM 响应的 stop_reason
            pending_tool_names: 待执行的工具名称列表（用于 HITL 检查）
            current_cost_usd: 当前任务累计费用（美元，V12 新增）
        """
        # === 1. 用户主动停止 ===
        if stop_requested:
            logger.info("终止决策: 用户主动停止")
            return TerminationDecision(
                should_stop=True,
                reason="user_stop",
                finish_reason=FinishReason.USER_STOP,
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
                finish_reason=FinishReason.COMPLETED,
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
                finish_reason=FinishReason.MAX_TURNS,
                action=TerminationAction.STOP,
            )

        # === 4.5 智能费用感知：阶梯式 HITL 提醒（V12.1 重构）===
        # 无需用户配置 max_cost_usd，智能体自主感知并分级处理
        # 注意：所有阶梯都是 HITL 询问，智能体不会主动替用户终止任务！
        if current_cost_usd is not None:
            alert = self.config.cost_alert

            # 阶梯 3: 紧急提醒 — HITL 再次询问（仅触发一次，决定权在用户）
            if (
                not self._cost_urgent_confirmed
                and current_cost_usd >= alert.urgent_threshold
            ):
                logger.warning(
                    f"费用紧急提醒: 费用已达 "
                    f"${current_cost_usd:.4f} >= ${alert.urgent_threshold:.2f}，"
                    f"等待用户确认"
                )
                return TerminationDecision(
                    should_stop=False,
                    reason=f"cost_urgent:${current_cost_usd:.4f}",
                    finish_reason=FinishReason.COST_LIMIT,
                    action=TerminationAction.ASK_USER,
                )

            # 阶梯 2: 确认阈值 — HITL 暂停询问（仅触发一次）
            if (
                not self._cost_confirmed
                and current_cost_usd >= alert.confirm_threshold
            ):
                logger.warning(
                    f"费用确认: 费用达到 "
                    f"${current_cost_usd:.4f} >= ${alert.confirm_threshold:.2f}，"
                    f"等待用户确认"
                )
                return TerminationDecision(
                    should_stop=False,
                    reason=f"cost_confirm:${current_cost_usd:.4f}",
                    finish_reason=FinishReason.COST_LIMIT,
                    action=TerminationAction.ASK_USER,
                )

            # 阶梯 1: 预警阈值 — 仅日志 + 前端提示（仅触发一次）
            if (
                not self._cost_warned
                and current_cost_usd >= alert.warn_threshold
            ):
                self._cost_warned = True
                logger.info(
                    f"费用预警: 本次任务费用已达 "
                    f"${current_cost_usd:.4f} (阈值 ${alert.warn_threshold:.2f})"
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
                finish_reason=FinishReason.MAX_DURATION,
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
                finish_reason=FinishReason.IDLE_TIMEOUT,
                action=TerminationAction.STOP,
            )

        # === 6.5 回溯感知（V12 新增）===
        backtracks_exhausted = getattr(ctx, "backtracks_exhausted", False)
        if backtracks_exhausted:
            escalation = getattr(ctx, "backtrack_escalation", None)
            total_bt = getattr(ctx, "total_backtracks", 0)

            if escalation == "intent_clarify":
                # 意图不清晰，请求用户澄清
                logger.info(
                    f"终止决策: 回溯升级为意图澄清 "
                    f"(回溯 {total_bt} 次后仍失败)"
                )
                return TerminationDecision(
                    should_stop=False,
                    reason="backtrack_intent_clarify",
                    finish_reason=FinishReason.INTENT_CLARIFY,
                    action=TerminationAction.ASK_USER,
                )
            else:
                # 回溯耗尽，提供三选一
                logger.warning(
                    f"终止决策: 回溯耗尽 "
                    f"(回溯 {total_bt} 次后仍失败)，等待用户决定"
                )
                return TerminationDecision(
                    should_stop=False,
                    reason="backtrack_exhausted",
                    finish_reason=FinishReason.BACKTRACK_EXHAUSTED,
                    action=TerminationAction.ASK_USER,
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
                finish_reason=FinishReason.CONSECUTIVE_FAILURES,
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
                finish_reason=FinishReason.LONG_RUNNING_CONFIRM,
                action=TerminationAction.ASK_USER,
            )

        return TerminationDecision(should_stop=False, reason="")

    def confirm_long_running(self) -> None:
        """用户确认继续长任务后调用，避免重复询问"""
        self._long_running_confirmed = True
        logger.info("长任务确认: 用户选择继续执行")

    def confirm_cost_continue(self, level: str = "confirm") -> None:
        """
        用户确认费用后继续执行，避免重复询问
        
        Args:
            level: 确认级别 "confirm" 或 "urgent"
        """
        if level == "urgent":
            self._cost_urgent_confirmed = True
            logger.info("费用紧急确认: 用户选择继续执行")
        else:
            self._cost_confirmed = True
            logger.info("费用确认: 用户选择继续执行")

    def reset(self) -> None:
        """重置状态（新任务开始时调用）"""
        self._long_running_confirmed = False
        self._cost_warned = False
        self._cost_confirmed = False
        self._cost_urgent_confirmed = False

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
