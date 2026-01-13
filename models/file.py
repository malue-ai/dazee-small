"""文件模型"""

from typing import Optional
from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str = Field(..., description="文件 ID")
    file_name: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    file_type: str = Field(..., description="文件类型（MIME）")
    file_url: Optional[str] = Field(None, description="文件访问 URL")
    created_at: str = Field(..., description="创建时间")


class FileInfo(BaseModel):
    """文件信息"""
    file_id: str = Field(..., description="文件 ID")
    file_name: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    file_type: str = Field(..., description="文件类型（MIME）")
    file_url: Optional[str] = Field(None, description="文件访问 URL")
    created_at: Optional[str] = Field(None, description="创建时间")


class FileUrlResponse(BaseModel):
    """文件 URL 响应"""
    file_id: str = Field(..., description="文件 ID")
    file_url: str = Field(..., description="访问 URL")
    expires_in: int = Field(..., description="过期时间（秒）")


class FileDownloadResponse(BaseModel):
    """文件下载响应"""
    file_id: str = Field(..., description="文件 ID")
    file_name: str = Field(..., description="文件名")
    file_url: str = Field(..., description="下载 URL")


class FileListResponse(BaseModel):
    """文件列表响应"""
    user_id: str = Field(..., description="用户 ID")
    total: int = Field(..., description="总数")
    files: list[FileInfo] = Field(..., description="文件列表")
    has_more: bool = Field(..., description="是否有更多")


class FileDeleteResponse(BaseModel):
    """文件删除响应"""
    file_id: str = Field(..., description="文件 ID")
    success: bool = Field(True, description="是否成功")
