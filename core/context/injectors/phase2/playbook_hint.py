"""
PlaybookHintInjector - Playbook 策略提示注入器

职责：
1. 根据当前用户 query 和 task_type 匹配历史成功策略（Playbook）
2. 以 <playbook_hint> 标签注入 Phase 2，供 Agent 参考（不强制遵循）

缓存策略：SESSION
注入位置：Phase 2 - User Context Message
优先级：80（低于用户记忆）
"""

from typing import Any, Dict, List, Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.playbook_hint")


def _format_playbook_hint(entry: Any, score: float) -> str:
    """Format a single playbook entry as playbook_hint content."""
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
            matched: List[tuple] = await manager.find_matching_async(
                query=query,
                task_type=task_type,
                top_k=1,
                min_score=0.3,
                only_approved=True,
            )
        except Exception as e:
            logger.debug(f"Playbook 匹配跳过: {e}")
            return InjectionResult()

        if not matched:
            return InjectionResult()

        entry, score = matched[0]
        content = _format_playbook_hint(entry, score)
        logger.info(f"PlaybookHintInjector: 注入 1 条策略 hint (score={score:.2f})")
        return InjectionResult(content=content, xml_tag=None)
