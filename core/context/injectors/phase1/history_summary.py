"""
HistorySummaryProvider - 历史摘要提供器

职责：
1. 从 InjectionContext 获取历史摘要
2. 如果没有预生成的摘要，使用 ConversationSummarizer 生成
3. 格式化为 XML 标签

缓存策略：DYNAMIC（不缓存，每次都可能不同）
注入位置：Phase 1 - System Message
优先级：60（在工具定义之后）
"""

from typing import Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase1.history_summary")


class HistorySummaryProvider(BaseInjector):
    """
    历史摘要提供器

    注入对话历史的摘要，帮助 LLM 理解上下文。

    输出示例：
    ```
    <chat_history_summary>
    目标：用户希望构建一个 CRM 系统
    已完成：
    - 设计了数据库模型
    - 创建了基础 API 框架
    关键信息：
    - 使用 PostgreSQL 数据库
    - 采用 FastAPI 框架
    待完成：实现用户认证模块
    </chat_history_summary>
    ```
    """

    @property
    def name(self) -> str:
        return "history_summary"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.SYSTEM

    @property
    def cache_strategy(self) -> CacheStrategy:
        # 历史摘要每次都可能不同，不缓存
        return CacheStrategy.DYNAMIC

    @property
    def priority(self) -> int:
        # 在工具定义之后
        return 60

    async def should_inject(self, context: InjectionContext) -> bool:
        """只有存在历史或预生成摘要时才注入"""
        # 检查是否有预生成的摘要
        if context.get("history_summary"):
            return True

        # 检查是否有足够的历史消息（至少 5 条）
        return len(context.history_messages) >= 5

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入历史摘要

        1. 优先使用预生成的摘要
        2. 否则生成简单摘要
        """
        # 1. 尝试获取预生成的摘要
        summary = context.get("history_summary")

        if summary:
            logger.debug(f"使用预生成的历史摘要: {len(summary)} 字符")
        else:
            # 2. 生成简单摘要（不调用 LLM，避免延迟）
            summary = self._generate_simple_summary(context)

            if not summary:
                logger.debug("历史摘要为空，跳过")
                return InjectionResult()

            logger.debug(f"生成简单历史摘要: {len(summary)} 字符")

        logger.info(f"HistorySummaryProvider: {len(summary)} 字符")

        return InjectionResult(content=summary, xml_tag="chat_history_summary")

    def _generate_simple_summary(self, context: InjectionContext) -> Optional[str]:
        """
        生成简单摘要（不调用 LLM）

        提取最近几轮对话的关键信息
        """
        if not context.history_messages:
            return None

        messages = context.history_messages

        # 只处理最近 10 条消息
        recent_messages = messages[-10:]

        # 提取用户消息和助手消息
        user_messages = []
        assistant_summaries = []

        for msg in recent_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if isinstance(content, list):
                # 处理 content blocks 格式
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = " ".join(text_parts)

            if not content:
                continue

            # 截断长内容
            if len(content) > 200:
                content = content[:200] + "..."

            if role == "user":
                user_messages.append(content)
            elif role == "assistant":
                # 只保留前 100 字符
                assistant_summaries.append(content[:100])

        if not user_messages:
            return None

        # 构建摘要
        lines = []

        # 最近的用户请求
        if user_messages:
            lines.append(f"最近的用户请求：{user_messages[-1]}")

        # 对话轮数
        lines.append(f"对话轮数：{len(messages)} 轮")

        return "\n".join(lines)
