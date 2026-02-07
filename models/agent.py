"""
Agent Pydantic 模型

用于 Agent API 请求/响应的数据模型
"""

from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

# 从拆分的模块导入
from .llm import LLMConfig
from .mcp import MCPToolConfig, MCPToolDetail
from .skill import SkillStatus


# ============================================================
# 枚举类型
# ============================================================

class AgentStatus(str, Enum):
    """Agent 状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


# ============================================================
# REST API 配置
# ============================================================

class APIAuthConfig(BaseModel):
    """API 认证配置"""
    type: str = Field("none", description="认证类型: none / bearer / api_key / basic")
    header: str = Field("Authorization", description="认证头名称")
    env: Optional[str] = Field(None, description="认证密钥的环境变量名")


class RESTAPIConfig(BaseModel):
    """REST API 配置"""
    name: str = Field(..., description="API 名称")
    base_url: str = Field(..., description="API 基础 URL")
    auth: APIAuthConfig = Field(default_factory=APIAuthConfig, description="认证配置")
    doc: Optional[str] = Field(None, description="API 文档名称（对应 api_desc/{doc}.md）")
    capability: Optional[str] = Field(None, description="API 能力分类")
    description: str = Field("", description="API 描述")


class APIDetail(BaseModel):
    """API 详情（用于 AgentDetail 响应）"""
    name: str = Field(..., description="API 名称")
    base_url: str = Field("", description="API 基础 URL")
    auth_type: str = Field("none", description="认证类型")
    auth_env: Optional[str] = Field(None, description="认证密钥的环境变量名")
    doc: Optional[str] = Field(None, description="API 文档名称")
    capability: Optional[str] = Field(None, description="API 能力分类")
    description: str = Field("", description="API 描述")


# ============================================================
# 记忆配置
# ============================================================

class MemoryConfig(BaseModel):
    """记忆配置"""
    mem0_enabled: bool = Field(True, description="是否启用 Mem0 用户记忆")
    smart_retrieval: bool = Field(True, description="是否启用智能记忆检索")
    retention_policy: str = Field("user", description="记忆保留策略: session / user / persistent")


# ============================================================
# Agent 请求模型
# ============================================================

class AgentCreateRequest(BaseModel):
    """创建 Agent 请求"""
    agent_id: Optional[str] = Field(None, description="Agent ID（可选，不填则自动生成 UUID）", max_length=64)
    name: str = Field(..., description="Agent 名称（用户可读的显示名称）", min_length=1, max_length=100)
    description: str = Field("", description="Agent 描述")
    prompt: str = Field(..., description="Agent 提示词（prompt.md 内容）")
    
    # 模型配置
    model: str = Field("claude-sonnet-4-5-20250929", description="使用的模型")
    max_turns: int = Field(20, description="最大对话轮数")
    plan_manager_enabled: bool = Field(True, description="是否启用计划管理器")
    
    # LLM 超参数
    llm: LLMConfig = Field(default_factory=LLMConfig, description="LLM 超参数")
    
    # 工具能力
    enabled_capabilities: Dict[str, bool] = Field(
        default_factory=dict,
        description="启用的工具能力，如 {'code_execution': True, 'document_skills': False}"
    )
    
    # MCP 工具
    mcp_tools: List[MCPToolConfig] = Field(default_factory=list, description="MCP 工具配置列表")
    
    # REST APIs
    apis: List[RESTAPIConfig] = Field(default_factory=list, description="REST API 配置列表")
    
    # 记忆
    memory: MemoryConfig = Field(default_factory=MemoryConfig, description="记忆配置")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "编程助手",
                    "description": "专业的编程助手，擅长代码审查和优化",
                    "prompt": "你是一个专业的助手...",
                    "model": "claude-sonnet-4-5-20250929",
                    "max_turns": 20,
                    "enabled_capabilities": {
                        "code_execution": False,
                    },
                    "mcp_tools": [
                        {
                            "name": "dify_workflow",
                            "server_url": "https://api.dify.ai/mcp/server/xxx/mcp",
                            "auth_type": "bearer",
                            "auth_env": "DIFY_API_KEY"
                        }
                    ]
                }
            ]
        }
    }


class AgentUpdateRequest(BaseModel):
    """更新 Agent 请求（所有字段可选）"""
    description: Optional[str] = Field(None, description="Agent 描述")
    prompt: Optional[str] = Field(None, description="Agent 提示词")
    model: Optional[str] = Field(None, description="使用的模型")
    max_turns: Optional[int] = Field(None, description="最大对话轮数")
    plan_manager_enabled: Optional[bool] = Field(None, description="是否启用计划管理器")
    llm: Optional[LLMConfig] = Field(None, description="LLM 超参数")
    enabled_capabilities: Optional[Dict[str, bool]] = Field(None, description="启用的工具能力")
    mcp_tools: Optional[List[MCPToolConfig]] = Field(None, description="MCP 工具配置列表")
    apis: Optional[List[RESTAPIConfig]] = Field(None, description="REST API 配置列表")
    memory: Optional[MemoryConfig] = Field(None, description="记忆配置")
    is_active: Optional[bool] = Field(None, description="是否激活")


# ============================================================
# Agent 响应模型
# ============================================================

class AgentSummary(BaseModel):
    """Agent 摘要（用于列表）"""
    agent_id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    description: str = Field("", description="描述")
    version: str = Field("1.0.0", description="版本")
    is_active: bool = Field(True, description="是否激活")
    total_calls: int = Field(0, description="总调用次数")
    created_at: datetime = Field(..., description="创建时间")
    last_used_at: Optional[datetime] = Field(None, description="最后使用时间")


class AgentDetail(BaseModel):
    """Agent 详情"""
    agent_id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    description: str = Field("", description="描述")
    version: str = Field("1.0.0", description="版本")
    is_active: bool = Field(True, description="是否激活")
    
    # 配置
    model: Optional[str] = Field(None, description="使用的模型")
    max_turns: Optional[int] = Field(None, description="最大对话轮数")
    plan_manager_enabled: bool = Field(False, description="是否启用计划管理器")
    enabled_capabilities: Dict[str, bool] = Field(
        default_factory=dict, 
        description="启用的工具能力，如 {'code_execution': True, 'document_skills': False}"
    )
    mcp_tools: List[MCPToolDetail] = Field(default_factory=list, description="MCP 工具配置列表")
    apis: List[APIDetail] = Field(default_factory=list, description="API 配置列表")
    skills: List[str] = Field(default_factory=list, description="Skill 名称列表")
    
    # 统计
    total_calls: int = Field(0, description="总调用次数")
    success_calls: int = Field(0, description="成功调用次数")
    failed_calls: int = Field(0, description="失败调用次数")
    
    # 时间戳
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    last_used_at: Optional[datetime] = Field(None, description="最后使用时间")
    loaded_at: Optional[str] = Field(None, description="最后加载时间（ISO 格式字符串）")
    load_time_ms: Optional[float] = Field(None, description="加载耗时（毫秒）")


class AgentListResponse(BaseModel):
    """Agent 列表响应"""
    total: int = Field(..., description="总数")
    agents: List[AgentSummary] = Field(..., description="Agent 列表")
