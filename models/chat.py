from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, model_validator, AliasChoices
from datetime import datetime


# ============================================================
# 文件引用模型（用于 ChatRequest）
# ============================================================

class FileReference(BaseModel):
    """
    文件引用

    支持三种方式引用文件（优先级从高到低）：

    1. local_path：本地文件系统绝对路径（上传接口返回，Agent 直接读取）
    2. file_url：API URL 或远程 HTTP URL（前端预览/远程文件）
    3. file_id：文件 ID（预留）

    本地桌面模式下，优先使用 local_path。
    """
    # 本地文件系统路径（优先，桌面模式上传后返回）
    local_path: Optional[str] = Field(None, description="本地文件系统绝对路径")

    # API URL 或远程 URL
    file_url: Optional[str] = Field(None, description="文件访问 URL（API 路径或远程 HTTP）")

    # 文件 ID（预留）
    file_id: Optional[str] = Field(None, description="文件 ID（通过上传接口获取）")

    # 元数据
    file_name: Optional[str] = Field(None, description="文件名")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    file_type: Optional[str] = Field(None, description="文件类型（MIME）")

    @model_validator(mode='after')
    def check_file_reference(self):
        """验证至少有一种文件来源"""
        if not self.local_path and not self.file_url and not self.file_id:
            raise ValueError("local_path、file_url、file_id 至少需要提供一个")
        return self


# ============================================================
# Content Block 模型（统一的消息内容块格式）
# ============================================================

class TextBlock(BaseModel):
    """文本内容块"""
    type: Literal["text"] = "text"
    text: str = Field(..., description="文本内容")


class ThinkingBlock(BaseModel):
    """思考过程块（Extended Thinking）"""
    type: Literal["thinking"] = "thinking"
    thinking: str = Field(..., description="思考内容")
    signature: Optional[str] = Field(None, description="思考签名（用于续传）")


class ToolUseBlock(BaseModel):
    """
    工具调用块
    
    统一格式，不区分客户端工具和服务端工具：
    - 客户端工具（如 execute_code）：由我们执行
    - 服务端工具（如 web_search）：由 LLM Provider 执行
    
    前端和 LLM Adaptor 层都只看到 tool_use，不需要知道是谁执行的
    """
    type: Literal["tool_use"] = "tool_use"
    id: str = Field(..., description="工具调用ID")
    name: str = Field(..., description="工具名称")
    input: Dict[str, Any] = Field(default_factory=dict, description="工具输入参数")


class ToolResultBlock(BaseModel):
    """
    工具结果块

    统一格式，不区分客户端工具结果和服务端工具结果：
    - 客户端工具结果：我们执行后返回
    - 服务端工具结果（如 web_search_tool_result）：LLM Provider 返回

    前端只看到 tool_result。
    content 支持字符串或多模态内容块列表（如截图工具返回 text + image）。
    """
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = Field(..., description="对应的工具调用ID")
    content: Union[str, List[Dict[str, Any]]] = Field(
        ..., description="工具执行结果（字符串或 content blocks 列表，如 [text, image]）"
    )
    is_error: bool = Field(False, description="是否执行出错")


class ImageBlock(BaseModel):
    """图片内容块"""
    type: Literal["image"] = "image"
    source: Dict[str, Any] = Field(..., description="图片来源（base64 或 url）")
    # source 格式：
    # - {"type": "base64", "media_type": "image/png", "data": "..."}
    # - {"type": "url", "url": "https://..."}


# Content Block 联合类型
ContentBlock = Union[TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock, ImageBlock]


class MessageContent(BaseModel):
    """
    消息内容模型
    
    支持两种格式：
    1. 简单字符串（纯文本消息）
    2. Content Block 数组（包含多种内容类型）
    """
    role: Literal["user", "assistant"] = Field(..., description="消息角色")
    content: Union[str, List[ContentBlock]] = Field(..., description="消息内容")
    
    @classmethod
    def from_text(cls, role: str, text: str) -> "MessageContent":
        """从纯文本创建消息"""
        return cls(role=role, content=text)
    
    @classmethod
    def from_blocks(cls, role: str, blocks: List[ContentBlock]) -> "MessageContent":
        """从内容块列表创建消息"""
        return cls(role=role, content=blocks)
    
    def get_text_content(self) -> str:
        """提取纯文本内容"""
        if isinstance(self.content, str):
            return self.content
        
        text_parts = []
        for block in self.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "\n".join(text_parts)
    
    def get_tool_uses(self) -> List[ToolUseBlock]:
        """提取所有工具调用"""
        if isinstance(self.content, str):
            return []
        
        tool_uses = []
        for block in self.content:
            if isinstance(block, ToolUseBlock):
                tool_uses.append(block)
            elif isinstance(block, dict) and block.get("type") == "tool_use":
                tool_uses.append(ToolUseBlock(**block))
        return tool_uses


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息", min_length=1)
    message_id: Optional[str] = Field(None, alias="messageId", description="消息ID（可选，用于追踪单条消息）")
    user_id: str = Field(..., alias="userId", description="用户ID（必填，用于多租户隔离/知识库分区映射）")
    conversation_id: Optional[str] = Field(
        None,
        alias="conversationId",
        description="对话线程ID（客户端会话ID，可选）：用于区分同一用户的多个对话，并在多次请求间延续上下文"
    )
    agent_id: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("agentId", "intentId", "agent_id", "intent_id"),
        serialization_alias="agentId",
        description="指定 Agent 实例 ID（对应 instances/ 目录名），支持别名 intentId，不传则使用默认 Agent"
    )
    stream: bool = Field(True, description="是否使用流式输出（默认为True）")
    background_tasks: Optional[List[str]] = Field(
        None, 
        alias="backgroundTasks", 
        description="需要启用的后台任务列表（可选），如 ['title_generation']"
    )
    files: Optional[List[FileReference]] = Field(
        None, 
        description="文件引用列表（可选），支持 local_path / file_url / file_id"
    )
    variables: Optional[Dict[str, Any]] = Field(
        None,
        description="前端上下文变量（可选），如用户位置、时区、设备信息等，用于个性化响应"
    )
    
    model_config = {
        "populate_by_name": True,  # 支持驼峰和下划线命名
        "json_schema_extra": {
            "examples": [
                {
                    "message": "帮我分析这张图片和这份报告",
                    "messageId": "msg_001",
                    "userId": "user_001",
                    "conversationId": "conv_20231224_120000",
                    "agentId": "test_agent",
                    "stream": True,
                    "backgroundTasks": ["title_generation"],
                    "files": [
                        {"file_id": "file_abc123"},
                        {
                            "file_url": "https://example.com/report.pdf",
                            "file_name": "季度报告.pdf",
                            "file_size": 102400,
                            "file_type": "application/pdf"
                        }
                    ],
                    "variables": {
                        "location": "北京市朝阳区",
                        "timezone": "Asia/Shanghai",
                        "locale": "zh-CN",
                        "device": "mobile",
                        "userAgent": "Mozilla/5.0...",
                        "currentTime": "2023-12-24T12:00:00+08:00"
                    }
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    """聊天响应"""
    conversation_id: str = Field(..., description="对话线程ID（客户端会话ID）")
    session_id: str = Field(..., description="运行会话ID（服务端内部ID）")
    content: str = Field(..., description="回复内容")
    status: str = Field(..., description="任务状态：success/failed/incomplete")
    turns: int = Field(..., description="执行轮次")
    plan: Optional[Dict[str, Any]] = Field(None, description="执行计划（如果有）")
    progress: Optional[Dict[str, Any]] = Field(None, description="进度信息")
    invocation_stats: Optional[Dict[str, int]] = Field(None, description="工具调用统计")
    # 🆕 新增字段：详细的执行信息
    routing_decisions: Optional[List[Dict[str, Any]]] = Field(None, description="能力路由决策记录")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="工具调用详情")
    intent_analysis: Optional[Dict[str, Any]] = Field(None, description="意图识别结果")
    selected_tools: Optional[List[str]] = Field(None, description="本次选择的工具列表")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "conv_20231224_120000",
                    "session_id": "20231224_120000",
                    "content": "已经为您生成了PPT...",
                    "status": "success",
                    "turns": 5,
                    "progress": {
                        "total": 4,
                        "completed": 4,
                        "progress": 1.0
                    },
                    "routing_decisions": [
                        {
                            "keywords": ["ppt", "专业"],
                            "selected": "slidespeak-generator",
                            "score": 276,
                            "reason": "专业PPT需求"
                        }
                    ],
                    "tool_calls": [
                        {
                            "tool_name": "slidespeak-generator",
                            "status": "success",
                            "duration": 2.5
                        }
                    ]
                }
            ]
        }
    }


class StreamEvent(BaseModel):
    """流式输出事件"""
    conversation_id: Optional[str] = Field(None, description="对话线程ID（客户端会话ID）")
    session_id: Optional[str] = Field(None, description="运行会话ID（服务端内部ID）")
    type: str = Field(..., description="事件类型")
    data: Dict[str, Any] = Field(..., description="事件数据")
    timestamp: str = Field(..., description="时间戳")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "thinking",
                    "data": {"text": "让我思考一下..."},
                    "timestamp": "2023-12-24T12:00:00"
                }
            ]
        }
    }


class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str = Field(..., description="会话ID")
    active: bool = Field(..., description="是否活跃")
    turns: int = Field(..., description="对话轮次")
    message_count: int = Field(..., description="消息数量")
    has_plan: bool = Field(..., description="是否有执行计划")
    start_time: Optional[str] = Field(None, description="会话开始时间")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "20231224_120000",
                    "active": True,
                    "turns": 3,
                    "message_count": 6,
                    "has_plan": True,
                    "start_time": "2023-12-24T12:00:00"
                }
            ]
        }
    }


class RefineRequest(BaseModel):
    """改进请求（简化版）"""
    session_id: str = Field(..., description="会话ID")
    message: str = Field(..., description="用户反馈/修改要求", min_length=1)
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "20231224_120000",
                    "message": "标题字体太小了，需要调整为48号并加粗"
                }
            ]
        }
    }

