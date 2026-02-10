"""
Gateway message types

Unified message format for multi-channel gateway.
All channel adapters convert platform-specific messages to/from these types.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ChannelStatus(str, Enum):
    """Channel connection status."""
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class Sender(BaseModel):
    """Inbound message sender info."""
    id: str = Field(..., description="Platform user ID")
    name: Optional[str] = Field(None, description="Display name")
    username: Optional[str] = Field(None, description="Username / handle")


class ConversationInfo(BaseModel):
    """Inbound message conversation context."""
    id: str = Field(..., description="Group / DM / channel ID")
    type: Literal["dm", "group", "channel"] = Field(
        "dm", description="Conversation type"
    )
    thread_id: Optional[str] = Field(None, description="Thread / topic ID")
    title: Optional[str] = Field(None, description="Group / channel title")


class MediaAttachment(BaseModel):
    """Media attachment in a message."""
    type: Literal["image", "audio", "video", "file"] = "file"
    url: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None


class InboundMessage(BaseModel):
    """
    Unified inbound message from any channel.

    Channel adapters convert platform-specific events into this format.
    """
    message_id: str = Field(..., description="Platform message ID")
    channel: str = Field(..., description="Channel identifier, e.g. 'telegram', 'feishu'")
    sender: Sender
    conversation: ConversationInfo
    text: Optional[str] = Field(None, description="Text content")
    media: Optional[List[MediaAttachment]] = Field(None, description="Media attachments")
    timestamp: float = Field(..., description="Message timestamp (epoch seconds)")
    raw: Optional[Any] = Field(None, exclude=True, description="Raw platform event for debugging")


class OutboundMessage(BaseModel):
    """
    Unified outbound message to a channel.
    """
    channel: str
    to: str = Field(..., description="Target conversation / user ID")
    thread_id: Optional[str] = None
    text: Optional[str] = None
    media: Optional[List[MediaAttachment]] = None


class ChannelConfig(BaseModel):
    """Configuration for a single channel."""
    enabled: bool = False
    params: Dict[str, Any] = Field(default_factory=dict, description="Channel-specific params")


class GatewayBinding(BaseModel):
    """Route binding: channel -> agent instance."""
    channel: str
    agent_id: str
    conversation_id: Optional[str] = Field(
        None, description="Specific conversation to bind (None = all)"
    )


class GatewayConfig(BaseModel):
    """Full gateway configuration."""
    enabled: bool = False
    channels: Dict[str, ChannelConfig] = Field(default_factory=dict)
    bindings: List[GatewayBinding] = Field(default_factory=list)
