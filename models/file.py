"""
文件模型 - File Models

定义文件上传、管理相关的数据模型
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class FileCategory(str, Enum):
    """文件分类"""
    KNOWLEDGE = "knowledge"  # 知识库文件
    AVATAR = "avatar"  # 用户头像
    ATTACHMENT = "attachment"  # 聊天附件
    TEMP = "temp"  # 临时文件
    EXPORT = "export"  # 导出文件（PPT、文档等）
    MEDIA = "media"  # 媒体文件（图片、音视频）


class FileStatus(str, Enum):
    """文件状态"""
    UPLOADING = "uploading"  # 上传中
    UPLOADED = "uploaded"  # 已上传（未处理）
    PROCESSING = "processing"  # 处理中
    READY = "ready"  # 已就绪（可使用）
    FAILED = "failed"  # 处理失败
    DELETED = "deleted"  # 已删除（软删除）


class StorageType(str, Enum):
    """存储类型"""
    S3 = "s3"  # AWS S3
    LOCAL = "local"  # 本地存储
    OSS = "oss"  # 阿里云 OSS
    COS = "cos"  # 腾讯云 COS


class FileInfo(BaseModel):
    """
    文件信息模型
    
    完整的文件元数据，用于 API 响应
    """
    # 基础信息
    id: str = Field(..., description="文件 ID")
    user_id: str = Field(..., description="所属用户 ID")
    filename: str = Field(..., description="原始文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    content_type: str = Field(..., description="文件 MIME 类型")
    
    # 分类和状态
    category: FileCategory = Field(..., description="文件分类")
    status: FileStatus = Field(..., description="文件状态")
    
    # 存储信息
    storage_type: StorageType = Field(..., description="存储类型")
    storage_path: str = Field(..., description="存储路径/S3 Key")
    storage_url: Optional[str] = Field(None, description="存储 URL")
    bucket_name: Optional[str] = Field(None, description="S3 Bucket 名称")
    
    # 访问控制
    is_public: bool = Field(default=False, description="是否公开访问")
    access_url: Optional[str] = Field(None, description="公开访问 URL（如有）")
    presigned_url: Optional[str] = Field(None, description="预签名 URL（临时）")
    presigned_expires_at: Optional[datetime] = Field(None, description="预签名 URL 过期时间")
    
    # 关联信息
    conversation_id: Optional[str] = Field(None, description="关联的对话 ID")
    message_id: Optional[str] = Field(None, description="关联的消息 ID")
    document_id: Optional[str] = Field(None, description="关联的文档 ID（Ragie）")
    
    # 文件处理信息
    thumbnail_url: Optional[str] = Field(None, description="缩略图 URL（图片/视频）")
    duration: Optional[float] = Field(None, description="时长（音视频文件，秒）")
    width: Optional[int] = Field(None, description="宽度（图片/视频）")
    height: Optional[int] = Field(None, description="高度（图片/视频）")
    page_count: Optional[int] = Field(None, description="页数（PDF/文档）")
    
    # 元数据
    metadata: Optional[Dict[str, Any]] = Field(None, description="自定义元数据")
    tags: Optional[list[str]] = Field(None, description="文件标签")
    
    # 时间戳
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    deleted_at: Optional[datetime] = Field(None, description="删除时间（软删除）")
    
    # 统计信息
    download_count: int = Field(default=0, description="下载次数")
    view_count: int = Field(default=0, description="查看次数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "file_abc123",
                "user_id": "user_001",
                "filename": "产品文档.pdf",
                "file_size": 1048576,
                "content_type": "application/pdf",
                "category": "knowledge",
                "status": "ready",
                "storage_type": "s3",
                "storage_path": "knowledge/user_001/20231224/doc_abc123.pdf",
                "storage_url": "s3://bucket/knowledge/user_001/20231224/doc_abc123.pdf",
                "is_public": False,
                "page_count": 10,
                "created_at": "2023-12-24T12:00:00Z"
            }
        }


class FileUploadRequest(BaseModel):
    """文件上传请求"""
    user_id: str = Field(..., description="用户 ID")
    category: FileCategory = Field(FileCategory.TEMP, description="文件分类")
    conversation_id: Optional[str] = Field(None, description="关联的对话 ID")
    message_id: Optional[str] = Field(None, description="关联的消息 ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="自定义元数据")
    tags: Optional[list[str]] = Field(None, description="文件标签")
    is_public: bool = Field(False, description="是否公开")


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str = Field(..., description="文件 ID")
    filename: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小")
    storage_url: str = Field(..., description="存储 URL")
    access_url: Optional[str] = Field(None, description="访问 URL")
    status: FileStatus = Field(..., description="文件状态")
    message: str = Field(..., description="提示信息")


class FileListRequest(BaseModel):
    """文件列表查询请求"""
    user_id: str = Field(..., description="用户 ID")
    category: Optional[FileCategory] = Field(None, description="按分类过滤")
    status: Optional[FileStatus] = Field(None, description="按状态过滤")
    conversation_id: Optional[str] = Field(None, description="按对话过滤")
    tags: Optional[list[str]] = Field(None, description="按标签过滤")
    keyword: Optional[str] = Field(None, description="关键词搜索（文件名）")
    limit: int = Field(20, ge=1, le=100, description="每页数量")
    offset: int = Field(0, ge=0, description="偏移量")
    order_by: str = Field("created_at", description="排序字段")
    order_desc: bool = Field(True, description="是否降序")


class FileListResponse(BaseModel):
    """文件列表响应"""
    user_id: str
    total: int = Field(..., description="总数")
    files: list[FileInfo] = Field(..., description="文件列表")
    has_more: bool = Field(..., description="是否还有更多")


class FileUpdateRequest(BaseModel):
    """文件更新请求"""
    filename: Optional[str] = Field(None, description="新文件名")
    tags: Optional[list[str]] = Field(None, description="文件标签")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    is_public: Optional[bool] = Field(None, description="是否公开")


class FileStatsResponse(BaseModel):
    """用户文件统计"""
    user_id: str
    total_files: int = Field(..., description="文件总数")
    total_size: int = Field(..., description="总存储大小（字节）")
    by_category: Dict[str, int] = Field(..., description="按分类统计")
    by_status: Dict[str, int] = Field(..., description="按状态统计")
    recent_uploads: list[FileInfo] = Field(..., description="最近上传（最多5个）")

