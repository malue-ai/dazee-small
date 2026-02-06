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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger
from models.ragie import (
    ChunkInfo,
    DocumentInfo,
    DocumentStatus,
    UserKnowledgeStats,
)
from utils.knowledge_store import KnowledgeStore, get_knowledge_store
from utils.ragie_client import RagieClient, get_ragie_client
from utils.s3_uploader import get_s3_uploader

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
        knowledge_store: Optional[KnowledgeStore] = None,
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
        mode: str = "hi_res",
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

            # 1. 确保用户记录存在（用于本地存储）
            user = await self.knowledge_store.get_or_create_user(user_id)

            # 2. 准备元数据（用 metadata.user_id 区分用户，不使用 partition）
            # 注意：由于 Ragie 账户限制，我们不使用自定义 Partition，
            # 而是通过 metadata.user_id 来区分不同用户的文档
            doc_metadata = metadata or {}
            doc_metadata.update(
                {
                    "user_id": user_id,  # 关键：用 metadata 区分用户
                    "filename": filename,
                    "uploaded_at": datetime.now().isoformat(),
                }
            )

            # 3. 调用 Ragie API 创建文档（不指定 partition，使用 default）
            ragie_response = await self.ragie_client.create_document_from_file(
                file_path=file_path,
                partition=None,  # 使用 default partition
                metadata=doc_metadata,
                mode=mode,
            )

            document_id = ragie_response.get("id")
            status = ragie_response.get("status", "pending")
            partition_id = ragie_response.get("partition", "default")

            logger.info(
                f"✅ 文档已创建: document_id={document_id}, status={status}, partition={partition_id}"
            )

            # 4. 存储到本地 knowledge_store
            await self.knowledge_store.add_document(
                user_id=user_id,
                document_id=document_id,
                filename=filename,
                status=status,
                metadata=doc_metadata,
            )

            return {
                "document_id": document_id,
                "status": status,
                "filename": filename,
                "user_id": user_id,
                "partition_id": partition_id,  # 返回实际使用的 partition
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
        mode: str = "hi_res",
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

            # 1. 确保用户记录存在
            user = await self.knowledge_store.get_or_create_user(user_id)

            # 2. 准备元数据（用 metadata.user_id 区分用户）
            doc_metadata = metadata or {}
            doc_metadata.update(
                {
                    "user_id": user_id,  # 关键：用 metadata 区分用户
                    "source_url": url,
                    "uploaded_at": datetime.now().isoformat(),
                }
            )

            # 3. 调用 Ragie API（不指定 partition，使用 default）
            ragie_response = await self.ragie_client.create_document_from_url(
                url=url,
                name=name,
                partition=None,  # 使用 default partition
                metadata=doc_metadata,
                mode=mode,
            )

            document_id = ragie_response.get("id")
            status = ragie_response.get("status", "pending")
            filename = name or ragie_response.get("name", url.split("/")[-1])
            partition_id = ragie_response.get("partition", "default")

            logger.info(f"✅ 文档已创建: document_id={document_id}, status={status}")

            # 4. 存储到本地
            await self.knowledge_store.add_document(
                user_id=user_id,
                document_id=document_id,
                filename=filename,
                status=status,
                metadata=doc_metadata,
            )

            return {
                "document_id": document_id,
                "status": status,
                "filename": filename,
                "user_id": user_id,
                "partition_id": partition_id,  # 从响应中获取
            }

        except Exception as e:
            logger.error(f"❌ URL 上传失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"URL 上传失败: {str(e)}") from e

    async def upload_document_from_text(
        self, text: str, name: str, user_id: str, metadata: Optional[Dict[str, Any]] = None
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

            # 1. 确保用户记录存在
            user = await self.knowledge_store.get_or_create_user(user_id)

            # 2. 准备元数据（用 metadata.user_id 区分用户）
            doc_metadata = metadata or {}
            doc_metadata.update(
                {
                    "user_id": user_id,  # 关键：用 metadata 区分用户
                    "source": "text",
                    "uploaded_at": datetime.now().isoformat(),
                    "content_length": len(text),
                }
            )

            # 3. 调用 Ragie API（不指定 partition，使用 default）
            ragie_response = await self.ragie_client.create_document_from_raw(
                text=text,
                name=name,
                partition=None,  # 使用 default partition
                metadata=doc_metadata,
            )

            document_id = ragie_response.get("id")
            status = ragie_response.get("status", "pending")
            partition_id = ragie_response.get("partition", "default")

            logger.info(f"✅ 文档已创建: document_id={document_id}, status={status}")

            # 4. 存储到本地
            await self.knowledge_store.add_document(
                user_id=user_id,
                document_id=document_id,
                filename=name,
                status=status,
                metadata=doc_metadata,
            )

            return {
                "document_id": document_id,
                "status": status,
                "filename": name,
                "user_id": user_id,
                "partition_id": partition_id,  # 从响应中获取
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
        max_concurrent: int = 5,
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

        # 1. 确保用户记录存在
        user = await self.knowledge_store.get_or_create_user(user_id)

        # 2. 批量上传（限制并发数）
        semaphore = asyncio.Semaphore(max_concurrent)

        async def upload_one(url: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    doc_metadata = metadata.copy() if metadata else {}
                    doc_metadata.update(
                        {
                            "user_id": user_id,  # 关键：用 metadata 区分用户
                            "source_url": url,
                            "uploaded_at": datetime.now().isoformat(),
                            "batch": True,
                        }
                    )

                    ragie_response = await self.ragie_client.create_document_from_url(
                        url=url,
                        partition=None,  # 使用 default partition
                        metadata=doc_metadata,
                        mode=mode,
                    )

                    document_id = ragie_response.get("id")
                    status = ragie_response.get("status", "pending")
                    filename = url.split("/")[-1]

                    # 存储到本地
                    await self.knowledge_store.add_document(
                        user_id=user_id,
                        document_id=document_id,
                        filename=filename,
                        status=status,
                        metadata=doc_metadata,
                    )

                    return {
                        "url": url,
                        "status": "success",
                        "document_id": document_id,
                        "filename": filename,
                    }

                except Exception as e:
                    logger.error(f"❌ 上传失败: url={url}, error={str(e)}")
                    return {"url": url, "status": "failed", "error": str(e)}

        # 3. 并发执行
        tasks = [upload_one(url) for url in urls]
        results = await asyncio.gather(*tasks)

        # 4. 统计结果
        succeeded = sum(1 for r in results if r["status"] == "success")
        failed = len(results) - succeeded

        logger.info(f"✅ 批量上传完成: total={len(urls)}, succeeded={succeeded}, failed={failed}")

        return {"total": len(urls), "succeeded": succeeded, "failed": failed, "results": results}

    # ==================== 文档管理 ====================

    async def list_user_documents(
        self,
        user_id: str,
        status_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        列出用户的所有文档

        Args:
            user_id: 用户ID
            status_filter: 状态过滤（可选）
            limit: 每页数量
            offset: 偏移量
            refresh: 是否从 Ragie API 刷新处理中的文档状态

        Returns:
            {
                "user_id": str,
                "total": int,
                "documents": List[DocumentInfo],
                "has_processing": bool  # 是否有处理中的文档
            }
        """
        logger.info(
            f"📋 查询用户文档: user_id={user_id}, status={status_filter}, limit={limit}, offset={offset}, refresh={refresh}"
        )

        all_documents = await self.knowledge_store.get_user_documents(user_id)

        # 定义处理中的状态
        PROCESSING_STATUSES = {
            "pending",
            "partitioning",
            "partitioned",
            "refined",
            "chunked",
            "indexed",
            "summary_indexed",
            "keyword_indexed",
        }

        # 如果 refresh=True，从 Ragie 刷新所有处理中文档的状态
        docs_to_remove = []  # 需要删除的无效文档

        if refresh:
            processing_docs = [
                doc for doc in all_documents if doc.get("status") in PROCESSING_STATUSES
            ]

            if processing_docs:
                logger.info(f"🔄 刷新 {len(processing_docs)} 个处理中文档的状态...")

                for doc in processing_docs:
                    try:
                        doc_id = doc.get("document_id")
                        ragie_doc = await self.ragie_client.get_document(doc_id)
                        new_status = ragie_doc.get("status")

                        # 更新本地缓存
                        await self.knowledge_store.update_document_status(
                            user_id, doc_id, new_status
                        )
                        doc["status"] = new_status  # 同时更新内存中的状态

                        logger.debug(f"  ✅ {doc_id}: {doc.get('status')} → {new_status}")
                    except Exception as e:
                        error_msg = str(e)
                        # 如果 Ragie 返回 404，说明文档已不存在，标记删除
                        if "404" in error_msg or "not found" in error_msg.lower():
                            logger.warning(
                                f"  🗑️ 文档 {doc.get('document_id')} 在 Ragie 中不存在，将从本地删除"
                            )
                            docs_to_remove.append(doc.get("document_id"))
                        else:
                            logger.warning(
                                f"  ⚠️ 刷新文档 {doc.get('document_id')} 状态失败: {error_msg}"
                            )

        # 删除在 Ragie 中不存在的文档
        for doc_id in docs_to_remove:
            await self.knowledge_store.delete_document(user_id, doc_id)
            all_documents = [doc for doc in all_documents if doc.get("document_id") != doc_id]

        if docs_to_remove:
            logger.info(f"🗑️ 已清理 {len(docs_to_remove)} 个无效文档")

        # 状态过滤
        if status_filter:
            all_documents = [doc for doc in all_documents if doc.get("status") == status_filter]

        # 分页
        total = len(all_documents)
        documents = all_documents[offset : offset + limit]

        # 检查是否有处理中的文档
        has_processing = any(doc.get("status") in PROCESSING_STATUSES for doc in all_documents)

        # 转换为 DocumentInfo 模型，并为有 S3 文件的文档生成预签名 URL
        s3_uploader = get_s3_uploader()

        document_infos = []
        for doc in documents:
            metadata = doc.get("metadata") or {}

            # 如果有 s3_key，生成预签名 URL（异步调用）
            if "s3_key" in metadata:
                try:
                    # 从数据库的永久 s3_key 生成临时预签名 URL
                    presigned_url = await s3_uploader.get_presigned_url(
                        metadata["s3_key"], expires_in=3600  # 1小时有效期
                    )
                    # 将预签名 URL 添加到 metadata，前端可直接使用
                    metadata["s3_presigned_url"] = presigned_url
                    logger.debug(f"✅ 已生成 S3 预签名 URL: {doc.get('document_id')}")
                except Exception as e:
                    logger.warning(f"⚠️ 生成 S3 预签名 URL 失败: {str(e)}")

            document_infos.append(
                DocumentInfo(
                    document_id=doc.get("document_id", ""),
                    filename=doc.get(
                        "name", doc.get("filename", "未知文件")
                    ),  # Ragie 返回 name 字段
                    status=DocumentStatus(doc.get("status", "pending")),
                    user_id=user_id,
                    partition_id=doc.get("partition_id"),
                    metadata=metadata,
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                )
            )

        return {
            "user_id": user_id,
            "total": total,
            "documents": document_infos,
            "has_processing": has_processing,
        }

    async def get_document_status(
        self, user_id: str, document_id: str, refresh: bool = False
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
        logger.info(
            f"🔍 查询文档状态: user_id={user_id}, document_id={document_id}, refresh={refresh}"
        )

        if refresh:
            # 从 Ragie 刷新状态
            ragie_doc = await self.ragie_client.get_document(document_id)

            # 更新本地缓存
            new_status = ragie_doc.get("status")
            await self.knowledge_store.update_document_status(user_id, document_id, new_status)

            logger.info(f"🔄 状态已刷新: document_id={document_id}, status={new_status}")

            return DocumentInfo(
                document_id=document_id,
                filename=ragie_doc.get("name", "未知文件"),  # 修正：使用 filename
                status=DocumentStatus(new_status),
                user_id=user_id,
                partition_id=ragie_doc.get("partition"),
                metadata=ragie_doc.get("metadata"),
                created_at=ragie_doc.get("created_at"),
                updated_at=ragie_doc.get("updated_at"),
            )
        else:
            # 从本地缓存读取
            doc = await self.knowledge_store.get_document(user_id, document_id)
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
                chunk_count=doc.get("chunk_count"),
            )

    async def update_document_metadata(
        self, user_id: str, document_id: str, metadata: Dict[str, Any]
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
            await self.knowledge_store.update_document_metadata(user_id, document_id, metadata)

            logger.info(f"✅ 元数据已更新: document_id={document_id}")

            return DocumentInfo(
                document_id=document_id,
                name=ragie_doc.get("name", ""),
                status=DocumentStatus(ragie_doc.get("status", "pending")),
                user_id=user_id,
                partition_id=ragie_doc.get("partition", ""),
                metadata=ragie_doc.get("metadata"),
                created_at=ragie_doc.get("created_at", ""),
                updated_at=ragie_doc.get("updated_at"),
            )

        except Exception as e:
            logger.error(f"❌ 更新元数据失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"更新元数据失败: {str(e)}") from e

    async def delete_document(self, user_id: str, document_id: str) -> None:
        """
        删除文档（从 Ragie、S3 和本地缓存）

        Args:
            user_id: 用户ID
            document_id: 文档ID

        Raises:
            DocumentProcessingError: 删除失败
        """
        try:
            logger.info(f"🗑️ 删除文档: user_id={user_id}, document_id={document_id}")

            # 1. 获取文档信息（用于获取 S3 key）
            try:
                doc_info = await self.get_document_status(user_id, document_id, refresh=False)
                s3_key = doc_info.metadata.get("s3_key") if doc_info.metadata else None
            except Exception as e:
                logger.warning(f"⚠️ 获取文档信息失败，将跳过: {str(e)}")
                s3_key = None

            # 2. 从 Ragie 删除（允许失败，因为可能已经不存在）
            try:
                await self.ragie_client.delete_document(document_id)
                logger.info(f"✅ 已从 Ragie 删除: document_id={document_id}")
            except Exception as e:
                error_msg = str(e)
                if "404" in error_msg or "not found" in error_msg.lower():
                    logger.warning(f"⚠️ 文档在 Ragie 中不存在，跳过: document_id={document_id}")
                else:
                    logger.error(f"❌ 从 Ragie 删除失败: {str(e)}")
                    # 不抛出异常，继续删除 S3 和本地缓存

            # 3. 从 S3 删除（如果有）
            if s3_key:
                try:
                    s3_uploader = get_s3_uploader()
                    await s3_uploader.delete_file(s3_key)
                    logger.info(f"✅ 已从 S3 删除: s3_key={s3_key}")
                except Exception as e:
                    logger.warning(f"⚠️ 从 S3 删除失败: {str(e)}")

            # 4. 从本地缓存删除
            await self.knowledge_store.delete_document(user_id, document_id)
            logger.info(f"✅ 已从本地缓存删除: document_id={document_id}")

            logger.info(f"✅ 文档删除完成: document_id={document_id}")

        except Exception as e:
            logger.error(f"❌ 删除文档失败: {str(e)}", exc_info=True)
            raise DocumentProcessingError(f"删除文档失败: {str(e)}") from e

    async def get_document_content(self, user_id: str, document_id: str) -> str:
        """
        获取文档的原始内容

        Args:
            user_id: 用户ID
            document_id: 文档ID

        Returns:
            文档的原始文本内容

        Raises:
            DocumentNotFoundError: 文档不存在
        """
        try:
            logger.info(f"📄 获取文档内容: user_id={user_id}, document_id={document_id}")

            result = await self.ragie_client.get_document_content(document_id)
            content = result.get("content", "")

            logger.info(f"✅ 已获取文档内容: document_id={document_id}, length={len(content)}")
            return content

        except Exception as e:
            logger.error(f"❌ 获取文档内容失败: {str(e)}", exc_info=True)
            raise DocumentNotFoundError(f"获取文档内容失败: {str(e)}") from e

    async def get_document_chunks(
        self, user_id: str, document_id: str, limit: int = 100
    ) -> Dict[str, Any]:
        """
        获取文档的所有分块

        Args:
            user_id: 用户ID
            document_id: 文档ID
            limit: 每页数量

        Returns:
            {
                "total": int,
                "chunks": List[Dict]  # 包含 id, text, metadata 等
            }

        Raises:
            DocumentNotFoundError: 文档不存在
        """
        try:
            logger.info(f"🧩 获取文档分块: user_id={user_id}, document_id={document_id}")

            result = await self.ragie_client.get_document_chunks(document_id, limit=limit)
            chunks = result.get("chunks", [])
            total = result.get("pagination", {}).get("total_count", len(chunks))

            logger.info(f"✅ 已获取文档分块: document_id={document_id}, count={len(chunks)}")

            return {"total": total, "chunks": chunks}

        except Exception as e:
            logger.error(f"❌ 获取文档分块失败: {str(e)}", exc_info=True)
            raise DocumentNotFoundError(f"获取文档分块失败: {str(e)}") from e

    async def download_document_source(self, user_id: str, document_id: str) -> bytes:
        """
        下载文档的原始文件

        Args:
            user_id: 用户ID
            document_id: 文档ID

        Returns:
            文件的二进制内容

        Raises:
            DocumentNotFoundError: 文档不存在
        """
        try:
            logger.info(f"⬇️ 下载文档源文件: user_id={user_id}, document_id={document_id}")

            file_bytes = await self.ragie_client.get_document_source(document_id)

            logger.info(f"✅ 已下载文档: document_id={document_id}, size={len(file_bytes)} bytes")
            return file_bytes

        except Exception as e:
            logger.error(f"❌ 下载文档失败: {str(e)}", exc_info=True)
            raise DocumentNotFoundError(f"下载文档失败: {str(e)}") from e

    async def get_s3_download_url(
        self, user_id: str, document_id: str, expiration: int = 3600
    ) -> Optional[str]:
        """
        获取文档的 S3 预签名下载链接

        设计说明：
        - 数据库存储永久的 s3_key
        - 调用 S3Uploader.get_presigned_url() 动态生成临时下载链接
        - 返回的 URL 可以直接在浏览器中访问/下载

        Args:
            user_id: 用户ID
            document_id: 文档ID
            expiration: 链接有效期（秒），默认 3600 秒（1小时）

        Returns:
            预签名 URL（可直接访问的 HTTPS 链接），如果文档不在 S3 则返回 None

        Raises:
            DocumentNotFoundError: 文档不存在
        """
        from utils import get_s3_uploader

        try:
            logger.info(f"🔗 生成 S3 下载链接: user_id={user_id}, document_id={document_id}")

            # 获取文档信息
            doc_info = await self.get_document_status(user_id, document_id, refresh=False)

            # 检查 metadata 中是否有 s3_key
            if not doc_info.metadata or "s3_key" not in doc_info.metadata:
                logger.warning(f"⚠️ 文档不在 S3: document_id={document_id}")
                return None

            s3_key = doc_info.metadata["s3_key"]  # 从数据库获取永久的 s3_key

            # 生成预签名 URL（异步调用）
            s3_uploader = get_s3_uploader()
            presigned_url = await s3_uploader.get_presigned_url(s3_key, expires_in=expiration)

            logger.info(f"✅ S3 链接已生成: document_id={document_id}, expires_in={expiration}s")
            logger.debug(f"   URL 预览: {presigned_url[:100]}...")
            return presigned_url

        except Exception as e:
            logger.error(f"❌ 生成 S3 链接失败: {str(e)}", exc_info=True)
            raise DocumentNotFoundError(f"生成 S3 链接失败: {str(e)}") from e

    # ==================== 知识库检索 ====================

    async def retrieve_from_knowledge_base(
        self, user_id: str, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None
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

        # 1. 确保用户存在
        user = await self.knowledge_store.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"用户不存在: user_id={user_id}")

        # 2. 使用 metadata 过滤用户的文档（而不是 partition）
        # 合并用户提供的 filters 和 user_id 过滤
        combined_filters = filters.copy() if filters else {}
        combined_filters["user_id"] = {"$eq": user_id}  # Ragie metadata 过滤语法

        # 3. 调用 Ragie Retrieval API
        retrieval_result = await self.ragie_client.retrieve(
            query=query,
            partition=None,  # 使用 default partition
            top_k=top_k,
            filters=combined_filters,
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
                metadata=chunk.get("metadata"),
            )
            for chunk in scored_chunks
        ]

        return {
            "query": query,
            "user_id": user_id,
            "partition_id": "default",  # 使用 default partition
            "total": len(chunks),
            "chunks": chunks,
        }

    # ==================== 统计信息 ====================

    async def get_user_knowledge_stats(self, user_id: str) -> UserKnowledgeStats:
        """
        获取用户知识库统计信息

        Args:
            user_id: 用户ID

        Returns:
            UserKnowledgeStats（用户不存在时返回空的统计数据）
        """
        logger.info(f"📊 查询用户统计: user_id={user_id}")

        # 用户不存在时返回空的统计数据（与 list_user_documents 行为一致）
        user = await self.knowledge_store.get_user(user_id)
        if not user:
            logger.info(f"📊 用户 {user_id} 暂无记录，返回空统计")
            return UserKnowledgeStats(
                user_id=user_id,
                total_documents=0,
                ready_documents=0,
                processing_documents=0,
                failed_documents=0,
                total_size=0,
            )

        documents = await self.knowledge_store.get_user_documents(user_id)

        # 统计各状态文档数
        total_documents = len(documents)
        ready_documents = sum(1 for doc in documents if doc.get("status") == "ready")
        pending_documents = sum(
            1
            for doc in documents
            if doc.get("status")
            in [
                "pending",
                "partitioning",
                "partitioned",
                "refined",
                "chunked",
                "indexed",
                "summary_indexed",
                "keyword_indexed",
            ]
        )
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
            total_documents=total_documents,
            ready_documents=ready_documents,
            processing_documents=pending_documents,  # 修正字段名
            failed_documents=failed_documents,
            total_size=storage_size if storage_size > 0 else 0,  # 修正字段名，不能为 None
        )


# ==================== 便捷函数 ====================

_default_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """获取默认知识库服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = KnowledgeService()
    return _default_service
