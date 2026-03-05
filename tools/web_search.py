"""
复合网络搜索工具

统一搜索入口，内部按优先级自动降级：Tavily → Exa。
LLM 只需调用 web_search(query=...)，无需感知后端选择。
"""

import os
from typing import Any, Dict, List, Optional
import httpx

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 15
_USER_AGENT = "ZenFlux-Agent/1.0"


class WebSearchTool(BaseTool):
    """搜索互联网获取最新信息，自动选择最佳搜索源并内置降级。"""

    name = "web_search"
    description = (
        "本地搜索互联网获取最新信息（Tavily/Exa，需本地配置 API Key）。"
        "适合快速搜索、简单查询。"
        "如果本地未配置搜索 Key 或需要深度调研，应改用 cloud_agent 工具（云端已有搜索能力）。"
    )
    execution_timeout = 30
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询",
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数（默认 5）",
                "default": 5,
            },
            "search_depth": {
                "type": "string",
                "enum": ["basic", "advanced"],
                "description": "basic（快速）或 advanced（深度）",
                "default": "basic",
            },
            "time_range": {
                "type": "string",
                "enum": ["day", "week", "month", "any"],
                "description": "时间范围过滤",
                "default": "any",
            },
        },
        "required": ["query"],
    }

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        query = (
            params.get("query")
            or params.get("q")
            or params.get("search_query")
            or ""
        ).strip()
        if not query:
            return {"success": False, "error": "query 参数不能为空"}

        max_results = min(params.get("max_results", 5), 20)
        search_depth = params.get("search_depth", "basic")
        time_range = params.get("time_range", "any")

        backends = [
            ("tavily", self._search_tavily),
            ("exa", self._search_exa),
        ]

        tried: List[str] = []
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            for name, fn in backends:
                tried.append(name)
                try:
                    results = await fn(
                        client, query, max_results, search_depth, time_range
                    )
                    if results is not None:
                        logger.info(
                            "web_search 成功 [%s]: query=%r, results=%d",
                            name, query, len(results),
                        )
                        return {
                            "success": True,
                            "provider": name,
                            "query": query,
                            "results": results[:max_results],
                        }
                except Exception as e:
                    logger.warning(
                        "web_search 后端 [%s] 失败: %s", name, e, exc_info=True
                    )
                    continue

        return {
            "success": False,
            "error": "所有搜索源均不可用",
            "tried": tried,
        }

    # ------------------------------------------------------------------
    # Tavily (https://api.tavily.com)
    # ------------------------------------------------------------------

    async def _search_tavily(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
        search_depth: str,
        time_range: str,
    ) -> Optional[List[Dict[str, str]]]:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return None

        body: Dict[str, Any] = {
            "api_key": api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
        }
        if time_range == "day":
            body["days"] = 1
        elif time_range == "week":
            body["days"] = 7
        elif time_range == "month":
            body["days"] = 30

        resp = await client.post("https://api.tavily.com/search", json=body)
        resp.raise_for_status()
        data = resp.json()

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:500],
                "source": "tavily",
            }
            for r in data.get("results", [])
        ]

    # ------------------------------------------------------------------
    # Exa (https://api.exa.ai)
    # ------------------------------------------------------------------

    async def _search_exa(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
        search_depth: str,
        time_range: str,
    ) -> Optional[List[Dict[str, str]]]:
        api_key = os.environ.get("EXA_API_KEY")
        if not api_key:
            return None

        body: Dict[str, Any] = {
            "query": query,
            "numResults": max_results,
            "contents": {"text": {"maxCharacters": 500}},
        }
        if time_range != "any":
            mapping = {"day": "1d", "week": "1w", "month": "1m"}
            body["startPublishedDate"] = f"now-{mapping.get(time_range, '1m')}"

        resp = await client.post(
            "https://api.exa.ai/search",
            json=body,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("text") or r.get("snippet") or "")[:500],
                "source": "exa",
            }
            for r in data.get("results", [])
        ]

