"""
知识库服务层 - Knowledge Service

职责：
1. 封装业务逻辑（文档上传、管理、检索）
2. 与 Ragie API 和本地存储交互
3. 提供可复用的业务方法

设计原则：
- 不包含 HTTP 相关逻辑（由 router 层处理）
- 可被多个 router 或其他 service 复用
- 统一的错误处理（抛出业务异常）
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from logger import get_logger
from utils.ragie_client import get_ragie_client, RagieClient
from utils.knowledge_store import get_knowledge_store, KnowledgeStore
from models.knowledge import (
    DocumentInfo,
    ChunkInfo,
    UserKnowledgeStats,
    DocumentStatus,
)

logger = get_logger("knowledge_service")


class KnowledgeServiceError(Exception):
    """知识库服务异常基类"""
    pass


class DocumentNotFoundError(KnowledgeServiceError):
    """文档不存在异常"""
    pass


class UserNotFoundError(KnowledgeServiceError):
    """用户不存在异常"""
    pass


class DocumentProcessingError(KnowledgeServiceError):
    """文档处理失败异常"""
    pass


class KnowledgeService:
    """
    知识库服务
    
    提供文档上传、管理、检索等业务逻辑
    """
    
    def __init__(
        self,
        ragie_client: Optional[RagieClient] = None,
        knowledge_store: Optional[KnowledgeStore] = None
    ):
        """
        初始化知识库服务
        
        Args:
            ragie_client: Ragie API 客户端（可选，默认使用全局单例）
            knowledge_store: 本地存储（可选，默认使用全局单例）
        """
        self.ragie_client = ragie_client or get_ragie_client()
        self.knowledge_store = knowledge_store or get_knowledge_store()
    
    # ==================== 文档上传 ====================
    
    async def upload_document_from_file(
        self,
        file_path: str,
        user_id: str,
        filename: str,
        metadata: Optional[Dict[str, Any]] = None,
        mode: str = "hi_res"
    ) -> Dict[str, Any]:
        """
        从文件上传文档
        
        Args:
            file_path: 临时文件路径
            user_id: 用户ID
            filename: 原始文件名
            metadata: 元数据
            mode: 处理模式
            
        Returns:
            {
                "document_id": str,
                "status": str,
                "filename": str,
                "user_id": str,
                "partition_id": str
            }
            
        Raises:
            UserNotFoundError: 用户不存在
            DocumentProcessingError: 文档处理失败
        """
        try:
            logger.info(f"📤 上传文档: user_id={user_id}, filename={filename}")
            
            # 1. 获取或创建用户的 Partition
            user = self.knowledge_store.get_or_create_user(user_id)
            partition_id = user["partition_id"]
            
            # 2. 准备元数据
            doc_metadata = metadata or {}
            doc_metadata.update({
                "user_id": user_id,
                "filename": filename,
                "uploaded_at": datetime.now().isoformat()
            })
            
            # 3. 调用 Ragie API 创建文档
            ragie_response = await self.ragie_client.create_document_from_file(
                file_path=file_path,
                partition=partition_id,
                metadata=doc_metadata,
                mode=mode
            )
            
            document_id = ragie_response.get("id")
            status = ragie_response.get("status", "pending")
            
            logger.info(f"✅ 文档已创建: document_id={document_id}, status={status}")
            
            # 4. 存储到本地 knowledge_store
            self.knowledge_store.add_document(
                user_id=user_id,
                document_id=document_id,
                filename=filename,
                status=status,
                metadata=doc_metadata
            )
            
            return {
                "document_id": document_id,
                "status": status,
                "filename": filename,
                "user_id": user_id,
                "partition_id": partition_id
            }
        
        except Exception as e:
            logger.error(f"❌ 文档上传失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"文档上传失败: {str(e)}") from e
    
    async def upload_document_from_url(
        self,
        url: str,
        user_id: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        mode: str = "hi_res"
    ) -> Dict[str, Any]:
        """
        从 URL 上传文档
        
        Args:
            url: 文档 URL
            user_id: 用户ID
            name: 文档名称（可选）
            metadata: 元数据
            mode: 处理模式
            
        Returns:
            文档信息
            
        Raises:
            DocumentProcessingError: 文档处理失败
        """
        try:
            logger.info(f"📤 从 URL 上传文档: user_id={user_id}, url={url}")
            
            # 1. 获取或创建用户的 Partition
            user = self.knowledge_store.get_or_create_user(user_id)
            partition_id = user["partition_id"]
            
            # 2. 准备元数据
            doc_metadata = metadata or {}
            doc_metadata.update({
                "user_id": user_id,
                "source_url": url,
                "uploaded_at": datetime.now().isoformat()
            })
            
            # 3. 调用 Ragie API
            ragie_response = await self.ragie_client.create_document_from_url(
                url=url,
                name=name,
                partition=partition_id,
                metadata=doc_metadata,
                mode=mode
            )
            
            document_id = ragie_response.get("id")
            status = ragie_response.get("status", "pending")
            filename = name or ragie_response.get("name", url.split("/")[-1])
            
            logger.info(f"✅ 文档已创建: document_id={document_id}, status={status}")
            
            # 4. 存储到本地
            self.knowledge_store.add_document(
                user_id=user_id,
                document_id=document_id,
                filename=filename,
                status=status,
                metadata=doc_metadata
            )
            
            return {
                "document_id": document_id,
                "status": status,
                "filename": filename,
                "user_id": user_id,
                "partition_id": partition_id
            }
        
        except Exception as e:
            logger.error(f"❌ URL 上传失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"URL 上传失败: {str(e)}") from e
    
    async def upload_document_from_text(
        self,
        text: str,
        name: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        从纯文本创建文档
        
        Args:
            text: 文本内容
            name: 文档名称
            user_id: 用户ID
            metadata: 元数据
            
        Returns:
            文档信息
            
        Raises:
            DocumentProcessingError: 文档处理失败
        """
        try:
            logger.info(f"📤 从文本创建文档: user_id={user_id}, name={name}")
            
            # 1. 获取或创建用户的 Partition
            user = self.knowledge_store.get_or_create_user(user_id)
            partition_id = user["partition_id"]
            
            # 2. 准备元数据
            doc_metadata = metadata or {}
            doc_metadata.update({
                "user_id": user_id,
                "source": "text",
                "uploaded_at": datetime.now().isoformat(),
                "content_length": len(text)
            })
            
            # 3. 调用 Ragie API
            ragie_response = await self.ragie_client.create_document_from_raw(
                text=text,
                name=name,
                partition=partition_id,
                metadata=doc_metadata
            )
            
            document_id = ragie_response.get("id")
            status = ragie_response.get("status", "pending")
            
            logger.info(f"✅ 文档已创建: document_id={document_id}, status={status}")
            
            # 4. 存储到本地
            self.knowledge_store.add_document(
                user_id=user_id,
                document_id=document_id,
                filename=name,
                status=status,
                metadata=doc_metadata
            )
            
            return {
                "document_id": document_id,
                "status": status,
                "filename": name,
                "user_id": user_id,
                "partition_id": partition_id
            }
        
        except Exception as e:
            logger.error(f"❌ 文本上传失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"文本上传失败: {str(e)}") from e
    
    async def upload_documents_batch(
        self,
        urls: List[str],
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        mode: str = "hi_res",
        max_concurrent: int = 5
    ) -> Dict[str, Any]:
        """
        批量上传文档（URL 列表）
        
        Args:
            urls: URL 列表
            user_id: 用户ID
            metadata: 公共元数据
            mode: 处理模式
            max_concurrent: 最大并发数
            
        Returns:
            {
                "total": int,
                "succeeded": int,
                "failed": int,
                "results": List[Dict]
            }
        """
        logger.info(f"📤 批量上传文档: user_id={user_id}, count={len(urls)}")
        
        # 1. 获取或创建用户的 Partition
        user = self.knowledge_store.get_or_create_user(user_id)
        partition_id = user["partition_id"]
        
        # 2. 批量上传（限制并发数）
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def upload_one(url: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    doc_metadata = metadata.copy() if metadata else {}
                    doc_metadata.update({
                        "user_id": user_id,
                        "source_url": url,
                        "uploaded_at": datetime.now().isoformat(),
                        "batch": True
                    })
                    
                    ragie_response = await self.ragie_client.create_document_from_url(
                        url=url,
                        partition=partition_id,
                        metadata=doc_metadata,
                        mode=mode
                    )
                    
                    document_id = ragie_response.get("id")
                    status = ragie_response.get("status", "pending")
                    filename = url.split("/")[-1]
                    
                    # 存储到本地
                    self.knowledge_store.add_document(
                        user_id=user_id,
                        document_id=document_id,
                        filename=filename,
                        status=status,
                        metadata=doc_metadata
                    )
                    
                    return {
                        "url": url,
                        "status": "success",
                        "document_id": document_id,
                        "filename": filename
                    }
                
                except Exception as e:
                    logger.error(f"❌ 上传失败: url={url}, error={str(e)}")
                    return {
                        "url": url,
                        "status": "failed",
                        "error": str(e)
                    }
        
        # 3. 并发执行
        tasks = [upload_one(url) for url in urls]
        results = await asyncio.gather(*tasks)
        
        # 4. 统计结果
        succeeded = sum(1 for r in results if r["status"] == "success")
        failed = len(results) - succeeded
        
        logger.info(f"✅ 批量上传完成: total={len(urls)}, succeeded={succeeded}, failed={failed}")
        
        return {
            "total": len(urls),
            "succeeded": succeeded,
            "failed": failed,
            "results": results
        }
    
    # ==================== 文档管理 ====================
    
    async def list_user_documents(
        self,
        user_id: str,
        status_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        列出用户的所有文档
        
        Args:
            user_id: 用户ID
            status_filter: 状态过滤（可选）
            limit: 每页数量
            offset: 偏移量
            
        Returns:
            {
                "user_id": str,
                "total": int,
                "documents": List[DocumentInfo]
            }
        """
        logger.info(f"📋 查询用户文档: user_id={user_id}, status={status_filter}, limit={limit}, offset={offset}")
        
        all_documents = self.knowledge_store.get_user_documents(user_id)
        
        # 状态过滤
        if status_filter:
            all_documents = [doc for doc in all_documents if doc.get("status") == status_filter]
        
        # 分页
        total = len(all_documents)
        documents = all_documents[offset:offset + limit]
        
        # 转换为 DocumentInfo 模型
        document_infos = [
            DocumentInfo(
                document_id=doc.get("document_id", ""),
                name=doc.get("filename", ""),
                status=DocumentStatus(doc.get("status", "pending")),
                user_id=user_id,
                partition_id=doc.get("partition_id", ""),
                metadata=doc.get("metadata"),
                created_at=doc.get("created_at", ""),
                updated_at=doc.get("updated_at"),
                file_size=doc.get("file_size"),
                chunk_count=doc.get("chunk_count")
            )
            for doc in documents
        ]
        
        return {
            "user_id": user_id,
            "total": total,
            "documents": document_infos
        }
    
    async def get_document_status(
        self,
        user_id: str,
        document_id: str,
        refresh: bool = False
    ) -> DocumentInfo:
        """
        获取文档状态
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            refresh: 是否从 Ragie 刷新状态
            
        Returns:
            DocumentInfo
            
        Raises:
            DocumentNotFoundError: 文档不存在
        """
        logger.info(f"🔍 查询文档状态: user_id={user_id}, document_id={document_id}, refresh={refresh}")
        
        if refresh:
            # 从 Ragie 刷新状态
            ragie_doc = await self.ragie_client.get_document(document_id)
            
            # 更新本地缓存
            new_status = ragie_doc.get("status")
            self.knowledge_store.update_document_status(user_id, document_id, new_status)
            
            logger.info(f"🔄 状态已刷新: document_id={document_id}, status={new_status}")
            
            return DocumentInfo(
                document_id=document_id,
                name=ragie_doc.get("name", ""),
                status=DocumentStatus(new_status),
                user_id=user_id,
                partition_id=ragie_doc.get("partition", ""),
                metadata=ragie_doc.get("metadata"),
                created_at=ragie_doc.get("created_at", ""),
                updated_at=ragie_doc.get("updated_at"),
                file_size=ragie_doc.get("file_size"),
                chunk_count=ragie_doc.get("chunk_count")
            )
        else:
            # 从本地缓存读取
            doc = self.knowledge_store.get_document(user_id, document_id)
            if not doc:
                raise DocumentNotFoundError(f"文档不存在: document_id={document_id}")
            
            return DocumentInfo(
                document_id=doc.get("document_id", ""),
                name=doc.get("filename", ""),
                status=DocumentStatus(doc.get("status", "pending")),
                user_id=user_id,
                partition_id=doc.get("partition_id", ""),
                metadata=doc.get("metadata"),
                created_at=doc.get("created_at", ""),
                updated_at=doc.get("updated_at"),
                file_size=doc.get("file_size"),
                chunk_count=doc.get("chunk_count")
            )
    
    async def update_document_metadata(
        self,
        user_id: str,
        document_id: str,
        metadata: Dict[str, Any]
    ) -> DocumentInfo:
        """
        更新文档元数据
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            metadata: 新的元数据
            
        Returns:
            DocumentInfo
            
        Raises:
            DocumentProcessingError: 更新失败
        """
        try:
            logger.info(f"🔄 更新文档元数据: user_id={user_id}, document_id={document_id}")
            
            # 调用 Ragie API
            ragie_doc = await self.ragie_client.patch_document_metadata(document_id, metadata)
            
            # 更新本地缓存
            self.knowledge_store.update_document_metadata(user_id, document_id, metadata)
            
            logger.info(f"✅ 元数据已更新: document_id={document_id}")
            
            return DocumentInfo(
                document_id=document_id,
                name=ragie_doc.get("name", ""),
                status=DocumentStatus(ragie_doc.get("status", "pending")),
                user_id=user_id,
                partition_id=ragie_doc.get("partition", ""),
                metadata=ragie_doc.get("metadata"),
                created_at=ragie_doc.get("created_at", ""),
                updated_at=ragie_doc.get("updated_at")
            )
        
        except Exception as e:
            logger.error(f"❌ 更新元数据失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"更新元数据失败: {str(e)}") from e
    
    async def delete_document(
        self,
        user_id: str,
        document_id: str
    ) -> None:
        """
        删除文档
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Raises:
            DocumentProcessingError: 删除失败
        """
        try:
            logger.info(f"🗑️ 删除文档: user_id={user_id}, document_id={document_id}")
            
            # 从 Ragie 删除
            await self.ragie_client.delete_document(document_id)
            
            # 从本地缓存删除
            self.knowledge_store.delete_document(user_id, document_id)
            
            logger.info(f"✅ 文档已删除: document_id={document_id}")
        
        except Exception as e:
            logger.error(f"❌ 删除文档失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"删除文档失败: {str(e)}") from e
    
    # ==================== 知识库检索 ====================
    
    async def retrieve_from_knowledge_base(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        从知识库检索相关内容
        
        Args:
            user_id: 用户ID
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            
        Returns:
            {
                "query": str,
                "user_id": str,
                "partition_id": str,
                "total": int,
                "chunks": List[ChunkInfo]
            }
            
        Raises:
            UserNotFoundError: 用户不存在
        """
        logger.info(f"🔍 知识库检索: user_id={user_id}, query={query[:50]}..., top_k={top_k}")
        
        # 1. 获取用户的 Partition
        user = self.knowledge_store.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"用户不存在: user_id={user_id}")
        
        partition_id = user["partition_id"]
        
        # 2. 调用 Ragie Retrieval API
        retrieval_result = await self.ragie_client.retrieve(
            query=query,
            partition=partition_id,
            top_k=top_k,
            filters=filters
        )
        
        scored_chunks = retrieval_result.get("scored_chunks", [])
        logger.info(f"✅ 检索完成: 找到 {len(scored_chunks)} 个相关片段")
        
        # 3. 转换为 ChunkInfo 模型
        chunks = [
            ChunkInfo(
                text=chunk.get("text", ""),
                score=chunk.get("score", 0.0),
                document_id=chunk.get("document_id", ""),
                document_name=chunk.get("document_metadata", {}).get("filename"),
                chunk_id=chunk.get("chunk_id"),
                metadata=chunk.get("metadata")
            )
            for chunk in scored_chunks
        ]
        
        return {
            "query": query,
            "user_id": user_id,
            "partition_id": partition_id,
            "total": len(chunks),
            "chunks": chunks
        }
    
    # ==================== 统计信息 ====================
    
    async def get_user_knowledge_stats(self, user_id: str) -> UserKnowledgeStats:
        """
        获取用户知识库统计信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            UserKnowledgeStats
            
        Raises:
            UserNotFoundError: 用户不存在
        """
        logger.info(f"📊 查询用户统计: user_id={user_id}")
        
        user = self.knowledge_store.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"用户不存在: user_id={user_id}")
        
        documents = self.knowledge_store.get_user_documents(user_id)
        
        # 统计各状态文档数
        total_documents = len(documents)
        ready_documents = sum(1 for doc in documents if doc.get("status") == "ready")
        pending_documents = sum(1 for doc in documents if doc.get("status") in [
            "pending", "partitioning", "partitioned", "refined",
            "chunked", "indexed", "summary_indexed", "keyword_indexed"
        ])
        failed_documents = sum(1 for doc in documents if doc.get("status") == "failed")
        
        # 统计片段数和存储大小
        total_chunks = sum(doc.get("chunk_count", 0) for doc in documents if doc.get("chunk_count"))
        storage_size = sum(doc.get("file_size", 0) for doc in documents if doc.get("file_size"))
        
        logger.info(
            f"✅ 统计完成: total={total_documents}, ready={ready_documents}, "
            f"pending={pending_documents}, failed={failed_documents}"
        )
        
        return UserKnowledgeStats(
            user_id=user_id,
            partition_id=user["partition_id"],
            total_documents=total_documents,
            ready_documents=ready_documents,
            pending_documents=pending_documents,
            failed_documents=failed_documents,
            total_chunks=total_chunks,
            storage_size=storage_size if storage_size > 0 else None
        )


# ==================== 便捷函数 ====================

_default_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """获取默认知识库服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = KnowledgeService()
    return _default_service

