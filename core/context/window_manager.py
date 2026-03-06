"""
动态上下文窗口管理器

在标准窗口即将耗尽时，通过 HITL 询问用户是否扩展到更大窗口。
仅 Claude 等支持 max_extended_input_tokens 的模型会触发扩展流程。

数据流:
  ContextWindowManager.check_expansion_needed(current_tokens)
    → ExpansionInfo (包含费用预估等上下文数据)
      → AdaptiveTerminator 返回 ASK_USER decision
        → RVR-B executor 拼装话术、yield SSE 事件
          → 前端渲染 HITL 对话框
            → 用户选择 expand/optimize
              → apply_expansion() 或 decline_expansion()
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from logger import get_logger

if TYPE_CHECKING:
    from core.context.compaction import ContextStrategy

logger = get_logger("context.window_manager")


@dataclass
class ExpansionInfo:
    """窗口扩展 HITL 所需的上下文数据，传给 executor 拼装话术"""

    current_tokens: int
    current_budget: int
    expanded_budget: int
    usage_ratio: float
    model_name: Optional[str] = None
    standard_input_price: Optional[float] = None
    extended_input_price: Optional[float] = None
    standard_output_price: Optional[float] = None
    extended_output_price: Optional[float] = None


class ContextWindowManager:
    """
    动态上下文窗口管理器

    职责:
    - 检测当前 token 使用率是否达到扩展 HITL 阈值
    - 返回 ExpansionInfo 供 executor 拼装话术
    - 处理用户的扩展/拒绝决策
    - 联动 Claude Adapter 启用 1M beta header
    """

    def __init__(self, strategy: "ContextStrategy") -> None:
        self.strategy = strategy
        self._expansion_asked: bool = False
        self._expansion_declined: bool = False

    @property
    def can_expand(self) -> bool:
        """当前模型是否支持窗口扩展且尚未询问过"""
        return (
            not self._expansion_asked
            and not self.strategy.is_expanded
            and self.strategy.max_expandable_budget is not None
        )

    def check_expansion_needed(
        self, current_tokens: int
    ) -> Optional[ExpansionInfo]:
        """
        检查是否需要触发窗口扩展 HITL。

        Returns:
            ExpansionInfo 供 executor 拼装话术，None 表示不需要扩展。
        """
        if not self.can_expand:
            return None

        if self.strategy.token_budget <= 0:
            return None

        usage_ratio = current_tokens / self.strategy.token_budget
        if usage_ratio < self.strategy.expansion_hitl_threshold:
            return None

        logger.info(
            f"上下文窗口扩展触发: {current_tokens:,} / {self.strategy.token_budget:,} "
            f"({usage_ratio:.0%}) >= {self.strategy.expansion_hitl_threshold:.0%}"
        )

        return ExpansionInfo(
            current_tokens=current_tokens,
            current_budget=self.strategy.token_budget,
            expanded_budget=self.strategy.max_expandable_budget,
            usage_ratio=usage_ratio,
            model_name=self.strategy.model_name,
        )

    def fill_pricing_info(self, info: ExpansionInfo) -> None:
        """从 ModelRegistry 填充费用预估到 ExpansionInfo"""
        if not info.model_name:
            return
        try:
            from core.llm.model_registry import ModelRegistry

            model_cfg = ModelRegistry.get(info.model_name)
            if not model_cfg:
                return
            p = model_cfg.pricing
            info.standard_input_price = p.input_per_million
            info.extended_input_price = (
                p.long_context_input_per_million or p.input_per_million
            )
            info.standard_output_price = p.output_per_million
            info.extended_output_price = (
                p.long_context_output_per_million or p.output_per_million
            )
        except Exception:
            logger.debug("填充费用预估失败", exc_info=True)

    def apply_expansion(self, llm_service: Any = None) -> None:
        """用户同意扩展后调用"""
        old_budget = self.strategy.token_budget
        self.strategy.token_budget = self.strategy.max_expandable_budget
        self.strategy.is_expanded = True
        self._expansion_asked = True

        if llm_service and hasattr(llm_service, "enable_extended_context"):
            llm_service.enable_extended_context()

        logger.info(
            f"上下文窗口已扩展: {old_budget:,} → {self.strategy.token_budget:,}"
        )

    def decline_expansion(self) -> None:
        """用户拒绝扩展后调用，后续由 compaction 接管"""
        self._expansion_asked = True
        self._expansion_declined = True
        logger.info("用户拒绝扩展，将启动上下文压缩")
