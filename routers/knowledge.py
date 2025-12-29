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

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from pathlib import Path
import tempfile
import os
import json as json_lib

from logger import get_logger
from models.api import APIResponse
from models.knowledge import (
    DocumentUploadRequest,
    DocumentUrlUploadRequest,
    DocumentRawUploadRequest,
    DocumentBatchUploadRequest,
    RetrievalRequest,
    DocumentUpdateMetadataRequest,
    DocumentUploadResponse,
    DocumentBatchUploadResponse,
    DocumentListResponse,
    RetrievalResponse,
    DocumentDeleteResponse,
    DocumentInfo,
    UserKnowledgeStats,
    DocumentStatus,
    DocumentMode
)
from services import (
    get_knowledge_service,
    DocumentNotFoundError,
    UserNotFoundError,
    DocumentProcessingError,
)

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


# ==================== 文档上传接口 ====================

@router.post("/upload", response_model=APIResponse[DocumentUploadResponse])
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    metadata: Optional[str] = Form(None),
    mode: str = Form("hi_res"),
    background_tasks: BackgroundTasks = None
):
    """
    上传文档到知识库（文件上传）
    
    ## 参数
    - **file**: 文件（必填）- 支持 PDF/DOCX/PPTX/MD/TXT/PNG/JPG/MP3/MP4 等
    - **user_id**: 用户ID（必填）- 用于多租户隔离
    - **metadata**: 元数据（可选）- JSON 字符串
    - **mode**: 处理模式（可选）- fast/hi_res，默认 hi_res
    
    ## 文档状态流程
    pending → partitioning → partitioned → refined → chunked → indexed → ready
    """
    try:
        logger.info(f"📤 收到文档上传请求: user_id={user_id}, filename={file.filename}")
        
        # 1. 临时保存上传的文件
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        try:
            # 2. 解析元数据
            doc_metadata = {}
            if metadata:
                doc_metadata = json_lib.loads(metadata)
            
            # 3. 调用 Service 层处理业务逻辑
            result = await knowledge_service.upload_document_from_file(
                file_path=tmp_file_path,
                user_id=user_id,
                filename=file.filename,
                metadata=doc_metadata,
                mode=mode
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
                    message="文档正在处理中，状态为 'ready' 后可检索"
                )
            )
        
        finally:
            # 如果没有后台任务，直接删除
            if not background_tasks and os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    except DocumentProcessingError as e:
        logger.error(f"❌ 文档上传失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 未知错误: {str(e)}", exc_info=True)
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
            mode=request.mode.value
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
                message="文档正在处理中，状态为 'ready' 后可检索"
            )
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
            text=request.text,
            name=request.name,
            user_id=request.user_id,
            metadata=request.metadata
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
                message="文档正在处理中，状态为 'ready' 后可检索"
            )
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
            mode=request.mode.value
        )
        
        return APIResponse(
            code=200,
            message=f"批量上传完成：成功 {result['succeeded']}，失败 {result['failed']}",
            data=DocumentBatchUploadResponse(
                total=result["total"],
                succeeded=result["succeeded"],
                failed=result["failed"],
                results=result["results"]
            )
        )
    
    except Exception as e:
        logger.error(f"❌ 批量上传失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== 文档管理接口 ====================

@router.get("/documents/{user_id}", response_model=APIResponse[DocumentListResponse])
async def list_user_documents(
    user_id: str,
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    列出用户的所有文档
    
    ## 参数
    - **user_id**: 用户ID（路径参数）
    - **status_filter**: 过滤状态（可选）
    - **limit**: 每页数量（默认 100）
    - **offset**: 偏移量（分页用）
    """
    try:
        logger.info(f"📋 查询用户文档: user_id={user_id}")
        
        # 调用 Service 层
        result = await knowledge_service.list_user_documents(
            user_id=user_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        
        return APIResponse(
            code=200,
            message="success",
            data=DocumentListResponse(
                user_id=result["user_id"],
                total=result["total"],
                documents=result["documents"]
            )
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
        logger.info(f"🔍 查询文档状态: user_id={user_id}, document_id={document_id}, refresh={refresh}")
        
        # 调用 Service 层
        doc_info = await knowledge_service.get_document_status(
            user_id=user_id,
            document_id=document_id,
            refresh=refresh
        )
        
        return APIResponse(
            code=200,
            message="success",
            data=doc_info
        )
    
    except DocumentNotFoundError as e:
        logger.error(f"❌ 文档不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 查询文档状态失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch("/documents/{user_id}/{document_id}/metadata", response_model=APIResponse[DocumentInfo])
async def update_document_metadata(
    user_id: str,
    document_id: str,
    request: DocumentUpdateMetadataRequest
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
            user_id=user_id,
            document_id=document_id,
            metadata=request.metadata
        )
        
        return APIResponse(
            code=200,
            message="元数据已更新",
            data=doc_info
        )
    
    except DocumentProcessingError as e:
        logger.error(f"❌ 更新元数据失败: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 未知错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/documents/{user_id}/{document_id}", response_model=APIResponse[DocumentDeleteResponse])
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
        await knowledge_service.delete_document(
            user_id=user_id,
            document_id=document_id
        )
        
        return APIResponse(
            code=200,
            message="文档已删除",
            data=DocumentDeleteResponse(
                document_id=document_id,
                user_id=user_id,
                message="文档已成功删除"
            )
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
            filters=request.filters
        )
        
        return APIResponse(
            code=200,
            message="success",
            data=RetrievalResponse(
                query=result["query"],
                user_id=result["user_id"],
                partition_id=result["partition_id"],
                total=result["total"],
                chunks=result["chunks"]
            )
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
        
        return APIResponse(
            code=200,
            message="success",
            data=stats
        )
    
    except UserNotFoundError as e:
        logger.error(f"❌ 用户不存在: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 查询统计失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
