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
from .database import Conversation, Message

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
