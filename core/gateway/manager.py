"""
Channel manager

Manages the lifecycle of all registered channel adapters:
start, stop, status reporting, and message routing.
"""

import asyncio
from typing import Dict, List, Optional

from logger import get_logger

from core.gateway.channel import ChannelAdapter, OnMessageCallback
from core.gateway.types import ChannelStatus, InboundMessage

logger = get_logger("gateway.manager")


class ChannelManager:
    """
    Manages all registered channel adapters.

    Responsibilities:
    - Register / unregister channel adapters
    - Start / stop all channels
    - Route inbound messages to the gateway bridge
    - Report channel status
    """

    def __init__(self) -> None:
        self._channels: Dict[str, ChannelAdapter] = {}
        self._on_message: Optional[OnMessageCallback] = None
        self._tasks: Dict[str, asyncio.Task] = {}

    def register(self, adapter: ChannelAdapter) -> None:
        """
        Register a channel adapter.

        Args:
            adapter: ChannelAdapter implementation
        """
        channel_id = adapter.id
        if channel_id in self._channels:
            logger.warning(
                "Channel already registered, replacing",
                extra={"channel": channel_id},
            )
        self._channels[channel_id] = adapter
        logger.info("Channel registered", extra={"channel": channel_id})

    def set_message_handler(self, handler: OnMessageCallback) -> None:
        """
        Set the inbound message handler (typically GatewayBridge.handle_inbound).

        Args:
            handler: async callback for inbound messages
        """
        self._on_message = handler

    async def start_all(self) -> None:
        """Start all registered and enabled channels."""
        if not self._on_message:
            raise RuntimeError("Message handler not set. Call set_message_handler() first.")

        started = []
        for channel_id, adapter in self._channels.items():
            try:
                await adapter.start(self._on_message)
                started.append(channel_id)
                logger.info("Channel started", extra={"channel": channel_id})
            except ImportError as e:
                logger.warning(
                    "Channel unavailable (optional dependency missing)",
                    extra={"channel": channel_id, "error": str(e)},
                )
            except Exception as e:
                logger.warning(
                    "Failed to start channel (missing dependency is non-fatal)",
                    extra={"channel": channel_id, "error": str(e)},
                )

        if started:
            logger.info(
                "Gateway channels started",
                extra={"started": started, "total": len(self._channels)},
            )
        else:
            logger.warning("No channels started")

    async def stop_all(self) -> None:
        """Stop all running channels gracefully."""
        for channel_id, adapter in self._channels.items():
            try:
                await adapter.stop()
                logger.info("Channel stopped", extra={"channel": channel_id})
            except Exception as e:
                logger.warning(
                    "Error stopping channel",
                    extra={"channel": channel_id, "error": str(e)},
                )

        # Cancel any background tasks
        for task_id, task in self._tasks.items():
            if not task.done():
                task.cancel()
        self._tasks.clear()

        logger.info("All gateway channels stopped")

    def get_adapter(self, channel_id: str) -> Optional[ChannelAdapter]:
        """Get a registered adapter by channel ID."""
        return self._channels.get(channel_id)

    def get_all_status(self) -> Dict[str, str]:
        """
        Get status of all registered channels.

        Returns:
            Dict mapping channel_id to status string
        """
        return {
            channel_id: adapter.get_status().value
            for channel_id, adapter in self._channels.items()
        }

    def list_channels(self) -> List[Dict[str, str]]:
        """
        List all registered channels with display info.

        Returns:
            List of channel info dicts
        """
        return [
            {
                "id": adapter.id,
                "display_name": adapter.display_name,
                "status": adapter.get_status().value,
            }
            for adapter in self._channels.values()
        ]
