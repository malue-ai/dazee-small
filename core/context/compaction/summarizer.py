"""
对话摘要生成器

使用 LLM 为对话历史生成智能摘要，用于上下文压缩。

设计原则：
- 使用轻量模型（如 Claude Haiku）减少延迟和成本
- 保留关键信息：用户目标、已完成步骤、重要发现、待完成任务
- 支持 fallback 到简单摘要（LLM 调用失败时）
"""

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

if TYPE_CHECKING:
    from core.llm.base import BaseLLMService

logger = get_logger("context.compaction.summarizer")


# 摘要生成 Prompt
SUMMARY_PROMPT = """请为以下对话历史生成简洁摘要（300字以内）。

## 重点保留
1. 用户的主要目标和需求
2. 已完成的关键步骤和结果
3. 重要的发现、决策和配置
4. 待完成的任务（如果有）
5. 关键的文件路径、变量名、配置值

## 对话历史
{messages}

## 输出格式（严格遵循）
```
目标：[用户的核心目标，一句话]
已完成：
- [步骤1及结果]
- [步骤2及结果]
关键信息：
- [重要发现/配置/路径等]
待完成：[剩余任务，如无则写"无"]
```

请直接输出摘要，不要添加其他说明。"""


class ConversationSummarizer:
    """
    对话摘要生成器

    使用 LLM 生成对话摘要，支持 fallback 到简单摘要。

    使用示例：
        summarizer = ConversationSummarizer()

        # 使用 LLM 生成摘要
        summary = await summarizer.generate_summary(
            messages=early_messages,
            llm_client=haiku_client
        )

        # 或使用简单摘要（无需 LLM）
        summary = summarizer.generate_simple_summary(early_messages)
    """

    def __init__(
        self,
        max_summary_tokens: int = 500,
        max_input_messages: int = 50,
        max_chars_per_message: int = 500,
    ):
        """
        初始化摘要生成器

        Args:
            max_summary_tokens: 摘要最大 token 数
            max_input_messages: 输入消息最大数量（避免超长输入）
            max_chars_per_message: 每条消息最大字符数（截断长消息）
        """
        self.max_summary_tokens = max_summary_tokens
        self.max_input_messages = max_input_messages
        self.max_chars_per_message = max_chars_per_message

    async def generate_summary(
        self, messages: List[Dict[str, Any]], llm_client: "BaseLLMService"
    ) -> str:
        """
        使用 LLM 生成对话摘要

        Args:
            messages: 要摘要的消息列表
            llm_client: LLM 客户端（推荐使用轻量模型如 Haiku）

        Returns:
            摘要文本
        """
        if not messages:
            return ""

        try:
            # 1. 格式化消息为文本
            formatted_messages = self._format_messages_for_prompt(messages)

            # 2. 构建 prompt
            prompt = SUMMARY_PROMPT.format(messages=formatted_messages)

            # 3. 调用 LLM
            from core.llm.base import Message

            response = await llm_client.create_message_async(
                messages=[Message(role="user", content=prompt)],
                system="你是一个专业的对话摘要助手。请生成简洁、信息丰富的摘要。",
                max_tokens=self.max_summary_tokens,
            )

            summary = response.content.strip()

            logger.info(
                f"✅ LLM 摘要生成完成: 输入 {len(messages)} 条消息, " f"输出 {len(summary)} 字符"
            )

            return summary

        except Exception as e:
            logger.warning(f"⚠️ LLM 摘要生成失败: {e}, 使用简单摘要 fallback")
            return self.generate_simple_summary(messages)

    def generate_simple_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        生成简单摘要（不使用 LLM）

        当 LLM 调用失败时作为 fallback，或在不需要智能摘要时使用。

        Args:
            messages: 要摘要的消息列表

        Returns:
            简单摘要文本
        """
        if not messages:
            return ""

        summary_lines = [f"[历史对话摘要 - 共 {len(messages)} 条消息]", ""]

        # 提取前几条和后几条消息的片段
        sample_count = min(3, max(1, len(messages) // 2))

        # 前几条消息
        for i, msg in enumerate(messages[:sample_count]):
            role = msg.get("role", "unknown")
            content = self._extract_text_content(msg.get("content", ""))
            truncated = content[:150] + "..." if len(content) > 150 else content
            summary_lines.append(f"[{role}] {truncated}")

        # 省略提示
        if len(messages) > sample_count * 2:
            summary_lines.append(f"... [省略 {len(messages) - sample_count * 2} 条消息] ...")

        # 后几条消息
        if len(messages) > sample_count:
            for msg in messages[-sample_count:]:
                role = msg.get("role", "unknown")
                content = self._extract_text_content(msg.get("content", ""))
                truncated = content[:150] + "..." if len(content) > 150 else content
                summary_lines.append(f"[{role}] {truncated}")

        return "\n".join(summary_lines)

    def _format_messages_for_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """
        格式化消息列表为 prompt 文本

        Args:
            messages: 消息列表

        Returns:
            格式化的文本
        """
        # 限制消息数量
        if len(messages) > self.max_input_messages:
            # 保留前后部分
            half = self.max_input_messages // 2
            messages = messages[:half] + messages[-half:]

        lines = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = self._extract_text_content(msg.get("content", ""))

            # 截断长消息
            if len(content) > self.max_chars_per_message:
                content = content[: self.max_chars_per_message] + "...[截断]"

            lines.append(f"[{role}]: {content}")

        return "\n\n".join(lines)

    def _extract_text_content(self, content: Any) -> str:
        """
        从消息内容中提取文本

        支持：
        - 字符串内容
        - content blocks 列表

        Args:
            content: 消息内容

        Returns:
            提取的文本
        """
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")

                    if block_type == "text":
                        texts.append(block.get("text", ""))
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_input = block.get("input", {})
                        # 简化工具调用描述
                        input_str = json.dumps(tool_input, ensure_ascii=False)
                        if len(input_str) > 200:
                            input_str = input_str[:200] + "..."
                        texts.append(f"[调用工具: {tool_name}({input_str})]")
                    elif block_type == "tool_result":
                        tool_content = block.get("content", "")
                        if isinstance(tool_content, str):
                            if len(tool_content) > 200:
                                tool_content = tool_content[:200] + "..."
                            texts.append(f"[工具结果: {tool_content}]")
                        else:
                            texts.append("[工具结果: ...]")
                    elif block_type == "thinking":
                        # 跳过 thinking 内容
                        pass
                elif isinstance(block, str):
                    texts.append(block)

            return " ".join(texts)

        return str(content)


# 便捷函数
async def generate_conversation_summary(
    messages: List[Dict[str, Any]], llm_client: Optional["BaseLLMService"] = None
) -> str:
    """
    生成对话摘要的便捷函数

    Args:
        messages: 要摘要的消息列表
        llm_client: LLM 客户端（可选，不提供则使用简单摘要）

    Returns:
        摘要文本
    """
    summarizer = ConversationSummarizer()

    if llm_client:
        return await summarizer.generate_summary(messages, llm_client)
    else:
        return summarizer.generate_simple_summary(messages)
