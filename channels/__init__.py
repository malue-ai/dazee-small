"""
通用渠道集成框架

支持飞书、钉钉、Slack、Telegram 等多渠道双向对话

架构：
    消息来源层（飞书/钉钉/Slack/Telegram）
        ↓
    Gateway 网关层（统一入口、预处理、权限检查）
        ↓
    ChannelPlugin 渠道插件层（核心抽象）
        ↓
    ChatService（Agent 调用层）
        ↓
    Outbound 发送层（回复消息）
"""

from channels.base import (
    ChannelPlugin,
    ChannelMeta,
    ChannelCapabilities,
    ChannelConfigAdapter,
    ChannelGatewayAdapter,
    ChannelOutboundAdapter,
    ChannelSecurityAdapter,
    ChannelActionsAdapter,
    ChannelStreamingAdapter,
)
from channels.base.types import (
    InboundMessage,
    ProcessedMessage,
    OutboundContext,
    DeliveryResult,
    GatewayContext,
    GatewayResponse,
    SecurityContext,
    SecurityResult,
    DmPolicy,
    GroupPolicy,
)
from channels.registry import ChannelRegistry, get_channel_registry
from channels.manager import ChannelManager, get_channel_manager

__all__ = [
    # 核心接口
    "ChannelPlugin",
    "ChannelMeta",
    "ChannelCapabilities",
    # 适配器
    "ChannelConfigAdapter",
    "ChannelGatewayAdapter",
    "ChannelOutboundAdapter",
    "ChannelSecurityAdapter",
    "ChannelActionsAdapter",
    "ChannelStreamingAdapter",
    # 类型
    "InboundMessage",
    "ProcessedMessage",
    "OutboundContext",
    "DeliveryResult",
    "GatewayContext",
    "GatewayResponse",
    "SecurityContext",
    "SecurityResult",
    "DmPolicy",
    "GroupPolicy",
    # 注册表和管理器
    "ChannelRegistry",
    "get_channel_registry",
    "ChannelManager",
    "get_channel_manager",
]
