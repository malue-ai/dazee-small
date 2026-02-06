"""
Realtime API 数据模型

用于 WebSocket 实时通信的请求/响应模型
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RealtimeEventType(str, Enum):
    """实时事件类型"""
    # 会话事件
    SESSION_CREATE = "session.create"
    SESSION_CREATED = "session.created"
    SESSION_UPDATE = "session.update"
    SESSION_UPDATED = "session.updated"
    
    # 音频事件
    INPUT_AUDIO_BUFFER_APPEND = "input_audio_buffer.append"
    INPUT_AUDIO_BUFFER_COMMIT = "input_audio_buffer.commit"
    INPUT_AUDIO_BUFFER_CLEAR = "input_audio_buffer.clear"
    INPUT_AUDIO_BUFFER_COMMITTED = "input_audio_buffer.committed"
    INPUT_AUDIO_BUFFER_CLEARED = "input_audio_buffer.cleared"
    INPUT_AUDIO_BUFFER_SPEECH_STARTED = "input_audio_buffer.speech_started"
    INPUT_AUDIO_BUFFER_SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
    
    # 对话事件
    CONVERSATION_ITEM_CREATE = "conversation.item.create"
    CONVERSATION_ITEM_CREATED = "conversation.item.created"
    CONVERSATION_ITEM_TRUNCATE = "conversation.item.truncate"
    CONVERSATION_ITEM_TRUNCATED = "conversation.item.truncated"
    CONVERSATION_ITEM_DELETE = "conversation.item.delete"
    CONVERSATION_ITEM_DELETED = "conversation.item.deleted"
    
    # 响应事件
    RESPONSE_CREATE = "response.create"
    RESPONSE_CREATED = "response.created"
    RESPONSE_OUTPUT_ITEM_ADDED = "response.output_item.added"
    RESPONSE_OUTPUT_ITEM_DONE = "response.output_item.done"
    RESPONSE_CONTENT_PART_ADDED = "response.content_part.added"
    RESPONSE_CONTENT_PART_DONE = "response.content_part.done"
    RESPONSE_TEXT_DELTA = "response.text.delta"
    RESPONSE_TEXT_DONE = "response.text.done"
    RESPONSE_AUDIO_DELTA = "response.audio.delta"
    RESPONSE_AUDIO_DONE = "response.audio.done"
    RESPONSE_AUDIO_TRANSCRIPT_DELTA = "response.audio_transcript.delta"
    RESPONSE_AUDIO_TRANSCRIPT_DONE = "response.audio_transcript.done"
    RESPONSE_FUNCTION_CALL_ARGUMENTS_DELTA = "response.function_call_arguments.delta"
    RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE = "response.function_call_arguments.done"
    RESPONSE_DONE = "response.done"
    RESPONSE_CANCEL = "response.cancel"
    RESPONSE_CANCELLED = "response.cancelled"
    
    # 速率限制
    RATE_LIMITS_UPDATED = "rate_limits.updated"
    
    # 错误
    ERROR = "error"


class AudioFormat(str, Enum):
    """音频格式"""
    PCM16 = "pcm16"
    G711_ULAW = "g711_ulaw"
    G711_ALAW = "g711_alaw"


class Voice(str, Enum):
    """语音类型"""
    ALLOY = "alloy"
    ASH = "ash"
    BALLAD = "ballad"
    CORAL = "coral"
    ECHO = "echo"
    SAGE = "sage"
    SHIMMER = "shimmer"
    VERSE = "verse"


class TurnDetectionType(str, Enum):
    """轮次检测类型"""
    SERVER_VAD = "server_vad"
    NONE = "none"


# ==================== 会话配置 ====================

class TurnDetection(BaseModel):
    """轮次检测配置"""
    type: TurnDetectionType = TurnDetectionType.SERVER_VAD
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="语音检测阈值")
    prefix_padding_ms: int = Field(default=300, ge=0, description="语音前置填充（毫秒）")
    silence_duration_ms: int = Field(default=500, ge=0, description="静音持续时间（毫秒）")


class InputAudioTranscription(BaseModel):
    """输入音频转录配置"""
    model: str = Field(default="whisper-1", description="转录模型")


class AudioConfig(BaseModel):
    """音频配置"""
    voice: Voice = Voice.ALLOY
    input_audio_format: AudioFormat = AudioFormat.PCM16
    output_audio_format: AudioFormat = AudioFormat.PCM16


class SessionConfig(BaseModel):
    """会话配置"""
    model: str = Field(default="gpt-4o-realtime-preview", description="模型名称")
    modalities: List[str] = Field(default=["text", "audio"], description="支持的模态")
    instructions: Optional[str] = Field(default=None, description="系统指令")
    voice: Voice = Voice.ALLOY
    input_audio_format: AudioFormat = AudioFormat.PCM16
    output_audio_format: AudioFormat = AudioFormat.PCM16
    input_audio_transcription: Optional[InputAudioTranscription] = None
    turn_detection: Optional[TurnDetection] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list, description="可用工具")
    tool_choice: str = Field(default="auto", description="工具选择策略")
    temperature: float = Field(default=0.8, ge=0.0, le=2.0, description="温度")
    max_response_output_tokens: Optional[int] = Field(default=None, description="最大输出 token 数")


# ==================== 客户端事件 ====================

class RealtimeClientEvent(BaseModel):
    """客户端发送的事件基类"""
    type: RealtimeEventType
    event_id: Optional[str] = Field(default=None, description="事件 ID")


class SessionUpdateEvent(RealtimeClientEvent):
    """会话更新事件"""
    type: RealtimeEventType = RealtimeEventType.SESSION_UPDATE
    session: SessionConfig


class InputAudioBufferAppendEvent(RealtimeClientEvent):
    """追加音频缓冲区事件"""
    type: RealtimeEventType = RealtimeEventType.INPUT_AUDIO_BUFFER_APPEND
    audio: str = Field(..., description="Base64 编码的音频数据")


class InputAudioBufferCommitEvent(RealtimeClientEvent):
    """提交音频缓冲区事件"""
    type: RealtimeEventType = RealtimeEventType.INPUT_AUDIO_BUFFER_COMMIT


class InputAudioBufferClearEvent(RealtimeClientEvent):
    """清空音频缓冲区事件"""
    type: RealtimeEventType = RealtimeEventType.INPUT_AUDIO_BUFFER_CLEAR


class ConversationItemContent(BaseModel):
    """对话项内容"""
    type: str = Field(..., description="内容类型: input_text, input_audio, text, audio")
    text: Optional[str] = Field(default=None, description="文本内容")
    audio: Optional[str] = Field(default=None, description="Base64 编码的音频")
    transcript: Optional[str] = Field(default=None, description="音频转录")


class ConversationItem(BaseModel):
    """对话项"""
    id: Optional[str] = Field(default=None, description="对话项 ID")
    type: str = Field(default="message", description="类型: message, function_call, function_call_output")
    role: Optional[str] = Field(default=None, description="角色: user, assistant, system")
    content: List[ConversationItemContent] = Field(default_factory=list)


class ConversationItemCreateEvent(RealtimeClientEvent):
    """创建对话项事件"""
    type: RealtimeEventType = RealtimeEventType.CONVERSATION_ITEM_CREATE
    item: ConversationItem


class ResponseCreateEvent(RealtimeClientEvent):
    """创建响应事件"""
    type: RealtimeEventType = RealtimeEventType.RESPONSE_CREATE
    response: Optional[Dict[str, Any]] = Field(default=None, description="响应配置")


class ResponseCancelEvent(RealtimeClientEvent):
    """取消响应事件"""
    type: RealtimeEventType = RealtimeEventType.RESPONSE_CANCEL


# ==================== 服务端事件 ====================

class RealtimeServerEvent(BaseModel):
    """服务端发送的事件基类"""
    type: RealtimeEventType
    event_id: Optional[str] = Field(default=None, description="事件 ID")


class SessionCreatedEvent(RealtimeServerEvent):
    """会话创建完成事件"""
    type: RealtimeEventType = RealtimeEventType.SESSION_CREATED
    session: Dict[str, Any]


class ErrorEvent(RealtimeServerEvent):
    """错误事件"""
    type: RealtimeEventType = RealtimeEventType.ERROR
    error: Dict[str, Any]


class ResponseAudioDeltaEvent(RealtimeServerEvent):
    """音频增量事件"""
    type: RealtimeEventType = RealtimeEventType.RESPONSE_AUDIO_DELTA
    response_id: str
    item_id: str
    output_index: int
    content_index: int
    delta: str = Field(..., description="Base64 编码的音频增量")


class ResponseTextDeltaEvent(RealtimeServerEvent):
    """文本增量事件"""
    type: RealtimeEventType = RealtimeEventType.RESPONSE_TEXT_DELTA
    response_id: str
    item_id: str
    output_index: int
    content_index: int
    delta: str


class ResponseDoneEvent(RealtimeServerEvent):
    """响应完成事件"""
    type: RealtimeEventType = RealtimeEventType.RESPONSE_DONE
    response: Dict[str, Any]


# ==================== WebSocket 连接模型 ====================

class RealtimeConnectRequest(BaseModel):
    """WebSocket 连接请求参数"""
    model: str = Field(default="gpt-4o-realtime-preview", description="模型名称")
    voice: Voice = Field(default=Voice.ALLOY, description="语音类型")
    instructions: Optional[str] = Field(default=None, description="系统指令")


class RealtimeConnectionInfo(BaseModel):
    """WebSocket 连接信息"""
    session_id: str
    model: str
    status: str = Field(default="connected")
    created_at: str
