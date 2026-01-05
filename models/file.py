"""文件模型"""

from datetime import datetime
from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str
    filename: str
    file_size: int
    mime_type: str
    created_at: str


class FileInfo(BaseModel):
    """文件信息"""
    file_id: str
    filename: str
    file_size: int
    mime_type: str
    created_at: str


class FileUrlResponse(BaseModel):
    """文件 URL 响应"""
    file_id: str
    file_url: str
    expires_in: int


class FileDownloadResponse(BaseModel):
    """文件下载响应"""
    file_id: str
    filename: str
    url: str


class FileListResponse(BaseModel):
    """文件列表响应"""
    user_id: str
    total: int
    files: list[FileInfo]
    has_more: bool


class FileDeleteResponse(BaseModel):
    """文件删除响应"""
    file_id: str

