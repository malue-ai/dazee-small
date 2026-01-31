"""
Exa搜索工具 - 高质量语义搜索

使用Exa API进行高质量的语义搜索，获取网页内容
参考: https://dashboard.exa.ai/playground/search
"""

import os
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime


class ExaSearchTool:
    """
    Exa搜索工具
    
    使用Exa API进行语义搜索，返回高质量的网页内容
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化Exa搜索工具
        
        Args:
            api_key: Exa API密钥，如果为None则从环境变量读取
        """
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        if not self.api_key:
            raise ValueError("Exa API key is required. Set EXA_API_KEY environment variable.")
        
        self.base_url = "https://api.exa.ai"
        self.timeout = 30  # 30秒超时
    
    @property
    def name(self) -> str:
        return "exa_search"
    
    @property
    def description(self) -> str:
        return """使用Exa API进行高质量的语义搜索。

特点：
- 语义理解：理解查询意图，返回最相关内容
- 网页内容提取：自动提取网页正文内容
- 时间过滤：支持按发布时间过滤结果
- 分类搜索：支持按类别过滤（papers, news, github等）

输入：搜索查询和可选的过滤条件
输出：搜索结果列表，包含标题、URL、内容摘要、发布时间等"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询（支持自然语言）"
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量（默认10，最大10）",
                    "default": 10
                },
                "category": {
                    "type": "string",
                    "description": "内容分类（papers/news/github/company/personal_site/pdf等）",
                    "enum": ["papers", "news", "github", "company", "personal_site", "pdf", "tweet"],
                    "default": None
                },
                "include_text": {
                    "type": "boolean",
                    "description": "是否包含网页正文内容（默认true）",
                    "default": True
                },
                "start_published_date": {
                    "type": "string",
                    "description": "开始发布日期（ISO格式，如'2024-01-01'）",
                    "default": None
                }
            },
            "required": ["query"]
        }
    
    async def execute(
        self,
        query: str,
        num_results: int = 10,
        category: Optional[str] = None,
        include_text: bool = True,
        start_published_date: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行Exa搜索
        
        Args:
            query: 搜索查询
            num_results: 返回结果数量
            category: 内容分类
            include_text: 是否包含正文
            start_published_date: 开始发布日期
            
        Returns:
            包含搜索结果的字典
        """
        try:
            # 构建请求参数
            payload = {
                "query": query,
                "numResults": min(num_results, 10),  # 限制最大10个结果
                "type": "neural",  # 使用神经网络搜索
                "contents": {
                    "text": include_text
                }
            }
            
            # 添加可选参数
            if category:
                payload["category"] = category
            
            if start_published_date:
                payload["startPublishedDate"] = start_published_date
            
            # 调用Exa API
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/search",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return {
                            "status": "error",
                            "message": f"Exa API error (status {response.status}): {error_text}"
                        }
                    
                    data = await response.json()
            
            # 格式化搜索结果
            results = self._format_results(data)
            
            return {
                "status": "success",
                "query": query,
                "num_results": len(results),
                "results": results,
                "metadata": {
                    "autoprompt": data.get("autopromptString"),
                    "resolved_search_type": data.get("resolvedSearchType")
                }
            }
        
        except aiohttp.ClientError as e:
            return {
                "status": "error",
                "message": f"Network error: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }
    
    def _format_results(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        格式化搜索结果
        
        Args:
            data: Exa API返回的原始数据
            
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
    
    async def search_and_get_contents(
        self,
        query: str,
        num_results: int = 5
    ) -> Dict[str, Any]:
        """
        简化的搜索接口，直接获取内容
        
        Args:
            query: 搜索查询
            num_results: 结果数量
            
        Returns:
            搜索结果
        """
        return await self.execute(
            query=query,
            num_results=num_results,
            include_text=True
        )

