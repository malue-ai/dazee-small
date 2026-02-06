"""
知识库管理路由 - Knowledge Base Management

职责：
- 处理 HTTP 请求/响应
- 参数验证和转换
- 调用 Service 层处理业务逻辑
- 统一异常处理

提供文档上传、管理、检索等功能，基于 Ragie API
接口设计参考: https://docs.ragie.ai/reference/createdocument
"""

import json as json_lib
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from logger import get_logger
from models.api import APIResponse
from models.ragie import (
    DocumentBatchUploadRequest,
    DocumentBatchUploadResponse,
    DocumentDeleteResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentMode,
    DocumentRawUploadRequest,
    DocumentStatus,
    DocumentUpdateMetadataRequest,
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentUrlUploadRequest,
    RetrievalRequest,
    RetrievalResponse,
    UserKnowledgeStats,
)
from services import (
    DocumentNotFoundError,
    DocumentProcessingError,
    UserNotFoundError,
    get_knowledge_service,
)
from utils import get_s3_uploader

# 配置日志
logger = get_logger("knowledge_router")

# 创建路由器
router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    responses={404: {"description": "Not found"}},
)

# 获取服务实例
knowledge_service = get_knowledge_service()
s3_uploader = get_s3_uploader()


# ==================== 文档上传接口 ====================


@router.post("/upload")
async def upload_document(
    files: List[UploadFile] = File(...),
    user_id: str = Form(...),
    metadata: Optional[str] = Form(None),
    mode: str = Form("hi_res"),
    background_tasks: BackgroundTasks = None,
):
    """
    上传文档到知识库（支持单个或批量文件上传）

    ## 参数
    - **files**: 文件列表（必填）- 支持单个或多个文件（最多 20 个），支持 PDF/DOCX/PPTX/MD/TXT/PNG/JPG/MP3/MP4 等
    - **user_id**: 用户ID（必填）- 用于多租户隔离
    - **metadata**: 元数据（可选）- JSON 字符串，应用于所有文件
    - **mode**: 处理模式（可选）- fast/hi_res，默认 hi_res

    ## 返回
    - 单个文件：返回 DocumentUploadResponse
    - 多个文件：返回 DocumentBatchUploadResponse

    ## 文档状态流程
    pending → partitioning → partitioned → refined → chunked → indexed → ready
    """
    try:
        # 验证文件数量
        if len(files) > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="批量上传最多支持 20 个文件"
            )

        # 解析公共元数据
        common_metadata = {}
        if metadata:
            common_metadata = json_lib.loads(metadata)

        # ========== 单个文件上传 ==========
        if len(files) == 1:
            file = files[0]
            logger.info(f"📤 收到文档上传请求: user_id={user_id}, filename={file.filename}")

            # 1. 临时保存文件
            suffix = Path(file.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                content = await file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name

            try:
                # 2. 上传到 S3
                doc_metadata = {**common_metadata}
                try:
                    logger.info(f"☁️ 上传文件到 S3: {file.filename}")
                    s3_result = await s3_uploader.upload_file(
                        file_path=tmp_file_path,
                        category="knowledge",
                        user_id=user_id,
                        filename=file.filename,
                        metadata={
                            "original_filename": file.filename,
                            "content_type": file.content_type,
                            "upload_mode": mode,
                        },
                    )

                    doc_metadata.update(
                        {
                            "s3_key": s3_result["s3_key"],
                            "s3_url": s3_result["s3_url"],
                            "file_size": s3_result["file_size"],
                            "storage": "s3",
                        }
                    )

                    logger.info(f"✅ S3 上传成功: {s3_result['s3_key']}")
                except Exception as e:
                    logger.warning(f"⚠️ S3 上传失败（继续处理）: {str(e)}")
                    doc_metadata["storage"] = "local"

                # 3. 上传到 Ragie
                result = await knowledge_service.upload_document_from_file(
                    file_path=tmp_file_path,
                    user_id=user_id,
                    filename=file.filename,
                    metadata=doc_metadata,
                    mode=mode,
                )

                # 4. 后台任务：清理临时文件
                if background_tasks:
                    background_tasks.add_task(os.unlink, tmp_file_path)

                return APIResponse(
                    code=200,
                    message="文档上传成功",
                    data=DocumentUploadResponse(
                        document_id=result["document_id"],
                        status=DocumentStatus(result["status"]),
                        filename=result["filename"],
                        user_id=result["user_id"],
                        partition_id=result["partition_id"],
                        message="文档正在处理中，状态为 'ready' 后可检索",
                    ),
                )

            finally:
                if not background_tasks and os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)

        # ========== 批量文件上传 ==========
        else:
            logger.info(f"📤 收到批量文件上传请求: user_id={user_id}, count={len(files)}")

            import asyncio
            from asyncio import Semaphore

            succeeded = 0
            failed = 0

            async def upload_single_file(file: UploadFile, index: int):
                """上传单个文件"""
                try:
                    logger.info(f"📁 [{index+1}/{len(files)}] 上传文件: {file.filename}")

                    # 1. 临时保存文件
                    suffix = Path(file.filename).suffix
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                        content = await file.read()
                        tmp_file.write(content)
                        tmp_file_path = tmp_file.name

                    try:
                        # 2. 上传到 S3
                        doc_metadata = {**common_metadata}
                        try:
                            s3_result = await s3_uploader.upload_file(
                                file_path=tmp_file_path,
                                category="knowledge",
                                user_id=user_id,
                                filename=file.filename,
                                metadata={
                                    "original_filename": file.filename,
                                    "content_type": file.content_type,
                                    "upload_mode": mode,
                                    "batch_index": index,
                                },
                            )

                            doc_metadata.update(
                                {
                                    "s3_key": s3_result["s3_key"],
                                    "s3_url": s3_result["s3_url"],
                                    "file_size": s3_result["file_size"],
                                    "storage": "s3",
                                }
                            )
                        except Exception as e:
                            logger.warning(f"⚠️ [{index+1}] S3 上传失败: {str(e)}")
                            doc_metadata["storage"] = "local"

                        # 3. 上传到 Ragie
                        result = await knowledge_service.upload_document_from_file(
                            file_path=tmp_file_path,
                            user_id=user_id,
                            filename=file.filename,
                            metadata=doc_metadata,
                            mode=mode,
                        )

                        logger.info(f"✅ [{index+1}/{len(files)}] {file.filename} 上传成功")
                        return {
                            "success": True,
                            "filename": file.filename,
                            "document_id": result["document_id"],
                            "status": result["status"],
                            "user_id": result["user_id"],
                            "partition_id": result.get("partition_id"),
                        }

                    finally:
                        if os.path.exists(tmp_file_path):
                            os.unlink(tmp_file_path)

                except Exception as e:
                    logger.error(f"❌ [{index+1}/{len(files)}] {file.filename} 上传失败: {str(e)}")
                    return {"success": False, "filename": file.filename, "error": str(e)}

            # 并发上传（控制并发数为 5）
            semaphore = Semaphore(5)

            async def upload_with_semaphore(file: UploadFile, index: int):
                async with semaphore:
                    return await upload_single_file(file, index)

            tasks = [upload_with_semaphore(file, i) for i, file in enumerate(files)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 统计结果
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                elif result.get("success"):
                    succeeded += 1
                else:
                    failed += 1

            return APIResponse(
                code=200,
                message=f"批量上传完成：成功 {succeeded}，失败 {failed}",
                data=DocumentBatchUploadResponse(
                    total=len(files),
                    succeeded=succeeded,
                    failed=failed,
                    documents=[
                        DocumentUploadResponse(
                            document_id=r.get("document_id", ""),
                            filename=r.get("filename", ""),
                            user_id=r.get("user_id", user_id),
                            status=DocumentStatus(r.get("status", "failed")),
                            partition_id=r.get("partition_id"),
                            message=r.get("error") if not r.get("success") else "上传成功",
                        )
                        for r in results
                        if not isinstance(r, Exception)
                    ],
                ),
            )

    except HTTPException:
        raise
    except DocumentProcessingError as e:
        logger.error(f"❌ 文档上传失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 文档上传失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/upload-url", response_model=APIResponse[DocumentUploadResponse])
async def upload_document_from_url(request: DocumentUrlUploadRequest):
    """
    从 URL 上传文档到知识库

    ## 参数
    - **user_id**: 用户ID（必填）
    - **url**: 文档 URL（必填）
    - **name**: 文档名称（可选）
    - **metadata**: 元数据（可选）
    - **mode**: 处理模式（可选）
    """
    try:
        logger.info(f"📤 收到 URL 上传请求: user_id={request.user_id}, url={request.url}")

        # 调用 Service 层
        result = await knowledge_service.upload_document_from_url(
            url=str(request.url),
            user_id=request.user_id,
            name=request.name,
            metadata=request.metadata,
            mode=request.mode.value,
        )

        return APIResponse(
            code=200,
            message="文档上传成功",
            data=DocumentUploadResponse(
                document_id=result["document_id"],
                status=DocumentStatus(result["status"]),
                filename=result["filename"],
                user_id=result["user_id"],
                partition_id=result["partition_id"],
                message="文档正在处理中，状态为 'ready' 后可检索",
            ),
        )

    except DocumentProcessingError as e:
        logger.error(f"❌ URL 上传失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 未知错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/upload-text", response_model=APIResponse[DocumentUploadResponse])
async def upload_document_from_text(request: DocumentRawUploadRequest):
    """
    从纯文本创建文档

    ## 参数
    - **user_id**: 用户ID（必填）
    - **text**: 文档文本内容（必填）
    - **name**: 文档名称（必填）
    - **metadata**: 元数据（可选）
    """
    try:
        logger.info(f"📤 收到文本上传请求: user_id={request.user_id}, name={request.name}")

        # 调用 Service 层
        result = await knowledge_service.upload_document_from_text(
            text=request.text, name=request.name, user_id=request.user_id, metadata=request.metadata
        )

        return APIResponse(
            code=200,
            message="文档创建成功",
            data=DocumentUploadResponse(
                document_id=result["document_id"],
                status=DocumentStatus(result["status"]),
                filename=result["filename"],
                user_id=result["user_id"],
                partition_id=result["partition_id"],
                message="文档正在处理中，状态为 'ready' 后可检索",
            ),
        )

    except DocumentProcessingError as e:
        logger.error(f"❌ 文本上传失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 未知错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/upload-batch", response_model=APIResponse[DocumentBatchUploadResponse])
async def upload_documents_batch(request: DocumentBatchUploadRequest):
    """
    批量上传文档（URL 列表）

    ## 参数
    - **user_id**: 用户ID（必填）
    - **urls**: 文档 URL 列表（必填，最多 100 个）
    - **metadata**: 公共元数据（应用于所有文档）
    - **mode**: 处理模式
    """
    try:
        logger.info(f"📤 收到批量上传请求: user_id={request.user_id}, count={len(request.urls)}")

        # 调用 Service 层
        result = await knowledge_service.upload_documents_batch(
            urls=[str(url) for url in request.urls],
            user_id=request.user_id,
            metadata=request.metadata,
            mode=request.mode.value,
        )

        return APIResponse(
            code=200,
            message=f"批量上传完成：成功 {result['succeeded']}，失败 {result['failed']}",
            data=DocumentBatchUploadResponse(
                total=result["total"],
                succeeded=result["succeeded"],
                failed=result["failed"],
                results=result["results"],
            ),
        )

    except Exception as e:
        logger.error(f"❌ 批量上传失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/import-from-files", response_model=APIResponse[DocumentBatchUploadResponse])
async def import_from_files(
    user_id: str = Form(...),
    file_ids: str = Form(...),  # JSON 字符串: ["id1", "id2", ...]
    metadata: Optional[str] = Form(None),
    mode: str = Form("hi_res"),
):
    """
    从 Files 表导入文件到知识库

    ## 参数
    - **user_id**: 用户ID（必填）
    - **file_ids**: 文件ID列表（必填）- JSON 字符串，如 ["file1", "file2"]
    - **metadata**: 公共元数据（可选）- JSON 字符串，应用于所有文件
    - **mode**: 处理模式（可选）- fast/hi_res

    ## 返回
    - 批量导入结果，包含成功/失败统计
    """
    try:
        # 解析 file_ids
        try:
            file_id_list = json_lib.loads(file_ids)
            if not isinstance(file_id_list, list) or len(file_id_list) == 0:
                raise ValueError("file_ids 必须是非空数组")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"file_ids 格式错误: {str(e)}"
            )

        if len(file_id_list) > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="批量导入最多支持 20 个文件"
            )

        logger.info(f"📤 收到从 Files 导入请求: user_id={user_id}, count={len(file_id_list)}")

        # 解析公共元数据
        common_metadata = {}
        if metadata:
            common_metadata = json_lib.loads(metadata)

        # 查询文件信息（使用 infra.database）
        import asyncio
        from asyncio import Semaphore

        succeeded = 0
        failed = 0

        async def import_single_file(file_id: str, index: int):
            """导入单个文件"""
            try:
                logger.info(f"📁 [{index+1}/{len(file_id_list)}] 导入文件: {file_id}")

                # 1. 通过 FileService 查询文件记录
                from services.file_service import FileNotFoundError as FileNotFoundErr
                from services.file_service import get_file_service

                file_service = get_file_service()

                try:
                    file_record = await file_service.get_file(file_id)
                except FileNotFoundErr:
                    raise ValueError(f"文件不存在: {file_id}")

                # 补充 s3_key 字段（storage_path 就是 S3 key）
                file_record["s3_key"] = file_record.get("storage_path")

                # 验证用户权限
                if file_record.get("user_id") != user_id:
                    raise ValueError(f"无权访问文件: {file_id}")

                # 2. 检查文件是否在 S3
                if file_record.get("storage_type") != "s3":
                    raise ValueError(f"仅支持从 S3 导入文件: {file_id}")

                s3_key = file_record.get("s3_key")
                if not s3_key:
                    raise ValueError(f"文件缺少 S3 key: {file_id}")

                # 3. 生成预签名 URL
                s3_url = await s3_uploader.get_presigned_url(s3_key, expiration=3600)

                # 4. 准备元数据
                doc_metadata = {**common_metadata}
                doc_metadata.update(
                    {
                        "imported_from_file_id": file_id,
                        "s3_key": s3_key,
                        "s3_url": s3_url,
                        "file_size": file_record.get("file_size"),
                        "storage": "s3",
                        "original_filename": file_record.get("filename"),
                    }
                )

                # 5. 通过 URL 上传到 Ragie（使用 S3 预签名 URL）
                result = await knowledge_service.upload_document_from_url(
                    url=s3_url,
                    user_id=user_id,
                    name=file_record.get("filename"),
                    metadata=doc_metadata,
                    mode=mode,
                )

                logger.info(
                    f"✅ [{index+1}/{len(file_id_list)}] {file_record.get('filename')} 导入成功"
                )
                return {
                    "success": True,
                    "filename": file_record.get("filename"),
                    "document_id": result["document_id"],
                    "status": result["status"],
                    "user_id": result["user_id"],
                    "partition_id": result.get("partition_id"),
                }

            except Exception as e:
                logger.error(
                    f"❌ [{index+1}/{len(file_id_list)}] 导入文件 {file_id} 失败: {str(e)}"
                )
                return {"success": False, "filename": file_id, "error": str(e)}

        # 并发导入（控制并发数为 5）
        semaphore = Semaphore(5)

        async def import_with_semaphore(file_id: str, index: int):
            async with semaphore:
                return await import_single_file(file_id, index)

        tasks = [import_with_semaphore(fid, i) for i, fid in enumerate(file_id_list)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        for result in results:
            if isinstance(result, Exception):
                failed += 1
            elif result.get("success"):
                succeeded += 1
            else:
                failed += 1

        return APIResponse(
            code=200,
            message=f"批量导入完成：成功 {succeeded}，失败 {failed}",
            data=DocumentBatchUploadResponse(
                total=len(file_id_list),
                succeeded=succeeded,
                failed=failed,
                documents=[
                    DocumentUploadResponse(
                        document_id=r.get("document_id", ""),
                        filename=r.get("filename", ""),
                        user_id=r.get("user_id", user_id),
                        status=DocumentStatus(r.get("status", "failed")),
                        partition_id=r.get("partition_id"),
                        message=r.get("error") if not r.get("success") else "导入成功",
                    )
                    for r in results
                    if not isinstance(r, Exception)
                ],
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 从 Files 导入失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== 文档管理接口 ====================


@router.get("/documents/{user_id}", response_model=APIResponse[DocumentListResponse])
async def list_user_documents(
    user_id: str,
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    refresh: bool = False,
):
    """
    列出用户的所有文档

    ## 参数
    - **user_id**: 用户ID（路径参数）
    - **status_filter**: 过滤状态（可选）
    - **limit**: 每页数量（默认 100）
    - **offset**: 偏移量（分页用）
    - **refresh**: 是否从 Ragie API 刷新处理中文档的状态（默认 false）

    ## 返回
    - documents: 文档列表
    - has_processing: 是否有处理中的文档（用于前端轮询判断）
    """
    try:
        logger.info(f"📋 查询用户文档: user_id={user_id}, refresh={refresh}")

        # 调用 Service 层
        result = await knowledge_service.list_user_documents(
            user_id=user_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset,
            refresh=refresh,
        )

        return APIResponse(
            code=200,
            message="success",
            data=DocumentListResponse(
                user_id=result["user_id"], total=result["total"], documents=result["documents"]
            ),
        )

    except Exception as e:
        logger.error(f"❌ 查询文档失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/documents/{user_id}/{document_id}", response_model=APIResponse[DocumentInfo])
async def get_document_status(user_id: str, document_id: str, refresh: bool = False):
    """
    获取文档状态

    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID
    - **refresh**: 是否从 Ragie 刷新状态（默认 false）
    """
    try:
        logger.info(
            f"🔍 查询文档状态: user_id={user_id}, document_id={document_id}, refresh={refresh}"
        )

        # 调用 Service 层
        doc_info = await knowledge_service.get_document_status(
            user_id=user_id, document_id=document_id, refresh=refresh
        )

        return APIResponse(code=200, message="success", data=doc_info)

    except DocumentNotFoundError as e:
        logger.error(f"❌ 文档不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 查询文档状态失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch(
    "/documents/{user_id}/{document_id}/metadata", response_model=APIResponse[DocumentInfo]
)
async def update_document_metadata(
    user_id: str, document_id: str, request: DocumentUpdateMetadataRequest
):
    """
    更新文档元数据

    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID
    - **metadata**: 新的元数据
    """
    try:
        logger.info(f"🔄 更新文档元数据: user_id={user_id}, document_id={document_id}")

        # 调用 Service 层
        doc_info = await knowledge_service.update_document_metadata(
            user_id=user_id, document_id=document_id, metadata=request.metadata
        )

        return APIResponse(code=200, message="元数据已更新", data=doc_info)

    except DocumentProcessingError as e:
        logger.error(f"❌ 更新元数据失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 未知错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/documents/{user_id}/{document_id}", response_model=APIResponse[DocumentDeleteResponse]
)
async def delete_document(user_id: str, document_id: str):
    """
    删除文档

    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID
    """
    try:
        logger.info(f"🗑️ 删除文档: user_id={user_id}, document_id={document_id}")

        # 调用 Service 层
        await knowledge_service.delete_document(user_id=user_id, document_id=document_id)

        return APIResponse(
            code=200,
            message="文档已删除",
            data=DocumentDeleteResponse(
                document_id=document_id, user_id=user_id, message="文档已成功删除"
            ),
        )

    except DocumentProcessingError as e:
        logger.error(f"❌ 删除文档失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 未知错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== 知识库检索接口 ====================


@router.post("/retrieve", response_model=APIResponse[RetrievalResponse])
async def retrieve_from_knowledge_base(request: RetrievalRequest):
    """
    从知识库检索相关内容

    ## 参数
    - **user_id**: 用户ID（必填）
    - **query**: 查询文本（必填）
    - **top_k**: 返回结果数量（可选，默认 5）
    - **filters**: 元数据过滤条件（可选）
    - **rerank**: 是否重排序（默认 true）
    """
    try:
        logger.info(f"🔍 知识库检索: user_id={request.user_id}, query={request.query[:50]}...")

        # 调用 Service 层
        result = await knowledge_service.retrieve_from_knowledge_base(
            user_id=request.user_id,
            query=request.query,
            top_k=request.top_k,
            filters=request.filters,
        )

        return APIResponse(
            code=200,
            message="success",
            data=RetrievalResponse(
                query=result["query"],
                user_id=result["user_id"],
                partition_id=result["partition_id"],
                total=result["total"],
                chunks=result["chunks"],
            ),
        )

    except UserNotFoundError as e:
        logger.error(f"❌ 用户不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 知识库检索失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== 统计接口 ====================


@router.get("/stats/{user_id}", response_model=APIResponse[UserKnowledgeStats])
async def get_user_knowledge_stats(user_id: str):
    """
    获取用户知识库统计信息

    ## 参数
    - **user_id**: 用户ID
    """
    try:
        logger.info(f"📊 查询用户统计: user_id={user_id}")

        # 调用 Service 层
        stats = await knowledge_service.get_user_knowledge_stats(user_id)

        return APIResponse(code=200, message="success", data=stats)

    except UserNotFoundError as e:
        logger.error(f"❌ 用户不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 查询统计失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== 文档内容和分块接口 ====================


@router.get("/documents/{user_id}/{document_id}/content")
async def get_document_content(user_id: str, document_id: str):
    """
    获取文档的原始内容

    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID

    ## 返回
    - 文档的原始文本内容
    """
    try:
        logger.info(f"📄 获取文档内容: user_id={user_id}, document_id={document_id}")

        content = await knowledge_service.get_document_content(user_id, document_id)

        return APIResponse(code=200, message="success", data={"content": content})

    except DocumentNotFoundError as e:
        logger.error(f"❌ 文档不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取文档内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/documents/{user_id}/{document_id}/chunks")
async def get_document_chunks(
    user_id: str,
    document_id: str,
    limit: int = Query(100, ge=1, le=100, description="每页数量（最大 100）"),
):
    """
    获取文档的所有分块

    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID
    - **limit**: 每页数量

    ## 返回
    - 文档的所有分块列表
    """
    try:
        logger.info(f"🧩 获取文档分块: user_id={user_id}, document_id={document_id}")

        result = await knowledge_service.get_document_chunks(user_id, document_id, limit=limit)

        return APIResponse(code=200, message="success", data=result)

    except DocumentNotFoundError as e:
        logger.error(f"❌ 文档不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 获取文档分块失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/documents/{user_id}/{document_id}/download")
async def download_document(
    user_id: str,
    document_id: str,
    source: str = Query("auto", description="下载源: auto(自动), s3(S3), ragie(Ragie)"),
):
    """
    下载文档的原始文件

    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID
    - **source**: 下载源
      - `auto`: 优先使用 S3，失败则使用 Ragie
      - `s3`: 仅从 S3 下载
      - `ragie`: 仅从 Ragie 下载

    ## 返回
    - 文件的二进制内容
    """
    from fastapi.responses import RedirectResponse, Response

    try:
        logger.info(f"⬇️ 下载文档: user_id={user_id}, document_id={document_id}, source={source}")

        # 获取文档信息（用于获取文件名和类型）
        doc_info = await knowledge_service.get_document_status(user_id, document_id, refresh=False)
        filename = doc_info.filename

        # 策略 1: 尝试从 S3 下载
        if source in ["auto", "s3"]:
            try:
                presigned_url = await knowledge_service.get_s3_download_url(
                    user_id, document_id, expiration=300  # 5分钟有效期
                )

                if presigned_url:
                    logger.info(f"✅ 重定向到 S3: document_id={document_id}")
                    # 重定向到 S3 预签名 URL
                    return RedirectResponse(url=presigned_url)
            except Exception as e:
                if source == "s3":
                    # 如果明确指定 S3，则抛出错误
                    raise
                logger.warning(f"⚠️ S3 下载失败，尝试 Ragie: {str(e)}")

        # 策略 2: 从 Ragie 下载
        if source in ["auto", "ragie"]:
            file_bytes = await knowledge_service.download_document_source(user_id, document_id)

            # 根据文件扩展名确定 Content-Type
            import mimetypes

            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

            logger.info(
                f"✅ 从 Ragie 下载: document_id={document_id}, size={len(file_bytes)} bytes"
            )

            return Response(
                content=file_bytes,
                media_type=content_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    except DocumentNotFoundError as e:
        logger.error(f"❌ 文档不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 下载文档失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
