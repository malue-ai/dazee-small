"""
错误层级分类器

职责：
- 区分基础设施层错误（Layer 1）与业务逻辑层错误（Layer 2）
- 为不同层级的错误提供不同的处理建议
- 支持 BacktrackManager 的回溯决策

错误分层模型：
- Layer 1（基础设施层）：API 超时、Rate Limit、服务不可用
  - 处理策略：重试、降级、主备切换
  - 由 ZenFlux 现有的 resilience 机制处理
  
- Layer 2（业务逻辑层）：Plan 不合理、工具选错、结果不满足需求
  - 处理策略：状态重评估、策略调整、部分重规划
  - 由 BacktrackManager 处理
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Type
import re

from logger import get_logger

logger = get_logger(__name__)


class ErrorLayer(Enum):
    """错误层级"""
    INFRASTRUCTURE = "infrastructure"  # Layer 1: 基础设施层
    BUSINESS_LOGIC = "business_logic"  # Layer 2: 业务逻辑层
    UNKNOWN = "unknown"                # 未知层级


class ErrorCategory(Enum):
    """错误类别（细分）"""
    # Layer 1: 基础设施层错误
    API_TIMEOUT = "api_timeout"              # API 超时
    RATE_LIMIT = "rate_limit"                # 速率限制
    SERVICE_UNAVAILABLE = "service_unavailable"  # 服务不可用
    NETWORK_ERROR = "network_error"          # 网络错误
    AUTHENTICATION_ERROR = "auth_error"      # 认证错误
    QUOTA_EXCEEDED = "quota_exceeded"        # 配额超限
    
    # Layer 2: 业务逻辑层错误
    PLAN_INVALID = "plan_invalid"            # Plan 不合理
    TOOL_MISMATCH = "tool_mismatch"          # 工具选错
    RESULT_UNSATISFACTORY = "result_unsatisfactory"  # 结果不满足需求
    INTENT_UNCLEAR = "intent_unclear"        # 用户意图不明确
    PARAMETER_ERROR = "parameter_error"      # 参数错误（业务层面）
    CONTEXT_INSUFFICIENT = "context_insufficient"  # 上下文不足
    EXECUTION_LOGIC_ERROR = "execution_logic_error"  # 执行逻辑错误
    
    # 未知
    UNKNOWN = "unknown"


class BacktrackType(Enum):
    """回溯类型（仅适用于 Layer 2 错误）"""
    PLAN_REPLAN = "plan_replan"          # Plan 重规划
    TOOL_REPLACE = "tool_replace"        # 工具替换
    INTENT_CLARIFY = "intent_clarify"    # 意图澄清
    PARAM_ADJUST = "param_adjust"        # 参数调整
    CONTEXT_ENRICH = "context_enrich"    # 上下文补充
    NO_BACKTRACK = "no_backtrack"        # 不需要回溯（Layer 1 或可重试）


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
    
    区分基础设施层错误与业务逻辑层错误，
    为不同层级的错误提供不同的处理建议。
    """
    
    # Layer 1 错误关键词模式
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
            r"quota\s*exceeded",
        ],
        ErrorCategory.SERVICE_UNAVAILABLE: [
            r"service\s*unavailable",
            r"503",
            r"502",
            r"bad\s*gateway",
            r"server\s*error",
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
            r"authentication\s*(failed|error)",
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
    
    # Layer 2 错误关键词模式
    BUSINESS_LOGIC_PATTERNS = {
        ErrorCategory.PLAN_INVALID: [
            r"plan\s*(invalid|failed|error)",
            r"cannot\s*execute\s*plan",
            r"step\s*failed",
            r"task\s*decomposition\s*error",
        ],
        ErrorCategory.TOOL_MISMATCH: [
            r"tool\s*(not\s*found|mismatch|unavailable)",
            r"wrong\s*tool",
            r"unsupported\s*tool",
            r"tool\s*selection\s*error",
        ],
        ErrorCategory.RESULT_UNSATISFACTORY: [
            r"result\s*(unsatisfactory|incomplete|invalid)",
            r"output\s*(error|invalid)",
            r"unexpected\s*result",
            r"quality\s*(check|validation)\s*failed",
        ],
        ErrorCategory.INTENT_UNCLEAR: [
            r"intent\s*(unclear|ambiguous)",
            r"clarification\s*needed",
            r"ambiguous\s*request",
            r"cannot\s*understand",
        ],
        ErrorCategory.PARAMETER_ERROR: [
            r"(invalid|missing|wrong)\s*parameter",
            r"parameter\s*(error|validation)",
            r"argument\s*(error|invalid)",
            r"input\s*validation\s*failed",
        ],
        ErrorCategory.CONTEXT_INSUFFICIENT: [
            r"context\s*(insufficient|missing)",
            r"need\s*more\s*(context|information)",
            r"incomplete\s*context",
        ],
        ErrorCategory.EXECUTION_LOGIC_ERROR: [
            r"execution\s*(error|failed)",
            r"logic\s*error",
            r"assertion\s*failed",
            r"unexpected\s*state",
        ],
    }
    
    # 异常类型到层级的映射
    EXCEPTION_TYPE_MAPPING: Dict[str, ErrorLayer] = {
        # Layer 1 异常类型
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
        
        # Layer 2 异常类型
        "PlanExecutionError": ErrorLayer.BUSINESS_LOGIC,
        "ToolExecutionError": ErrorLayer.BUSINESS_LOGIC,
        "ValidationError": ErrorLayer.BUSINESS_LOGIC,
        "IntentAnalysisError": ErrorLayer.BUSINESS_LOGIC,
        "ContextError": ErrorLayer.BUSINESS_LOGIC,
    }
    
    def __init__(self):
        """初始化分类器"""
        # 编译正则表达式
        self._compiled_infra_patterns = {
            category: [re.compile(p, re.IGNORECASE) for p in patterns]
            for category, patterns in self.INFRASTRUCTURE_PATTERNS.items()
        }
        self._compiled_business_patterns = {
            category: [re.compile(p, re.IGNORECASE) for p in patterns]
            for category, patterns in self.BUSINESS_LOGIC_PATTERNS.items()
        }
    
    def classify(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> ClassifiedError:
        """
        分类错误
        
        Args:
            error: 异常对象
            context: 额外上下文信息，可包含：
                - tool_name: 工具名称
                - tool_input: 工具输入
                - step_index: 当前步骤索引
                - plan_id: 计划 ID
                - turn: 当前轮次
                
        Returns:
            ClassifiedError: 分类结果
        """
        context = context or {}
        error_message = str(error).lower()
        error_type = type(error).__name__
        
        # 步骤 1：通过异常类型判断
        layer = self._classify_by_exception_type(error_type)
        category = ErrorCategory.UNKNOWN
        confidence = 0.5
        
        if layer != ErrorLayer.UNKNOWN:
            confidence = 0.8
            category = self._get_category_from_patterns(
                error_message, 
                layer == ErrorLayer.INFRASTRUCTURE
            )
        
        # 步骤 2：通过错误消息模式匹配
        if layer == ErrorLayer.UNKNOWN or category == ErrorCategory.UNKNOWN:
            matched_layer, matched_category, pattern_confidence = \
                self._classify_by_patterns(error_message)
            
            if pattern_confidence > confidence:
                layer = matched_layer
                category = matched_category
                confidence = pattern_confidence
        
        # 步骤 3：通过上下文信息辅助判断
        if context:
            layer, category, confidence = self._refine_by_context(
                layer, category, confidence, context, error_message
            )
        
        # 步骤 4：确定回溯类型和处理建议
        backtrack_type, suggested_action = self._determine_backtrack_strategy(
            layer, category, context
        )
        
        # 步骤 5：确定是否可重试
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
        """通过异常类型分类"""
        return self.EXCEPTION_TYPE_MAPPING.get(error_type, ErrorLayer.UNKNOWN)
    
    def _get_category_from_patterns(
        self,
        error_message: str,
        is_infrastructure: bool
    ) -> ErrorCategory:
        """从模式匹配获取类别"""
        patterns = (
            self._compiled_infra_patterns 
            if is_infrastructure 
            else self._compiled_business_patterns
        )
        
        for category, compiled_patterns in patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(error_message):
                    return category
        
        return ErrorCategory.UNKNOWN
    
    def _classify_by_patterns(
        self,
        error_message: str
    ) -> tuple[ErrorLayer, ErrorCategory, float]:
        """通过模式匹配分类"""
        # 先检查基础设施层
        for category, compiled_patterns in self._compiled_infra_patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(error_message):
                    return ErrorLayer.INFRASTRUCTURE, category, 0.7
        
        # 再检查业务逻辑层
        for category, compiled_patterns in self._compiled_business_patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(error_message):
                    return ErrorLayer.BUSINESS_LOGIC, category, 0.7
        
        return ErrorLayer.UNKNOWN, ErrorCategory.UNKNOWN, 0.3
    
    def _refine_by_context(
        self,
        layer: ErrorLayer,
        category: ErrorCategory,
        confidence: float,
        context: Dict[str, Any],
        error_message: str
    ) -> tuple[ErrorLayer, ErrorCategory, float]:
        """通过上下文信息细化分类"""
        # 如果有工具名称，更可能是业务逻辑错误
        if context.get("tool_name"):
            tool_name = context["tool_name"]
            
            # 检查是否是工具执行相关的错误
            if any(keyword in error_message for keyword in [
                "tool", tool_name.lower(), "execution", "result"
            ]):
                if layer == ErrorLayer.UNKNOWN:
                    layer = ErrorLayer.BUSINESS_LOGIC
                    category = ErrorCategory.TOOL_MISMATCH
                    confidence = max(confidence, 0.6)
        
        # 如果有 plan_id，更可能是业务逻辑错误
        if context.get("plan_id"):
            if any(keyword in error_message for keyword in [
                "plan", "step", "task"
            ]):
                if layer == ErrorLayer.UNKNOWN:
                    layer = ErrorLayer.BUSINESS_LOGIC
                    category = ErrorCategory.PLAN_INVALID
                    confidence = max(confidence, 0.6)
        
        # 如果是最后几轮，可能是上下文不足
        if context.get("turn", 0) >= context.get("max_turns", 10) - 2:
            if layer == ErrorLayer.BUSINESS_LOGIC:
                if category == ErrorCategory.UNKNOWN:
                    category = ErrorCategory.CONTEXT_INSUFFICIENT
                    confidence = max(confidence, 0.5)
        
        return layer, category, confidence
    
    def _determine_backtrack_strategy(
        self,
        layer: ErrorLayer,
        category: ErrorCategory,
        context: Dict[str, Any]
    ) -> tuple[BacktrackType, str]:
        """确定回溯策略"""
        # Layer 1 错误不需要回溯，使用 resilience 机制
        if layer == ErrorLayer.INFRASTRUCTURE:
            return BacktrackType.NO_BACKTRACK, "使用基础设施层重试/降级机制"
        
        # Layer 2 错误需要回溯
        if category == ErrorCategory.PLAN_INVALID:
            return BacktrackType.PLAN_REPLAN, "重新评估任务分解，生成新的执行计划"
        
        if category == ErrorCategory.TOOL_MISMATCH:
            return BacktrackType.TOOL_REPLACE, "当前工具不适合，尝试替代工具"
        
        if category == ErrorCategory.INTENT_UNCLEAR:
            return BacktrackType.INTENT_CLARIFY, "用户意图不明确，请求澄清"
        
        if category == ErrorCategory.PARAMETER_ERROR:
            return BacktrackType.PARAM_ADJUST, "调整参数后重试"
        
        if category == ErrorCategory.CONTEXT_INSUFFICIENT:
            return BacktrackType.CONTEXT_ENRICH, "补充上下文信息后重试"
        
        if category == ErrorCategory.RESULT_UNSATISFACTORY:
            # 根据上下文决定是重规划还是工具替换
            if context.get("step_index", 0) <= 1:
                return BacktrackType.PLAN_REPLAN, "早期步骤失败，建议重规划"
            else:
                return BacktrackType.TOOL_REPLACE, "尝试替代方法完成当前步骤"
        
        if category == ErrorCategory.EXECUTION_LOGIC_ERROR:
            return BacktrackType.PARAM_ADJUST, "检查执行逻辑，调整参数重试"
        
        # 默认：未知错误使用参数调整
        if layer == ErrorLayer.BUSINESS_LOGIC:
            return BacktrackType.PARAM_ADJUST, "尝试调整参数重试"
        
        return BacktrackType.NO_BACKTRACK, "无法确定回溯策略"
    
    def _is_retryable(self, layer: ErrorLayer, category: ErrorCategory) -> bool:
        """判断是否可重试（基础设施层重试）"""
        if layer != ErrorLayer.INFRASTRUCTURE:
            return False
        
        # 可重试的基础设施错误
        retryable_categories = {
            ErrorCategory.API_TIMEOUT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.SERVICE_UNAVAILABLE,
            ErrorCategory.NETWORK_ERROR,
        }
        
        return category in retryable_categories
    
    def classify_tool_error(
        self,
        error: Exception,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Optional[Dict[str, Any]] = None
    ) -> ClassifiedError:
        """
        分类工具执行错误
        
        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            tool_output: 工具输出（如果有）
            
        Returns:
            ClassifiedError: 分类结果
        """
        context = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "source": "tool_execution",
        }
        
        return self.classify(error, context)
    
    def classify_plan_error(
        self,
        error: Exception,
        plan_id: str,
        step_index: int,
        step_content: Optional[str] = None
    ) -> ClassifiedError:
        """
        分类计划执行错误
        
        Args:
            error: 异常对象
            plan_id: 计划 ID
            step_index: 步骤索引
            step_content: 步骤内容
            
        Returns:
            ClassifiedError: 分类结果
        """
        context = {
            "plan_id": plan_id,
            "step_index": step_index,
            "step_content": step_content,
            "source": "plan_execution",
        }
        
        return self.classify(error, context)
    
    def classify_llm_error(
        self,
        error: Exception,
        model_name: str,
        turn: int,
        max_turns: int
    ) -> ClassifiedError:
        """
        分类 LLM 调用错误
        
        Args:
            error: 异常对象
            model_name: 模型名称
            turn: 当前轮次
            max_turns: 最大轮次
            
        Returns:
            ClassifiedError: 分类结果
        """
        context = {
            "model_name": model_name,
            "turn": turn,
            "max_turns": max_turns,
            "source": "llm_call",
        }
        
        return self.classify(error, context)


# 全局单例
_error_classifier: Optional[ErrorClassifier] = None


def get_error_classifier() -> ErrorClassifier:
    """获取全局错误分类器实例"""
    global _error_classifier
    if _error_classifier is None:
        _error_classifier = ErrorClassifier()
    return _error_classifier
