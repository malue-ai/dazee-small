"""
AdaptiveGuardrails - 自适应护栏

V8.0 新增

职责：
- 根据任务复杂度动态调整限制
- 根据用户等级调整配额
- 运行时监控和干预
- 提供预警和建议

护栏类型：
- turn_limit: 最大轮次
- tool_limit: 工具调用次数
- token_budget: Token 预算
- time_limit: 执行时间
- depth_limit: 递归/嵌套深度

调整策略：
- 简单任务：收紧限制，快速完成
- 复杂任务：放宽限制，充分执行
- VIP 用户：更高配额
- 资源紧张：动态降级
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


class GuardrailAction(Enum):
    """护栏动作"""

    ALLOW = "allow"  # 允许继续
    WARN = "warn"  # 警告但允许
    THROTTLE = "throttle"  # 限速
    BLOCK = "block"  # 阻断
    SUGGEST = "suggest"  # 建议调整


@dataclass
class GuardrailCheckResult:
    """护栏检查结果"""

    action: GuardrailAction
    guardrail_type: str  # 触发的护栏类型
    current_value: float  # 当前值
    limit_value: float  # 限制值
    usage_ratio: float  # 使用率（0-1）
    message: str  # 人类可读消息
    suggestion: Optional[str] = None  # 调整建议

    def is_allowed(self) -> bool:
        """是否允许继续"""
        return self.action in (GuardrailAction.ALLOW, GuardrailAction.WARN, GuardrailAction.SUGGEST)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "guardrail_type": self.guardrail_type,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "usage_ratio": self.usage_ratio,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class GuardrailConfig:
    """
    护栏配置

    支持基于复杂度和用户等级的动态调整
    """

    # 基础限制（默认值）
    max_turns: int = 15
    max_tool_calls: int = 50
    max_tokens: int = 100_000
    max_execution_time: int = 300  # 秒
    max_depth: int = 5

    # 复杂度调整系数
    complexity_multipliers: Dict[str, float] = field(
        default_factory=lambda: {
            "simple": 0.5,  # 简单任务：50% 配额
            "medium": 1.0,  # 中等任务：100% 配额
            "complex": 1.5,  # 复杂任务：150% 配额
        }
    )

    # 用户等级调整系数
    tier_multipliers: Dict[str, float] = field(
        default_factory=lambda: {
            "FREE": 0.5,  # 免费用户：50% 配额
            "BASIC": 0.8,  # 基础用户：80% 配额
            "PRO": 1.0,  # 专业用户：100% 配额
            "ENTERPRISE": 2.0,  # 企业用户：200% 配额
        }
    )

    # 预警阈值
    warn_threshold: float = 0.8  # 80% 时警告
    throttle_threshold: float = 0.95  # 95% 时限速

    # 是否启用自适应
    adaptive_enabled: bool = True

    def get_adjusted_limit(
        self, base_limit: float, complexity_level: str = "medium", user_tier: str = "PRO"
    ) -> float:
        """
        获取调整后的限制值

        Args:
            base_limit: 基础限制
            complexity_level: 复杂度等级
            user_tier: 用户等级

        Returns:
            调整后的限制值
        """
        if not self.adaptive_enabled:
            return base_limit

        complexity_mult = self.complexity_multipliers.get(complexity_level, 1.0)
        tier_mult = self.tier_multipliers.get(user_tier, 1.0)

        return base_limit * complexity_mult * tier_mult


class AdaptiveGuardrails:
    """
    自适应护栏

    根据任务上下文动态调整限制，提供智能预警和干预。

    使用方式：
        guardrails = AdaptiveGuardrails(config)

        # 设置上下文
        guardrails.set_context(
            complexity_level="complex",
            user_tier="PRO"
        )

        # 检查护栏
        result = guardrails.check_turns(current=10)
        if not result.is_allowed():
            # 处理限制
            pass

        # 运行时更新
        guardrails.record_turn()
        guardrails.record_tool_call("web_search")
        guardrails.record_tokens(5000)
    """

    def __init__(
        self,
        config: GuardrailConfig = None,
        on_warning: Callable[[GuardrailCheckResult], None] = None,
        on_block: Callable[[GuardrailCheckResult], None] = None,
    ):
        """
        初始化护栏

        Args:
            config: 护栏配置
            on_warning: 警告回调
            on_block: 阻断回调
        """
        self.config = config or GuardrailConfig()
        self.on_warning = on_warning
        self.on_block = on_block

        # 上下文
        self._complexity_level = "medium"
        self._user_tier = "PRO"
        self._session_id = None

        # 运行时计数器
        self._turn_count = 0
        self._tool_calls: List[str] = []
        self._token_count = 0
        self._start_time: Optional[datetime] = None
        self._depth = 0

        # 历史检查结果
        self._check_history: List[GuardrailCheckResult] = []

        logger.debug("✅ AdaptiveGuardrails 初始化")

    def set_context(
        self, complexity_level: str = None, user_tier: str = None, session_id: str = None
    ):
        """
        设置上下文

        Args:
            complexity_level: 复杂度等级（simple/medium/complex）
            user_tier: 用户等级
            session_id: 会话 ID
        """
        if complexity_level:
            self._complexity_level = complexity_level
        if user_tier:
            self._user_tier = user_tier
        if session_id:
            self._session_id = session_id

        logger.debug(f"护栏上下文: complexity={self._complexity_level}, " f"tier={self._user_tier}")

    def start_session(self):
        """开始会话"""
        self._turn_count = 0
        self._tool_calls = []
        self._token_count = 0
        self._start_time = datetime.now()
        self._depth = 0
        self._check_history = []

    def _get_limit(self, base_attr: str) -> float:
        """获取调整后的限制值"""
        base_value = getattr(self.config, base_attr)
        return self.config.get_adjusted_limit(base_value, self._complexity_level, self._user_tier)

    def _check(self, guardrail_type: str, current: float, limit: float) -> GuardrailCheckResult:
        """
        通用检查逻辑

        Args:
            guardrail_type: 护栏类型
            current: 当前值
            limit: 限制值

        Returns:
            检查结果
        """
        ratio = current / limit if limit > 0 else 0

        # 判断动作
        if ratio >= 1.0:
            action = GuardrailAction.BLOCK
            message = f"已达到 {guardrail_type} 限制: {current:.0f}/{limit:.0f}"
            suggestion = f"建议优化执行策略或升级用户等级"
        elif ratio >= self.config.throttle_threshold:
            action = GuardrailAction.THROTTLE
            message = f"{guardrail_type} 接近限制: {current:.0f}/{limit:.0f} ({ratio:.0%})"
            suggestion = f"建议尽快完成任务"
        elif ratio >= self.config.warn_threshold:
            action = GuardrailAction.WARN
            message = f"{guardrail_type} 使用较高: {current:.0f}/{limit:.0f} ({ratio:.0%})"
            suggestion = None
        else:
            action = GuardrailAction.ALLOW
            message = f"{guardrail_type}: {current:.0f}/{limit:.0f} ({ratio:.0%})"
            suggestion = None

        result = GuardrailCheckResult(
            action=action,
            guardrail_type=guardrail_type,
            current_value=current,
            limit_value=limit,
            usage_ratio=ratio,
            message=message,
            suggestion=suggestion,
        )

        # 记录历史
        self._check_history.append(result)

        # 触发回调
        if action == GuardrailAction.WARN and self.on_warning:
            self.on_warning(result)
        elif action == GuardrailAction.BLOCK and self.on_block:
            self.on_block(result)

        return result

    # ==================== 具体检查方法 ====================

    def check_turns(self, current: int = None) -> GuardrailCheckResult:
        """检查轮次限制"""
        current = current if current is not None else self._turn_count
        limit = self._get_limit("max_turns")
        return self._check("turn_limit", current, limit)

    def check_tool_calls(self, current: int = None) -> GuardrailCheckResult:
        """检查工具调用限制"""
        current = current if current is not None else len(self._tool_calls)
        limit = self._get_limit("max_tool_calls")
        return self._check("tool_limit", current, limit)

    def check_tokens(self, current: int = None) -> GuardrailCheckResult:
        """检查 Token 限制"""
        current = current if current is not None else self._token_count
        limit = self._get_limit("max_tokens")
        return self._check("token_budget", current, limit)

    def check_time(self) -> GuardrailCheckResult:
        """检查执行时间限制"""
        if not self._start_time:
            return GuardrailCheckResult(
                action=GuardrailAction.ALLOW,
                guardrail_type="time_limit",
                current_value=0,
                limit_value=self.config.max_execution_time,
                usage_ratio=0,
                message="会话未开始",
            )

        elapsed = (datetime.now() - self._start_time).total_seconds()
        limit = self._get_limit("max_execution_time")
        return self._check("time_limit", elapsed, limit)

    def check_depth(self, current: int = None) -> GuardrailCheckResult:
        """检查递归深度限制"""
        current = current if current is not None else self._depth
        limit = self._get_limit("max_depth")
        return self._check("depth_limit", current, limit)

    def check_all(self) -> List[GuardrailCheckResult]:
        """检查所有护栏"""
        return [
            self.check_turns(),
            self.check_tool_calls(),
            self.check_tokens(),
            self.check_time(),
            self.check_depth(),
        ]

    def get_blocking_issues(self) -> List[GuardrailCheckResult]:
        """获取阻断性问题"""
        results = self.check_all()
        return [r for r in results if r.action == GuardrailAction.BLOCK]

    def get_warnings(self) -> List[GuardrailCheckResult]:
        """获取警告"""
        results = self.check_all()
        return [r for r in results if r.action in (GuardrailAction.WARN, GuardrailAction.THROTTLE)]

    # ==================== 记录方法 ====================

    def record_turn(self):
        """记录一轮执行"""
        self._turn_count += 1

    def record_tool_call(self, tool_name: str):
        """记录工具调用"""
        self._tool_calls.append(tool_name)

    def record_tokens(self, count: int):
        """记录 Token 使用"""
        self._token_count += count

    def enter_depth(self):
        """进入嵌套层级"""
        self._depth += 1

    def exit_depth(self):
        """退出嵌套层级"""
        self._depth = max(0, self._depth - 1)

    # ==================== 统计和报告 ====================

    def get_usage_stats(self) -> Dict[str, Any]:
        """获取使用统计"""
        elapsed = 0
        if self._start_time:
            elapsed = (datetime.now() - self._start_time).total_seconds()

        return {
            "turns": {
                "current": self._turn_count,
                "limit": self._get_limit("max_turns"),
                "ratio": self._turn_count / self._get_limit("max_turns"),
            },
            "tool_calls": {
                "current": len(self._tool_calls),
                "limit": self._get_limit("max_tool_calls"),
                "ratio": len(self._tool_calls) / self._get_limit("max_tool_calls"),
                "tools_used": list(set(self._tool_calls)),
            },
            "tokens": {
                "current": self._token_count,
                "limit": self._get_limit("max_tokens"),
                "ratio": self._token_count / self._get_limit("max_tokens"),
            },
            "time": {
                "current": elapsed,
                "limit": self._get_limit("max_execution_time"),
                "ratio": elapsed / self._get_limit("max_execution_time"),
            },
            "context": {
                "complexity_level": self._complexity_level,
                "user_tier": self._user_tier,
            },
            "warnings_count": len(
                [
                    r
                    for r in self._check_history
                    if r.action in (GuardrailAction.WARN, GuardrailAction.THROTTLE)
                ]
            ),
            "blocks_count": len(
                [r for r in self._check_history if r.action == GuardrailAction.BLOCK]
            ),
        }

    def get_remaining_budget(self) -> Dict[str, float]:
        """获取剩余配额"""
        return {
            "turns": self._get_limit("max_turns") - self._turn_count,
            "tool_calls": self._get_limit("max_tool_calls") - len(self._tool_calls),
            "tokens": self._get_limit("max_tokens") - self._token_count,
        }

    def suggest_adjustments(self) -> List[str]:
        """根据使用情况建议调整"""
        suggestions = []
        stats = self.get_usage_stats()

        # 轮次使用过高
        if stats["turns"]["ratio"] > 0.8:
            suggestions.append(
                f"轮次使用率 {stats['turns']['ratio']:.0%}，" "建议简化执行策略或拆分任务"
            )

        # 工具调用过多
        if stats["tool_calls"]["ratio"] > 0.7:
            tools_used = stats["tool_calls"]["tools_used"]
            if len(tools_used) > 5:
                suggestions.append(f"使用了 {len(tools_used)} 种工具，" "建议聚焦核心工具")

        # Token 使用过高
        if stats["tokens"]["ratio"] > 0.6:
            suggestions.append(f"Token 使用率 {stats['tokens']['ratio']:.0%}，" "建议压缩上下文")

        return suggestions


def create_adaptive_guardrails(
    complexity_level: str = "medium", user_tier: str = "PRO", **config_overrides
) -> AdaptiveGuardrails:
    """
    创建自适应护栏

    Args:
        complexity_level: 复杂度等级
        user_tier: 用户等级
        **config_overrides: 配置覆盖

    Returns:
        AdaptiveGuardrails
    """
    config = GuardrailConfig(**config_overrides)
    guardrails = AdaptiveGuardrails(config)
    guardrails.set_context(complexity_level=complexity_level, user_tier=user_tier)
    return guardrails
