"""
KnowledgeContextInjector — 知识库上下文注入器

职责：
1. 根据用户查询自动从本地知识库检索相关片段
2. 注入到 user context message，为 Agent 提供本地知识背景

缓存策略：DYNAMIC（每轮查询不同，结果不同）
注入位置：Phase 2 - User Context Message
优先级：70（低于 user_memory(90) 和 playbook_hint(80)）

Token 预算：≤ 800 tokens（遵守上下文工程规范）
"""

from typing import Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.knowledge_context")

# Token budget for knowledge injection
MAX_KNOWLEDGE_CHARS = 2000  # ~500 tokens
MAX_RESULTS = 3


class KnowledgeContextInjector(BaseInjector):
    """
    知识库上下文注入器

    自动检索本地知识库中与用户查询相关的内容，
    注入到 user context message，让 Agent 有背景知识。

    输出示例：
    ```
    <knowledge_context>
    以下是与你的问题相关的本地知识库内容（共 2 条）：

    [1] 项目规划.md (相关度: 0.82)
    ...项目第一阶段目标是完成 MVP...

    [2] 会议纪要.txt (相关度: 0.65)
    ...讨论了技术选型问题，决定使用 FastAPI...

    来源目录：用户本地知识库
    </knowledge_context>
    ```
    """

    @property
    def name(self) -> str:
        return "knowledge_context"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT

    @property
    def cache_strategy(self) -> CacheStrategy:
        # Every query may retrieve different knowledge
        return CacheStrategy.DYNAMIC

    @property
    def priority(self) -> int:
        # Lower than user_memory(90), playbook_hint(80)
        return 70

    async def should_inject(self, context: InjectionContext) -> bool:
        """
        Inject when:
        1. User query exists
        2. Knowledge is not explicitly skipped by intent
        """
        if not context.user_query:
            return False

        # Skip if intent says to skip (e.g., simple greeting)
        intent = context.get("intent")
        if intent and getattr(intent, "skip_memory", False):
            return False

        return True

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        Retrieve and inject relevant knowledge context.

        Steps:
        1. Get knowledge manager (lazy)
        2. Search with user query
        3. Format results within token budget
        """
        knowledge_text = await self._retrieve_knowledge(context)

        if not knowledge_text:
            return InjectionResult()

        logger.info(
            f"KnowledgeContextInjector: {len(knowledge_text)} chars"
        )

        return InjectionResult(
            content=knowledge_text,
            xml_tag="knowledge_context",
        )

    async def _retrieve_knowledge(
        self, context: InjectionContext
    ) -> Optional[str]:
        """
        Retrieve relevant knowledge from local index.

        Returns formatted text or None.
        """
        query = context.user_query
        if not query:
            return None

        try:
            from core.knowledge.local_search import LocalKnowledgeManager

            # Try to get shared instance from service layer
            try:
                from services.knowledge_service import get_knowledge_manager

                km = await get_knowledge_manager()
            except ImportError:
                logger.debug(
                    "knowledge_service not available, skipping injection"
                )
                return None

            results = await km.search(
                query=query,
                limit=MAX_RESULTS,
                min_score=0.1,  # Higher threshold for injection
            )

            if not results:
                return None

            # Format within token budget
            return self._format_results(results)

        except Exception as e:
            logger.warning(f"知识检索注入失败: {e}")
            return None

    def _format_results(self, results) -> Optional[str]:
        """
        Format search results within token budget.

        Args:
            results: List of SearchResult

        Returns:
            Formatted text or None
        """
        if not results:
            return None

        parts = [
            f"以下是与你的问题相关的本地知识库内容"
            f"（共 {len(results)} 条）：",
            "",
        ]

        total_chars = sum(len(p) for p in parts)

        for i, r in enumerate(results, 1):
            # Build entry header
            header = f"[{i}] {r.title}"
            if r.file_type:
                header += f" ({r.file_type})"
            header += f" 相关度: {r.score:.2f}"

            # Truncate snippet to fit budget
            remaining = MAX_KNOWLEDGE_CHARS - total_chars - len(header) - 10
            if remaining <= 50:
                break

            snippet = r.snippet[:remaining] if r.snippet else ""

            entry = f"{header}\n{snippet}"
            parts.append(entry)
            parts.append("")
            total_chars += len(entry) + 1

        text = "\n".join(parts).strip()
        return text if len(text) > 20 else None
