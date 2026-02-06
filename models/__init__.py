"""
数据模型包

导出所有 Pydantic 模型
"""

from .chat import (
    # Content Block 模型
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    ImageBlock,
    ContentBlock,
    MessageContent,
    # Chat 模型
    ChatRequest,
    ChatResponse,
    StreamEvent,
    SessionInfo,
    RefineRequest,
)
from .api import APIResponse
from .database import User, Conversation, Message

# 工具模型
from .tool import (
    # 枚举
    ToolType,
    ReturnMode,
    InteractionMode,
    ToolStatus,
    ExecutionStatus,
    # 工具定义
    ToolParameter,
    ToolInputSchema,
    MCPConfig,
    ToolDefinition,
    # 工具执行
    ToolInvocation,
    ToolResultChunk,
    ToolResult,
    # 工具注册
    ToolRegistration,
    MCPServerRegistration,
    ToolRegistrationResponse,
    MCPServerRegistrationResponse,
    # 工具查询
    ToolListQuery,
    ToolListResponse,
    ToolDetailResponse,
)

# Ragie 文档模型（用于文档上传和检索）
from .ragie import (
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

# 知识库系统模型（用于知识库管理）
from .knowledge import (
    # 枚举
    KBVisibility,
    KBPermission,
    MemberRole,
    ShareType,
    # 知识库模型
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    # 文件夹模型
    KnowledgeFolder,
    KnowledgeFolderCreate,
    KnowledgeFolderUpdate,
    # 文档模型
    KnowledgeDocument,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    # 分享模型
    KnowledgeShare,
    KnowledgeShareCreate,
    # 成员模型
    KnowledgeMember,
    KnowledgeMemberInvite,
    # 响应模型
    KnowledgeBaseListResponse,
    KnowledgeFolderTreeNode,
    KnowledgeBaseDetailResponse,
)

# Usage 模型（计费响应）
from .usage import UsageResponse, UsageSummary

# LLM 配置
from .llm import LLMConfig

# MCP 工具配置
from .mcp import MCPToolConfig, MCPToolDetail

# Skill 模型
from .skill import (
    SkillStatus,
    SkillCreateRequest,
    SkillUpdateRequest,
    SkillSummary,
    SkillDetail,
    SkillListResponse,
    SkillSyncResponse,
    SkillInstallRequest,
    SkillUninstallRequest,
    SkillToggleRequest,
    SkillUpdateContentRequest,
)

# Agent 模型
from .agent import (
    AgentStatus,
    APIAuthConfig,
    RESTAPIConfig,
    APIDetail,
    MemoryConfig,
    AgentCreateRequest,
    AgentUpdateRequest,
    AgentSummary,
    AgentDetail,
    AgentListResponse,
)

__all__ = [
    # Content Block 模型
    "TextBlock",
    "ThinkingBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "ImageBlock",
    "ContentBlock",
    "MessageContent",
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
    # Tool 模型 - 枚举
    "ToolType",
    "ReturnMode",
    "InteractionMode",
    "ToolStatus",
    "ExecutionStatus",
    # Tool 模型 - 工具定义
    "ToolParameter",
    "ToolInputSchema",
    "MCPConfig",
    "ToolDefinition",
    # Tool 模型 - 工具执行
    "ToolInvocation",
    "ToolResultChunk",
    "ToolResult",
    # Tool 模型 - 工具注册
    "ToolRegistration",
    "MCPServerRegistration",
    "ToolRegistrationResponse",
    "MCPServerRegistrationResponse",
    # Tool 模型 - 工具查询
    "ToolListQuery",
    "ToolListResponse",
    "ToolDetailResponse",
    # Ragie 文档模型 - 请求
    "DocumentUploadRequest",
    "DocumentUrlUploadRequest",
    "DocumentRawUploadRequest",
    "DocumentBatchUploadRequest",
    "RetrievalRequest",
    "DocumentUpdateMetadataRequest",
    # Ragie 文档模型 - 响应
    "DocumentUploadResponse",
    "DocumentBatchUploadResponse",
    "DocumentListResponse",
    "RetrievalResponse",
    "DocumentDeleteResponse",
    "DocumentInfo",
    "ChunkInfo",
    "UserKnowledgeStats",
    # Ragie 文档模型 - 枚举
    "DocumentStatus",
    "DocumentMode",
    # 知识库系统模型 - 枚举
    "KBVisibility",
    "KBPermission",
    "MemberRole",
    "ShareType",
    # 知识库系统模型 - 知识库
    "KnowledgeBase",
    "KnowledgeBaseCreate",
    "KnowledgeBaseUpdate",
    "KnowledgeBaseListResponse",
    # 知识库系统模型 - 文件夹
    "KnowledgeFolder",
    "KnowledgeFolderCreate",
    "KnowledgeFolderUpdate",
    "KnowledgeFolderTreeNode",
    # 知识库系统模型 - 文档
    "KnowledgeDocument",
    "KnowledgeDocumentCreate",
    "KnowledgeDocumentUpdate",
    # 知识库系统模型 - 分享
    "KnowledgeShare",
    "KnowledgeShareCreate",
    # 知识库系统模型 - 成员
    "KnowledgeMember",
    "KnowledgeMemberInvite",
    # 知识库系统模型 - 详情
    "KnowledgeBaseDetailResponse",
    # Usage 模型
    "UsageResponse",
    "UsageSummary",
    # LLM 配置
    "LLMConfig",
    # MCP 工具配置
    "MCPToolConfig",
    "MCPToolDetail",
    # Skill 模型
    "SkillStatus",
    "SkillCreateRequest",
    "SkillUpdateRequest",
    "SkillSummary",
    "SkillDetail",
    "SkillListResponse",
    "SkillSyncResponse",
    "SkillInstallRequest",
    "SkillUninstallRequest",
    "SkillToggleRequest",
    "SkillUpdateContentRequest",
    # Agent 模型
    "AgentStatus",
    "APIAuthConfig",
    "RESTAPIConfig",
    "APIDetail",
    "MemoryConfig",
    "AgentCreateRequest",
    "AgentUpdateRequest",
    "AgentSummary",
    "AgentDetail",
    "AgentListResponse",
]
