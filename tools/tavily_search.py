"""
Tavily 搜索工具 - 通用网络搜索

使用 Tavily API 进行通用网络搜索
参考: https://docs.tavily.com/documentation/api-reference/search
"""

import os
import aiohttp
from typing import Dict, Any, Optional, List

from core.tool.base import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class TavilySearchTool(BaseTool):
    """
    Tavily 搜索工具
    
    使用 Tavily API 进行通用网络搜索，支持 AI 摘要和深度搜索。
    
    注意：input_schema 由 capabilities.yaml 定义，此处不重复。
    """
    
    # 工具名称（用于匹配 capabilities.yaml 配置）
    name = "tavily_search"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 Tavily 搜索工具
        
        Args:
            api_key: Tavily API 密钥，如果为 None 则从环境变量读取
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("Tavily API key is required. Set TAVILY_API_KEY environment variable.")
        
        self.base_url = "https://api.tavily.com"
        self.timeout = 30  # 30秒超时
    
    async def execute(
        self,
        params: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
        """
        执行 Tavily 搜索
        
        Args:
            params: 工具输入参数（由 Claude 根据 capabilities.yaml 的 input_schema 传入）
            context: 工具执行上下文
            
        Returns:
            包含搜索结果的字典
        """
        # 从 params 提取参数
        query = params.get("query")
        if not query:
            return {"success": False, "error": "缺少必需参数: query"}
        
        search_depth = params.get("search_depth", "basic")
        max_results = params.get("max_results", 5)
        include_answer = params.get("include_answer", True)
        include_raw_content = params.get("include_raw_content", False)
        include_domains = params.get("include_domains")
        exclude_domains = params.get("exclude_domains")
        topic = params.get("topic", "general")
        
        try:
            # 构建请求参数
            payload = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": search_depth,
                "max_results": min(max_results, 20),
                "include_answer": include_answer,
                "include_raw_content": include_raw_content,
                "topic": topic
            }
            
            if include_domains:
                payload["include_domains"] = include_domains
            
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains
            
            headers = {"Content-Type": "application/json"}
            
            logger.info(f"🔍 Tavily 搜索: query={query[:50]}..., depth={search_depth}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/search",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Tavily API 错误: status={response.status}, error={error_text}")
                        return {
                            "success": False,
                            "error": f"Tavily API error (status {response.status}): {error_text}"
                        }
                    
                    data = await response.json()
            
            results = self._format_results(data)
            
            result = {
                "success": True,
                "query": query,
                "num_results": len(results),
                "results": results
            }
            
            if include_answer and data.get("answer"):
                result["answer"] = data["answer"]
            
            if data.get("follow_up_questions"):
                result["follow_up_questions"] = data["follow_up_questions"]
            
            logger.info(f"✅ Tavily 搜索完成: query={query[:30]}..., results={len(results)}")
            
            return result
        
        except aiohttp.ClientError as e:
            logger.error(f"Tavily 网络错误: {str(e)}")
            return {"success": False, "error": f"Network error: {str(e)}"}
        except Exception as e:
            logger.error(f"Tavily 意外错误: {str(e)}", exc_info=True)
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    def _format_results(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """格式化搜索结果"""
        results = []
        
        for item in data.get("results", []):
            result = {
                "title": item.get("title", "Untitled"),
                "url": item.get("url"),
                "content": item.get("content", ""),
            }
            
            if "score" in item:
                result["score"] = item["score"]
            
            if "published_date" in item:
                result["published_date"] = item["published_date"]
            
            if "raw_content" in item and item["raw_content"]:
                raw = item["raw_content"].strip()
                result["raw_content"] = raw[:3000] + "..." if len(raw) > 3000 else raw
            
            results.append(result)
        
        return results
