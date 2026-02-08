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

# Usage 模型（计费响应）
from .usage import UsageResponse, UsageSummary

# LLM 配置与模型管理
from .llm import (
    LLMConfig,
    ModelRegisterRequest,
    ModelActivateRequest,
    ModelCapabilitiesRequest,
    ModelPricingRequest,
    ModelCapabilitiesResponse,
    ModelPricingResponse,
    ModelDetailResponse,
    SupportedModelResponse,
    ActivatedModelResponse,
    ProviderInfoResponse,
    ProviderDetailResponse,
)

# Skill 模型
from .skill import (
    SkillCreateRequest,
    SkillUpdateRequest,
    SkillSummary,
    SkillDetail,
    SkillListResponse,
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
    # Usage 模型
    "UsageResponse",
    "UsageSummary",
    # LLM 配置与模型管理
    "LLMConfig",
    "ModelRegisterRequest",
    "ModelActivateRequest",
    "ModelCapabilitiesRequest",
    "ModelPricingRequest",
    "ModelCapabilitiesResponse",
    "ModelPricingResponse",
    "ModelDetailResponse",
    "SupportedModelResponse",
    "ActivatedModelResponse",
    "ProviderInfoResponse",
    "ProviderDetailResponse",
    # Skill 模型
    "SkillCreateRequest",
    "SkillUpdateRequest",
    "SkillSummary",
    "SkillDetail",
    "SkillListResponse",
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
    "AgentSummary",
    "AgentDetail",
    "AgentListResponse",
]
