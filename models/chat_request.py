"""
统一聊天输入模型 - Enhanced Chat Request Schema

提供完整的、标准化的聊天输入接口，支持：
- 多种消息格式（文本、图片、文档）
- 历史消息上下文
- 文件附件（PDF、Word、Excel、图片）
- 前端上下文变量
- 工具调用结果回传
"""

from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, model_validator, field_validator, AliasChoices
from datetime import datetime
from enum import Enum


# ============================================================
# 文件附件模型
# ============================================================

class FileType(str, Enum):
    """支持的文件类型"""
    PDF = "pdf"
    WORD = "word"  # .doc, .docx
    EXCEL = "excel"  # .xls, .xlsx
    IMAGE = "image"  # .jpg, .png, .gif, .webp
    TEXT = "text"  # .txt, .md, .csv
    AUDIO = "audio"  # .mp3, .wav, .m4a
    VIDEO = "video"  # .mp4, .avi, .mov


class FileSource(str, Enum):
    """文件来源"""
    UPLOAD = "upload"      # 通过上传接口
    URL = "url"            # 外部URL
    BASE64 = "base64"      # Base64 编码
    STORAGE = "storage"    # 云存储（如 S3）


class AttachmentFile(BaseModel):
    """
    文件附件
    
    支持多种文件来源：
    1. 上传的文件（file_id）
    2. 外部 URL（file_url）
    3. Base64 编码（file_data）
    4. 云存储（storage_key）
    """
    # 文件标识
    file_id: Optional[str] = Field(None, description="文件ID（上传接口返回）")
    file_url: Optional[str] = Field(None, description="文件URL（外部文件）")
    file_data: Optional[str] = Field(None, description="文件Base64数据（小文件）")
    storage_key: Optional[str] = Field(None, description="云存储Key（如 S3）")
    
    # 文件元数据
    file_name: str = Field(..., description="文件名", min_length=1)
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    file_type: FileType = Field(..., description="文件类型")
    mime_type: Optional[str] = Field(None, description="MIME类型")
    
    # 文件来源
    source: FileSource = Field(FileSource.UPLOAD, description="文件来源")
    
    # 处理选项
    extract_text: bool = Field(True, description="是否提取文本内容")
    extract_images: bool = Field(False, description="是否提取图片（PDF/Word）")
    max_pages: Optional[int] = Field(None, description="最大页数限制（PDF）")
    
    @model_validator(mode='after')
    def validate_file_source(self):
        """验证文件来源的一致性"""
        sources = [self.file_id, self.file_url, self.file_data, self.storage_key]
        provided = sum(1 for s in sources if s is not None)
        
        if provided == 0:
            raise ValueError("必须提供至少一种文件来源（file_id/file_url/file_data/storage_key）")
        if provided > 1:
            raise ValueError("只能提供一种文件来源")
        
        return self


# ============================================================
# 消息内容块模型
# ============================================================

class TextContentBlock(BaseModel):
    """文本内容块"""
    type: Literal["text"] = "text"
    text: str = Field(..., description="文本内容", min_length=1)


class ImageContentBlock(BaseModel):
    """图片内容块"""
    type: Literal["image"] = "image"
    source: Dict[str, Any] = Field(..., description="图片来源")
    # source 格式示例：
    # {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgoAAAANS..."}
    # {"type": "url", "url": "https://example.com/image.png"}
    alt_text: Optional[str] = Field(None, description="图片描述（可选）")


class DocumentContentBlock(BaseModel):
    """文档内容块（PDF、Word等）"""
    type: Literal["document"] = "document"
    document_id: str = Field(..., description="文档ID")
    document_name: str = Field(..., description="文档名称")
    document_type: FileType = Field(..., description="文档类型")
    page_range: Optional[str] = Field(None, description="页码范围（如 '1-10'）")
    extracted_text: Optional[str] = Field(None, description="提取的文本内容（可选）")


class ToolResultContentBlock(BaseModel):
    """工具结果内容块（用户提供的工具执行结果）"""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = Field(..., description="工具调用ID")
    content: str = Field(..., description="工具执行结果")
    is_error: bool = Field(False, description="是否执行出错")


# 内容块联合类型
ContentBlock = Union[
    TextContentBlock,
    ImageContentBlock,
    DocumentContentBlock,
    ToolResultContentBlock
]


# ============================================================
# 消息模型
# ============================================================

class Message(BaseModel):
    """
    消息模型
    
    支持两种格式：
    1. 简单格式：纯文本字符串
    2. 复杂格式：内容块数组（支持多模态）
    """
    role: Literal["user", "assistant"] = Field(..., description="消息角色")
    content: Union[str, List[ContentBlock]] = Field(..., description="消息内容")
    timestamp: Optional[datetime] = Field(None, description="消息时间戳")
    message_id: Optional[str] = Field(None, description="消息ID（可选）")
    
    @classmethod
    def from_text(cls, role: str, text: str, **kwargs) -> "Message":
        """从纯文本创建消息"""
        return cls(role=role, content=text, **kwargs)
    
    @classmethod
    def from_blocks(cls, role: str, blocks: List[ContentBlock], **kwargs) -> "Message":
        """从内容块列表创建消息"""
        return cls(role=role, content=blocks, **kwargs)


# ============================================================
# 上下文变量模型
# ============================================================

class UserContext(BaseModel):
    """用户上下文变量（前端提供）"""
    # 地理位置
    location: Optional[str] = Field(None, description="用户位置（城市或地区）")
    coordinates: Optional[Dict[str, float]] = Field(
        None,
        description="地理坐标（{'lat': 39.9, 'lng': 116.4}）"
    )
    
    # 时间与本地化
    timezone: Optional[str] = Field(None, description="时区（如 'Asia/Shanghai'）")
    locale: Optional[str] = Field(None, description="语言区域（如 'zh-CN'）")
    current_time: Optional[datetime] = Field(None, description="客户端当前时间")
    
    # 设备信息
    device: Optional[str] = Field(None, description="设备类型（mobile/tablet/desktop）")
    os: Optional[str] = Field(None, description="操作系统（iOS/Android/Windows/macOS）")
    browser: Optional[str] = Field(None, description="浏览器（Chrome/Safari/Firefox）")
    user_agent: Optional[str] = Field(None, description="完整的 User-Agent")
    
    # 用户状态
    is_authenticated: bool = Field(True, description="是否已认证")
    subscription_tier: Optional[str] = Field(None, description="订阅等级（free/pro/enterprise）")
    
    # 自定义字段
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="自定义字段（灵活扩展）")


# ============================================================
# 聊天请求选项
# ============================================================

class ChatOptions(BaseModel):
    """聊天请求选项"""
    # 响应格式
    stream: bool = Field(True, description="是否使用流式输出")
    event_format: Literal["zenflux"] = Field(
        "zenflux",
        description="事件格式，默认 zenflux"
    )
    
    # LLM 参数
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="温度参数（0-2）")
    max_tokens: Optional[int] = Field(None, gt=0, description="最大生成token数")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Top-p采样")
    
    # 功能开关
    enable_thinking: bool = Field(True, description="是否启用思考过程（Extended Thinking）")
    enable_memory: bool = Field(True, description="是否启用记忆系统（Mem0）")
    enable_plan: bool = Field(True, description="是否生成执行计划")
    enable_tools: bool = Field(True, description="是否启用工具调用")
    
    # 后台任务
    background_tasks: Optional[List[str]] = Field(
        None,
        description="后台任务列表（如 ['title_generation', 'mem0_update']）"
    )
    
    # 安全选项
    max_turns: int = Field(20, ge=1, le=50, description="最大执行轮次")
    timeout: Optional[int] = Field(None, gt=0, description="超时时间（秒）")


# ============================================================
# 增强版聊天请求
# ============================================================

class EnhancedChatRequest(BaseModel):
    """
    增强版聊天请求
    
    提供完整的、标准化的输入接口，支持：
    - 当前消息 + 历史消息
    - 文件附件（PDF、Word、Excel、图片）
    - 用户上下文变量
    - 丰富的配置选项
    """
    # ===== 基础字段 =====
    # 当前用户消息
    message: Union[str, Message] = Field(..., description="用户消息（字符串或Message对象）")
    
    # 用户标识
    user_id: str = Field("local", alias="userId", description="用户ID（桌面端默认 local）")
    
    # 会话标识
    conversation_id: Optional[str] = Field(
        None,
        alias="conversationId",
        description="对话线程ID（可选，用于多轮对话）"
    )
    message_id: Optional[str] = Field(
        None,
        alias="messageId",
        description="消息ID（可选，用于追踪）"
    )
    
    # Agent 配置
    agent_id: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("agentId", "intentId", "agent_id", "intent_id"),
        serialization_alias="agentId",
        description="指定 Agent 实例 ID（不传则使用默认 Agent）"
    )
    
    # ===== 历史消息 =====
    history: Optional[List[Message]] = Field(
        None,
        description="历史消息列表（可选，用于提供上下文）",
        max_length=50
    )
    
    # ===== 文件附件 =====
    attachments: Optional[List[AttachmentFile]] = Field(
        None,
        description="文件附件列表（可选）",
        max_length=20
    )
    
    # ===== 用户上下文 =====
    context: Optional[UserContext] = Field(
        None,
        description="用户上下文变量（可选，用于个性化响应）"
    )
    
    # ===== 请求选项 =====
    options: Optional[ChatOptions] = Field(
        None,
        description="聊天选项（可选，用于控制行为）"
    )
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        """将字符串消息转换为 Message 对象"""
        if isinstance(v, str):
            return Message.from_text("user", v)
        return v
    
    def get_all_messages(self) -> List[Message]:
        """
        获取所有消息（历史+当前）
        
        Returns:
            消息列表，按时间顺序排列
        """
        messages = []
        
        # 添加历史消息
        if self.history:
            messages.extend(self.history)
        
        # 添加当前消息
        if isinstance(self.message, Message):
            messages.append(self.message)
        else:
            messages.append(Message.from_text("user", self.message))
        
        return messages
    
    def get_effective_options(self) -> ChatOptions:
        """
        获取有效的选项配置（包含默认值）
        
        Returns:
            ChatOptions 对象
        """
        return self.options or ChatOptions()
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    # 示例 1: 简单文本消息
                    "message": "你好，请帮我分析一下今天的天气",
                    "userId": "user_001",
                },
                {
                    # 示例 2: 带历史消息的多轮对话
                    "message": "那明天呢？",
                    "userId": "user_001",
                    "conversationId": "conv_20240114_001",
                    "history": [
                        {"role": "user", "content": "今天天气怎么样？"},
                        {"role": "assistant", "content": "今天北京天气晴朗，温度5-15°C"}
                    ]
                },
                {
                    # 示例 3: 带文件附件的请求
                    "message": "请帮我总结这份PDF报告的要点",
                    "userId": "user_001",
                    "conversationId": "conv_20240114_002",
                    "attachments": [
                        {
                            "file_id": "file_abc123",
                            "file_name": "2023年度报告.pdf",
                            "file_size": 1048576,
                            "file_type": "pdf",
                            "source": "upload",
                            "extract_text": True,
                            "max_pages": 50
                        }
                    ]
                },
                {
                    # 示例 4: 完整的请求（包含所有选项）
                    "message": "根据当前位置，推荐附近的餐厅",
                    "userId": "user_001",
                    "conversationId": "conv_20240114_003",
                    "agentId": "recommendation_agent",
                    "context": {
                        "location": "北京市朝阳区",
                        "coordinates": {"lat": 39.9, "lng": 116.4},
                        "timezone": "Asia/Shanghai",
                        "locale": "zh-CN",
                        "device": "mobile",
                        "current_time": "2024-01-14T12:00:00+08:00"
                    },
                    "options": {
                        "stream": True,
                        "event_format": "zenflux",
                        "temperature": 0.7,
                        "enable_thinking": True,
                        "enable_memory": True,
                        "background_tasks": ["title_generation", "mem0_update"],
                        "max_turns": 20
                    }
                }
            ]
        }
    }
