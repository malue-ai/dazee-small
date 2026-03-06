"""
格式适配器模块

负责不同 LLM 格式之间的转换，以 Claude 格式为内部标准。

设计参考：
- one-api / new-api 的 Adaptor 设计
- 统一使用 Claude 格式作为内部存储格式

格式对比：
┌─────────────┬──────────────────────────────────────────────┐
│   Provider  │              消息格式                         │
├─────────────┼──────────────────────────────────────────────┤
│   Claude    │ content: str | List[ContentBlock]           │
│             │ ContentBlock: {type, text/thinking/tool_use}│
├─────────────┼──────────────────────────────────────────────┤
│   OpenAI    │ content: str | List[ContentPart]            │
│             │ ContentPart: {type, text/image_url}         │
│             │ tool_calls: List[{id, type, function}]      │
├─────────────┼──────────────────────────────────────────────┤
│   Gemini    │ parts: List[Part]                           │
│             │ Part: {text} | {inline_data} | {function_call}│
└─────────────┴──────────────────────────────────────────────┘
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from logger import get_logger

from .base import LLMResponse, Message, ToolType

logger = get_logger("adaptor")


# ============================================================
# 公共安全函数
# ============================================================


def _ensure_user_last(
    messages: List[Dict[str, Any]], provider: str = ""
) -> List[Dict[str, Any]]:
    """
    Ensure messages end with a user message.

    Multiple LLM providers (Claude, OpenAI-compatible, Gemini) require the
    conversation to end with a user message.  After tool-pair cleanup and
    consecutive-role merging, the tail may accidentally become an assistant
    message.  This guard appends a minimal user message when needed.

    Args:
        messages: provider-formatted message list (mutated in place)
        provider: label for log messages

    Returns:
        The (possibly appended) message list.
    """
    if not messages:
        return messages

    assistant_roles = {"assistant", "model"}  # Claude/OpenAI + Gemini
    last_role = messages[-1].get("role", "")

    if last_role in assistant_roles:
        logger.warning(
            f"⚠️ [{provider}] 消息链以 {last_role} 结尾（共 {len(messages)} 条），"
            f"追加 user 消息以满足 API 要求"
        )
        messages.append({"role": "user", "content": "请继续。"})

    return messages


# ============================================================
# 格式转换器基类
# ============================================================


class BaseAdaptor(ABC):
    """
    格式适配器基类

    职责：
    1. 将统一格式（Claude）转换为特定 Provider 格式
    2. 将特定 Provider 响应转换为统一格式（Claude）
    """

    @abstractmethod
    def convert_messages_to_provider(
        self, messages: List[Message], system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        将 Claude 格式消息转换为 Provider 格式

        Args:
            messages: Claude 格式的消息列表
            system: 系统提示词

        Returns:
            Provider 格式的请求参数
        """
        pass

    @abstractmethod
    def convert_response_to_claude(self, response: Any) -> LLMResponse:
        """
        将 Provider 响应转换为 Claude 格式

        Args:
            response: Provider 的原始响应

        Returns:
            Claude 格式的 LLMResponse
        """
        pass

    @abstractmethod
    def convert_tools_to_provider(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将 Claude 格式工具定义转换为 Provider 格式

        Args:
            tools: Claude 格式的工具定义

        Returns:
            Provider 格式的工具定义
        """
        pass


# ============================================================
# Claude 适配器
# ============================================================


class ClaudeAdaptor(BaseAdaptor):
    """
    Claude 适配器

    职责：
    1. 加载历史消息时：清理 thinking/index，分离 tool_result
    2. 发送 API 前：确保消息格式符合 Claude API 要求

    Claude API 消息格式规范：
    - assistant 消息可包含：text, thinking, tool_use
    - user 消息可包含：text, tool_result
    - tool_result 必须在 user 消息中，且紧跟对应的 tool_use
    """

    # ==================== 加载历史消息 ====================

    @staticmethod
    def prepare_messages_from_db(db_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        从数据库加载的消息 → LLM 格式

        处理逻辑：
        1. 按 index 字段排序内容块
        2. 清理 thinking, redacted_thinking 块
        3. 去重 tool_use 和 tool_result
        4. 移除 index 字段
        5. **交错分离**：遇到 tool_result 时立即创建 user 消息
           - 数据库: assistant [text, tool_use, tool_result, tool_use, tool_result]
           - 输出: assistant [text, tool_use] → user [tool_result] → assistant [tool_use] → user [tool_result]
        6. 确保 tool_use/tool_result 配对

        Args:
            db_messages: 数据库消息列表 [{"role": "...", "content": [...]}]

        Returns:
            符合 Claude API 格式的消息列表
        """

        logger.info(f"📥 prepare_messages_from_db: 输入 {len(db_messages)} 条消息")

        result = []

        # 用于全局去重：记录已添加的 tool_use id 和 tool_result tool_use_id
        seen_tool_use_ids: set = set()
        seen_tool_result_ids: set = set()

        for msg in db_messages:
            role = msg.get("role", "")
            content = msg.get("content", [])

            # 如果 content 是字符串，直接添加
            if isinstance(content, str):
                result.append({"role": role, "content": content})
                continue

            # 如果不是列表，跳过
            if not isinstance(content, list):
                continue

            # 按 index 字段排序（确保顺序正确）
            sorted_content = sorted(
                content, key=lambda b: b.get("index", 999) if isinstance(b, dict) else 999
            )

            if role == "assistant":
                # 🔧 关键改进：交错分离 tool_result
                # 遍历内容块，遇到 tool_result 时立即创建 user 消息
                current_assistant_blocks = []

                for block in sorted_content:
                    if not isinstance(block, dict):
                        current_assistant_blocks.append(block)
                        continue

                    block_type = block.get("type", "")

                    # 跳过 thinking 块
                    if block_type in ("thinking", "redacted_thinking"):
                        continue

                    # 移除 index 字段
                    clean_block = {k: v for k, v in block.items() if k != "index"}

                    # tool_use 去重检查
                    if block_type == "tool_use":
                        tool_id = block.get("id")
                        if tool_id in seen_tool_use_ids:
                            continue  # 跳过重复的 tool_use
                        seen_tool_use_ids.add(tool_id)
                        current_assistant_blocks.append(clean_block)

                    # tool_result：先保存当前 assistant 块，然后创建 user 消息
                    elif block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in seen_tool_result_ids:
                            continue  # 跳过重复的 tool_result
                        seen_tool_result_ids.add(tool_use_id)

                        # 先保存当前累积的 assistant 块
                        if current_assistant_blocks:
                            result.append(
                                {"role": "assistant", "content": current_assistant_blocks}
                            )
                            current_assistant_blocks = []

                        # tool_result 作为独立的 user 消息
                        result.append({"role": "user", "content": [clean_block]})

                    else:
                        # text 等其他类型
                        current_assistant_blocks.append(clean_block)

                # 保存最后累积的 assistant 块
                if current_assistant_blocks:
                    result.append({"role": "assistant", "content": current_assistant_blocks})

            else:
                # user/system 消息：过滤并保留
                filtered_blocks = []
                for block in sorted_content:
                    if not isinstance(block, dict):
                        continue

                    block_type = block.get("type", "")

                    # 跳过 thinking 块
                    if block_type in ("thinking", "redacted_thinking"):
                        continue

                    # 移除 index 字段
                    clean_block = {k: v for k, v in block.items() if k != "index"}

                    # tool_result 去重
                    if block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in seen_tool_result_ids:
                            continue
                        seen_tool_result_ids.add(tool_use_id)

                    filtered_blocks.append(clean_block)

                if filtered_blocks:
                    result.append({"role": role, "content": filtered_blocks})

        # 统计 tool_use 和 tool_result 数量
        pre_tool_use_ids = set()
        pre_tool_result_ids = set()
        for msg in result:
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            pre_tool_use_ids.add(block.get("id"))
                        elif block.get("type") == "tool_result":
                            pre_tool_result_ids.add(block.get("tool_use_id"))

        logger.info(
            f"📊 交错分离后: {len(result)} 条消息, tool_use={len(pre_tool_use_ids)}, tool_result={len(pre_tool_result_ids)}"
        )

        if pre_tool_use_ids - pre_tool_result_ids:
            logger.warning(f"⚠️ 检测到未配对的 tool_use: {pre_tool_use_ids - pre_tool_result_ids}")

        # 确保 tool_use/tool_result 配对
        result = ClaudeAdaptor.ensure_tool_pairs(result)

        logger.info(f"📤 prepare_messages_from_db: 输出 {len(result)} 条消息")

        return result

    @staticmethod
    def ensure_tool_pairs(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        确保 tool_use 和 tool_result 成对且邻接出现（同时去重）

        Claude API 要求：
        - 每个 tool_use 后面必须紧跟对应的 tool_result（在下一个 user 消息中）
        - 如果 tool_use 没有对应的 tool_result，需要移除
        - 如果 tool_result 没有对应的 tool_use，也需要移除
        - 每个 tool_use_id 只能有一个 tool_result（去重）
        - tool_result 必须在 tool_use 所在 assistant 消息的**紧邻下一条** user 消息中

        Args:
            messages: 消息列表

        Returns:
            清理后的消息列表（只保留配对、邻接且不重复的 tool_use/tool_result）
        """
        if not messages:
            return messages

        # Phase 1: 全局配对检查 — 收集所有 tool_use ID 和 tool_result ID
        tool_use_ids: set = set()
        tool_result_ids: set = set()

        for msg in messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "tool_use":
                    tool_use_ids.add(block.get("id"))
                elif block_type == "tool_result":
                    tool_result_ids.add(block.get("tool_use_id"))

        globally_paired = tool_use_ids & tool_result_ids

        if tool_use_ids - tool_result_ids:
            logger.warning(
                f"⚠️ 发现 {len(tool_use_ids - tool_result_ids)} 个全局未配对的 tool_use，将移除: "
                f"{tool_use_ids - tool_result_ids}"
            )
        if tool_result_ids - tool_use_ids:
            logger.warning(
                f"⚠️ 发现 {len(tool_result_ids - tool_use_ids)} 个全局未配对的 tool_result，将移除: "
                f"{tool_result_ids - tool_use_ids}"
            )

        # Phase 2: 邻接性检查 — tool_use 所在 assistant 消息的下一条必须是包含
        # 对应 tool_result 的 user 消息
        adjacent_paired: set = set()

        for i, msg in enumerate(messages):
            content = msg.get("content", [])
            if msg.get("role") != "assistant" or not isinstance(content, list):
                continue

            # 收集该 assistant 消息中的 tool_use IDs
            tu_ids_in_msg = {
                b.get("id")
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") in globally_paired
            }
            if not tu_ids_in_msg:
                continue

            # 检查紧邻的下一条消息是否为 user 且包含对应 tool_result
            next_idx = i + 1
            if next_idx < len(messages):
                next_msg = messages[next_idx]
                next_content = next_msg.get("content", [])
                if next_msg.get("role") == "user" and isinstance(next_content, list):
                    tr_ids_in_next = {
                        b.get("tool_use_id")
                        for b in next_content
                        if isinstance(b, dict) and b.get("type") == "tool_result"
                    }
                    # 只有在下一条消息中有对应 tool_result 的才算邻接配对
                    matched = tu_ids_in_msg & tr_ids_in_next
                    adjacent_paired.update(matched)

                    not_adjacent = tu_ids_in_msg - tr_ids_in_next
                    if not_adjacent:
                        logger.warning(
                            f"⚠️ 消息[{i}] 中的 tool_use 在下一条消息中缺少对应 tool_result，"
                            f"将移除: {not_adjacent}"
                        )
                else:
                    # 下一条不是 user 消息，所有 tool_use 都不满足邻接性
                    logger.warning(
                        f"⚠️ 消息[{i}] 含 tool_use 但下一条消息不是 user，将移除: {tu_ids_in_msg}"
                    )
            else:
                # assistant 是最后一条消息，tool_use 没有 tool_result
                logger.warning(
                    f"⚠️ 消息[{i}] 含 tool_use 但已是最后一条消息，将移除: {tu_ids_in_msg}"
                )

        # Phase 3: 基于邻接配对集合过滤消息，同时去重
        # Orphan tool_use blocks are converted to text summaries (max 10)
        # so the model retains awareness of previous actions.
        MAX_ORPHAN_SUMMARIES = 10
        added_tool_use_ids: set = set()
        added_tool_result_ids: set = set()
        orphan_tool_use_count = 0
        cleaned_messages = []

        # Pre-count orphan tool_use to decide which ones to summarize
        # (keep the most recent ones within the cap)
        total_orphan_tool_use = 0
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("id") not in adjacent_paired
                    ):
                        total_orphan_tool_use += 1
        # Skip threshold: only summarize the last N orphans
        skip_threshold = max(0, total_orphan_tool_use - MAX_ORPHAN_SUMMARIES)

        for msg in messages:
            content = msg.get("content", [])
            role = msg.get("role", "user")

            if isinstance(content, list):
                filtered_content = []
                for block in content:
                    if not isinstance(block, dict):
                        continue

                    block_type = block.get("type")

                    if block_type == "tool_use":
                        tool_id = block.get("id")
                        if tool_id in adjacent_paired:
                            if tool_id in added_tool_use_ids:
                                logger.warning(f"🧹 移除重复的 tool_use: {tool_id}")
                                continue
                            added_tool_use_ids.add(tool_id)
                            filtered_content.append(block)
                        else:
                            orphan_tool_use_count += 1
                            if orphan_tool_use_count > skip_threshold:
                                # Convert to text summary to preserve context
                                summary = ClaudeAdaptor._summarize_orphan_tool_use(block)
                                filtered_content.append({"type": "text", "text": summary})
                            logger.debug(f"🧹 移除未配对/非邻接的 tool_use: {tool_id}")
                    elif block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in adjacent_paired:
                            if tool_use_id in added_tool_result_ids:
                                logger.warning(f"🧹 移除重复的 tool_result: {tool_use_id}")
                                continue
                            added_tool_result_ids.add(tool_use_id)
                            filtered_content.append(block)
                        else:
                            logger.debug(f"🧹 移除未配对/非邻接的 tool_result: {tool_use_id}")
                    else:
                        filtered_content.append(block)

                # 只添加有内容的消息
                if filtered_content:
                    cleaned_messages.append({"role": role, "content": filtered_content})
            else:
                # 纯文本消息，直接保留
                if content:
                    cleaned_messages.append(msg)

        removed_count = len(messages) - len(cleaned_messages)
        if removed_count > 0:
            logger.info(
                f"✅ ensure_tool_pairs: {len(messages)} → {len(cleaned_messages)} 条消息 "
                f"(adjacent_paired={len(adjacent_paired)})"
            )
        else:
            logger.debug(
                f"✅ ensure_tool_pairs: {len(messages)} 条消息无需清理 "
                f"(adjacent_paired={len(adjacent_paired)})"
            )

        return cleaned_messages

    @staticmethod
    def _summarize_orphan_tool_use(block: Dict[str, Any]) -> str:
        """
        Convert an orphan tool_use block to a concise text summary.

        Preserves the model's awareness of what it previously attempted,
        preventing hallucination about actions that were never executed
        or re-attempting actions without context.

        Args:
            block: tool_use block dict with name, input fields

        Returns:
            Short text summary (max ~120 chars)
        """
        tool_name = block.get("name", "unknown")
        tool_input = block.get("input", {})

        summary = f"[之前调用了 {tool_name}"
        if isinstance(tool_input, dict) and tool_input:
            # Extract up to 3 key params, each value truncated to 40 chars
            params = []
            for k, v in list(tool_input.items())[:3]:
                val_str = str(v)
                if len(val_str) > 40:
                    val_str = val_str[:37] + "..."
                params.append(f"{k}={val_str}")
            if params:
                summary += f"({', '.join(params)})"
        summary += "，结果未记录]"
        return summary

    @staticmethod
    def clean_content_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        清理 content blocks

        处理：
        - 移除 thinking, redacted_thinking 块
        - 移除 index 字段

        Args:
            blocks: content blocks 列表

        Returns:
            清理后的 blocks
        """
        result = []
        for block in blocks:
            if not isinstance(block, dict):
                result.append(block)
                continue

            block_type = block.get("type", "")

            # 跳过 thinking 块
            if block_type in ("thinking", "redacted_thinking"):
                continue

            # 移除 index 字段
            clean_block = {k: v for k, v in block.items() if k != "index"}
            result.append(clean_block)

        return result

    # ==================== 发送 API 前 ====================

    def convert_messages_to_provider(
        self, messages: List[Message], system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Message → Claude API 格式

        兜底检查：
        1. 确保 tool_result 在 user 消息中
        2. 过滤无效的 thinking 块（无 signature 会导致 API 400 错误）
        """
        converted_messages = []

        for msg in messages:
            content = msg.content

            # 字符串内容直接添加
            if isinstance(content, str):
                converted_messages.append({"role": msg.role, "content": content})
                continue

            # 列表内容需要检查 tool_result
            if isinstance(content, list) and msg.role == "assistant":
                assistant_blocks = []
                tool_result_blocks = []

                for block in content:
                    if not isinstance(block, dict):
                        assistant_blocks.append(block)
                        continue

                    block_type = block.get("type", "")

                    if block_type == "tool_result":
                        tool_result_blocks.append(block)
                    elif block_type == "input_audio":
                        assistant_blocks.append({
                            "type": "text",
                            "text": "[音频文件: 当前模型不支持音频输入]",
                        })
                    elif block_type in ("thinking", "redacted_thinking"):
                        if block.get("signature"):
                            assistant_blocks.append(block)
                        else:
                            logger.debug(
                                f"🧹 过滤无 signature 的 {block_type} 块"
                            )
                    else:
                        assistant_blocks.append(block)

                # 添加 assistant 消息（不含 tool_result）
                if assistant_blocks:
                    converted_messages.append({"role": "assistant", "content": assistant_blocks})

                # tool_result 分离到 user 消息
                if tool_result_blocks:
                    converted_messages.append({"role": "user", "content": tool_result_blocks})
            else:
                if isinstance(content, list):
                    filtered_content = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "input_audio":
                            filtered_content.append({
                                "type": "text",
                                "text": "[音频文件: 当前模型不支持音频输入]",
                            })
                        else:
                            filtered_content.append(block)
                    converted_messages.append({"role": msg.role, "content": filtered_content})
                else:
                    converted_messages.append({"role": msg.role, "content": content})

        # 🔧 关键：确保 tool_use/tool_result 配对且邻接（移除未配对/非邻接的 tool_use）
        converted_messages = ClaudeAdaptor.ensure_tool_pairs(converted_messages)

        # 🔧 合并连续同角色消息（ensure_tool_pairs 移除内容后可能产生）
        converted_messages = ClaudeAdaptor._merge_consecutive_same_role(converted_messages)

        # 🛡️ 最终防线：合并后再次验证 tool_use/tool_result 配对
        # _merge_consecutive_same_role 可能改变消息邻接关系，需要二次验证
        converted_messages = ClaudeAdaptor.ensure_tool_pairs(converted_messages)

        # 🛡️ 最终安全检查：确保消息以 user 结尾
        # Claude API 要求 messages 必须以 user 消息结尾，否则返回 400:
        # "This model does not support assistant message prefill.
        #  The conversation must end with a user message."
        # ensure_tool_pairs 移除孤立 tool_use/tool_result 后，
        # 可能导致尾部 user 消息被清空，使最后一条变为 assistant。
        converted_messages = _ensure_user_last(converted_messages, "Claude")

        result: Dict[str, Any] = {"messages": converted_messages}
        if system:
            result["system"] = system
        return result

    @staticmethod
    def _merge_consecutive_same_role(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并连续同角色消息（Claude API 要求 user/assistant 严格交替）

        当 ensure_tool_pairs 移除 tool_use/tool_result 后，可能产生连续同角色消息，
        需要合并以满足 Claude API 的交替要求。

        Args:
            messages: 消息列表

        Returns:
            合并后的消息列表
        """
        if not messages:
            return messages

        merged = [messages[0]]

        for msg in messages[1:]:
            prev = merged[-1]
            if msg.get("role") == prev.get("role"):
                # 同角色，合并 content
                prev_content = prev.get("content", [])
                curr_content = msg.get("content", [])

                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    prev["content"] = prev_content + "\n" + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    prev["content"] = prev_content + curr_content
                elif isinstance(prev_content, str) and isinstance(curr_content, list):
                    prev["content"] = [{"type": "text", "text": prev_content}] + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, str):
                    prev["content"] = prev_content + [{"type": "text", "text": curr_content}]

                logger.debug(
                    f"🔗 合并连续 {msg.get('role')} 消息"
                )
            else:
                merged.append(msg)

        if len(merged) != len(messages):
            logger.info(
                f"🔗 合并连续同角色消息: {len(messages)} → {len(merged)} 条"
            )

        return merged

    def convert_response_to_claude(self, response: Any) -> LLMResponse:
        """Claude 响应 → LLMResponse（原生）"""
        # 已经是 Claude 格式，直接返回
        if isinstance(response, LLMResponse):
            return response
        raise ValueError("Expected LLMResponse for Claude adaptor")

    def convert_tools_to_provider(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Claude 格式工具 → Claude API（原生）"""
        return tools


# ============================================================
# OpenAI 适配器
# ============================================================


class OpenAIAdaptor(BaseAdaptor):
    """
    OpenAI 适配器

    转换规则：
    - Claude content blocks → OpenAI content + tool_calls
    - Claude tool_use → OpenAI function calling
    - Claude thinking → OpenAI 不支持（存为 metadata）
    """

    def convert_messages_to_provider(
        self, messages: List[Message], system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Claude 格式 → OpenAI 格式

        转换规则：
        - system prompt → messages[0] with role="system"
        - content blocks → 展开为 content 字符串
        - tool_result → role="tool" 消息
        - 🔧 确保 tool_calls 和 tool 消息配对
        """
        openai_messages = []

        # System prompt 作为第一条消息
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            converted = self._convert_message(msg)
            if isinstance(converted, list):
                openai_messages.extend(converted)
            else:
                openai_messages.append(converted)

        # 🔧 关键：确保 tool_calls 和 tool 消息配对
        openai_messages = self._ensure_tool_pairs(openai_messages)

        # 🛡️ 安全检查：确保消息不以 assistant 结尾（部分 OpenAI 兼容模型同样要求）
        openai_messages = _ensure_user_last(openai_messages, "OpenAI")

        return {"messages": openai_messages}

    def _convert_message(self, msg: Message) -> Union[Dict, List[Dict]]:
        """转换单条消息"""
        content = msg.content

        # 简单字符串
        if isinstance(content, str):
            return {"role": msg.role, "content": content}

        # Content blocks
        if isinstance(content, list):
            content_parts = []
            tool_calls = []
            tool_results = []

            for block in content:
                block_type = block.get("type", "")

                if block_type == "text":
                    text_val = block.get("text", "")
                    if text_val:
                        content_parts.append({"type": "text", "text": text_val})

                elif block_type == "image":
                    # 处理图片
                    source = block.get("source", {})
                    source_type = source.get("type")

                    if source_type == "url":
                        content_parts.append(
                            {"type": "image_url", "image_url": {"url": source.get("url", "")}}
                        )
                    elif source_type == "base64":
                        media_type = source.get("media_type", "image/jpeg")
                        data = source.get("data", "")
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{data}"},
                            }
                        )

                elif block_type == "input_audio":
                    source = block.get("source", {})
                    data = source.get("data", "")
                    fmt = source.get("format", "wav")
                    content_parts.append({
                        "type": "input_audio",
                        "input_audio": {"data": data, "format": fmt},
                    })

                elif block_type == "thinking":
                    # OpenAI 不支持 thinking，跳过
                    pass

                elif block_type == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": self._serialize_json(block.get("input", {})),
                            },
                        }
                    )

                elif block_type == "tool_result":
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": self._get_tool_result_content(block),
                        }
                    )

            # 构建消息
            result = []

            if msg.role == "assistant":
                assistant_msg: Dict[str, Any] = {"role": "assistant"}

                # 处理 content
                if content_parts:
                    # 如果只有纯文本，可以简化为字符串（兼容性更好）
                    if all(p["type"] == "text" for p in content_parts):
                        assistant_msg["content"] = "\n".join(p["text"] for p in content_parts)
                    else:
                        # 多模态（含图片），使用列表
                        assistant_msg["content"] = content_parts

                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls

                # 只有当消息有内容或有 tool_calls 时才添加
                if assistant_msg.get("content") or assistant_msg.get("tool_calls"):
                    result.append(assistant_msg)

            elif msg.role == "user":
                # tool_results 必须先于 text content 加入，确保 role="tool"
                # 紧跟前一条 assistant(tool_calls)，满足 OpenAI/Qwen 邻接要求
                result.extend(tool_results)

                if content_parts:
                    if all(p["type"] == "text" for p in content_parts):
                        result.append(
                            {"role": "user", "content": "\n".join(p["text"] for p in content_parts)}
                        )
                    else:
                        result.append({"role": "user", "content": content_parts})

                tool_results = []  # 已处理，防止下方重复 extend

            # Tool results 作为独立消息（仅 assistant 角色走到这里）
            result.extend(tool_results)

            # 如果 result 为空但原始消息有内容（例如只有 thinking 被过滤了），返回空内容的消息以防报错
            # 但通常 thinking 伴随着 text 或 tool_use

            return (
                result
                if len(result) > 1
                else result[0] if result else {"role": msg.role, "content": ""}
            )

        return {"role": msg.role, "content": str(content)}

    def _ensure_tool_pairs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        确保 tool_calls 和 tool 消息配对

        OpenAI API 要求：
        - assistant 消息中的每个 tool_call_id 都必须有对应的 tool 消息响应
        - 如果没有配对，移除该 tool_call（避免 API 报错）

        Args:
            messages: OpenAI 格式的消息列表

        Returns:
            清理后的消息列表（只保留配对的 tool_calls）
        """
        if not messages:
            return messages

        # 1. 收集所有 tool_call_id 和 tool 响应的 tool_call_id
        tool_call_ids: set = set()
        tool_response_ids: set = set()

        for msg in messages:
            role = msg.get("role", "")

            if role == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tool_call_ids.add(tc.get("id"))

            elif role == "tool":
                tool_response_ids.add(msg.get("tool_call_id"))

        # 2. 找出配对的 tool_call_id
        paired_ids = tool_call_ids & tool_response_ids
        unpaired_tool_calls = tool_call_ids - tool_response_ids
        unpaired_tool_responses = tool_response_ids - tool_call_ids

        if unpaired_tool_calls:
            logger.warning(
                f"⚠️ [OpenAI] 发现 {len(unpaired_tool_calls)} 个未配对的 tool_calls，将移除: {unpaired_tool_calls}"
            )
        if unpaired_tool_responses:
            logger.warning(
                f"⚠️ [OpenAI] 发现 {len(unpaired_tool_responses)} 个未配对的 tool 响应，将移除: {unpaired_tool_responses}"
            )

        # 3. 过滤消息，移除未配对的 tool_calls 和 tool 响应
        cleaned_messages = []

        for msg in messages:
            role = msg.get("role", "")

            if role == "assistant" and msg.get("tool_calls"):
                # 过滤掉未配对的 tool_calls
                filtered_tool_calls = [tc for tc in msg["tool_calls"] if tc.get("id") in paired_ids]

                # 构建新的 assistant 消息
                new_msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                if filtered_tool_calls:
                    new_msg["tool_calls"] = filtered_tool_calls

                # 只有当消息有内容或有 tool_calls 时才添加
                if new_msg.get("content") or new_msg.get("tool_calls"):
                    cleaned_messages.append(new_msg)
                elif not new_msg.get("content") and not filtered_tool_calls:
                    # 原消息只有 tool_calls 且全被移除，跳过
                    logger.debug(f"🧹 [OpenAI] 移除空的 assistant 消息（tool_calls 全被移除）")

            elif role == "tool":
                # 只保留配对的 tool 响应
                if msg.get("tool_call_id") in paired_ids:
                    cleaned_messages.append(msg)
                else:
                    logger.debug(f"🧹 [OpenAI] 移除未配对的 tool 响应: {msg.get('tool_call_id')}")

            else:
                # 其他消息直接保留
                cleaned_messages.append(msg)

        if len(messages) != len(cleaned_messages):
            logger.info(
                f"✅ [OpenAI] ensure_tool_pairs: {len(messages)} → {len(cleaned_messages)} 条消息"
            )

        return cleaned_messages

    # ============================================================
    # Responses API: Claude CCB → Responses input items (zero-copy)
    # ============================================================

    def convert_messages_for_responses(
        self, messages: List[Message], system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Claude CCB → Responses API format in one pass (no Chat intermediate).

        Returns:
            {"instructions": str, "input": List[Dict]}
        """
        instructions = system or ""
        input_items: List[Dict[str, Any]] = []

        func_call_ids: set = set()
        func_output_ids: set = set()

        for msg in messages:
            content = msg.content

            if isinstance(content, str):
                input_items.append({"role": msg.role, "content": content})
                continue

            if not isinstance(content, list):
                input_items.append({"role": msg.role, "content": str(content)})
                continue

            content_parts: List[Dict[str, Any]] = []

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")

                if btype == "text":
                    text = block.get("text", "")
                    if text:
                        content_parts.append({"type": "input_text", "text": text})

                elif btype == "image":
                    source = block.get("source", {})
                    stype = source.get("type")
                    if stype == "url":
                        content_parts.append({"type": "input_image", "image_url": source.get("url", "")})
                    elif stype == "base64":
                        mt = source.get("media_type", "image/jpeg")
                        content_parts.append({"type": "input_image", "image_url": f"data:{mt};base64,{source.get('data', '')}"})

                elif btype == "input_audio":
                    content_parts.append(block)

                elif btype == "document":
                    source = block.get("source", {})
                    text = source.get("data", "") or source.get("text", "")
                    if text:
                        content_parts.append({"type": "input_text", "text": text})

                elif btype in ("thinking", "redacted_thinking"):
                    pass

                elif btype == "tool_use":
                    call_id = block.get("id", "")
                    func_call_ids.add(call_id)
                    input_items.append({
                        "type": "function_call",
                        "call_id": call_id,
                        "name": block.get("name", ""),
                        "arguments": self._serialize_json(block.get("input", {})),
                    })

                elif btype == "tool_result":
                    call_id = block.get("tool_use_id", "")
                    func_output_ids.add(call_id)
                    output = self._get_tool_result_content(block)
                    if not isinstance(output, str):
                        output = json.dumps(output, ensure_ascii=False)
                    input_items.append({
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": output,
                    })

                else:
                    logger.warning(f"⚠️ [Responses] Unknown block type '{btype}', converting to text")
                    text = block.get("text", "")
                    if text:
                        content_parts.append({"type": "input_text", "text": text})

            if content_parts:
                if msg.role == "assistant":
                    text = "\n".join(
                        p["text"] for p in content_parts if p.get("type") == "input_text" and p.get("text")
                    )
                    if text:
                        input_items.append({"role": "assistant", "content": text})
                else:
                    if len(content_parts) == 1 and content_parts[0].get("type") == "input_text":
                        input_items.append({"role": msg.role, "content": content_parts[0]["text"]})
                    else:
                        input_items.append({"role": msg.role, "content": content_parts})

        unpaired_calls = func_call_ids - func_output_ids
        unpaired_outputs = func_output_ids - func_call_ids
        if unpaired_calls or unpaired_outputs:
            input_items = [
                item for item in input_items
                if not (item.get("type") == "function_call" and item.get("call_id") in unpaired_calls)
                and not (item.get("type") == "function_call_output" and item.get("call_id") in unpaired_outputs)
            ]

        return {"instructions": instructions, "input": input_items}

    # ============================================================
    # Shared utilities
    # ============================================================

    def _serialize_json(self, obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False)

    def _get_tool_result_content(self, block: Dict) -> Any:
        """Get tool_result content. Returns str or list of content blocks (multimodal)."""
        content = block.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return content
        return str(content)

    def convert_response_to_claude(self, response: Any) -> LLMResponse:
        """
        OpenAI 响应 → Claude 格式

        转换规则：
        - choices[0].message.content → content
        - choices[0].message.tool_calls → tool_calls
        - finish_reason → stop_reason
        """
        # 假设 response 是 OpenAI 的响应对象或字典
        if isinstance(response, dict):
            return self._convert_dict_response(response)

        # OpenAI SDK 响应对象
        choice = response.choices[0] if response.choices else None
        if not choice:
            return LLMResponse(content="", stop_reason="end_turn")

        message = choice.message
        content = message.content or ""
        tool_calls = None
        raw_content = []

        # 添加文本内容
        if content:
            raw_content.append({"type": "text", "text": content})

        # 转换 tool_calls
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                tool_call = {
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments) if tc.function.arguments else {},
                }
                tool_calls.append(tool_call)
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": tool_call["input"],
                    }
                )

        # 转换 stop_reason
        stop_reason_map = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "content_filter": "end_turn",
        }
        stop_reason = stop_reason_map.get(choice.finish_reason, "end_turn")

        # Usage
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(
            content=content,
            thinking=None,  # OpenAI 不支持 thinking
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content,
        )

    def _convert_dict_response(self, response: Dict) -> LLMResponse:
        """转换字典格式的响应"""
        choices = response.get("choices", [])
        if not choices:
            return LLMResponse(content="", stop_reason="end_turn")

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""
        tool_calls = None
        raw_content = []

        if content:
            raw_content.append({"type": "text", "text": content})

        if message.get("tool_calls"):
            tool_calls = []
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                tool_call = {
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": json.loads(func.get("arguments", "{}")),
                }
                tool_calls.append(tool_call)
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_call["id"],
                        "name": tool_call["name"],
                        "input": tool_call["input"],
                    }
                )

        stop_reason_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
        stop_reason = stop_reason_map.get(choice.get("finish_reason", ""), "end_turn")

        usage = {}
        if response.get("usage"):
            usage = {
                "input_tokens": response["usage"].get("prompt_tokens", 0),
                "output_tokens": response["usage"].get("completion_tokens", 0),
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content,
        )

    def convert_tools_to_provider(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Claude 格式工具 → OpenAI 格式

        转换规则：
        - name → function.name
        - description → function.description
        - input_schema → function.parameters
        """
        openai_tools = []

        for tool in tools:
            # 跳过 Claude 原生工具（如 web_search_20250305）
            if "type" in tool and tool["type"] != "function":
                continue

            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get(
                        "input_schema", {"type": "object", "properties": {}, "required": []}
                    ),
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools


# ============================================================
# DeepSeek 适配器
# ============================================================


class DeepSeekAdaptor(OpenAIAdaptor):
    """
    DeepSeek adaptor

    Extends OpenAI adaptor with thinking/reasoning_content support.

    Response handling:
    - ``convert_response_to_claude`` strips leaked thinking markers
      from the content field (see ``deepseek._strip_thinking_markers``).
      The actual response parsing lives in ``DeepSeekLLMService._parse_response``
      which calls the cleanup directly; the adaptor only handles the
      message *sending* direction.

    Key difference from plain OpenAI:
    - Converts Claude-format thinking blocks to the ``reasoning_content``
      field on assistant messages.
    - DeepSeek thinking mode with tools requires ``reasoning_content``
      to be passed back within the same tool-call loop (400 error otherwise).
    - For previous user turns the API silently ignores the field, so it is
      safe to always include it.
    """

    def _convert_message(self, msg: Message) -> Union[Dict, List[Dict]]:
        """
        Override to convert thinking blocks → reasoning_content.

        For assistant messages that contain ``{"type": "thinking", ...}``
        blocks, extract the thinking text and attach it as
        ``reasoning_content`` on the resulting OpenAI-format assistant
        message.  All other conversion logic is inherited from
        ``OpenAIAdaptor``.
        """
        content = msg.content

        # Only special handling for assistant messages with list content
        if not (isinstance(content, list) and msg.role == "assistant"):
            return super()._convert_message(msg)

        # Separate thinking blocks from the rest
        thinking_text = ""
        non_thinking_blocks = []

        for block in content:
            if isinstance(block, dict) and block.get("type") in (
                "thinking",
                "redacted_thinking",
            ):
                thinking_text += block.get("thinking", "")
            else:
                non_thinking_blocks.append(block)

        if not thinking_text:
            # No thinking blocks – delegate entirely to parent
            return super()._convert_message(msg)

        # Build a Message without thinking blocks so the parent logic
        # handles text / tool_use / tool_result normally.
        modified_msg = Message(
            role=msg.role,
            content=non_thinking_blocks if non_thinking_blocks else [{"type": "text", "text": ""}],
        )
        result = super()._convert_message(modified_msg)

        # Inject reasoning_content into the assistant message dict(s)
        if isinstance(result, list):
            for r in result:
                if isinstance(r, dict) and r.get("role") == "assistant":
                    r["reasoning_content"] = thinking_text
                    break
        elif isinstance(result, dict) and result.get("role") == "assistant":
            result["reasoning_content"] = thinking_text

        return result


# ============================================================
# Gemini 适配器
# ============================================================


class GeminiAdaptor(BaseAdaptor):
    """
    Gemini 适配器

    转换规则：
    - Claude content → Gemini parts
    - Claude tool_use → Gemini function_call
    """

    def convert_messages_to_provider(
        self, messages: List[Message], system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Claude 格式 → Gemini 格式

        Gemini 格式：
        {
            "contents": [
                {"role": "user", "parts": [{"text": "..."}]},
                {"role": "model", "parts": [{"text": "..."}]}
            ],
            "system_instruction": {"parts": [{"text": "..."}]}
        }
        """
        gemini_contents = []

        for msg in messages:
            # Gemini 使用 "model" 而不是 "assistant"
            role = "model" if msg.role == "assistant" else msg.role
            parts = self._convert_content_to_parts(msg.content)

            gemini_contents.append({"role": role, "parts": parts})

        # 🛡️ 安全检查：确保消息不以 model 结尾
        # Gemini 使用 "model" 而非 "assistant"，但同样要求最后一条是 user
        if gemini_contents and gemini_contents[-1].get("role") == "model":
            logger.warning(
                "⚠️ [Gemini] 消息链以 model 结尾，追加 user 消息以满足 API 要求"
            )
            gemini_contents.append(
                {"role": "user", "parts": [{"text": "请继续。"}]}
            )

        result: Dict[str, Any] = {"contents": gemini_contents}

        if system:
            result["system_instruction"] = {"parts": [{"text": system}]}

        return result

    def _convert_content_to_parts(self, content: Union[str, List[Dict]]) -> List[Dict[str, Any]]:
        """将 Claude content 转换为 Gemini parts"""
        if isinstance(content, str):
            return [{"text": content}]

        parts = []
        for block in content:
            block_type = block.get("type", "")

            if block_type == "text":
                parts.append({"text": block.get("text", "")})

            elif block_type == "input_audio":
                source = block.get("source", {})
                mime_type = source.get("media_type", "audio/wav")
                data = source.get("data", "")
                parts.append({
                    "inline_data": {"mime_type": mime_type, "data": data},
                })

            elif block_type == "image":
                source = block.get("source", {})
                source_type = source.get("type")
                if source_type == "base64":
                    mime_type = source.get("media_type", "image/jpeg")
                    data = source.get("data", "")
                    parts.append({
                        "inline_data": {"mime_type": mime_type, "data": data},
                    })
                elif source_type == "url":
                    parts.append({"text": f"[Image URL: {source.get('url', '')}]"})

            elif block_type == "thinking":
                pass

            elif block_type == "tool_use":
                parts.append(
                    {
                        "function_call": {
                            "name": block.get("name", ""),
                            "args": block.get("input", {}),
                        }
                    }
                )

            elif block_type == "tool_result":
                parts.append(
                    {
                        "function_response": {
                            "name": block.get("name", ""),
                            "response": {"result": block.get("content", "")},
                        }
                    }
                )

        return parts if parts else [{"text": ""}]

    def convert_response_to_claude(self, response: Any) -> LLMResponse:
        """
        Gemini 响应 → Claude 格式

        Gemini 响应格式：
        {
            "candidates": [{
                "content": {"parts": [{"text": "..."}]},
                "finishReason": "STOP"
            }]
        }
        """
        if isinstance(response, dict):
            return self._convert_dict_response(response)

        # Gemini SDK 响应对象
        candidate = response.candidates[0] if response.candidates else None
        if not candidate:
            return LLMResponse(content="", stop_reason="end_turn")

        content_parts = candidate.content.parts if candidate.content else []

        text_content = ""
        tool_calls = []
        raw_content = []

        for part in content_parts:
            if hasattr(part, "text") and part.text:
                text_content += part.text
                raw_content.append({"type": "text", "text": part.text})

            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_call = {
                    "id": f"gemini_{fc.name}",  # Gemini 没有 id，生成一个
                    "name": fc.name,
                    "input": dict(fc.args) if fc.args else {},
                }
                tool_calls.append(tool_call)
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_call["id"],
                        "name": tool_call["name"],
                        "input": tool_call["input"],
                    }
                )

        # 转换 finish_reason
        stop_reason_map = {
            "STOP": "end_turn",
            "MAX_TOKENS": "max_tokens",
            "SAFETY": "end_turn",
            "RECITATION": "end_turn",
            "OTHER": "end_turn",
        }
        finish_reason = getattr(candidate, "finish_reason", None)
        stop_reason = stop_reason_map.get(str(finish_reason), "end_turn")

        # Usage
        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "input_tokens": response.usage_metadata.prompt_token_count,
                "output_tokens": response.usage_metadata.candidates_token_count,
            }

        return LLMResponse(
            content=text_content,
            thinking=None,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content,
        )

    def _convert_dict_response(self, response: Dict) -> LLMResponse:
        """转换字典格式的响应"""
        candidates = response.get("candidates", [])
        if not candidates:
            return LLMResponse(content="", stop_reason="end_turn")

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        text_content = ""
        tool_calls = []
        raw_content = []

        for part in parts:
            if "text" in part:
                text_content += part["text"]
                raw_content.append({"type": "text", "text": part["text"]})

            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_call = {
                    "id": f"gemini_{fc.get('name', '')}",
                    "name": fc.get("name", ""),
                    "input": fc.get("args", {}),
                }
                tool_calls.append(tool_call)
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_call["id"],
                        "name": tool_call["name"],
                        "input": tool_call["input"],
                    }
                )

        stop_reason_map = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}
        stop_reason = stop_reason_map.get(candidate.get("finishReason", ""), "end_turn")

        usage = {}
        if response.get("usageMetadata"):
            usage = {
                "input_tokens": response["usageMetadata"].get("promptTokenCount", 0),
                "output_tokens": response["usageMetadata"].get("candidatesTokenCount", 0),
            }

        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content,
        )

    def convert_tools_to_provider(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Claude 格式工具 → Gemini 格式

        Gemini 工具格式：
        {
            "function_declarations": [{
                "name": "...",
                "description": "...",
                "parameters": {...}
            }]
        }
        """
        function_declarations = []

        for tool in tools:
            # 跳过 Claude 原生工具
            if "type" in tool and tool["type"] != "function":
                continue

            declaration = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get(
                    "input_schema", {"type": "object", "properties": {}, "required": []}
                ),
            }
            function_declarations.append(declaration)

        return [{"function_declarations": function_declarations}] if function_declarations else []


# ============================================================
# 工厂函数
# ============================================================


def get_adaptor(provider: str) -> BaseAdaptor:
    """
    获取对应 Provider 的适配器

    Args:
        provider: 提供商名称 (claude, openai, gemini, qwen)

    Returns:
        对应的适配器实例
    """
    adaptors = {
        "claude": ClaudeAdaptor,
        "openai": OpenAIAdaptor,
        "gemini": GeminiAdaptor,
        "qwen": OpenAIAdaptor,  # 千问使用 OpenAI 兼容接口
        "deepseek": DeepSeekAdaptor,  # DeepSeek 需要 reasoning_content 支持
    }

    adaptor_class = adaptors.get(provider.lower())
    if not adaptor_class:
        raise ValueError(f"Unknown provider: {provider}")

    return adaptor_class()
