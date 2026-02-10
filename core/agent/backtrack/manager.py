"""
回溯管理器

职责：
- LLM 驱动的回溯决策
- 状态重评估与策略调整
- 执行回溯操作（Plan 重规划、工具替换、意图澄清、参数调整）

回溯类型：
- PLAN_REPLAN: Plan 重规划 - 当前 Plan 步骤不可行，重新分解
- TOOL_REPLACE: 工具替换 - 当前工具不适合，换用替代工具
- INTENT_CLARIFY: 意图澄清 - 用户意图理解偏差，请求澄清
- PARAM_ADJUST: 参数调整 - 执行参数不合理，调整后重试
- CONTEXT_ENRICH: 上下文补充 - 补充上下文信息后重试
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.agent.backtrack.error_classifier import (
    BacktrackType,
    ClassifiedError,
    ErrorClassifier,
    ErrorLayer,
    get_error_classifier,
)
from logger import get_logger

logger = get_logger(__name__)


class BacktrackDecision(Enum):
    """回溯决策"""

    CONTINUE = "continue"  # 继续执行下一轮
    BACKTRACK = "backtrack"  # 需要回溯
    FAIL_GRACEFULLY = "fail_gracefully"  # 优雅失败
    ESCALATE = "escalate"  # 升级（需要人工介入）


@dataclass
class BacktrackContext:
    """回溯上下文"""

    session_id: str
    turn: int
    max_turns: int
    error: ClassifiedError
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    backtrack_count: int = 0
    max_backtracks: int = 3  # 最大回溯次数

    # 当前执行状态
    current_plan: Optional[Dict[str, Any]] = None
    current_step_index: int = 0
    failed_tools: List[str] = field(default_factory=list)
    failed_strategies: List[str] = field(default_factory=list)


@dataclass
class BacktrackResult:
    """回溯结果"""

    decision: BacktrackDecision
    backtrack_type: BacktrackType
    action: Dict[str, Any]  # 具体操作
    reason: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "backtrack_type": self.backtrack_type.value,
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
        }


class BacktrackManager:
    """
    回溯管理器

    负责处理业务逻辑层错误的回溯决策，
    使用 LLM 进行状态重评估和策略调整。
    """

    def __init__(
        self,
        llm_service: Optional[Any] = None,
        error_classifier: Optional[ErrorClassifier] = None,
        max_backtracks: int = 3,
    ):
        """
        初始化回溯管理器

        Args:
            llm_service: LLM 服务（用于智能决策）
            error_classifier: 错误分类器
            max_backtracks: 最大回溯次数
        """
        self.llm_service = llm_service
        self.error_classifier = error_classifier or get_error_classifier()
        self.max_backtracks = max_backtracks

        # 回溯历史记录
        self._backtrack_history: Dict[str, List[BacktrackResult]] = {}

    async def evaluate_and_decide(
        self, ctx: BacktrackContext, use_llm: bool = True
    ) -> BacktrackResult:
        """
        评估错误并做出回溯决策

        Args:
            ctx: 回溯上下文
            use_llm: 是否使用 LLM 进行智能决策

        Returns:
            BacktrackResult: 回溯决策结果
        """
        logger.info(
            f"🔄 开始回溯评估: session={ctx.session_id}, "
            f"turn={ctx.turn}, backtrack_count={ctx.backtrack_count}"
        )

        # 检查是否已达最大回溯次数
        if ctx.backtrack_count >= ctx.max_backtracks:
            logger.warning(f"⚠️ 已达最大回溯次数 ({ctx.max_backtracks})，优雅失败")
            return BacktrackResult(
                decision=BacktrackDecision.FAIL_GRACEFULLY,
                backtrack_type=BacktrackType.NO_BACKTRACK,
                action={"message": "已达最大回溯次数"},
                reason=f"已尝试 {ctx.backtrack_count} 次回溯仍失败",
                confidence=1.0,
            )

        # 检查是否是基础设施层错误（不应该到这里）
        if ctx.error.is_infrastructure_error():
            logger.info("📦 基础设施层错误，使用 resilience 机制处理")
            return BacktrackResult(
                decision=BacktrackDecision.CONTINUE,
                backtrack_type=BacktrackType.NO_BACKTRACK,
                action={"delegate_to": "resilience"},
                reason="基础设施层错误由 resilience 机制处理",
                confidence=1.0,
            )

        # 业务逻辑层错误，需要决策
        if use_llm and self.llm_service:
            result = await self._llm_decide(ctx)
        else:
            result = self._rule_based_decide(ctx)

        # 记录回溯历史
        self._record_backtrack(ctx.session_id, result)

        logger.info(
            f"✅ 回溯决策完成: decision={result.decision.value}, "
            f"backtrack_type={result.backtrack_type.value}, "
            f"confidence={result.confidence:.2f}"
        )

        return result

    async def _llm_decide(self, ctx: BacktrackContext) -> BacktrackResult:
        """使用 LLM 进行智能决策"""
        try:
            from prompts.backtrack_prompt import (
                BACKTRACK_DECISION_PROMPT,
                BACKTRACK_SYSTEM_PROMPT,
            )

            prompt = BACKTRACK_DECISION_PROMPT.format(
                error_type=type(ctx.error.original_error).__name__,
                error_message=str(ctx.error.original_error),
                error_category=ctx.error.category.value,
                suggested_backtrack_type=ctx.error.backtrack_type.value,
                turn=ctx.turn,
                max_turns=ctx.max_turns,
                backtrack_count=ctx.backtrack_count,
                max_backtracks=ctx.max_backtracks,
                current_step=self._format_current_step(ctx),
                failed_tools=", ".join(ctx.failed_tools) or "无",
                failed_strategies=", ".join(ctx.failed_strategies) or "无",
                execution_history=self._format_execution_history(ctx),
            )

            response = await self.llm_service.create_message_async(
                messages=[{"role": "user", "content": prompt}],
                system=BACKTRACK_SYSTEM_PROMPT,
            )

            # 解析响应
            result = self._parse_llm_response(response.content)
            return result

        except Exception as e:
            logger.warning(f"⚠️ LLM 决策失败，回退到规则决策: {e}")
            return self._rule_based_decide(ctx)

    def _rule_based_decide(self, ctx: BacktrackContext) -> BacktrackResult:
        """
        Conservative fallback when LLM is unavailable.

        Uses PARAM_ADJUST as the safest default (least disruptive).
        If PARAM_ADJUST was already tried for this step, escalates
        via the deterministic escalation path.
        """
        backtrack_type = BacktrackType.PARAM_ADJUST

        # Escalate if this strategy already failed for the current step
        strategy_key = f"{backtrack_type.value}_{ctx.current_step_index}"
        if strategy_key in ctx.failed_strategies:
            backtrack_type = self._escalate_backtrack_type(backtrack_type)

        action = self._build_action(backtrack_type, ctx)

        return BacktrackResult(
            decision=BacktrackDecision.BACKTRACK,
            backtrack_type=backtrack_type,
            action=action,
            reason="LLM 不可用，使用保守回溯策略",
            confidence=0.4,
        )

    def _escalate_backtrack_type(self, current_type: BacktrackType) -> BacktrackType:
        """升级回溯类型"""
        escalation_path = {
            BacktrackType.PARAM_ADJUST: BacktrackType.TOOL_REPLACE,
            BacktrackType.TOOL_REPLACE: BacktrackType.PLAN_REPLAN,
            BacktrackType.CONTEXT_ENRICH: BacktrackType.INTENT_CLARIFY,
            BacktrackType.PLAN_REPLAN: BacktrackType.INTENT_CLARIFY,
            BacktrackType.INTENT_CLARIFY: BacktrackType.NO_BACKTRACK,  # 需要人工
        }

        return escalation_path.get(current_type, BacktrackType.PLAN_REPLAN)

    def _build_action(self, backtrack_type: BacktrackType, ctx: BacktrackContext) -> Dict[str, Any]:
        """构建具体操作"""
        if backtrack_type == BacktrackType.PLAN_REPLAN:
            return {
                "operation": "replan",
                "from_step": ctx.current_step_index,
                "hint": "基于当前错误重新规划后续步骤",
            }

        if backtrack_type == BacktrackType.TOOL_REPLACE:
            return {
                "operation": "replace_tool",
                "failed_tool": ctx.failed_tools[-1] if ctx.failed_tools else None,
                "find_alternative": True,
            }

        if backtrack_type == BacktrackType.PARAM_ADJUST:
            return {
                "operation": "adjust_params",
                "retry_with_modified_params": True,
            }

        if backtrack_type == BacktrackType.CONTEXT_ENRICH:
            return {
                "operation": "enrich_context",
                "gather_more_info": True,
            }

        if backtrack_type == BacktrackType.INTENT_CLARIFY:
            return {
                "operation": "clarify_intent",
                "ask_user": True,
                "question_hint": "请澄清您的具体需求",
            }

        return {"operation": "unknown"}

    def _parse_llm_response(self, content: str) -> BacktrackResult:
        """解析 LLM 响应"""
        try:
            # 提取 JSON
            json_match = content
            if "```json" in content:
                json_match = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_match = content.split("```")[1].split("```")[0]

            data = json.loads(json_match.strip())

            decision = BacktrackDecision[data.get("decision", "BACKTRACK").upper()]
            backtrack_type = BacktrackType[
                data.get("backtrack_type", "NO_BACKTRACK").upper().replace("-", "_")
            ]

            return BacktrackResult(
                decision=decision,
                backtrack_type=backtrack_type,
                action=data.get("action", {}),
                reason=data.get("reason", ""),
                confidence=float(data.get("confidence", 0.5)),
            )

        except Exception as e:
            logger.warning(f"⚠️ 解析 LLM 响应失败: {e}")
            # 返回默认决策
            return BacktrackResult(
                decision=BacktrackDecision.BACKTRACK,
                backtrack_type=BacktrackType.PARAM_ADJUST,
                action={"operation": "retry_with_adjustment"},
                reason="LLM 响应解析失败，使用默认策略",
                confidence=0.3,
            )

    def _format_current_step(self, ctx: BacktrackContext) -> str:
        """格式化当前步骤信息"""
        if not ctx.current_plan:
            return "无计划信息"

        steps = ctx.current_plan.get("steps", [])
        if ctx.current_step_index < len(steps):
            step = steps[ctx.current_step_index]
            return f"步骤 {ctx.current_step_index + 1}: {step.get('description', '未知')}"

        return f"步骤 {ctx.current_step_index + 1}: 未知"

    def _format_execution_history(self, ctx: BacktrackContext) -> str:
        """格式化执行历史"""
        if not ctx.execution_history:
            return "无执行历史"

        # 只显示最近 5 条
        recent = ctx.execution_history[-5:]
        lines = []
        for i, entry in enumerate(recent):
            status = "✅" if entry.get("success") else "❌"
            action = entry.get("action", "unknown")
            result = entry.get("result", "")[:100]  # 截断
            lines.append(f"{i+1}. {status} {action}: {result}")

        return "\n".join(lines)

    def _record_backtrack(self, session_id: str, result: BacktrackResult):
        """记录回溯历史"""
        if session_id not in self._backtrack_history:
            self._backtrack_history[session_id] = []

        self._backtrack_history[session_id].append(result)

        # 限制历史记录数量
        if len(self._backtrack_history[session_id]) > 20:
            self._backtrack_history[session_id] = self._backtrack_history[session_id][-20:]

    def get_backtrack_history(self, session_id: str) -> List[BacktrackResult]:
        """获取回溯历史"""
        return self._backtrack_history.get(session_id, [])

    def clear_session_history(self, session_id: str):
        """清除会话历史"""
        if session_id in self._backtrack_history:
            del self._backtrack_history[session_id]

    # NOTE: execute_backtrack() 回调方法已删除（从未被调用）。
    # 回溯执行逻辑内联在 RVRBExecutor._handle_tool_error_with_backtrack() 中。


# 全局单例
_backtrack_manager: Optional[BacktrackManager] = None


def get_backtrack_manager(llm_service: Optional[Any] = None) -> BacktrackManager:
    """获取全局回溯管理器实例

    注意：如果传入了 llm_service 且现有实例缺少 LLM，会自动更新。
    这修复了单例首次不带 LLM 创建后，后续 LLM 决策永远不执行的 Bug。
    """
    global _backtrack_manager
    if _backtrack_manager is None:
        _backtrack_manager = BacktrackManager(llm_service=llm_service)
    elif llm_service and not _backtrack_manager.llm_service:
        # 首次创建时 LLM 可能为 None，后续传入时必须更新
        logger.info("🔄 BacktrackManager: 更新 LLM 服务（首次创建时缺失）")
        _backtrack_manager.llm_service = llm_service
    return _backtrack_manager
