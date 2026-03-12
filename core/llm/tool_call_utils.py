"""
工具调用格式兼容工具
"""

import json
import re
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("llm.tool_calls")


def repair_tool_arguments(raw: str) -> dict | None:
    """Attempt to repair malformed JSON in LLM tool call arguments.

    OpenAI-compatible LLMs (DeepSeek, Qwen, GLM, etc.) sometimes emit
    invalid JSON in tool call arguments:
      - Single-quoted string values:  'some text'
      - Unescaped double quotes inside single-quoted strings
      - Truncated JSON (stream cut off mid-value)
      - Unescaped backslashes in file paths

    Returns parsed dict on success, None on failure.
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Phase 1: fix single-quoted strings → double-quoted with inner escaping.
    def _replace_sq(m: re.Match) -> str:
        prefix = m.group(1)
        inner = m.group(2)
        inner = inner.replace("\\", "\\\\").replace('"', '\\"')
        return f'{prefix}"{inner}"'

    text = re.sub(
        r"""([:,\[\s])\s*'((?:[^'\\]|\\.)*)'\s*""",
        _replace_sq,
        text,
    )

    # Phase 2: fix unescaped backslashes
    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)

    # Phase 3: try to close truncated JSON
    if not text.rstrip().endswith("}"):
        depth_brace = text.count("{") - text.count("}")
        depth_bracket = text.count("[") - text.count("]")
        if 0 < depth_brace <= 3 and depth_bracket >= 0:
            for trim_char in (",", "[", "{", ":"):
                idx = text.rfind(trim_char)
                if idx > 0:
                    candidate = text[:idx].rstrip().rstrip(",")
                    candidate += "]" * max(0, candidate.count("[") - candidate.count("]"))
                    candidate += "}" * max(0, candidate.count("{") - candidate.count("}"))
                    try:
                        return json.loads(candidate, strict=False)
                    except json.JSONDecodeError:
                        continue

    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        return None


def _parse_tool_input(raw_input: Any) -> Dict[str, Any]:
    """Parse tool call arguments from various formats."""
    if raw_input is None:
        return {}
    if isinstance(raw_input, dict):
        return raw_input
    if isinstance(raw_input, str):
        try:
            return json.loads(raw_input, strict=False)
        except json.JSONDecodeError:
            repaired = repair_tool_arguments(raw_input)
            if repaired is not None:
                logger.warning("工具入参 JSON 修复成功 (repair_tool_arguments)")
                return repaired
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
