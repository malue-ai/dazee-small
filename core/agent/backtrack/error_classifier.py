"""
错误层级分类器

职责：
- 区分基础设施层错误（Layer 1）与业务逻辑层错误（Layer 2）
- Layer 1 使用确定性规则分类（异常类型 + HTTP 协议模式）
- Layer 2 不做语义分类，返回保守默认值，由 BacktrackManager 调 LLM 决策

错误分层模型：
- Layer 1（基础设施层）：API 超时、Rate Limit、服务不可用
  - 处理策略：重试、降级、主备切换
  - 由 ZenFlux 现有的 resilience 机制处理
  - 分类方式：Python 异常类型 + HTTP/网络协议模式匹配（确定性）

- Layer 2（业务逻辑层）：Plan 不合理、工具选错、结果不满足需求
  - 处理策略：状态重评估、策略调整、部分重规划
  - 分类方式：由 BacktrackManager 通过 LLM 语义推断（LLM-First）
  - 本分类器仅标记为 BUSINESS_LOGIC + 保守默认值
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from logger import get_logger

logger = get_logger(__name__)


class ErrorLayer(Enum):
    """错误层级"""

    INFRASTRUCTURE = "infrastructure"  # Layer 1: 基础设施层
    BUSINESS_LOGIC = "business_logic"  # Layer 2: 业务逻辑层
    UNKNOWN = "unknown"  # 未知层级


class ErrorCategory(Enum):
    """错误类别（细分）"""

    # Layer 1: 基础设施层错误
    API_TIMEOUT = "api_timeout"  # API 超时
    RATE_LIMIT = "rate_limit"  # 速率限制
    SERVICE_UNAVAILABLE = "service_unavailable"  # 服务不可用
    NETWORK_ERROR = "network_error"  # 网络错误
    AUTHENTICATION_ERROR = "auth_error"  # 认证错误
    QUOTA_EXCEEDED = "quota_exceeded"  # 配额超限

    # Layer 2: 业务逻辑层错误（具体类别由 LLM 判断，此处仅作枚举定义）
    PLAN_INVALID = "plan_invalid"
    TOOL_MISMATCH = "tool_mismatch"
    RESULT_UNSATISFACTORY = "result_unsatisfactory"
    INTENT_UNCLEAR = "intent_unclear"
    PARAMETER_ERROR = "parameter_error"
    CONTEXT_INSUFFICIENT = "context_insufficient"
    EXECUTION_LOGIC_ERROR = "execution_logic_error"

    # 未知
    UNKNOWN = "unknown"


class BacktrackType(Enum):
    """回溯类型（仅适用于 Layer 2 错误）"""

    PLAN_REPLAN = "plan_replan"  # Plan 重规划
    TOOL_REPLACE = "tool_replace"  # 工具替换
    INTENT_CLARIFY = "intent_clarify"  # 意图澄清
    PARAM_ADJUST = "param_adjust"  # 参数调整
    CONTEXT_ENRICH = "context_enrich"  # 上下文补充
    NO_BACKTRACK = "no_backtrack"  # 不需要回溯（Layer 1 或可重试）


@dataclass
class ClassifiedError:
    """分类后的错误"""

    original_error: Exception
    layer: ErrorLayer
    category: ErrorCategory
    backtrack_type: BacktrackType
    is_retryable: bool
    confidence: float  # 分类置信度 0-1
    context: Dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""

    def is_infrastructure_error(self) -> bool:
        """是否是基础设施层错误"""
        return self.layer == ErrorLayer.INFRASTRUCTURE

    def is_business_logic_error(self) -> bool:
        """是否是业务逻辑层错误"""
        return self.layer == ErrorLayer.BUSINESS_LOGIC

    def needs_backtrack(self) -> bool:
        """是否需要回溯"""
        return self.backtrack_type != BacktrackType.NO_BACKTRACK

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error_type": type(self.original_error).__name__,
            "error_message": str(self.original_error),
            "layer": self.layer.value,
            "category": self.category.value,
            "backtrack_type": self.backtrack_type.value,
            "is_retryable": self.is_retryable,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
            "context": self.context,
        }


class ErrorClassifier:
    """
    错误层级分类器

    Layer 1（基础设施）：确定性规则分类
    - Python 异常类型映射（TimeoutError → INFRASTRUCTURE）
    - HTTP/网络协议模式匹配（"429" → RATE_LIMIT）
    - 这些是技术协议层面的确定性检查，非语义判断

    Layer 2（业务逻辑）：保守默认值
    - 不做正则/关键词语义分类（违反 LLM-First）
    - 返回 PARAM_ADJUST 保守默认，由 BacktrackManager 调 LLM 决策
    """

    # ── Layer 1: 基础设施层协议模式 ──────────────────────────
    # 匹配对象：HTTP 状态码、网络库异常消息（确定性技术字符串）
    # 不涉及自然语言语义判断，符合 LLM-First 规范
    INFRASTRUCTURE_PATTERNS = {
        ErrorCategory.API_TIMEOUT: [
            r"timeout",
            r"timed?\s*out",
            r"deadline\s*exceeded",
            r"request\s*timeout",
        ],
        ErrorCategory.RATE_LIMIT: [
            r"rate\s*limit",
            r"too\s*many\s*requests",
            r"429",
            r"throttl",
        ],
        ErrorCategory.SERVICE_UNAVAILABLE: [
            r"service\s*unavailable",
            r"503",
            r"502",
            r"bad\s*gateway",
            r"internal\s*server",
            r"500",
        ],
        ErrorCategory.NETWORK_ERROR: [
            r"connection\s*(error|refused|reset|closed)",
            r"network\s*(error|unreachable)",
            r"dns\s*(error|resolution)",
            r"socket\s*error",
            r"ssl\s*error",
            r"certificate\s*(error|verify)",
        ],
        ErrorCategory.AUTHENTICATION_ERROR: [
            r"unauthorized",
            r"401",
            r"403",
            r"forbidden",
            r"invalid\s*(api\s*)?key",
            r"access\s*denied",
        ],
        ErrorCategory.QUOTA_EXCEEDED: [
            r"quota\s*exceeded",
            r"limit\s*exceeded",
            r"billing",
            r"payment\s*required",
            r"402",
        ],
    }

    # ── 异常类型到层级的映射（确定性） ────────────────────────
    EXCEPTION_TYPE_MAPPING: Dict[str, ErrorLayer] = {
        # Layer 1: 基础设施层异常类型
        "TimeoutError": ErrorLayer.INFRASTRUCTURE,
        "ConnectionError": ErrorLayer.INFRASTRUCTURE,
        "ConnectionRefusedError": ErrorLayer.INFRASTRUCTURE,
        "ConnectionResetError": ErrorLayer.INFRASTRUCTURE,
        "SSLError": ErrorLayer.INFRASTRUCTURE,
        "HTTPError": ErrorLayer.INFRASTRUCTURE,
        "RequestException": ErrorLayer.INFRASTRUCTURE,
        "APIError": ErrorLayer.INFRASTRUCTURE,
        "RateLimitError": ErrorLayer.INFRASTRUCTURE,
        "AuthenticationError": ErrorLayer.INFRASTRUCTURE,
        "ServiceUnavailableError": ErrorLayer.INFRASTRUCTURE,
        # Layer 2: 业务逻辑层异常类型
        "PlanExecutionError": ErrorLayer.BUSINESS_LOGIC,
        "ToolExecutionError": ErrorLayer.BUSINESS_LOGIC,
        "ValidationError": ErrorLayer.BUSINESS_LOGIC,
        "IntentAnalysisError": ErrorLayer.BUSINESS_LOGIC,
        "ContextError": ErrorLayer.BUSINESS_LOGIC,
    }

    def __init__(self):
        """Initialize classifier (compile infra patterns only)."""
        self._compiled_infra_patterns = {
            category: [re.compile(p, re.IGNORECASE) for p in patterns]
            for category, patterns in self.INFRASTRUCTURE_PATTERNS.items()
        }

    def classify(
        self, error: Exception, context: Optional[Dict[str, Any]] = None
    ) -> ClassifiedError:
        """
        Classify an error into infrastructure vs business-logic layer.

        Flow:
        1. Exception type mapping (deterministic)
        2. Infrastructure pattern matching (HTTP/network protocol strings)
        3. If neither matches → BUSINESS_LOGIC with conservative defaults

        Layer 2 errors get PARAM_ADJUST as a safe default; the actual
        backtrack strategy is determined by BacktrackManager via LLM.

        Args:
            error: The exception
            context: Extra context (tool_name, step_index, etc.)

        Returns:
            ClassifiedError with classification result
        """
        context = context or {}
        error_message = str(error).lower()
        error_type = type(error).__name__

        # Step 1: Exception type (deterministic)
        layer = self._classify_by_exception_type(error_type)
        category = ErrorCategory.UNKNOWN
        confidence = 0.5

        if layer == ErrorLayer.INFRASTRUCTURE:
            confidence = 0.8
            category = self._match_infra_category(error_message)
        elif layer == ErrorLayer.BUSINESS_LOGIC:
            confidence = 0.8
            # Layer 2: no regex semantic classification, keep UNKNOWN category
            # BacktrackManager._llm_decide will determine the actual strategy

        # Step 2: Infrastructure pattern matching (only if not yet classified)
        if layer == ErrorLayer.UNKNOWN:
            matched_category = self._match_infra_category(error_message)
            if matched_category != ErrorCategory.UNKNOWN:
                layer = ErrorLayer.INFRASTRUCTURE
                category = matched_category
                confidence = 0.7

        # Step 3: If still unknown → treat as business logic (conservative)
        # Most tool execution errors that don't match infra patterns are
        # business logic issues that the LLM should analyze.
        if layer == ErrorLayer.UNKNOWN:
            layer = ErrorLayer.BUSINESS_LOGIC
            confidence = 0.4

        # Step 4: Determine backtrack strategy
        backtrack_type, suggested_action = self._determine_backtrack_strategy(layer)
        is_retryable = self._is_retryable(layer, category)

        classified = ClassifiedError(
            original_error=error,
            layer=layer,
            category=category,
            backtrack_type=backtrack_type,
            is_retryable=is_retryable,
            confidence=confidence,
            context=context,
            suggested_action=suggested_action,
        )

        logger.info(
            f"🔍 错误分类完成: layer={layer.value}, category={category.value}, "
            f"backtrack={backtrack_type.value}, confidence={confidence:.2f}"
        )

        return classified

    def _classify_by_exception_type(self, error_type: str) -> ErrorLayer:
        """Classify by Python exception type (deterministic)."""
        return self.EXCEPTION_TYPE_MAPPING.get(error_type, ErrorLayer.UNKNOWN)

    def _match_infra_category(self, error_message: str) -> ErrorCategory:
        """Match infrastructure category from protocol-level error patterns."""
        for category, compiled_patterns in self._compiled_infra_patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(error_message):
                    return category
        return ErrorCategory.UNKNOWN

    def _determine_backtrack_strategy(
        self, layer: ErrorLayer
    ) -> tuple[BacktrackType, str]:
        """
        Determine backtrack strategy.

        - Layer 1 (infrastructure): NO_BACKTRACK, handled by resilience
        - Layer 2 (business logic): conservative PARAM_ADJUST default
          Actual strategy decided by BacktrackManager via LLM
        """
        if layer == ErrorLayer.INFRASTRUCTURE:
            return BacktrackType.NO_BACKTRACK, "使用基础设施层重试/降级机制"

        # Layer 2: conservative default — BacktrackManager._llm_decide
        # will override with a proper strategy
        return BacktrackType.PARAM_ADJUST, "业务逻辑错误，由回溯管理器决策具体策略"

    def _is_retryable(self, layer: ErrorLayer, category: ErrorCategory) -> bool:
        """Check if error is retryable (infrastructure layer only)."""
        if layer != ErrorLayer.INFRASTRUCTURE:
            return False

        retryable_categories = {
            ErrorCategory.API_TIMEOUT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.SERVICE_UNAVAILABLE,
            ErrorCategory.NETWORK_ERROR,
        }

        return category in retryable_categories

    # ── Convenience methods (public API unchanged) ─────────────

    def classify_tool_error(
        self,
        error: Exception,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Optional[Dict[str, Any]] = None,
    ) -> ClassifiedError:
        """Classify a tool execution error."""
        context = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "source": "tool_execution",
        }
        return self.classify(error, context)

    def classify_plan_error(
        self, error: Exception, plan_id: str, step_index: int, step_content: Optional[str] = None
    ) -> ClassifiedError:
        """Classify a plan execution error."""
        context = {
            "plan_id": plan_id,
            "step_index": step_index,
            "step_content": step_content,
            "source": "plan_execution",
        }
        return self.classify(error, context)

    def classify_llm_error(
        self, error: Exception, model_name: str, turn: int, max_turns: int
    ) -> ClassifiedError:
        """Classify an LLM call error."""
        context = {
            "model_name": model_name,
            "turn": turn,
            "max_turns": max_turns,
            "source": "llm_call",
        }
        return self.classify(error, context)


# Global singleton
_error_classifier: Optional[ErrorClassifier] = None


def get_error_classifier() -> ErrorClassifier:
    """Get the global error classifier instance."""
    global _error_classifier
    if _error_classifier is None:
        _error_classifier = ErrorClassifier()
    return _error_classifier
