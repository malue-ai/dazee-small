"""
PlaybookHintInjector - Playbook 策略提示注入器

职责：
1. 根据当前用户 query 和 task_type 匹配历史成功策略（Playbook）
2. 以 <playbook_hint> 标签注入 Phase 2，供 Agent 参考（不强制遵循）
3. 注入成功后 fire-and-forget 记录 usage（更新 last_used_at 用于过期判定）

缓存策略：SESSION
注入位置：Phase 2 - User Context Message
优先级：80（低于用户记忆）
"""

import asyncio
from typing import Any, Dict, List, Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.playbook_hint")


def _format_playbook_hint(entry: Any, score: float) -> str:
    """Format a single playbook entry as playbook_hint content.

    LLM-First: always inject the best match with confidence score.
    The Agent decides whether to follow the hint based on relevance.
    Low-confidence matches get an explicit disclaimer.
    """
    parts = [f"类似任务的成功策略：{entry.description or entry.name}"]
    tools = entry.strategy.get("suggested_tools") or [
        t.get("tool") for t in (entry.tool_sequence or []) if t.get("tool")
    ]
    if tools:
        parts.append(f"建议工具序列：{' → '.join(tools[:5])}")
    metrics = entry.quality_metrics or {}
    avg_turns = metrics.get("avg_turns")
    success_rate = metrics.get("success_rate")
    if avg_turns is not None or success_rate is not None:
        line_parts = []
        if avg_turns is not None:
            line_parts.append(f"平均约 {int(avg_turns)} 步")
        if success_rate is not None:
            line_parts.append(f"成功率 {int(success_rate * 100)}%")
        parts.append("，".join(line_parts))
    confidence = min(1.0, max(0.0, score))
    # Low-confidence: add disclaimer so the Agent knows to judge relevance itself
    if confidence < 0.5:
        parts.append("（低置信度匹配，请自行判断是否适用当前任务）")
    return f'<playbook_hint confidence="{confidence:.2f}">\n' + "\n".join(parts) + "\n</playbook_hint>"


class PlaybookHintInjector(BaseInjector):
    """
    Playbook 策略提示注入器

    在 Phase 2 注入与当前任务匹配的历史成功策略，供 Agent 参考。
    可参考但不强制遵循。
    """

    @property
    def name(self) -> str:
        return "playbook_hint"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT

    @property
    def cache_strategy(self) -> CacheStrategy:
        return CacheStrategy.SESSION

    @property
    def priority(self) -> int:
        return 80

    async def should_inject(self, context: InjectionContext) -> bool:
        """有用户 query 时才尝试匹配 Playbook"""
        return bool(context.user_query and context.user_query.strip())

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        查询匹配的 Playbook，格式化为 <playbook_hint> 注入。
        """
        query = (context.user_query or "").strip()

        task_type = ""
        if context.intent and hasattr(context.intent, "task_type"):
            tt = context.intent.task_type
            task_type = tt.value if hasattr(tt, "value") else str(tt)

        try:
            from core.playbook import create_playbook_manager

            manager = create_playbook_manager()
            await manager.load_all_async()
            # LLM-First: no hard threshold cutoff.
            # Always retrieve the best match; the confidence score in the hint
            # tells the Agent how confident the match is. The Agent decides.
            matched: List[tuple] = await manager.find_matching_async(
                query=query,
                task_type=task_type,
                top_k=1,
                min_score=0.1,  # Only filter noise; Agent judges relevance
                only_approved=True,
            )
        except Exception as e:
            logger.info(f"PlaybookHintInjector: 匹配跳过 ({e})")
            return InjectionResult()

        if not matched:
            approved_count = sum(
                1 for e in manager._entries.values()
                if e.status.value == "approved"
            )
            if approved_count > 0:
                logger.info(
                    f"PlaybookHintInjector: 有 {approved_count} 个策略但 Mem0 未返回结果 "
                    f"(query={query[:50]}...)"
                )
            return InjectionResult()

        entry, score = matched[0]
        content = _format_playbook_hint(entry, score)

        # Fire-and-forget: record usage for staleness tracking.
        # MUST NOT block the chat response — use create_task so the
        # injector returns immediately and the user sees no delay.
        asyncio.create_task(
            self._record_usage_safe(manager, entry.id)
        )

        logger.info(f"PlaybookHintInjector: 注入 1 条策略 hint (score={score:.2f})")
        return InjectionResult(content=content, xml_tag=None)

    @staticmethod
    async def _record_usage_safe(manager: Any, entry_id: str):
        """Best-effort usage recording. Never raises."""
        try:
            await manager.record_usage(entry_id)
        except Exception as e:
            logger.debug(f"record_usage 失败（non-critical）: {e}")
