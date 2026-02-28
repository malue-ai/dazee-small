"""
knowledge_search — 本地知识库搜索工具

让 Agent 从用户本地知识库中检索信息。
底层使用 LocalKnowledgeManager 的混合搜索（FTS5 + 向量）。

使用场景：
- 用户提到"我的文档"、"我上传的资料"
- 需要查找用户本地目录中的内容
- 个人知识回忆场景
"""

from typing import Any, Dict

from logger import get_logger

from core.tool.types import BaseTool, ToolContext

logger = get_logger("tools.knowledge_search")


class KnowledgeSearchTool(BaseTool):
    """
    本地知识库搜索工具

    搜索用户指定目录中已索引的文档。
    支持 FTS5 全文搜索和可选的向量语义搜索。
    """

    name = "knowledge_search"
    description = "从用户本地知识库检索信息"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询（自然语言）",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果数量（默认 5）",
                "default": 5,
            },
            "file_type": {
                "type": "string",
                "description": "过滤文件类型（如 .md, .txt, .pdf），不填则搜索所有类型",
            },
        },
        "required": ["query"],
    }

    def __init__(self):
        self._knowledge_manager = None

    async def _get_knowledge_manager(self):
        """Lazy load knowledge manager singleton."""
        if self._knowledge_manager is None:
            from core.knowledge.local_search import LocalKnowledgeManager

            # Use a shared instance — initialized by service layer
            # Fallback: create a default FTS5-only instance
            try:
                from services.knowledge_service import get_knowledge_manager

                self._knowledge_manager = await get_knowledge_manager()
            except ImportError:
                logger.debug(
                    "knowledge_service not available, "
                    "using default FTS5-only manager"
                )
                self._knowledge_manager = LocalKnowledgeManager()
                await self._knowledge_manager.initialize()

        return self._knowledge_manager

    async def execute(
        self, params: Dict[str, Any], context: ToolContext
    ) -> Dict[str, Any]:
        """
        Execute knowledge search.

        Args:
            params: {"query": str, "limit": int, "file_type": str}
            context: Tool execution context

        Returns:
            {"success": bool, "results": [...], "total": int}
        """
        query = params.get("query", "").strip()
        if not query:
            return {"success": False, "error": "搜索查询不能为空"}

        limit = params.get("limit", 5)
        file_type = params.get("file_type")

        try:
            km = await self._get_knowledge_manager()
            results = await km.search(
                query=query,
                limit=limit,
                file_type=file_type,
            )

            if not results:
                return {
                    "success": True,
                    "results": [],
                    "total": 0,
                    "message": "未找到相关文档。知识库可能为空或查询无匹配结果。",
                }

            # Format results for LLM consumption
            formatted = []
            for r in results:
                entry = {
                    "title": r.title,
                    "snippet": r.snippet,
                    "score": round(r.score, 3),
                    "file_path": r.file_path,
                }
                if r.file_type:
                    entry["file_type"] = r.file_type
                formatted.append(entry)

            logger.info(
                f"知识搜索: query={query!r}, "
                f"results={len(formatted)}/{limit}"
            )

            return {
                "success": True,
                "results": formatted,
                "total": len(formatted),
                "_compression_hint": "search",
            }

        except Exception as e:
            logger.error(f"知识搜索失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"知识搜索失败: {str(e)}",
            }
