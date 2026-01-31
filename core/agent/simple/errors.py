"""
单智能体错误处理模块

职责：
- 工具执行错误记录
- Context Engineering 错误保留
- 错误恢复辅助函数
"""

import json
from typing import Dict, Any, Optional
from logger import get_logger

logger = get_logger(__name__)


def create_error_tool_result(
    tool_id: str,
    tool_name: str,
    error: Exception,
    tool_input: Dict[str, Any] = None
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
        "error_msg": f"工具执行失败: {str(error)}"
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
            results.append({
                "type": "tool_result",
                "tool_use_id": tc.get("id"),
                "content": json.dumps({
                    "error": "已达到最大执行轮次，工具未执行",
                    "status": "skipped"
                }, ensure_ascii=False),
                "is_error": True
            })
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
        "content": json.dumps({"error": "工具执行结果未收集到，请重试"}),
        "is_error": True
    }


def record_tool_error(
    context_engineering,
    tool_name: str,
    error: Exception,
    input_params: Dict[str, Any]
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
            tool_name=tool_name,
            error=error,
            input_params=input_params
        )
        logger.debug(f"📝 错误保留: {tool_name} 错误已记录")
