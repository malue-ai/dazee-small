"""
SimpleAgent 错误处理模块

兼容性重导出 - 实际实现已移至 errors.py
"""

# 从 errors.py 重导出所有函数
from core.agent.simple.errors import (
    create_error_tool_result,
    create_timeout_tool_results,
    create_fallback_tool_result,
    record_tool_error,
)

__all__ = [
    "create_error_tool_result",
    "create_timeout_tool_results",
    "create_fallback_tool_result",
    "record_tool_error",
]
