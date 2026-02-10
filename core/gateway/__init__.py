"""
Multi-channel gateway

Provides inbound message reception from external platforms (Telegram, Feishu, etc.)
and routes them through the Agent engine, delivering responses back to the originating channel.

Architecture:
    ChannelAdapter (Telegram/Feishu/...)
        → ChannelManager (lifecycle)
            → GatewayBridge (InboundMessage → ChatService → response)
                → DeliveryService (chunking + send back)

Usage:
    from core.gateway import create_gateway

    gateway = await create_gateway(config)
    await gateway.start()    # Start all configured channels
    ...
    await gateway.stop()     # Graceful shutdown
"""

from core.gateway.bridge import GatewayBridge
from core.gateway.channel import ChannelAdapter
from core.gateway.manager import ChannelManager
from core.gateway.types import (
    ChannelConfig,
    ChannelStatus,
    GatewayBinding,
    GatewayConfig,
    InboundMessage,
    OutboundMessage,
)

__all__ = [
    "ChannelAdapter",
    "ChannelConfig",
    "ChannelManager",
    "ChannelStatus",
    "GatewayBinding",
    "GatewayBridge",
    "GatewayConfig",
    "InboundMessage",
    "OutboundMessage",
]
