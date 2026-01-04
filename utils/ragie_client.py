"""
Ragie API 客户端 - 知识库管理

参考文档: https://docs.ragie.ai/reference/createdocument

支持功能:
1. 创建文档 (文件/URL/Raw)
2. 查询文档状态
3. 检索相关文档
4. Partition 管理 (多租户隔离)
"""

import os
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path


class RagieClient:
    """
    Ragie API 客户端
    
    用于与 Ragie 知识库服务交互
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.ragie.ai"):
        """
        初始化 Ragie 客户端
        
        Args:
            api_key: Ragie API Key (默认从环境变量 RAGIE_API_KEY 读取)
            base_url: API 基础 URL
        """
        self.api_key = api_key or os.getenv("RAGIE_API_KEY")
        if not self.api_key:
            raise ValueError("RAGIE_API_KEY 未设置，请在 .env 中配置或通过参数传入")
        
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def create_document_from_file(
        self,
        file_path: str,
        partition: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        mode: str = "hi_res"
    ) -> Dict[str, Any]:
        """
        从文件创建文档
        
        Args:
            file_path: 文件路径
            partition: Partition ID (用于多租户隔离)
            metadata: 文档元数据 (自定义 JSON 对象)
            mode: 处理模式 (fast/hi_res，默认 hi_res)
            
        Returns:
            {
                "id": "doc_xxx",
                "status": "pending",
                "partition": "partition_xxx",
                ...
            }
            
        Ref: https://docs.ragie.ai/reference/createdocument
        """
        import json
        
        url = f"{self.base_url}/documents"
        
        # 添加文件
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 先读取文件内容到内存（避免文件在发送前关闭）
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        async with aiohttp.ClientSession() as session:
            # 构建 multipart form data
            data = aiohttp.FormData()
            
            # 添加文件（使用已读取的字节内容）
            data.add_field(
                'file',
            file_content,
                filename=file_path_obj.name,
                content_type='application/octet-stream'
            )
            
            # 添加可选参数
            if partition:
                data.add_field('partition', partition)
            if metadata:
                data.add_field('metadata', json.dumps(metadata))
            data.add_field('mode', mode)
            
            # 发送请求
            import logging
            logger = logging.getLogger("zenflux.ragie_client")
            
            logger.info(f"📤 调用 Ragie API: POST {url}")
            logger.debug(f"   partition={partition}, mode={mode}, file_size={len(file_content)} bytes")
            
            async with session.post(
                url,
                data=data,
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                response_text = await response.text()
                logger.info(f"📥 Ragie 响应: HTTP {response.status}")
                logger.debug(f"   响应内容: {response_text[:500]}")
                
                if response.status in [200, 201]:
                    import json as json_lib
                    result = json_lib.loads(response_text)
                    logger.info(f"✅ Ragie 创建文档成功: id={result.get('id')}, status={result.get('status')}")
                    return result
                else:
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {response_text}")
    
    async def create_document_from_url(
        self,
        url: str,
        partition: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        mode: str = "hi_res"
    ) -> Dict[str, Any]:
        """
        从 URL 创建文档
        
        Args:
            url: 文档 URL
            partition: Partition ID
            metadata: 文档元数据
            mode: 处理模式
            
        Returns:
            文档创建结果
            
        Ref: https://docs.ragie.ai/reference/createdocumentfromurl
        """
        api_url = f"{self.base_url}/documents/url"
        
        payload = {
            "url": url,
            "mode": mode
        }
        
        if partition:
            payload["partition"] = partition
        if metadata:
            payload["metadata"] = metadata
        
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers=self.headers) as response:
                if response.status in [200, 201]:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def create_document_raw(
        self,
        content: str,
        name: str,
        partition: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        从纯文本/Markdown 创建文档
        
        Args:
            content: 文本内容
            name: 文档名称
            partition: Partition ID
            metadata: 文档元数据
            
        Returns:
            文档创建结果
            
        Ref: https://docs.ragie.ai/reference/createdocumentraw
        """
        import logging
        logger = logging.getLogger("zenflux.ragie_client")
        
        api_url = f"{self.base_url}/documents/raw"
        
        # 根据 Ragie API 文档，格式应该是 {"data": 内容, "name": 名称}
        payload = {
            "data": content,  # 注意：字段名是 data 不是 content
            "name": name
        }
        
        if partition:
            payload["partition"] = partition
        if metadata:
            payload["metadata"] = metadata
        
        logger.info(f"📤 调用 Ragie API: POST {api_url}")
        logger.debug(f"   name={name}, partition={partition}, content_length={len(content)}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers=self.headers) as response:
                response_text = await response.text()
                logger.info(f"📥 Ragie 响应: HTTP {response.status}")
                
                if response.status in [200, 201]:
                    import json
                    result = json.loads(response_text)
                    logger.info(f"✅ Ragie 创建文档成功: id={result.get('id')}, status={result.get('status')}")
                    return result
                else:
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {response_text}")
    
    # 别名方法（兼容性）
    async def create_document_from_raw(
        self,
        text: str,
        name: str,
        partition: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """create_document_raw 的别名（参数名不同）"""
        return await self.create_document_raw(
            content=text,
            name=name,
            partition=partition,
            metadata=metadata
        )
    
    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """
        获取文档状态
        
        Args:
            document_id: 文档 ID
            
        Returns:
            文档详情 (包含 status: pending/indexed/ready/failed)
            
        Ref: https://docs.ragie.ai/reference/getdocument
        """
        import logging
        logger = logging.getLogger("zenflux.ragie_client")
        
        url = f"{self.base_url}/documents/{document_id}"
        logger.info(f"🔍 调用 Ragie API: GET {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                response_text = await response.text()
                logger.info(f"📥 Ragie 响应: HTTP {response.status}")
                logger.debug(f"   响应内容: {response_text[:500]}")
                
                if response.status == 200:
                    import json
                    result = json.loads(response_text)
                    logger.info(f"✅ Ragie 获取文档成功: id={result.get('id')}, status={result.get('status')}")
                    return result
                else:
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {response_text}")
    
    async def retrieve(
        self,
        query: str,
        partition: Optional[str] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        检索相关文档片段
        
        Args:
            query: 查询文本
            partition: Partition ID (指定用户空间)
            top_k: 返回结果数量
            filters: 元数据过滤条件
            
        Returns:
            {
                "scored_chunks": [
                    {
                        "text": "...",
                        "score": 0.95,
                        "document_id": "doc_xxx",
                        "metadata": {...}
                    },
                    ...
                ]
            }
            
        Ref: https://docs.ragie.ai/reference/retrieve
        """
        url = f"{self.base_url}/retrievals"
        
        payload = {
            "query": query,
            "top_k": top_k
        }
        
        if partition:
            payload["partition"] = partition
        if filters:
            payload["filter"] = filters
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def list_documents(
        self,
        partition: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        列出文档
        
        Args:
            partition: Partition ID (过滤特定用户空间，可选)
            limit: 返回数量限制（最大 100）
            cursor: 分页游标（用于获取下一页）
            filter: Metadata 过滤条件，格式如 {"user_id": {"$eq": "xxx"}}
            
        Returns:
            {
                "pagination": {"next_cursor": str, "total_count": int},
                "documents": [...]
            }
            
        Ref: https://docs.ragie.ai/reference/listdocuments
        """
        import logging
        import json
        logger = logging.getLogger("zenflux.ragie_client")
        
        url = f"{self.base_url}/documents"
        params = {"limit": min(limit, 100)}  # Ragie 最大限制 100
        
        if partition:
            params["partition"] = partition
        if cursor:
            params["cursor"] = cursor
        if filter:
            # Ragie 的 filter 参数需要 JSON 字符串格式
            params["filter"] = json.dumps(filter)
        
        logger.debug(f"📋 调用 Ragie API: GET {url}, params={params}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    result = json.loads(response_text)
                    doc_count = len(result.get("documents", []))
                    logger.debug(f"📥 Ragie 返回 {doc_count} 个文档")
                    return result
                else:
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {response_text}")
    
    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        """
        删除文档
        
        Args:
            document_id: 文档 ID
            
        Returns:
            删除结果
            
        Ref: https://docs.ragie.ai/reference/deletedocument
        """
        url = f"{self.base_url}/documents/{document_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=self.headers) as response:
                if response.status in [200, 204]:
                    return {"success": True, "document_id": document_id}
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def patch_document_metadata(
        self,
        document_id: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新文档元数据（部分更新）
        
        Args:
            document_id: 文档 ID
            metadata: 新的元数据（会合并到现有元数据）
            
        Returns:
            更新后的文档信息
            
        Ref: https://docs.ragie.ai/reference/patchdocumentmetadata
        """
        url = f"{self.base_url}/documents/{document_id}/metadata"
        
        payload = {"metadata": metadata}
        
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, json=payload, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def create_partition(self, name: str) -> Dict[str, Any]:
        """
        创建 Partition (多租户隔离空间)
        
        Args:
            name: Partition 名称 (建议用 user_id)
            
        Returns:
            {
                "id": "partition_xxx",
                "name": "user_001",
                ...
            }
            
        Ref: https://docs.ragie.ai/reference/createpartition
        """
        url = f"{self.base_url}/partitions"
        payload = {"name": name}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as response:
                if response.status in [200, 201]:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def get_partition(self, partition_id: str) -> Dict[str, Any]:
        """
        获取 Partition 详情
        
        Args:
            partition_id: Partition ID
            
        Returns:
            Partition 详情
            
        Ref: https://docs.ragie.ai/reference/getpartition
        """
        url = f"{self.base_url}/partitions/{partition_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def get_document_content(self, document_id: str) -> Dict[str, Any]:
        """
        获取文档的原始内容
        
        Args:
            document_id: 文档 ID
            
        Returns:
            {"content": str}  # 文档的原始文本内容
            
        Ref: https://docs.ragie.ai/reference/getdocumentcontent
        """
        url = f"{self.base_url}/documents/{document_id}/content"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def get_document_chunks(
        self,
        document_id: str,
        limit: int = 100,
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取文档的所有分块
        
        Args:
            document_id: 文档 ID
            limit: 每页数量（最大 100）
            cursor: 分页游标
            
        Returns:
            {
                "pagination": {"next_cursor": str, "total_count": int},
                "chunks": [{"id": str, "text": str, ...}, ...]
            }
            
        Ref: https://docs.ragie.ai/reference/getdocumentchunks
        """
        url = f"{self.base_url}/documents/{document_id}/chunks"
        params = {"limit": min(limit, 100)}
        if cursor:
            params["cursor"] = cursor
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")
    
    async def get_document_source(self, document_id: str) -> bytes:
        """
        获取文档的原始文件（二进制）
        
        Args:
            document_id: 文档 ID
            
        Returns:
            bytes: 原始文件的二进制内容
            
        Ref: https://docs.ragie.ai/reference/getdocumentsource
        """
        url = f"{self.base_url}/documents/{document_id}/source"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    error_text = await response.text()
                    raise Exception(f"Ragie API 错误 (HTTP {response.status}): {error_text}")


# ============================================================
# 便捷函数
# ============================================================

_default_client: Optional[RagieClient] = None


def get_ragie_client() -> RagieClient:
    """获取默认 Ragie 客户端 (单例)"""
    global _default_client
    if _default_client is None:
        _default_client = RagieClient()
    return _default_client

