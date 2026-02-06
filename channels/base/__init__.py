"""
渠道基础模块

定义核心接口和协议
"""

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
from channels.base.capabilities import ChannelCapabilities, ChannelMeta
from channels.base.adapters import (
    ChannelConfigAdapter,
    ChannelGatewayAdapter,
    ChannelOutboundAdapter,
    ChannelSecurityAdapter,
    ChannelActionsAdapter,
    ChannelStreamingAdapter,
)
from channels.base.plugin import ChannelPlugin

__all__ = [
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
    # 功能声明
    "ChannelCapabilities",
    "ChannelMeta",
    # 适配器
    "ChannelConfigAdapter",
    "ChannelGatewayAdapter",
    "ChannelOutboundAdapter",
    "ChannelSecurityAdapter",
    "ChannelActionsAdapter",
    "ChannelStreamingAdapter",
    # 插件
    "ChannelPlugin",
]
