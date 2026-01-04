"""
Ragie 文档模型 - Ragie Document Models

🎯 用途：与 Ragie API 对接（文档上传、向量化、RAG 检索）
📚 参考：https://docs.ragie.ai/

⚠️ 注意：
- 这个文件是 Ragie API 的模型（DocumentUploadRequest, DocumentInfo 等）
- 本地知识库管理模型在 knowledge_base.py（KnowledgeBase, KnowledgeFolder 等）
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ==================== 枚举类型 ====================

class DocumentStatus(str, Enum):
    """文档状态（Ragie 处理流程）"""
    PENDING = "pending"              # 等待处理
    PARTITIONING = "partitioning"    # 分割中
    PARTITIONED = "partitioned"      # 已分割
    REFINED = "refined"              # 已优化
    CHUNKED = "chunked"              # 已分块
    INDEXED = "indexed"              # 已索引
    READY = "ready"                  # 就绪
    FAILED = "failed"                # 失败


class DocumentMode(str, Enum):
    """文档处理模式"""
    FAST = "fast"        # 快速模式
    HI_RES = "hi_res"    # 高分辨率模式


# ==================== 请求模型 ====================

class DocumentUploadRequest(BaseModel):
    """文档上传请求（文件）"""
    user_id: str = Field(..., description="用户 ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    mode: DocumentMode = Field(DocumentMode.HI_RES, description="处理模式")


class DocumentUrlUploadRequest(BaseModel):
    """从 URL 上传文档"""
    user_id: str = Field(..., description="用户 ID")
    url: str = Field(..., description="文档 URL")
    name: str = Field(..., description="文档名称")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    mode: DocumentMode = Field(DocumentMode.HI_RES, description="处理模式")


class DocumentRawUploadRequest(BaseModel):
    """从原始文本上传文档"""
    user_id: str = Field(..., description="用户 ID")
    text: str = Field(..., description="文档文本内容")
    name: str = Field(..., description="文档名称")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class DocumentBatchUploadRequest(BaseModel):
    """批量上传文档"""
    user_id: str = Field(..., description="用户 ID")
    documents: List[Dict[str, Any]] = Field(..., description="文档列表")
    mode: DocumentMode = Field(DocumentMode.HI_RES, description="处理模式")


class RetrievalRequest(BaseModel):
    """知识库检索请求"""
    user_id: str = Field(..., description="用户 ID")
    query: str = Field(..., description="查询文本")
    top_k: int = Field(5, ge=1, le=20, description="返回结果数量")
    filters: Optional[Dict[str, Any]] = Field(None, description="过滤条件")
    rerank: bool = Field(True, description="是否重排序")


class DocumentUpdateMetadataRequest(BaseModel):
    """更新文档元数据"""
    metadata: Dict[str, Any] = Field(..., description="新的元数据")


# ==================== 响应模型 ====================

class DocumentInfo(BaseModel):
    """文档信息"""
    document_id: str = Field(..., description="文档 ID")
    filename: str = Field(..., description="文件名")
    user_id: str = Field(..., description="用户 ID")
    status: DocumentStatus = Field(..., description="处理状态")
    partition_id: Optional[str] = Field(None, description="分区 ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc_abc123",
                "filename": "产品手册.pdf",
                "user_id": "user_001",
                "status": "ready",
                "partition_id": "part_xyz",
                "metadata": {"category": "manual"},
                "created_at": "2024-01-01T00:00:00Z"
            }
        }


class ChunkInfo(BaseModel):
    """文档块信息"""
    chunk_id: str = Field(..., description="块 ID")
    document_id: str = Field(..., description="文档 ID")
    text: str = Field(..., description="文本内容")
    score: Optional[float] = Field(None, description="相关性分数")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    document_id: str = Field(..., description="文档 ID")
    filename: str = Field(..., description="文件名")
    user_id: str = Field(..., description="用户 ID")
    status: DocumentStatus = Field(..., description="处理状态")
    partition_id: Optional[str] = Field(None, description="分区 ID")
    message: str = Field(..., description="提示信息")
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc_abc123",
                "filename": "文档.pdf",
                "user_id": "user_001",
                "status": "pending",
                "partition_id": "part_xyz",
                "message": "文档上传成功，正在处理中"
            }
        }


class DocumentBatchUploadResponse(BaseModel):
    """批量上传响应"""
    total: int = Field(..., description="总数")
    succeeded: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    documents: List[DocumentUploadResponse] = Field(..., description="文档列表")


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    user_id: str = Field(..., description="用户 ID")
    total: int = Field(..., description="总数")
    documents: List[DocumentInfo] = Field(..., description="文档列表")


class RetrievalResponse(BaseModel):
    """检索响应"""
    query: str = Field(..., description="查询文本")
    chunks: List[ChunkInfo] = Field(..., description="检索到的文档块")
    total: int = Field(..., description="结果总数")


class DocumentDeleteResponse(BaseModel):
    """文档删除响应"""
    document_id: str = Field(..., description="文档 ID")
    deleted: bool = Field(..., description="是否删除成功")
    message: str = Field(..., description="提示信息")


class UserKnowledgeStats(BaseModel):
    """用户知识库统计"""
    user_id: str = Field(..., description="用户 ID")
    total_documents: int = Field(..., description="总文档数")
    ready_documents: int = Field(..., description="就绪文档数")
    processing_documents: int = Field(..., description="处理中文档数")
    failed_documents: int = Field(..., description="失败文档数")
    total_size: int = Field(..., description="总大小（字节）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_001",
                "total_documents": 50,
                "ready_documents": 45,
                "processing_documents": 3,
                "failed_documents": 2,
                "total_size": 104857600
            }
        }

