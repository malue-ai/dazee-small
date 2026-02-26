"""
memory_recall — 用户记忆检索工具

让 Agent 主动查询用户的长期记忆（MEMORY.md + FTS5 + Mem0 向量）。

使用场景：
- 用户询问"你记住了什么关于我的..."
- Agent 需要回忆用户偏好、习惯、历史
- 跨会话信息检索
"""

from typing import Any, Dict

from logger import get_logger

from core.tool.types import BaseTool, ToolContext

logger = get_logger("tools.memory_recall")


class MemoryRecallTool(BaseTool):
    """
    用户记忆检索工具

    融合搜索（FTS5 全文 + Mem0 语义 + MEMORY.md 全文），
    让 Agent 主动检索用户历史记忆。
    """

    name = "memory_recall"
    description = (
        "检索用户的长期记忆（偏好、习惯、历史经验等）。"
        "当用户询问你记住了什么、我的偏好/习惯、之前聊过什么时使用。"
        "也可以用 mode=full 读取完整记忆档案。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询（自然语言），如「写作风格偏好」「常用工具」",
            },
            "mode": {
                "type": "string",
                "enum": ["search", "full"],
                "description": (
                    "search: 语义搜索匹配记忆（默认）；"
                    "full: 读取完整 MEMORY.md 记忆档案"
                ),
                "default": "search",
            },
            "limit": {
                "type": "integer",
                "description": "搜索模式下返回结果数量（默认 10）",
                "default": 10,
            },
        },
        "required": ["query"],
    }

    def __init__(self):
        self._memory_manager = None

    async def _get_memory_manager(self, context: ToolContext):
        """Lazy-init InstanceMemoryManager with proper instance isolation."""
        if self._memory_manager is None:
            from core.memory.instance_memory import get_instance_memory_manager

            from utils.memory_config import load_memory_config
            mem_cfg = await load_memory_config()

            self._memory_manager = get_instance_memory_manager(
                user_id=context.user_id,
                instance_name=context.instance_id or None,
                mem0_enabled=mem_cfg.mem0_enabled,
                enabled=mem_cfg.enabled,
            )
        return self._memory_manager

    async def execute(
        self, params: Dict[str, Any], context: ToolContext
    ) -> Dict[str, Any]:
        """
        Execute memory recall.

        Args:
            params: {"query": str, "mode": "search"|"full", "limit": int}
            context: Tool execution context

        Returns:
            {"success": bool, "results": [...] | "memory": str}
        """
        query = params.get("query", "").strip()
        mode = params.get("mode", "search")
        limit = params.get("limit", 10)

        if not query and mode == "search":
            return {"success": False, "error": "搜索查询不能为空"}

        try:
            mgr = await self._get_memory_manager(context)

            if mode == "full":
                # Read complete MEMORY.md
                memory_content = await mgr.get_memory_context()
                if not memory_content or len(memory_content.strip()) < 20:
                    return {
                        "success": True,
                        "memory": "",
                        "message": "记忆档案为空，还没有记录任何信息。",
                    }

                logger.info(
                    f"记忆全量读取: {len(memory_content)} 字符"
                )
                return {
                    "success": True,
                    "memory": memory_content,
                    "total_chars": len(memory_content),
                }

            # mode == "search": fusion search
            results = await mgr.recall(
                query=query, limit=limit
            )

            if not results:
                return {
                    "success": True,
                    "results": [],
                    "total": 0,
                    "message": f"未找到与「{query}」相关的记忆。",
                }

            # Format for LLM consumption
            formatted = []
            for r in results:
                formatted.append({
                    "content": r.get("content", ""),
                    "score": round(r.get("score", 0.0), 3),
                    "source": r.get("source", "unknown"),
                    "category": r.get("category", "general"),
                })

            logger.info(
                f"记忆搜索: query={query!r}, "
                f"results={len(formatted)}/{limit}"
            )

            return {
                "success": True,
                "results": formatted,
                "total": len(formatted),
            }

        except Exception as e:
            logger.error(f"记忆检索失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"记忆检索失败: {str(e)}",
            }
