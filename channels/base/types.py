"""
渠道类型定义

定义消息、上下文、结果等核心数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal
from enum import Enum
from datetime import datetime


# ===========================================================================
# 消息类型
# ===========================================================================

@dataclass
class InboundMessage:
    """
    入站消息（从渠道接收的原始消息）
    
    Attributes:
        message_id: 消息唯一 ID
        channel_id: 渠道 ID（feishu/dingtalk/slack）
        account_id: 账户 ID（多账户支持）
        chat_id: 聊天 ID（群聊/私聊）
        chat_type: 聊天类型
        sender_id: 发送者 ID
        sender_name: 发送者名称
        content: 消息内容（文本）
        msg_type: 消息类型（text/image/file）
        media: 媒体附件列表
        reply_to: 回复的消息 ID
        thread_id: 线程 ID（论坛话题）
        mentions: @ 的用户列表
        timestamp: 消息时间戳
        raw_event: 原始事件数据
        is_fragment: 是否为文本片段（长消息拆分）
        media_group_id: 媒体组 ID（多图消息）
    """
    message_id: str
    channel_id: str
    account_id: str
    chat_id: str
    chat_type: Literal["direct", "group", "channel"]
    sender_id: str
    sender_name: str = ""
    content: str = ""
    msg_type: str = "text"
    media: List[Dict[str, Any]] = field(default_factory=list)
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    mentions: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    raw_event: Dict[str, Any] = field(default_factory=dict)
    is_fragment: bool = False
    media_group_id: Optional[str] = None


@dataclass
class ProcessedMessage:
    """
    预处理后的消息
    
    经过去重、防抖、合并等预处理后的消息
    """
    message_id: str
    channel_id: str
    account_id: str
    chat_id: str
    chat_type: Literal["direct", "group", "channel"]
    sender_id: str
    sender_name: str
    content: str
    msg_type: str = "text"
    media: List[Dict[str, Any]] = field(default_factory=list)
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    mentions: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    raw_events: List[Dict[str, Any]] = field(default_factory=list)
    merged_count: int = 1  # 合并的消息数量


# ===========================================================================
# 发送上下文和结果
# ===========================================================================

@dataclass
class OutboundContext:
    """
    出站消息上下文
    
    Attributes:
        channel_id: 渠道 ID
        account_id: 账户 ID
        chat_id: 目标聊天 ID
        text: 文本内容
        card_data: 卡片数据
        media_url: 媒体 URL
        media_type: 媒体类型
        reply_to: 回复的消息 ID
        thread_id: 线程 ID
        buttons: 按钮列表
        session_id: 关联的 Session ID
        message_id: 关联的消息 ID
    """
    channel_id: str
    account_id: str
    chat_id: str
    text: str = ""
    card_data: Optional[Dict[str, Any]] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    buttons: List[Dict[str, Any]] = field(default_factory=list)
    session_id: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class DeliveryResult:
    """
    消息发送结果
    
    Attributes:
        success: 是否成功
        message_id: 发送后的消息 ID
        error: 错误信息
        raw_response: 原始响应
    """
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    
    @classmethod
    def ok(cls, message_id: str, raw_response: Dict[str, Any] = None) -> "DeliveryResult":
        return cls(success=True, message_id=message_id, raw_response=raw_response)
    
    @classmethod
    def fail(cls, error: str, raw_response: Dict[str, Any] = None) -> "DeliveryResult":
        return cls(success=False, error=error, raw_response=raw_response)


# ===========================================================================
# Gateway 上下文和响应
# ===========================================================================

@dataclass
class GatewayContext:
    """
    Gateway 上下文
    
    Attributes:
        channel_id: 渠道 ID
        account_id: 账户 ID
        account: 账户配置对象
        config: 完整配置
    """
    channel_id: str
    account_id: str
    account: Any  # 具体账户类型由插件定义
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayResponse:
    """
    Gateway 响应
    
    Attributes:
        code: 响应码（0 表示成功）
        message: 响应消息
        challenge: URL 验证挑战码
        data: 额外数据
    """
    code: int = 0
    message: str = "success"
    challenge: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"code": self.code, "msg": self.message}
        if self.challenge:
            result["challenge"] = self.challenge
        if self.data:
            result["data"] = self.data
        return result


# ===========================================================================
# 安全策略
# ===========================================================================

class PolicyType(str, Enum):
    """策略类型"""
    OPEN = "open"           # 开放，所有人可用
    PAIRING = "pairing"     # 需要配对验证
    ALLOWLIST = "allowlist" # 白名单模式
    DISABLED = "disabled"   # 禁用


@dataclass
class DmPolicy:
    """
    私聊策略
    
    Attributes:
        policy: 策略类型
        allow_from: 白名单列表
        policy_path: 配置路径（用于提示）
        allow_from_path: 白名单配置路径
        approve_hint: 批准提示
    """
    policy: PolicyType = PolicyType.OPEN
    allow_from: List[str] = field(default_factory=list)
    policy_path: str = ""
    allow_from_path: str = ""
    approve_hint: str = ""


@dataclass
class GroupPolicy:
    """
    群聊策略
    
    Attributes:
        policy: 策略类型
        allow_from: 群聊白名单
        require_mention: 是否需要 @机器人
        groups: 特定群组配置
    """
    policy: PolicyType = PolicyType.OPEN
    allow_from: List[str] = field(default_factory=list)
    require_mention: bool = True
    groups: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class SecurityContext:
    """
    安全检查上下文
    
    Attributes:
        channel_id: 渠道 ID
        account_id: 账户 ID
        account: 账户配置
        chat_id: 聊天 ID
        chat_type: 聊天类型
        sender_id: 发送者 ID
        sender_name: 发送者名称
        message: 原始消息
    """
    channel_id: str
    account_id: str
    account: Any
    chat_id: str
    chat_type: Literal["direct", "group", "channel"]
    sender_id: str
    sender_name: str = ""
    message: Optional[InboundMessage] = None


class SecurityResultType(str, Enum):
    """安全检查结果类型"""
    ALLOWED = "allowed"
    DENIED = "denied"
    PENDING = "pending"  # 等待配对验证


@dataclass
class SecurityResult:
    """
    安全检查结果
    
    Attributes:
        result: 结果类型
        reason: 原因说明
        reply_message: 需要回复的消息（如配对提示）
    """
    result: SecurityResultType
    reason: str = ""
    reply_message: Optional[str] = None
    
    @classmethod
    def allowed(cls) -> "SecurityResult":
        return cls(result=SecurityResultType.ALLOWED)
    
    @classmethod
    def denied(cls, reason: str, reply_message: str = None) -> "SecurityResult":
        return cls(
            result=SecurityResultType.DENIED,
            reason=reason,
            reply_message=reply_message
        )
    
    @classmethod
    def pending(cls, reason: str, reply_message: str = None) -> "SecurityResult":
        return cls(
            result=SecurityResultType.PENDING,
            reason=reason,
            reply_message=reply_message
        )
    
    @property
    def is_allowed(self) -> bool:
        return self.result == SecurityResultType.ALLOWED
