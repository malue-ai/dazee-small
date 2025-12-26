"""
知识库管理路由 - Knowledge Base Management

⚠️ **临时测试接口** ⚠️
------------------------------------------------------------
这些接口仅用于验证 Ragie 集成和测试"上传 → 检索"链路。
后续这些上传逻辑会移到后端自动处理，这些手动上传接口可能会被移除。

提供文档上传、管理、检索等功能，基于 Ragie API

接口设计参考: https://docs.ragie.ai/reference/createdocument
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import tempfile
import os

from logger import get_logger
from models.api import APIResponse
from utils.ragie_client import get_ragie_client
from utils.knowledge_store import get_knowledge_store

# 配置日志
logger = get_logger("knowledge")

# 创建路由器
router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    responses={404: {"description": "Not found"}},
)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    metadata: Optional[str] = Form(None),
    mode: str = Form("hi_res"),
    background_tasks: BackgroundTasks = None
):
    """
    上传文档到知识库
    
    ## 参数
    - **file**: 文件（必填）- 支持 PDF/DOCX/PPTX/MD/TXT/PNG/JPG/MP3/MP4 等
    - **user_id**: 用户ID（必填）- 用于多租户隔离
    - **metadata**: 元数据（可选）- JSON 字符串，如 '{"source": "upload", "tags": ["important"]}'
    - **mode**: 处理模式（可选）- fast/hi_res，默认 hi_res
    
    ## 返回
    ```json
    {
        "code": 200,
        "message": "success",
        "data": {
            "document_id": "doc_xxx",
            "status": "pending",
            "filename": "example.pdf",
            "user_id": "user_001",
            "partition_id": "partition_xxx"
        }
    }
    ```
    
    ## 文档状态流程
    pending → partitioning → partitioned → refined → chunked → indexed → ready
    
    - **indexed**: 可以开始检索（但 summary 还未完成）
    - **ready**: 完全就绪（包含 summary）
    
    Ref: https://docs.ragie.ai/reference/createdocument
    """
    try:
        logger.info(f"📤 收到文档上传请求: user_id={user_id}, filename={file.filename}")
        
        # 1. 获取或创建用户的 Partition
        store = get_knowledge_store()
        user = store.get_or_create_user(user_id)
        partition_id = user["partition_id"]
        
        logger.info(f"📦 用户 Partition: partition_id={partition_id}")
        
        # 2. 临时保存上传的文件
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        logger.info(f"💾 文件已保存到临时路径: {tmp_file_path}")
        
        try:
            # 3. 解析元数据
            doc_metadata = {}
            if metadata:
                import json
                doc_metadata = json.loads(metadata)
            
            # 添加系统元数据
            doc_metadata.update({
                "user_id": user_id,
                "filename": file.filename,
                "uploaded_at": datetime.now().isoformat()
            })
            
            # 4. 调用 Ragie API 创建文档
            client = get_ragie_client()
            ragie_response = await client.create_document_from_file(
                file_path=tmp_file_path,
                partition=partition_id,
                metadata=doc_metadata,
                mode=mode
            )
            
            document_id = ragie_response.get("id")
            status = ragie_response.get("status", "pending")
            
            logger.info(f"✅ 文档已创建: document_id={document_id}, status={status}")
            
            # 5. 存储到本地 knowledge_store
            store.add_document(
                user_id=user_id,
                document_id=document_id,
                filename=file.filename,
                status=status,
                metadata=doc_metadata
            )
            
            # 6. 后台任务：清理临时文件
            if background_tasks:
                background_tasks.add_task(os.unlink, tmp_file_path)
            
            return APIResponse(
                code=200,
                message="文档上传成功",
                data={
                    "document_id": document_id,
                    "status": status,
                    "filename": file.filename,
                    "user_id": user_id,
                    "partition_id": partition_id,
                    "message": "文档正在处理中，状态为 'ready' 后可检索"
                }
            )
        
        finally:
            # 如果没有后台任务，直接删除
            if not background_tasks and os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    except Exception as e:
        logger.error(f"❌ 文档上传失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{user_id}")
async def list_user_documents(user_id: str, status: Optional[str] = None):
    """
    列出用户的所有文档
    
    ## 参数
    - **user_id**: 用户ID（路径参数）
    - **status**: 过滤状态（可选）- pending/indexed/ready/failed
    
    ## 返回
    用户的文档列表
    """
    try:
        logger.info(f"📋 查询用户文档: user_id={user_id}, status_filter={status}")
        
        store = get_knowledge_store()
        documents = store.get_user_documents(user_id)
        
        # 状态过滤
        if status:
            documents = [doc for doc in documents if doc.get("status") == status]
        
        return APIResponse(
            code=200,
            message="success",
            data={
                "user_id": user_id,
                "total": len(documents),
                "documents": documents
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 查询文档失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{user_id}/{document_id}")
async def get_document_status(user_id: str, document_id: str, refresh: bool = False):
    """
    获取文档状态
    
    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID
    - **refresh**: 是否从 Ragie 刷新状态（默认 false，从本地缓存读取）
    
    ## 返回
    文档详情和当前状态
    """
    try:
        logger.info(f"🔍 查询文档状态: user_id={user_id}, document_id={document_id}, refresh={refresh}")
        
        store = get_knowledge_store()
        
        if refresh:
            # 从 Ragie 刷新状态
            client = get_ragie_client()
            ragie_doc = await client.get_document(document_id)
            
            # 更新本地缓存
            new_status = ragie_doc.get("status")
            store.update_document_status(user_id, document_id, new_status)
            
            logger.info(f"🔄 状态已刷新: document_id={document_id}, status={new_status}")
            
            return APIResponse(
                code=200,
                message="success",
                data=ragie_doc
            )
        else:
            # 从本地缓存读取
            doc = store.get_document(user_id, document_id)
            if not doc:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            return APIResponse(
                code=200,
                message="success",
                data=doc
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 查询文档状态失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{user_id}/{document_id}")
async def delete_document(user_id: str, document_id: str):
    """
    删除文档
    
    ## 参数
    - **user_id**: 用户ID
    - **document_id**: 文档ID
    
    ## 返回
    删除结果
    """
    try:
        logger.info(f"🗑️ 删除文档: user_id={user_id}, document_id={document_id}")
        
        # 1. 从 Ragie 删除
        client = get_ragie_client()
        await client.delete_document(document_id)
        
        # 2. 从本地缓存删除
        store = get_knowledge_store()
        store.delete_document(user_id, document_id)
        
        logger.info(f"✅ 文档已删除: document_id={document_id}")
        
        return APIResponse(
            code=200,
            message="文档已删除",
            data={
                "document_id": document_id,
                "user_id": user_id
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 删除文档失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieve")
async def retrieve_from_knowledge_base(
    user_id: str = Form(...),
    query: str = Form(...),
    top_k: int = Form(5),
):
    """
    从知识库检索相关内容
    
    ## 参数
    - **user_id**: 用户ID（必填）
    - **query**: 查询文本（必填）
    - **top_k**: 返回结果数量（可选，默认 5）
    
    ## 返回
    相关文档片段列表
    
    Ref: https://docs.ragie.ai/reference/retrieve
    """
    try:
        logger.info(f"🔍 知识库检索: user_id={user_id}, query={query[:50]}..., top_k={top_k}")
        
        # 1. 获取用户的 Partition
        store = get_knowledge_store()
        user = store.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        partition_id = user["partition_id"]
        
        # 2. 构建过滤条件（如果需要过滤特定对话）
        filters = None
        # 3. 调用 Ragie Retrieval API
        client = get_ragie_client()
        retrieval_result = await client.retrieve(
            query=query,
            partition=partition_id,
            top_k=top_k,
            filters=filters
        )
        
        scored_chunks = retrieval_result.get("scored_chunks", [])
        logger.info(f"✅ 检索完成: 找到 {len(scored_chunks)} 个相关片段")
        
        return APIResponse(
            code=200,
            message="success",
            data={
                "query": query,
                "user_id": user_id,
                "partition_id": partition_id,
                "total": len(scored_chunks),
                "chunks": scored_chunks
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 知识库检索失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

