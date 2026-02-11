"""
Feishu (Lark) channel adapter

Uses lark-oapi SDK with WebSocket long connection.
No public IP / webhook URL required.
"""

import asyncio
import json
import re
import time
from typing import Any, Optional

from logger import get_logger

from core.gateway.channel import OnMessageCallback
from core.gateway.types import (
    ChannelStatus,
    ConversationInfo,
    InboundMessage,
    Sender,
)

logger = get_logger("gateway.channels.feishu")


class FeishuChannel:
    """
    Feishu bot adapter using WebSocket long connection.

    Config params:
        app_id: Feishu application App ID
        app_secret: Feishu application App Secret
    """

    def __init__(self, config: dict) -> None:
        self._app_id: str = config["app_id"]
        self._app_secret: str = config["app_secret"]
        self._client = None
        self._ws_client = None
        self._ws_task = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._status: ChannelStatus = ChannelStatus.DISCONNECTED
        self._on_message: Optional[OnMessageCallback] = None

    @property
    def id(self) -> str:
        return "feishu"

    @property
    def display_name(self) -> str:
        return "Feishu"

    def get_status(self) -> ChannelStatus:
        return self._status

    async def start(self, on_message: OnMessageCallback) -> None:
        """Start Feishu bot with WebSocket long connection."""
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )
        except ImportError:
            raise ImportError(
                "lark-oapi is required for Feishu channel. "
                "Install it with: pip install lark-oapi>=1.3.0"
            )

        self._on_message = on_message
        self._status = ChannelStatus.CONNECTING

        logger.info("Starting Feishu channel (WebSocket)")

        # Capture the running event loop for cross-thread scheduling
        self._loop = asyncio.get_running_loop()

        # Create Feishu API client
        self._client = lark.Client.builder() \
            .app_id(self._app_id) \
            .app_secret(self._app_secret) \
            .log_level(lark.LogLevel.WARNING) \
            .build()

        # Define event handler for incoming messages
        def _handle_message_receive(data: Any) -> None:
            """Handle im.message.receive_v1 event."""
            try:
                event = data.event
                message = event.message
                sender_info = event.sender

                # Parse message content
                msg_content = json.loads(message.content)
                text = msg_content.get("text", "")

                # Skip empty messages
                if not text:
                    return

                # Determine conversation type
                chat_type = message.chat_type
                if chat_type == "p2p":
                    conv_type = "dm"
                else:
                    conv_type = "group"

                # For group chats, extract @bot mention and clean the text
                # Feishu group messages may contain @bot prefix
                if conv_type == "group" and text:
                    text = re.sub(r'@_user_\d+\s*', '', text).strip()

                if not text:
                    return

                # Build sender info
                sender_id = ""
                sender_name = None
                if sender_info and sender_info.sender_id:
                    sender_id = (
                        sender_info.sender_id.open_id
                        or sender_info.sender_id.user_id
                        or ""
                    )

                inbound = InboundMessage(
                    message_id=message.message_id,
                    channel="feishu",
                    sender=Sender(
                        id=sender_id,
                        name=sender_name,
                    ),
                    conversation=ConversationInfo(
                        id=message.chat_id,
                        type=conv_type,
                        thread_id=(
                            message.root_id
                            if hasattr(message, "root_id") and message.root_id
                            else None
                        ),
                    ),
                    text=text,
                    timestamp=float(message.create_time) / 1000
                    if message.create_time
                    else time.time(),
                )

                # Schedule async handling on the main event loop
                # This callback runs in lark SDK's background thread,
                # so we must use call_soon_threadsafe to dispatch to the main loop
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._safe_handle(inbound), self._loop
                    )

            except Exception as e:
                logger.error(
                    "Error parsing Feishu message",
                    extra={"error": str(e)},
                    exc_info=True,
                )

        # Build event handler
        event_handler = lark.EventDispatcherHandler.builder(
            "",  # Not needed for WebSocket mode (no HTTP callback)
            "",  # Not needed for WebSocket mode (no HTTP callback)
        ).register_p2_im_message_receive_v1(
            _handle_message_receive
        ).build()

        # Create WebSocket client
        self._ws_client = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.WARNING,
        )

        # Start WebSocket in a background thread.
        # lark SDK captures asyncio event loop at module-import time.
        # When imported inside FastAPI, it grabs the RUNNING loop, then
        # start() calls loop.run_until_complete() → "already running" error.
        # Fix: give the thread its own loop and patch the SDK's reference.
        def _run_ws() -> None:
            from lark_oapi.ws import client as ws_module
            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            ws_module.loop = ws_loop
            try:
                self._ws_client.start()
            except Exception as e:
                logger.error(
                    "Feishu WebSocket exited",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                self._status = ChannelStatus.DISCONNECTED

        self._ws_task = self._loop.run_in_executor(None, _run_ws)

        # Poll for WebSocket handshake completion (up to 8 seconds)
        # The lark SDK WebSocket handshake may take several seconds;
        # a fixed 2s sleep is often too short.
        poll_interval = 0.5
        max_wait = 8.0
        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            if self._ws_client._conn is not None:
                break

        if self._ws_client._conn is not None:
            self._status = ChannelStatus.CONNECTED
            logger.info(
                "Feishu channel started (WebSocket connected)",
                extra={"handshake_seconds": elapsed},
            )
        else:
            self._status = ChannelStatus.ERROR
            logger.warning(
                "Feishu channel started but WebSocket not connected after timeout",
                extra={"timeout_seconds": max_wait},
            )

    async def _safe_handle(self, msg: InboundMessage) -> None:
        """Safely invoke on_message callback with error handling."""
        try:
            if self._on_message:
                await self._on_message(msg)
        except Exception as e:
            logger.error(
                "Error handling Feishu message",
                extra={"message_id": msg.message_id, "error": str(e)},
                exc_info=True,
            )

    async def stop(self) -> None:
        """Stop the Feishu WebSocket client."""
        # lark SDK WebSocket client doesn't have a clean stop method
        # The connection will be closed when the process exits
        self._status = ChannelStatus.DISCONNECTED
        logger.info("Feishu channel stopped")

    async def send_text(
        self,
        to: str,
        text: str,
        thread_id: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> None:
        """Send a text message via Feishu."""
        if not self._client:
            raise RuntimeError("Feishu client not started")

        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )
        except ImportError:
            raise ImportError("lark-oapi is required for Feishu channel")

        content = json.dumps({"text": text}, ensure_ascii=False)

        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(to)
                .msg_type("text")
                .content(content)
                .build()
            ).build()

        # Run sync API call in executor to avoid blocking
        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._client.im.v1.message.create(request),
        )

        if not response.success():
            logger.error(
                "Failed to send Feishu message",
                extra={
                    "code": response.code,
                    "msg": response.msg,
                    "to": to,
                },
            )
            raise RuntimeError(
                f"Feishu send_text failed: code={response.code}, msg={response.msg}"
            )

    async def send_media(
        self,
        to: str,
        media: Any,
        caption: str = "",
    ) -> None:
        """Send media via Feishu (upload then send)."""
        # Feishu requires uploading images first, then sending image_key
        # For now, send caption as text if media sending is not implemented
        if caption:
            await self.send_text(to, caption)
        logger.warning("Feishu media sending not yet implemented")
