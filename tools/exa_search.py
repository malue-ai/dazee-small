"""
Exa 搜索工具 - 高质量语义搜索

使用 Exa API 进行高质量的语义搜索，获取网页内容
参考: https://dashboard.exa.ai/playground/search

配置说明：
- input_schema 在 config/capabilities.yaml 中定义
- 运营可直接修改 YAML 调整参数，无需改代码
"""

import os
from typing import Any, Dict, List, Optional

import aiohttp

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class ExaSearchTool(BaseTool):
    """
    Exa 搜索工具

    使用 Exa API 进行语义搜索，返回高质量的网页内容。

    特点：
    - 语义理解：理解查询意图，返回最相关内容
    - 网页内容提取：自动提取网页正文内容
    - 时间过滤：支持按发布时间过滤结果
    - 分类搜索：支持按类别过滤（papers, news, github 等）

    注意：input_schema 由 capabilities.yaml 定义，此处不重复
    """

    # 工具名称（用于匹配 capabilities.yaml 配置）
    name = "exa_search"

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 Exa 搜索工具

        Args:
            api_key: Exa API 密钥，如果为 None 则从环境变量读取
        """
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        if not self.api_key:
            raise ValueError("Exa API key is required. Set EXA_API_KEY environment variable.")

        self.base_url = "https://api.exa.ai"
        self.timeout = 30  # 30秒超时

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行 Exa 搜索

        Args:
            params: 工具输入参数（由 Claude 根据 capabilities.yaml 的 input_schema 传入）
                - query: 搜索查询
                - num_results: 返回结果数量
                - category: 内容分类
                - include_text: 是否包含正文
                - start_published_date: 开始发布日期
            context: 工具执行上下文

        Returns:
            包含搜索结果的字典
        """
        # 从 params 提取参数
        query = params.get("query")
        if not query:
            return {"success": False, "error": "缺少必需参数: query"}

        num_results = params.get("num_results", 10)
        category = params.get("category")
        include_text = params.get("include_text", True)
        start_published_date = params.get("start_published_date")

        try:
            # 构建请求参数
            payload = {
                "query": query,
                "numResults": min(num_results, 10),  # 限制最大10个结果
                "type": "neural",  # 使用神经网络搜索
                "contents": {"text": include_text},
            }

            # 添加可选参数
            if category:
                payload["category"] = category

            if start_published_date:
                payload["startPublishedDate"] = start_published_date

            # 调用 Exa API
            headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}

            logger.info(f"🔍 Exa 搜索: query={query[:50]}...")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/search",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Exa API 错误: status={response.status}, error={error_text}")
                        return {
                            "success": False,
                            "error": f"Exa API error (status {response.status}): {error_text}",
                        }

                    data = await response.json()

            # 格式化搜索结果
            results = self._format_results(data)

            logger.info(f"✅ Exa 搜索完成: query={query[:30]}..., results={len(results)}")

            return {
                "success": True,
                "query": query,
                "num_results": len(results),
                "results": results,
                "metadata": {
                    "autoprompt": data.get("autopromptString"),
                    "resolved_search_type": data.get("resolvedSearchType"),
                },
            }

        except aiohttp.ClientError as e:
            logger.error(f"Exa 网络错误: {str(e)}")
            return {"success": False, "error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"Exa 意外错误: {str(e)}", exc_info=True)
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def _format_results(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        格式化搜索结果

        Args:
            data: Exa API 返回的原始数据

        Returns:
            格式化后的结果列表
        """
        results = []

        for item in data.get("results", []):
            result = {
                "title": item.get("title", "Untitled"),
                "url": item.get("url"),
                "score": item.get("score", 0),
            }

            # 添加可选字段
            if "publishedDate" in item:
                result["published_date"] = item["publishedDate"]

            if "author" in item:
                result["author"] = item["author"]

            if "text" in item:
                # 截取前2000字符，避免内容过长
                text = item["text"].strip()
                result["text"] = text[:2000] + "..." if len(text) > 2000 else text

            if "image" in item:
                result["image"] = item["image"]

            results.append(result)

        return results
