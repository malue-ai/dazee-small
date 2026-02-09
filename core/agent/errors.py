"""
单智能体错误处理模块

职责：
- 工具执行错误记录
- Context Engineering 错误保留
- 错误恢复辅助函数
- 错误分类（ErrorClassifier）
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Type

from core.context import stable_json_dumps  # KV-Cache 优化：稳定序列化
from logger import get_logger

logger = get_logger(__name__)


# ==================== 错误分类器 ====================


class ErrorType(str, Enum):
    """错误类型枚举"""

    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION_ERROR = "authentication_error"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorClassification:
    """错误分类结果"""

    error_type: ErrorType
    user_message: str
    is_retryable: bool = False


class ErrorClassifier:
    """
    错误分类器

    使用异常类型匹配进行错误分类，不使用字符串匹配。
    符合 LLM-First 原则：错误分类是确定性任务，使用硬规则更可靠。

    使用示例：
        classification = ErrorClassifier.classify(error)
        error_type = classification.error_type.value
        user_message = classification.user_message
    """

    # 错误类型映射表：异常类名 -> ErrorClassification
    _ERROR_MAP: Dict[str, ErrorClassification] = {
        # 权限错误
        "PermissionDeniedError": ErrorClassification(
            ErrorType.PERMISSION_DENIED, "API 权限错误，请检查 API Key 配置", is_retryable=False
        ),
        "PermissionError": ErrorClassification(
            ErrorType.PERMISSION_DENIED, "API 权限错误，请检查 API Key 配置", is_retryable=False
        ),
        # 频率限制
        "RateLimitError": ErrorClassification(
            ErrorType.RATE_LIMIT, "请求频率过高，请稍后重试", is_retryable=True
        ),
        # 认证错误
        "AuthenticationError": ErrorClassification(
            ErrorType.AUTHENTICATION_ERROR, "API 认证失败，请检查 API Key", is_retryable=False
        ),
        # 超时错误
        "TimeoutError": ErrorClassification(
            ErrorType.TIMEOUT, "请求超时，请稍后重试", is_retryable=True
        ),
        # 连接错误
        "ConnectionError": ErrorClassification(
            ErrorType.CONNECTION_ERROR, "网络连接失败，请检查网络", is_retryable=True
        ),
        "ConnectionRefusedError": ErrorClassification(
            ErrorType.CONNECTION_ERROR, "网络连接失败，请检查网络", is_retryable=True
        ),
    }

    # HTTP 状态码映射
    _STATUS_CODE_MAP: Dict[int, ErrorClassification] = {
        401: ErrorClassification(
            ErrorType.AUTHENTICATION_ERROR, "API 认证失败，请检查 API Key", is_retryable=False
        ),
        403: ErrorClassification(
            ErrorType.PERMISSION_DENIED, "API 权限错误，请检查 API Key 配置", is_retryable=False
        ),
        429: ErrorClassification(
            ErrorType.RATE_LIMIT, "请求频率过高，请稍后重试", is_retryable=True
        ),
        500: ErrorClassification(
            ErrorType.UNKNOWN_ERROR, "服务器内部错误，请稍后重试", is_retryable=True
        ),
        502: ErrorClassification(
            ErrorType.CONNECTION_ERROR, "网关错误，请稍后重试", is_retryable=True
        ),
        503: ErrorClassification(
            ErrorType.CONNECTION_ERROR, "服务暂时不可用，请稍后重试", is_retryable=True
        ),
    }

    # 默认分类结果
    _DEFAULT = ErrorClassification(
        ErrorType.UNKNOWN_ERROR, "执行失败，请稍后重试", is_retryable=False
    )

    @classmethod
    def classify(cls, error: Exception) -> ErrorClassification:
        """
        分类错误

        优先级：
        1. asyncio.TimeoutError 特殊处理
        2. 异常类型精确匹配
        3. 异常类型父类匹配（MRO 遍历）
        4. HTTP 状态码匹配（从异常属性中提取）
        5. 默认 unknown_error

        Args:
            error: 异常对象

        Returns:
            ErrorClassification 分类结果
        """
        # 1. asyncio.TimeoutError 特殊处理（因为它不在标准异常链中）
        if isinstance(error, asyncio.TimeoutError):
            return cls._ERROR_MAP["TimeoutError"]

        # 2. 精确匹配异常类名
        error_class_name = type(error).__name__
        if error_class_name in cls._ERROR_MAP:
            return cls._ERROR_MAP[error_class_name]

        # 3. 父类匹配（检查 MRO，跳过 object 和 BaseException）
        for parent_class in type(error).__mro__[1:]:
            parent_name = parent_class.__name__
            if parent_name in ("object", "BaseException", "Exception"):
                continue
            if parent_name in cls._ERROR_MAP:
                return cls._ERROR_MAP[parent_name]

        # 4. 尝试从异常属性中提取 HTTP 状态码
        status_code = cls._extract_status_code(error)
        if status_code and status_code in cls._STATUS_CODE_MAP:
            return cls._STATUS_CODE_MAP[status_code]

        # 5. 默认返回 unknown_error
        return cls._DEFAULT

    @classmethod
    def _extract_status_code(cls, error: Exception) -> Optional[int]:
        """
        从异常中提取 HTTP 状态码

        尝试多种属性名：status_code, code, status, response.status_code
        """
        # 直接属性
        for attr in ("status_code", "code", "status"):
            value = getattr(error, attr, None)
            if isinstance(value, int):
                return value

        # 嵌套在 response 中
        response = getattr(error, "response", None)
        if response:
            for attr in ("status_code", "status"):
                value = getattr(response, attr, None)
                if isinstance(value, int):
                    return value

        return None


# ==================== 工具错误处理函数 ====================


def create_error_tool_result(
    tool_id: str, tool_name: str, error: Exception, tool_input: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    创建错误工具结果

    Args:
        tool_id: 工具调用 ID
        tool_name: 工具名称
        error: 异常对象
        tool_input: 工具输入参数

    Returns:
        标准化的错误结果字典
    """
    return {
        "tool_id": tool_id,
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "result": {"error": str(error)},
        "is_error": True,
        "error_msg": f"工具执行失败: {str(error)}",
    }


def create_timeout_tool_results(tool_calls: list) -> list:
    """
    为最后一轮的工具调用创建超时结果

    当达到最大执行轮次时，需要为每个未执行的工具调用提供 tool_result，
    否则 Claude API 会报错。

    Args:
        tool_calls: 工具调用列表

    Returns:
        tool_result 列表
    """
    results = []
    for tc in tool_calls:
        if tc.get("type") == "tool_use":
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc.get("id"),
                    "content": stable_json_dumps(
                        {"error": "已达到最大执行轮次，工具未执行", "status": "skipped"}
                    ),
                    "is_error": True,
                }
            )
    return results


def create_fallback_tool_result(tool_id: str, tool_name: str) -> Dict[str, Any]:
    """
    创建兜底工具结果（当工具执行结果未收集到时）

    Args:
        tool_id: 工具调用 ID
        tool_name: 工具名称

    Returns:
        兜底的 tool_result
    """
    logger.warning(f"⚠️ 工具 {tool_name} (id={tool_id}) 缺少 tool_result，添加兜底结果")
    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": stable_json_dumps({"error": "工具执行结果未收集到，请重试"}),
        "is_error": True,
    }


def record_tool_error(
    context_engineering, tool_name: str, error: Exception, input_params: Dict[str, Any]
) -> None:
    """
    记录工具执行错误（Context Engineering 错误保留）

    Args:
        context_engineering: ContextEngineeringManager 实例
        tool_name: 工具名称
        error: 异常对象
        input_params: 工具输入参数
    """
    if context_engineering:
        context_engineering.record_error(
            tool_name=tool_name, error=error, input_params=input_params
        )
        logger.debug(f"📝 错误保留: {tool_name} 错误已记录")
