"""
Channel adapter protocol

Defines the interface that all channel implementations must follow.
"""

from typing import Any, Awaitable, Callable, Optional, Protocol, runtime_checkable

from core.gateway.types import ChannelStatus, InboundMessage


# Callback type: called when a channel receives a message
OnMessageCallback = Callable[[InboundMessage], Awaitable[None]]


@runtime_checkable
class ChannelAdapter(Protocol):
    """
    Channel adapter protocol.

    Each channel (Telegram, Feishu, etc.) implements this interface to:
    - Start listening for inbound messages
    - Send outbound messages back to the platform
    - Report connection status
    """

    @property
    def id(self) -> str:
        """Channel identifier, e.g. 'telegram', 'feishu'."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable channel name."""
        ...

    async def start(self, on_message: OnMessageCallback) -> None:
        """
        Start the channel: connect to platform and begin listening.

        Args:
            on_message: callback invoked for each inbound message
        """
        ...

    async def stop(self) -> None:
        """Stop the channel gracefully."""
        ...

    async def send_text(
        self,
        to: str,
        text: str,
        thread_id: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> None:
        """
        Send a text message to the platform.

        Args:
            to: target conversation / user ID
            text: message text
            thread_id: optional thread to reply in
            reply_to: optional message ID to reply to
        """
        ...

    async def send_media(
        self,
        to: str,
        media: Any,
        caption: str = "",
    ) -> None:
        """
        Send a media message to the platform.

        Args:
            to: target conversation / user ID
            media: MediaAttachment or platform-specific media object
            caption: optional caption text
        """
        ...

    def get_status(self) -> ChannelStatus:
        """Return current connection status."""
        ...
