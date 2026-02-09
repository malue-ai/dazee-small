"""
工具调用格式兼容工具
"""

import json
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("llm.tool_calls")


def _parse_tool_input(raw_input: Any) -> Dict[str, Any]:
    """
    解析工具入参
    """
    if raw_input is None:
        return {}
    if isinstance(raw_input, dict):
        return raw_input
    if isinstance(raw_input, str):
        try:
            return json.loads(raw_input)
        except json.JSONDecodeError:
            logger.warning("⚠️ 工具入参不是合法 JSON，已降级为空对象")
            return {}
    return {}


def normalize_tool_calls(
    tool_calls: Optional[List[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    """
    规范化工具调用格式为 Claude 内部格式

    Returns:
        [{"id", "name", "input", "type"}]
    """
    if not tool_calls:
        return None

    normalized: List[Dict[str, Any]] = []
    for idx, call in enumerate(tool_calls):
        if not isinstance(call, dict):
            continue

        call_type = "tool_use"

        call_id = call.get("id") or f"tool_{idx}"
        name = (
            call.get("name")
            or (call.get("function") or {}).get("name")
            or call.get("tool_name")
            or "unknown_tool"
        )

        input_payload = call.get("input")
        if input_payload is None:
            if "arguments" in call:
                input_payload = _parse_tool_input(call.get("arguments"))
            elif "function" in call and "arguments" in call["function"]:
                input_payload = _parse_tool_input(call["function"].get("arguments"))
            elif "parameters" in call:
                input_payload = _parse_tool_input(call.get("parameters"))
            else:
                input_payload = {}
        else:
            input_payload = _parse_tool_input(input_payload)

        normalized.append({"id": call_id, "name": name, "input": input_payload, "type": call_type})

    return normalized if normalized else None
