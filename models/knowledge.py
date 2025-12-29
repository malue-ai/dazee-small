"""
知识库相关数据模型

基于 Ragie API 的数据结构定义
参考: https://docs.ragie.ai/reference/createdocument
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator
from datetime import datetime
from enum import Enum


# ==================== 枚举类型 ====================

class DocumentStatus(str, Enum):
    """
    文档处理状态流程
    
    pending → partitioning → partitioned → refined → 
    chunked → indexed → summary_indexed → keyword_indexed → ready → failed
    """
    PENDING = "pending"
    PARTITIONING = "partitioning"
    PARTITIONED = "partitioned"
    REFINED = "refined"
    CHUNKED = "chunked"
    INDEXED = "indexed"  # 可以开始检索（但 summary 还未完成）
    SUMMARY_INDEXED = "summary_indexed"
    KEYWORD_INDEXED = "keyword_indexed"
    READY = "ready"  # 完全就绪（包含 summary）
    FAILED = "failed"


class DocumentMode(str, Enum):
    """文档处理模式"""
    FAST = "fast"  # 快速模式
    HI_RES = "hi_res"  # 高分辨率模式（默认）


# ==================== 请求模型 ====================

class DocumentUploadRequest(BaseModel):
    """文档上传请求（文件上传）"""
    user_id: str = Field(..., description="用户ID（必填）- 用于多租户隔离")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据（可选）")
    mode: DocumentMode = Field(DocumentMode.HI_RES, description="处理模式")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_001",
                    "metadata": {"source": "upload", "tags": ["important"]},
                    "mode": "hi_res"
                }
            ]
        }
    }


class DocumentUrlUploadRequest(BaseModel):
    """文档 URL 上传请求"""
    user_id: str = Field(..., description="用户ID（必填）")
    url: HttpUrl = Field(..., description="文档 URL（必填）")
    name: Optional[str] = Field(None, description="文档名称（可选，默认从 URL 提取）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据（可选）")
    mode: DocumentMode = Field(DocumentMode.HI_RES, description="处理模式")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_001",
                    "url": "https://example.com/document.pdf",
                    "name": "产品说明书",
                    "metadata": {"source": "url"},
                    "mode": "hi_res"
                }
            ]
        }
    }


class DocumentRawUploadRequest(BaseModel):
    """文档原始文本上传请求"""
    user_id: str = Field(..., description="用户ID（必填）")
    text: str = Field(..., description="文档文本内容（必填）", min_length=1)
    name: str = Field(..., description="文档名称（必填）", min_length=1)
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据（可选）")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_001",
                    "text": "这是一段产品介绍文本...",
                    "name": "产品介绍",
                    "metadata": {"source": "manual"}
                }
            ]
        }
    }


class DocumentBatchUploadRequest(BaseModel):
    """批量文档上传请求"""
    user_id: str = Field(..., description="用户ID（必填）")
    urls: List[HttpUrl] = Field(..., description="文档 URL 列表（必填）", min_length=1)
    metadata: Optional[Dict[str, Any]] = Field(None, description="公共元数据（应用于所有文档）")
    mode: DocumentMode = Field(DocumentMode.HI_RES, description="处理模式")
    
    @field_validator('urls')
    @classmethod
    def validate_urls_count(cls, v):
        if len(v) > 100:
            raise ValueError("单次最多上传 100 个文档")
        return v
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_001",
                    "urls": [
                        "https://example.com/doc1.pdf",
                        "https://example.com/doc2.pdf"
                    ],
                    "metadata": {"batch": "batch_001"},
                    "mode": "hi_res"
                }
            ]
        }
    }


class RetrievalRequest(BaseModel):
    """知识库检索请求"""
    user_id: str = Field(..., description="用户ID（必填）")
    query: str = Field(..., description="查询文本（必填）", min_length=1)
    top_k: int = Field(5, description="返回结果数量", ge=1, le=50)
    filters: Optional[Dict[str, Any]] = Field(None, description="元数据过滤条件")
    rerank: bool = Field(True, description="是否重排序（提高相关性）")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_001",
                    "query": "AI 产品的核心功能是什么？",
                    "top_k": 5,
                    "rerank": True
                }
            ]
        }
    }


class DocumentUpdateMetadataRequest(BaseModel):
    """文档元数据更新请求"""
    metadata: Dict[str, Any] = Field(..., description="新的元数据（必填）")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "metadata": {
                        "tags": ["updated", "important"],
                        "category": "product",
                        "version": "2.0"
                    }
                }
            ]
        }
    }


# ==================== 响应模型 ====================

class DocumentInfo(BaseModel):
    """文档信息"""
    document_id: str = Field(..., description="文档ID")
    name: str = Field(..., description="文档名称")
    status: DocumentStatus = Field(..., description="文档状态")
    user_id: str = Field(..., description="所属用户ID")
    partition_id: str = Field(..., description="所属 Partition ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="文档元数据")
    created_at: str = Field(..., description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    chunk_count: Optional[int] = Field(None, description="分块数量")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "document_id": "doc_abc123",
                    "name": "产品说明书.pdf",
                    "status": "ready",
                    "user_id": "user_001",
                    "partition_id": "partition_user_001",
                    "metadata": {"source": "upload", "tags": ["important"]},
                    "created_at": "2024-12-26T10:00:00Z",
                    "file_size": 1048576,
                    "chunk_count": 42
                }
            ]
        }
    }


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    document_id: str = Field(..., description="文档ID")
    status: DocumentStatus = Field(..., description="文档状态")
    filename: str = Field(..., description="文件名")
    user_id: str = Field(..., description="用户ID")
    partition_id: str = Field(..., description="Partition ID")
    message: str = Field(..., description="提示信息")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "document_id": "doc_abc123",
                    "status": "pending",
                    "filename": "example.pdf",
                    "user_id": "user_001",
                    "partition_id": "partition_user_001",
                    "message": "文档正在处理中，状态为 'ready' 后可检索"
                }
            ]
        }
    }


class DocumentBatchUploadResponse(BaseModel):
    """批量上传响应"""
    total: int = Field(..., description="提交总数")
    succeeded: int = Field(..., description="成功数量")
    failed: int = Field(..., description="失败数量")
    results: List[Dict[str, Any]] = Field(..., description="详细结果")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "total": 5,
                    "succeeded": 4,
                    "failed": 1,
                    "results": [
                        {
                            "url": "https://example.com/doc1.pdf",
                            "status": "success",
                            "document_id": "doc_abc123"
                        },
                        {
                            "url": "https://example.com/doc2.pdf",
                            "status": "failed",
                            "error": "URL 无法访问"
                        }
                    ]
                }
            ]
        }
    }


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    user_id: str = Field(..., description="用户ID")
    total: int = Field(..., description="文档总数")
    documents: List[DocumentInfo] = Field(..., description="文档列表")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_001",
                    "total": 10,
                    "documents": [
                        {
                            "document_id": "doc_abc123",
                            "name": "产品说明书.pdf",
                            "status": "ready",
                            "user_id": "user_001",
                            "partition_id": "partition_user_001",
                            "created_at": "2024-12-26T10:00:00Z"
                        }
                    ]
                }
            ]
        }
    }


class ChunkInfo(BaseModel):
    """文档片段信息"""
    text: str = Field(..., description="片段文本")
    score: float = Field(..., description="相关性得分")
    document_id: str = Field(..., description="所属文档ID")
    document_name: Optional[str] = Field(None, description="文档名称")
    chunk_id: Optional[str] = Field(None, description="片段ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="片段元数据")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "我们的产品具有强大的AI能力...",
                    "score": 0.95,
                    "document_id": "doc_abc123",
                    "document_name": "产品说明书.pdf",
                    "metadata": {"page": 5}
                }
            ]
        }
    }


class RetrievalResponse(BaseModel):
    """检索响应"""
    query: str = Field(..., description="查询文本")
    user_id: str = Field(..., description="用户ID")
    partition_id: str = Field(..., description="Partition ID")
    total: int = Field(..., description="结果数量")
    chunks: List[ChunkInfo] = Field(..., description="相关片段列表")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "AI 产品的核心功能",
                    "user_id": "user_001",
                    "partition_id": "partition_user_001",
                    "total": 5,
                    "chunks": [
                        {
                            "text": "我们的产品具有强大的AI能力...",
                            "score": 0.95,
                            "document_id": "doc_abc123",
                            "document_name": "产品说明书.pdf"
                        }
                    ]
                }
            ]
        }
    }


class DocumentDeleteResponse(BaseModel):
    """文档删除响应"""
    document_id: str = Field(..., description="文档ID")
    user_id: str = Field(..., description="用户ID")
    message: str = Field(..., description="删除结果")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "document_id": "doc_abc123",
                    "user_id": "user_001",
                    "message": "文档已成功删除"
                }
            ]
        }
    }


# ==================== 统计模型 ====================

class UserKnowledgeStats(BaseModel):
    """用户知识库统计"""
    user_id: str = Field(..., description="用户ID")
    partition_id: str = Field(..., description="Partition ID")
    total_documents: int = Field(..., description="文档总数")
    ready_documents: int = Field(..., description="就绪文档数")
    pending_documents: int = Field(..., description="处理中文档数")
    failed_documents: int = Field(..., description="失败文档数")
    total_chunks: int = Field(..., description="总片段数")
    storage_size: Optional[int] = Field(None, description="存储大小（字节）")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user_001",
                    "partition_id": "partition_user_001",
                    "total_documents": 50,
                    "ready_documents": 45,
                    "pending_documents": 3,
                    "failed_documents": 2,
                    "total_chunks": 1250,
                    "storage_size": 52428800
                }
            ]
        }
    }

