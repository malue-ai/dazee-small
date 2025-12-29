"""
数据模型包

导出所有 Pydantic 模型
"""

from .chat import ChatRequest, ChatResponse, StreamEvent, SessionInfo, RefineRequest
from .api import APIResponse
from .database import User, Conversation, Message
from .knowledge import (
    # 请求模型
    DocumentUploadRequest,
    DocumentUrlUploadRequest,
    DocumentRawUploadRequest,
    DocumentBatchUploadRequest,
    RetrievalRequest,
    DocumentUpdateMetadataRequest,
    # 响应模型
    DocumentUploadResponse,
    DocumentBatchUploadResponse,
    DocumentListResponse,
    RetrievalResponse,
    DocumentDeleteResponse,
    DocumentInfo,
    ChunkInfo,
    UserKnowledgeStats,
    # 枚举
    DocumentStatus,
    DocumentMode
)

__all__ = [
    # Chat 模型
    "ChatRequest",
    "ChatResponse",
    "StreamEvent",
    "SessionInfo",
    "RefineRequest",
    # API 模型
    "APIResponse",
    # Database 模型
    "User",
    "Conversation",
    "Message",
    # Knowledge 请求模型
    "DocumentUploadRequest",
    "DocumentUrlUploadRequest",
    "DocumentRawUploadRequest",
    "DocumentBatchUploadRequest",
    "RetrievalRequest",
    "DocumentUpdateMetadataRequest",
    # Knowledge 响应模型
    "DocumentUploadResponse",
    "DocumentBatchUploadResponse",
    "DocumentListResponse",
    "RetrievalResponse",
    "DocumentDeleteResponse",
    "DocumentInfo",
    "ChunkInfo",
    "UserKnowledgeStats",
    # Knowledge 枚举
    "DocumentStatus",
    "DocumentMode",
]
