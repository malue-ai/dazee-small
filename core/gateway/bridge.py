"""
Gateway bridge

Bridges inbound channel messages to the ChatService pipeline,
consumes the event stream, accumulates the response, and delivers
it back through the originating channel.

A semaphore limits the number of Agent executions that can run
concurrently, preventing resource starvation when scheduled tasks
and multiple channel messages arrive simultaneously.
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, cast

from logger import get_logger

from core.gateway.delivery import deliver_text
from core.gateway.session_mapper import (
    build_conversation_key,
    build_user_id,
    get_conversation_id,
    persist_conversation_id,
)
from core.gateway.types import GatewayBinding, InboundMessage

if TYPE_CHECKING:
    from core.gateway.manager import ChannelManager

logger = get_logger("gateway.bridge")

# Maximum number of Agent executions that can run concurrently through
# the gateway.  This prevents a burst of inbound messages from spawning
# too many parallel LLM streams, which would starve Telegram/Feishu
# heartbeats and the event loop in general.
_MAX_CONCURRENT_AGENTS = 3


class GatewayBridge:
    """
    Bridges channel messages to the Agent engine.

    Flow:
    1. Receive InboundMessage from ChannelManager
    2. Map channel identifiers to ZenFlux user_id / conversation_id
    3. Call ChatService.chat(stream=True)
    4. Consume event stream, accumulate text deltas
    5. Deliver accumulated response back to the channel
    """

    def __init__(
        self,
        channel_manager: "ChannelManager",
        bindings: List[GatewayBinding],
    ) -> None:
        self._channel_manager = channel_manager
        self._bindings = bindings
        self._chat_service = None  # Lazy-loaded to avoid circular imports
        self._agent_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_AGENTS)

        # Build binding lookup: channel → agent_id
        self._binding_map: Dict[str, str] = {}
        for binding in bindings:
            key = binding.channel
            if binding.conversation_id:
                key = f"{binding.channel}:{binding.conversation_id}"
            self._binding_map[key] = binding.agent_id

        logger.info(
            "Gateway bridge initialized",
            extra={
                "bindings_count": len(self._binding_map),
                "default_route": "chat_service.default_agent_key when no binding",
            },
        )

    def _get_chat_service(self):
        """Lazy-load ChatService to avoid circular imports at module level."""
        if self._chat_service is None:
            from services.chat_service import get_chat_service
            self._chat_service = get_chat_service()
        return self._chat_service

    def _resolve_agent_id(self, msg: InboundMessage) -> tuple[Optional[str], str]:
        """
        Resolve which agent instance should handle this message.

        Priority:
        1. Exact channel:conversation_id binding
        2. Channel-level binding
        3. None (use default agent)
        """
        # Try exact conversation binding
        exact_key = f"{msg.channel}:{msg.conversation.id}"
        if exact_key in self._binding_map:
            return self._binding_map[exact_key], "exact_binding"

        # Try channel-level binding
        if msg.channel in self._binding_map:
            return self._binding_map[msg.channel], "channel_binding"

        return None, "default"

    @staticmethod
    def _extract_conversation_id_from_event(data: object) -> Optional[str]:
        """Extract conversation_id from heterogeneous event payloads."""
        if not isinstance(data, dict):
            return None

        direct = data.get("conversation_id")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        nested = data.get("conversation")
        if isinstance(nested, dict):
            nested_id = nested.get("id")
            if isinstance(nested_id, str) and nested_id.strip():
                return nested_id.strip()

        return None

    async def handle_inbound(self, msg: InboundMessage) -> None:
        """
        Handle an inbound message from any channel.

        This is the main entry point called by ChannelManager.

        Args:
            msg: unified inbound message
        """
        start_time = time.time()
        channel_id = msg.channel
        sender_name = msg.sender.name or msg.sender.username or msg.sender.id

        logger.info(
            "Inbound message received",
            extra={
                "channel": channel_id,
                "sender": sender_name,
                "conversation_id": msg.conversation.id,
                "text_preview": (msg.text or "")[:50],
            },
        )

        if not msg.text:
            logger.debug("Skipping non-text message", extra={"channel": channel_id})
            return

        try:
            # Acquire semaphore to limit concurrent Agent executions.
            # This ensures that multiple simultaneous channel messages
            # don't starve the event loop (Telegram polling, Feishu WS).
            async with self._agent_semaphore:
                await self._process_message(msg, channel_id, sender_name, start_time)

        except Exception as e:
            logger.error(
                "Failed to handle inbound message",
                extra={
                    "channel": channel_id,
                    "sender": sender_name,
                    "error": str(e),
                },
                exc_info=True,
            )

            # Try to send an error message back to the user
            try:
                adapter = self._channel_manager.get_adapter(channel_id)
                if adapter:
                    await adapter.send_text(
                        to=msg.conversation.id,
                        text="Sorry, an error occurred while processing your message. Please try again later.",
                    )
            except Exception:
                logger.warning("Failed to send error message to channel")

    async def _process_message(
        self,
        msg: InboundMessage,
        channel_id: str,
        sender_name: str,
        start_time: float,
    ) -> None:
        """Core message processing logic, called under the agent semaphore."""
        # 1. Map identifiers
        user_id = build_user_id(channel_id, msg.sender.id)
        binding_agent_id, binding_source = self._resolve_agent_id(msg)
        conversation_key = build_conversation_key(
            channel_id, msg.conversation.id, msg.conversation.thread_id
        )
        conversation_id = await get_conversation_id(conversation_key)

        # 2. Call ChatService
        chat_service = self._get_chat_service()
        effective_agent_id = binding_agent_id
        if effective_agent_id is None:
            try:
                effective_agent_id = chat_service.default_agent_key
            except Exception:
                effective_agent_id = None

        logger.info(
            "Gateway route resolved",
            extra={
                "channel": channel_id,
                "conversation_key": conversation_key,
                "cached_conversation_id": conversation_id,
                "thread_id": msg.conversation.thread_id,
                "agent_id": effective_agent_id or "default",
                "agent_source": binding_source,
            },
        )

        raw_stream = await chat_service.chat(
            message=msg.text,
            user_id=user_id,
            conversation_id=conversation_id,
            agent_id=effective_agent_id,
            stream=True,
            channel=channel_id,
        )
        generator = cast(AsyncGenerator[Dict[str, Any], None], raw_stream)

        # 3. Consume event stream, accumulate text
        accumulated_text = ""
        result_conversation_id = conversation_id
        current_block_type = None

        async for event in generator:
            event_type = event.get("type", "")
            data = event.get("data", {})

            if event_type == "content_start":
                content_block = data.get("content_block", {})
                current_block_type = content_block.get("type")

            elif event_type == "content_delta" and current_block_type == "text":
                delta = data.get("delta", "")
                if isinstance(delta, str):
                    accumulated_text += delta
                elif isinstance(delta, dict):
                    delta_text = delta.get("text")
                    if isinstance(delta_text, str):
                        accumulated_text += delta_text

            elif event_type == "content_stop":
                current_block_type = None

            # conversation_start is ideal, but we also accept session_start and any
            # event that carries conversation_id to avoid mapping loss.
            elif event_type in ("conversation_start", "session_start", "message_start"):
                conv_id = self._extract_conversation_id_from_event(data)
                if conv_id:
                    result_conversation_id = conv_id
                    logger.info(
                        "Conversation ID captured",
                        extra={
                            "conversation_key": conversation_key,
                            "conversation_id": conv_id,
                            "event_type": event_type,
                        },
                    )

            elif event_type in ("message_stop", "session.stopped"):
                break

        # 4. Cache conversation mapping for future messages
        if result_conversation_id and result_conversation_id != conversation_id:
            await persist_conversation_id(conversation_key, result_conversation_id)
            logger.info(
                "Conversation cached for multi-turn",
                extra={"key": conversation_key, "conversation_id": result_conversation_id},
            )

        # 5. Deliver response
        response_text = accumulated_text.strip()
        if response_text:
            adapter = self._channel_manager.get_adapter(channel_id)
            if adapter:
                await deliver_text(
                    adapter=adapter,
                    channel_id=channel_id,
                    to=msg.conversation.id,
                    text=response_text,
                    thread_id=msg.conversation.thread_id,
                    reply_to=msg.message_id,
                )
            else:
                logger.error(
                    "Channel adapter not found for delivery",
                    extra={"channel": channel_id},
                )
        else:
            logger.warning(
                "Empty response from agent, nothing to deliver",
                extra={"channel": channel_id, "user_id": user_id},
            )

        elapsed = time.time() - start_time
        logger.info(
            "Inbound message handled",
            extra={
                "channel": channel_id,
                "sender": sender_name,
                "response_length": len(response_text),
                "elapsed_seconds": round(elapsed, 2),
            },
        )
