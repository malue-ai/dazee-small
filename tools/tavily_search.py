"""
Tavily 搜索工具 - 通用网络搜索

使用 Tavily API 进行通用网络搜索，替代 Claude 的 web_search Server Tool
参考: https://docs.tavily.com/documentation/api-reference/search
"""

import os
import logging
import aiohttp
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class TavilySearchTool:
    """
    Tavily 搜索工具
    
    使用 Tavily API 进行通用网络搜索，支持 AI 摘要和深度搜索
    
    特点：
    - 通用搜索：适合快速获取信息
    - AI 摘要：自动生成搜索结果的摘要（可选）
    - 深度搜索：支持 basic/advanced 两种深度
    - 域名过滤：支持包含/排除特定域名
    """
    
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
    
    @property
    def name(self) -> str:
        return "tavily_search"
    
    @property
    def description(self) -> str:
        return """使用 Tavily API 进行通用网络搜索。

特点：
- 通用搜索：快速获取互联网信息
- AI 摘要：自动生成搜索结果的智能摘要
- 深度搜索：basic（快速）或 advanced（深入）
- 域名过滤：可指定包含或排除的域名

适用场景：
- 快速查询事实信息
- 获取最新新闻动态
- 搜索产品/公司信息
- 通用知识检索

输入：搜索查询和可选的过滤条件
输出：搜索结果列表，包含标题、URL、内容摘要等"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询（支持自然语言）"
                },
                "search_depth": {
                    "type": "string",
                    "description": "搜索深度：basic（快速）或 advanced（深入，更多结果）",
                    "enum": ["basic", "advanced"],
                    "default": "basic"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量（默认5，最大20）",
                    "default": 5
                },
                "include_answer": {
                    "type": "boolean",
                    "description": "是否包含 AI 生成的摘要答案（默认true）",
                    "default": True
                },
                "include_raw_content": {
                    "type": "boolean",
                    "description": "是否包含网页原始内容（默认false，会增加响应大小）",
                    "default": False
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "只搜索这些域名（可选），如 ['github.com', 'stackoverflow.com']"
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "排除这些域名（可选），如 ['pinterest.com']"
                },
                "topic": {
                    "type": "string",
                    "description": "搜索主题类型：general（通用）或 news（新闻）",
                    "enum": ["general", "news"],
                    "default": "general"
                }
            },
            "required": ["query"]
        }
    
    async def execute(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        include_answer: bool = True,
        include_raw_content: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        topic: str = "general",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行 Tavily 搜索
        
        Args:
            query: 搜索查询
            search_depth: 搜索深度（basic/advanced）
            max_results: 返回结果数量
            include_answer: 是否包含 AI 摘要
            include_raw_content: 是否包含原始网页内容
            include_domains: 只搜索这些域名
            exclude_domains: 排除这些域名
            topic: 搜索主题（general/news）
            
        Returns:
            包含搜索结果的字典
        """
        try:
            # 构建请求参数
            payload = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": search_depth,
                "max_results": min(max_results, 20),  # 限制最大20个结果
                "include_answer": include_answer,
                "include_raw_content": include_raw_content,
                "topic": topic
            }
            
            # 添加可选的域名过滤
            if include_domains:
                payload["include_domains"] = include_domains
            
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains
            
            # 调用 Tavily API
            headers = {
                "Content-Type": "application/json"
            }
            
            logger.debug(f"Tavily 搜索请求: query={query}, depth={search_depth}")
            
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
                            "status": "error",
                            "message": f"Tavily API error (status {response.status}): {error_text}"
                        }
                    
                    data = await response.json()
            
            # 格式化搜索结果
            results = self._format_results(data)
            
            result = {
                "status": "success",
                "query": query,
                "num_results": len(results),
                "results": results
            }
            
            # 添加 AI 摘要（如果有）
            if include_answer and data.get("answer"):
                result["answer"] = data["answer"]
            
            # 添加相关查询建议（如果有）
            if data.get("follow_up_questions"):
                result["follow_up_questions"] = data["follow_up_questions"]
            
            logger.info(f"Tavily 搜索完成: query={query}, results={len(results)}")
            
            return result
        
        except aiohttp.ClientError as e:
            logger.error(f"Tavily 网络错误: {str(e)}")
            return {
                "status": "error",
                "message": f"Network error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Tavily 意外错误: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }
    
    def _format_results(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        格式化搜索结果
        
        Args:
            data: Tavily API 返回的原始数据
            
        Returns:
            格式化后的结果列表
        """
        results = []
        
        for item in data.get("results", []):
            result = {
                "title": item.get("title", "Untitled"),
                "url": item.get("url"),
                "content": item.get("content", ""),  # Tavily 返回的是摘要内容
            }
            
            # 添加评分（如果有）
            if "score" in item:
                result["score"] = item["score"]
            
            # 添加发布日期（如果有）
            if "published_date" in item:
                result["published_date"] = item["published_date"]
            
            # 添加原始内容（如果请求了）
            if "raw_content" in item and item["raw_content"]:
                # 截取前3000字符，避免内容过长
                raw = item["raw_content"].strip()
                result["raw_content"] = raw[:3000] + "..." if len(raw) > 3000 else raw
            
            results.append(result)
        
        return results
    
    async def quick_search(
        self,
        query: str,
        max_results: int = 5
    ) -> Dict[str, Any]:
        """
        快速搜索接口
        
        Args:
            query: 搜索查询
            max_results: 结果数量
            
        Returns:
            搜索结果
        """
        return await self.execute(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,
            include_raw_content=False
        )
    
    async def deep_search(
        self,
        query: str,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        深度搜索接口
        
        Args:
            query: 搜索查询
            max_results: 结果数量
            
        Returns:
            搜索结果
        """
        return await self.execute(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
            include_raw_content=True
        )
    
    async def news_search(
        self,
        query: str,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        新闻搜索接口
        
        Args:
            query: 搜索查询
            max_results: 结果数量
            
        Returns:
            搜索结果
        """
        return await self.execute(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
            topic="news"
        )
