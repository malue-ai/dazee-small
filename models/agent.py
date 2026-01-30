"""
Agent 和 Skill Pydantic 模型

用于 API 请求/响应的数据模型
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


# ============================================================
# 枚举类型
# ============================================================

class AgentStatus(str, Enum):
    """Agent 状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class SkillStatus(str, Enum):
    """Skill 状态"""
    REGISTERED = "registered"      # 已注册到 Claude API
    PENDING = "pending"            # 待注册
    FAILED = "failed"              # 注册失败
    DISABLED = "disabled"          # 已禁用


# ============================================================
# MCP 工具配置
# ============================================================

class MCPToolConfig(BaseModel):
    """MCP 工具配置"""
    name: str = Field(..., description="工具名称")
    server_url: str = Field(..., description="MCP 服务器 URL")
    server_name: str = Field("", description="服务器名称（用作工具前缀）")
    auth_type: str = Field("none", description="认证类型: none / bearer / api_key")
    auth_env: Optional[str] = Field(None, description="认证密钥的环境变量名")
    capability: Optional[str] = Field(None, description="工具能力分类")
    description: str = Field("", description="工具描述")


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


# ============================================================
# 记忆配置
# ============================================================

class MemoryConfig(BaseModel):
    """记忆配置"""
    mem0_enabled: bool = Field(True, description="是否启用 Mem0 用户记忆")
    smart_retrieval: bool = Field(True, description="是否启用智能记忆检索")
    retention_policy: str = Field("user", description="记忆保留策略: session / user / persistent")


# ============================================================
# LLM 配置
# ============================================================

class LLMConfig(BaseModel):
    """LLM 超参数配置"""
    temperature: Optional[float] = Field(None, description="温度参数 (0-1)")
    max_tokens: Optional[int] = Field(None, description="最大输出 token 数")
    enable_thinking: Optional[bool] = Field(None, description="是否启用 Extended Thinking")
    thinking_budget: Optional[int] = Field(None, description="Thinking token 预算")
    enable_caching: Optional[bool] = Field(None, description="是否启用 Prompt Caching")
    top_p: Optional[float] = Field(None, description="Top-P 核采样参数")


# ============================================================
# Agent 请求模型
# ============================================================

class AgentCreateRequest(BaseModel):
    """创建 Agent 请求"""
    agent_id: str = Field(..., description="Agent ID（唯一标识，将作为目录名）", min_length=1, max_length=64)
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
        description="启用的工具能力，如 {'web_search': True, 'sandbox_tools': False}"
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
                    "agent_id": "my_agent",
                    "description": "我的自定义 Agent",
                    "prompt": "你是一个专业的助手...",
                    "model": "claude-sonnet-4-5-20250929",
                    "max_turns": 20,
                    "enabled_capabilities": {
                        "tavily_search": True,
                        "knowledge_search": True,
                        "sandbox_tools": True
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


class MCPToolDetail(BaseModel):
    """MCP 工具详情（用于 AgentDetail 响应）"""
    name: str = Field(..., description="工具名称")
    server_url: str = Field("", description="MCP 服务器 URL")
    server_name: str = Field("", description="服务器名称")
    auth_type: str = Field("none", description="认证类型")
    auth_env: Optional[str] = Field(None, description="认证密钥的环境变量名")
    capability: Optional[str] = Field(None, description="工具能力分类")
    description: str = Field("", description="工具描述")


class APIDetail(BaseModel):
    """API 详情（用于 AgentDetail 响应）"""
    name: str = Field(..., description="API 名称")
    base_url: str = Field("", description="API 基础 URL")
    auth_type: str = Field("none", description="认证类型")
    auth_env: Optional[str] = Field(None, description="认证密钥的环境变量名")
    doc: Optional[str] = Field(None, description="API 文档名称")
    capability: Optional[str] = Field(None, description="API 能力分类")
    description: str = Field("", description="API 描述")


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
        description="启用的工具能力，如 {'tavily_search': True, 'knowledge_search': True, 'sandbox_tools': False}"
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


# ============================================================
# Skill 请求模型
# ============================================================

class SkillCreateRequest(BaseModel):
    """创建 Skill 请求"""
    name: str = Field(..., description="Skill 名称", min_length=1, max_length=64)
    description: str = Field("", description="Skill 描述")
    agent_id: str = Field(..., description="所属 Agent ID")
    skill_content: str = Field(..., description="SKILL.md 内容")
    enabled: bool = Field(True, description="是否启用")
    auto_register: bool = Field(True, description="是否自动注册到 Claude API")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "data_analysis",
                    "description": "数据分析技能",
                    "agent_id": "test_agent",
                    "skill_content": "---\nname: data_analysis\ndescription: 数据分析\n---\n\n# Data Analysis Skill\n...",
                    "enabled": True,
                    "auto_register": True
                }
            ]
        }
    }


class SkillUpdateRequest(BaseModel):
    """更新 Skill 请求"""
    description: Optional[str] = Field(None, description="Skill 描述")
    skill_content: Optional[str] = Field(None, description="SKILL.md 内容")
    enabled: Optional[bool] = Field(None, description="是否启用")


# ============================================================
# Skill 响应模型
# ============================================================

class SkillSummary(BaseModel):
    """Skill 摘要（用于列表）"""
    name: str = Field(..., description="Skill 名称")
    description: str = Field("", description="描述")
    agent_id: str = Field(..., description="所属 Agent ID")
    is_enabled: bool = Field(True, description="是否启用")
    is_registered: bool = Field(False, description="是否已注册到 Claude API")
    skill_id: Optional[str] = Field(None, description="Claude API 的 skill_id")
    created_at: datetime = Field(..., description="创建时间")


class SkillDetail(BaseModel):
    """Skill 详情（完整信息）"""
    name: str = Field(..., description="Skill 名称")
    description: str = Field("", description="描述")
    priority: str = Field("medium", description="优先级: high/medium/low")
    preferred_for: List[str] = Field(default_factory=list, description="适用场景")
    scripts: List[str] = Field(default_factory=list, description="脚本文件列表")
    resources: List[str] = Field(default_factory=list, description="资源文件列表")
    content: str = Field("", description="SKILL.md 完整内容")
    agent_id: str = Field(..., description="所属 Agent ID（global 表示全局库）")
    is_enabled: bool = Field(True, description="是否启用")
    is_registered: bool = Field(False, description="是否已注册到 Claude API")
    skill_id: Optional[str] = Field(None, description="Claude API 的 skill_id")
    registered_at: Optional[str] = Field(None, description="注册时间")
    created_at: Optional[datetime] = Field(None, description="创建时间")


class SkillListResponse(BaseModel):
    """Skill 列表响应"""
    total: int = Field(..., description="总数")
    skills: List[SkillSummary] = Field(..., description="Skill 列表")


class SkillSyncResponse(BaseModel):
    """Skill 同步响应"""
    name: str = Field(..., description="Skill 名称")
    success: bool = Field(..., description="是否成功")
    skill_id: Optional[str] = Field(None, description="Claude API 的 skill_id")
    message: str = Field("", description="消息")


class SkillInstallRequest(BaseModel):
    """安装 Skill 到实例请求"""
    skill_name: str = Field(..., description="Skill 名称（全局库中的 Skill）")
    agent_id: str = Field(..., description="目标实例 ID")
    auto_register: bool = Field(True, description="是否自动注册到 Claude API")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "skill_name": "ontology-builder",
                    "agent_id": "dazee_agent",
                    "auto_register": True
                }
            ]
        }
    }


class SkillUninstallRequest(BaseModel):
    """从实例卸载 Skill 请求"""
    skill_name: str = Field(..., description="Skill 名称")
    agent_id: str = Field(..., description="实例 ID")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "skill_name": "ontology-builder",
                    "agent_id": "dazee_agent"
                }
            ]
        }
    }


class SkillToggleRequest(BaseModel):
    """启用/禁用 Skill 请求"""
    skill_name: str = Field(..., description="Skill 名称")
    agent_id: str = Field(..., description="实例 ID")
    enabled: bool = Field(..., description="是否启用")


class SkillUpdateContentRequest(BaseModel):
    """更新 Skill 内容请求"""
    skill_name: str = Field(..., description="Skill 名称")
    agent_id: str = Field(..., description="实例 ID")
    content: str = Field(..., description="新的 SKILL.md 内容")

