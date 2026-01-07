"""
工具（Tool）相关数据模型

定义工具注册、执行、返回相关的数据结构

工具类型：
- USER_DEFINED: 用户自定义工具（函数式或类式）
- MCP: 通过 MCP 协议连接的外部工具

返回模式：
- DIRECT: 直接返回结果
- STREAMING: 流式返回结果

交互模式（主要用于 MCP）：
- SYNC: 同步执行
- ASYNC: 异步执行（返回 task_id，需轮询）
- CALLBACK: 回调通知
"""

from typing import Optional, List, Dict, Any, Union, Literal, Callable, Generic, TypeVar
from pydantic import BaseModel, Field, model_validator
from enum import Enum
from datetime import datetime


# ============================================================
# 枚举定义
# ============================================================

class ToolType(str, Enum):
    """
    工具类型
    
    - USER_DEFINED: 用户自定义工具（本地执行）
    - MCP: MCP 协议工具（远程执行）
    """
    USER_DEFINED = "user_defined"
    MCP = "mcp"


class ReturnMode(str, Enum):
    """
    返回模式
    
    - DIRECT: 直接返回完整结果
    - STREAMING: 流式返回（逐步输出）
    """
    DIRECT = "direct"
    STREAMING = "streaming"


class InteractionMode(str, Enum):
    """
    交互模式（主要用于 MCP 工具）
    
    - SYNC: 同步执行，等待结果返回
    - ASYNC: 异步执行，返回 task_id 后轮询
    - CALLBACK: 回调模式，完成后通知
    """
    SYNC = "sync"
    ASYNC = "async"
    CALLBACK = "callback"


class ToolStatus(str, Enum):
    """
    工具状态
    
    - AVAILABLE: 可用
    - UNAVAILABLE: 不可用（依赖缺失/配置错误）
    - DISABLED: 已禁用
    - RATE_LIMITED: 频率限制中
    """
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    RATE_LIMITED = "rate_limited"


class ExecutionStatus(str, Enum):
    """
    执行状态
    
    - PENDING: 等待执行
    - RUNNING: 执行中
    - SUCCESS: 执行成功
    - FAILED: 执行失败
    - TIMEOUT: 执行超时
    - CANCELLED: 已取消
    """
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# ============================================================
# 工具定义模型（Tool Definition）
# ============================================================

class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str = Field(..., description="参数名称")
    type: str = Field(..., description="参数类型（string/integer/boolean/object/array）")
    description: str = Field("", description="参数描述")
    required: bool = Field(False, description="是否必填")
    default: Optional[Any] = Field(None, description="默认值")
    enum: Optional[List[Any]] = Field(None, description="枚举值（如果适用）")
    
    # 嵌套类型支持
    items: Optional["ToolParameter"] = Field(None, description="数组元素类型（type=array 时）")
    properties: Optional[Dict[str, "ToolParameter"]] = Field(None, description="对象属性（type=object 时）")


class ToolInputSchema(BaseModel):
    """
    工具输入 Schema（JSON Schema 格式）
    
    与 Claude API 的 tool.input_schema 兼容
    """
    type: Literal["object"] = "object"
    properties: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, 
        description="参数属性定义"
    )
    required: List[str] = Field(
        default_factory=list, 
        description="必填参数列表"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索查询"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "返回结果数量",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            ]
        }
    }


class MCPConfig(BaseModel):
    """
    MCP 工具配置
    
    用于配置 MCP 协议连接和交互方式
    """
    server_url: str = Field(..., description="MCP 服务器 URL")
    server_name: Optional[str] = Field(None, description="服务器名称（用于工具命名空间）")
    
    # 交互配置
    interaction_mode: InteractionMode = Field(
        InteractionMode.SYNC, 
        description="交互模式"
    )
    
    # 认证配置
    auth_type: Optional[Literal["none", "api_key", "bearer", "oauth2"]] = Field(
        "none", 
        description="认证类型"
    )
    auth_config: Optional[Dict[str, Any]] = Field(
        None, 
        description="认证配置详情"
    )
    
    # 连接配置
    timeout: int = Field(30, description="请求超时时间（秒）")
    retry_count: int = Field(3, description="重试次数")
    retry_delay: float = Field(1.0, description="重试间隔（秒）")
    
    # 回调配置（interaction_mode=callback 时使用）
    callback_url: Optional[str] = Field(None, description="回调通知 URL")
    callback_secret: Optional[str] = Field(None, description="回调验证密钥")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "server_url": "http://localhost:8080",
                    "server_name": "office365",
                    "interaction_mode": "sync",
                    "auth_type": "bearer",
                    "auth_config": {
                        "token_env": "MCP_OFFICE365_TOKEN"
                    },
                    "timeout": 60
                }
            ]
        }
    }


class ToolDefinition(BaseModel):
    """
    工具定义
    
    描述一个可被注册和调用的工具
    """
    # 基本信息
    name: str = Field(..., description="工具名称（唯一标识）")
    description: str = Field(..., description="工具描述（供 LLM 理解）")
    
    # 类型和模式
    tool_type: ToolType = Field(ToolType.USER_DEFINED, description="工具类型")
    return_mode: ReturnMode = Field(ReturnMode.DIRECT, description="返回模式")
    
    # 输入输出 Schema
    input_schema: ToolInputSchema = Field(..., description="输入参数 Schema")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="输出 Schema（可选）")
    
    # MCP 配置（tool_type=MCP 时必填）
    mcp_config: Optional[MCPConfig] = Field(None, description="MCP 配置")
    
    # 实现配置（tool_type=USER_DEFINED 时使用）
    implementation: Optional[Dict[str, str]] = Field(
        None, 
        description="实现配置，如 {\"module\": \"tools.xxx\", \"class\": \"XxxTool\"}"
    )
    
    # 元数据
    keywords: List[str] = Field(default_factory=list, description="关键词（用于匹配）")
    examples: List[str] = Field(default_factory=list, description="使用示例")
    category: Optional[str] = Field(None, description="分类")
    
    # 约束和限制
    requires_confirmation: bool = Field(False, description="是否需要用户确认")
    rate_limit: Optional[int] = Field(None, description="频率限制（每分钟最大调用次数）")
    timeout: int = Field(30, description="默认超时时间（秒）")
    
    # 状态
    status: ToolStatus = Field(ToolStatus.AVAILABLE, description="工具状态")
    
    @model_validator(mode='after')
    def validate_mcp_config(self):
        """验证 MCP 工具必须有 MCP 配置"""
        if self.tool_type == ToolType.MCP and not self.mcp_config:
            raise ValueError("MCP 工具必须提供 mcp_config")
        return self
    
    def to_claude_schema(self) -> Dict[str, Any]:
        """
        转换为 Claude API 的工具格式
        
        Returns:
            Claude API 兼容的工具定义
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_dump()
        }
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "web_search",
                    "description": "搜索互联网信息",
                    "tool_type": "user_defined",
                    "return_mode": "direct",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "搜索查询"}
                        },
                        "required": ["query"]
                    },
                    "keywords": ["搜索", "查询", "信息"],
                    "category": "information_retrieval"
                }
            ]
        }
    }


# ============================================================
# 工具执行相关模型
# ============================================================

class ToolInvocation(BaseModel):
    """
    工具调用请求
    
    描述一次工具调用的完整信息
    """
    # 调用标识
    invocation_id: str = Field(..., description="调用 ID（唯一）")
    tool_name: str = Field(..., description="工具名称")
    
    # 输入参数
    input: Dict[str, Any] = Field(default_factory=dict, description="调用参数")
    
    # 上下文
    session_id: Optional[str] = Field(None, description="会话 ID")
    conversation_id: Optional[str] = Field(None, description="对话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    
    # 配置覆盖
    timeout: Optional[int] = Field(None, description="超时时间覆盖")
    return_mode: Optional[ReturnMode] = Field(None, description="返回模式覆盖")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class ToolResultChunk(BaseModel):
    """
    流式返回的结果块
    
    用于 return_mode=streaming 时
    """
    invocation_id: str = Field(..., description="调用 ID")
    chunk_index: int = Field(..., description="块索引")
    chunk_type: Literal["data", "progress", "log", "error", "done"] = Field(
        ..., 
        description="块类型"
    )
    content: Any = Field(..., description="块内容")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "invocation_id": "inv_001",
                    "chunk_index": 0,
                    "chunk_type": "progress",
                    "content": {"percent": 50, "message": "正在处理..."},
                    "timestamp": "2024-01-01T12:00:00"
                },
                {
                    "invocation_id": "inv_001",
                    "chunk_index": 1,
                    "chunk_type": "data",
                    "content": "部分结果数据...",
                    "timestamp": "2024-01-01T12:00:01"
                },
                {
                    "invocation_id": "inv_001",
                    "chunk_index": 2,
                    "chunk_type": "done",
                    "content": {"total_chunks": 3},
                    "timestamp": "2024-01-01T12:00:02"
                }
            ]
        }
    }


class ToolResult(BaseModel):
    """
    工具执行结果
    
    描述一次工具调用的完整结果
    """
    # 调用标识
    invocation_id: str = Field(..., description="调用 ID")
    tool_name: str = Field(..., description="工具名称")
    
    # 执行状态
    status: ExecutionStatus = Field(..., description="执行状态")
    
    # 结果内容
    output: Optional[Any] = Field(None, description="输出结果（成功时）")
    error: Optional[str] = Field(None, description="错误信息（失败时）")
    error_code: Optional[str] = Field(None, description="错误代码")
    
    # 时间信息
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    duration_ms: Optional[int] = Field(None, description="执行时长（毫秒）")
    
    # 资源使用
    usage: Optional[Dict[str, Any]] = Field(None, description="资源使用情况")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    @property
    def is_success(self) -> bool:
        """是否执行成功"""
        return self.status == ExecutionStatus.SUCCESS
    
    @property
    def is_error(self) -> bool:
        """是否执行失败"""
        return self.status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT)
    
    def to_claude_result(self) -> Dict[str, Any]:
        """
        转换为 Claude API 的 tool_result 格式
        
        Returns:
            Claude API 兼容的工具结果
        """
        import json
        
        if self.is_success:
            content = json.dumps(self.output, ensure_ascii=False) if isinstance(self.output, (dict, list)) else str(self.output)
        else:
            content = self.error or "Unknown error"
        
        return {
            "type": "tool_result",
            "tool_use_id": self.invocation_id,
            "content": content,
            "is_error": self.is_error
        }
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "invocation_id": "inv_001",
                    "tool_name": "web_search",
                    "status": "success",
                    "output": {"results": [{"title": "...", "url": "..."}]},
                    "started_at": "2024-01-01T12:00:00",
                    "completed_at": "2024-01-01T12:00:02",
                    "duration_ms": 2000
                },
                {
                    "invocation_id": "inv_002",
                    "tool_name": "api_call",
                    "status": "failed",
                    "error": "连接超时",
                    "error_code": "TIMEOUT",
                    "duration_ms": 30000
                }
            ]
        }
    }


# ============================================================
# 工具注册相关模型
# ============================================================

class ToolRegistration(BaseModel):
    """
    工具注册请求
    
    用于通过 API 注册新工具
    """
    # 工具定义
    definition: ToolDefinition = Field(..., description="工具定义")
    
    # 注册选项
    replace_existing: bool = Field(False, description="是否替换已存在的同名工具")
    enabled: bool = Field(True, description="注册后是否立即启用")
    
    # 权限控制
    allowed_users: Optional[List[str]] = Field(None, description="允许使用的用户列表（None=所有人）")
    allowed_roles: Optional[List[str]] = Field(None, description="允许使用的角色列表")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "definition": {
                        "name": "custom_search",
                        "description": "自定义搜索工具",
                        "tool_type": "user_defined",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"}
                            },
                            "required": ["query"]
                        }
                    },
                    "replace_existing": False,
                    "enabled": True
                }
            ]
        }
    }


class MCPServerRegistration(BaseModel):
    """
    MCP 服务器注册请求
    
    用于连接并注册 MCP 服务器上的所有工具
    """
    # 服务器配置
    server_url: str = Field(..., description="MCP 服务器 URL")
    server_name: str = Field(..., description="服务器名称（用于工具命名空间）")
    
    # 认证
    auth_type: Literal["none", "api_key", "bearer", "oauth2"] = Field(
        "none", 
        description="认证类型"
    )
    auth_config: Optional[Dict[str, Any]] = Field(None, description="认证配置")
    
    # 工具过滤
    tool_filter: Optional[List[str]] = Field(
        None, 
        description="只注册指定的工具（None=全部）"
    )
    tool_prefix: Optional[str] = Field(
        None, 
        description="工具名前缀（默认使用 server_name:）"
    )
    
    # 选项
    auto_reconnect: bool = Field(True, description="断线自动重连")
    health_check_interval: int = Field(60, description="健康检查间隔（秒）")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "server_url": "http://localhost:8080",
                    "server_name": "office365",
                    "auth_type": "bearer",
                    "auth_config": {
                        "token": "${MCP_OFFICE365_TOKEN}"
                    },
                    "tool_filter": ["create_document", "send_email"],
                    "auto_reconnect": True
                }
            ]
        }
    }


class ToolRegistrationResponse(BaseModel):
    """工具注册响应"""
    success: bool = Field(..., description="是否成功")
    tool_name: str = Field(..., description="工具名称")
    message: str = Field(..., description="消息")
    tool_definition: Optional[ToolDefinition] = Field(None, description="注册的工具定义")


class MCPServerRegistrationResponse(BaseModel):
    """MCP 服务器注册响应"""
    success: bool = Field(..., description="是否成功")
    server_name: str = Field(..., description="服务器名称")
    message: str = Field(..., description="消息")
    registered_tools: List[str] = Field(default_factory=list, description="注册的工具列表")
    failed_tools: List[Dict[str, str]] = Field(
        default_factory=list, 
        description="注册失败的工具及原因"
    )


# ============================================================
# 工具查询相关模型
# ============================================================

class ToolListQuery(BaseModel):
    """工具列表查询"""
    tool_type: Optional[ToolType] = Field(None, description="按类型过滤")
    category: Optional[str] = Field(None, description="按分类过滤")
    status: Optional[ToolStatus] = Field(None, description="按状态过滤")
    keyword: Optional[str] = Field(None, description="关键词搜索")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class ToolListResponse(BaseModel):
    """工具列表响应"""
    tools: List[ToolDefinition] = Field(..., description="工具列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class ToolDetailResponse(BaseModel):
    """工具详情响应"""
    definition: ToolDefinition = Field(..., description="工具定义")
    statistics: Optional[Dict[str, Any]] = Field(
        None, 
        description="使用统计（调用次数、成功率等）"
    )
    recent_invocations: Optional[List[Dict[str, Any]]] = Field(
        None, 
        description="最近调用记录"
    )

