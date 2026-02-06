"""
KnowledgeInjector - 知识库注入器

职责：
1. 从 Ragie/向量数据库获取相关知识
2. 格式化为 XML 标签注入

缓存策略：DYNAMIC（不缓存，每次查询可能不同）
注入位置：Phase 2 - User Context Message
优先级：80（在用户记忆之后）
"""

from typing import Any, Dict, List, Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.knowledge")


class KnowledgeInjector(BaseInjector):
    """
    知识库注入器

    从知识库检索相关内容，注入到 user context message。

    输出示例：
    ```
    <knowledge_base>
    ## 相关文档

    **文档1: API 设计规范**
    RESTful API 应该使用标准 HTTP 方法...

    **文档2: 数据库设计指南**
    数据库表设计应该遵循第三范式...
    </knowledge_base>
    ```
    """

    def __init__(self, max_results: int = 5, max_chars: int = 2000):
        """
        初始化知识库注入器

        Args:
            max_results: 最大检索结果数
            max_chars: 每个结果最大字符数
        """
        self.max_results = max_results
        self.max_chars = max_chars

    @property
    def name(self) -> str:
        return "knowledge"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT

    @property
    def cache_strategy(self) -> CacheStrategy:
        # 知识检索结果每次都可能不同
        return CacheStrategy.DYNAMIC

    @property
    def priority(self) -> int:
        # 在用户记忆之后
        return 80

    async def should_inject(self, context: InjectionContext) -> bool:
        """需要有用户查询才能检索"""
        # 检查是否有预加载的知识
        if context.get("knowledge_results"):
            return True

        # 需要有查询
        return bool(context.user_query)

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入知识库内容

        1. 检查是否有预加载的知识
        2. 否则尝试从知识库检索
        """
        # 1. 检查预加载的知识
        knowledge_results = context.get("knowledge_results")

        if knowledge_results:
            logger.debug(f"使用预加载的知识: {len(knowledge_results)} 条")
            content = self._format_results(knowledge_results)
        else:
            # 2. 尝试从知识库检索
            results = await self._search_knowledge(context)

            if not results:
                logger.debug("知识库检索结果为空，跳过")
                return InjectionResult()

            content = self._format_results(results)

        if not content:
            return InjectionResult()

        logger.info(f"KnowledgeInjector: {len(content)} 字符")

        return InjectionResult(content=content, xml_tag="knowledge_base")

    async def _search_knowledge(self, context: InjectionContext) -> List[Dict[str, Any]]:
        """
        从知识库检索相关内容

        使用 core.context.providers.knowledge 模块
        """
        if not context.user_query:
            return []

        try:
            from core.context.providers.knowledge import KnowledgeProvider

            provider = KnowledgeProvider()
            results = await provider.retrieve(
                query=context.user_query, user_id=context.user_id or "", top_k=self.max_results
            )

            return results

        except ImportError:
            logger.debug("知识库 Provider 不可用，跳过")
            return []
        except Exception as e:
            logger.warning(f"知识库检索失败: {e}")
            return []

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """
        格式化检索结果

        输出 Markdown 格式的文档列表
        """
        if not results:
            return ""

        lines = ["## 相关文档", ""]

        for i, result in enumerate(results[: self.max_results], 1):
            content = result.get("content", "")
            title = result.get("metadata", {}).get("title", f"文档{i}")
            score = result.get("score", 0)

            # 截断长内容
            if len(content) > self.max_chars:
                content = content[: self.max_chars] + "..."

            lines.append(f"**{title}** (相关度: {score:.2f})")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)
