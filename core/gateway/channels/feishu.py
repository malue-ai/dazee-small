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

    Includes automatic reconnection: a background watchdog task checks
    connection health every ``_HEALTH_CHECK_INTERVAL`` seconds and
    restarts the WebSocket thread when the connection is lost.

    Config params:
        app_id: Feishu application App ID
        app_secret: Feishu application App Secret
    """

    _HEALTH_CHECK_INTERVAL = 30  # seconds between health checks
    _MAX_RECONNECT_BACKOFF = 120  # max backoff between reconnect attempts
    _INITIAL_RECONNECT_DELAY = 5  # first reconnect wait

    def __init__(self, config: dict) -> None:
        self._app_id: str = config["app_id"]
        self._app_secret: str = config["app_secret"]
        self._client = None
        self._ws_client = None
        self._ws_task = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._status: ChannelStatus = ChannelStatus.DISCONNECTED
        self._on_message: Optional[OnMessageCallback] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._should_run: bool = False
        self._consecutive_failures: int = 0

    @property
    def id(self) -> str:
        return "feishu"

    @property
    def display_name(self) -> str:
        return "Feishu"

    def get_status(self) -> ChannelStatus:
        return self._status

    async def start(self, on_message: OnMessageCallback) -> None:
        """Start Feishu bot with WebSocket long connection and health watchdog."""
        try:
            import lark_oapi as lark  # noqa: F401
        except ImportError:
            raise ImportError(
                "lark-oapi is required for Feishu channel. "
                "Install it with: pip install lark-oapi>=1.3.0"
            )

        self._on_message = on_message
        self._should_run = True
        self._status = ChannelStatus.CONNECTING

        logger.info("Starting Feishu channel (WebSocket)")

        # Capture the running event loop for cross-thread scheduling
        self._loop = asyncio.get_running_loop()

        # Create Feishu REST API client (reused across reconnects)
        self._client = lark.Client.builder() \
            .app_id(self._app_id) \
            .app_secret(self._app_secret) \
            .log_level(lark.LogLevel.WARNING) \
            .build()

        # Initial connection
        await self._connect_ws()

        # Start health watchdog (auto-reconnect on failure)
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop(), name="feishu_watchdog"
        )

    def _build_event_handler(self):
        """Build lark event handler for incoming messages."""
        import lark_oapi as lark

        def _handle_message_receive(data: Any) -> None:
            """Handle im.message.receive_v1 event."""
            try:
                logger.info("Feishu event received (im.message.receive_v1)")

                event = data.event
                message = event.message
                sender_info = event.sender

                logger.debug(
                    "Feishu message details",
                    extra={
                        "msg_type": getattr(message, "msg_type", "unknown"),
                        "chat_type": getattr(message, "chat_type", "unknown"),
                        "message_id": getattr(message, "message_id", ""),
                    },
                )

                # Parse message content
                msg_content = json.loads(message.content)
                text = msg_content.get("text", "")

                # Skip empty messages
                if not text:
                    logger.debug(
                        "Skipping empty Feishu message",
                        extra={"msg_type": getattr(message, "msg_type", "unknown")},
                    )
                    return

                # Determine conversation type
                chat_type = message.chat_type
                if chat_type == "p2p":
                    conv_type = "dm"
                else:
                    conv_type = "group"

                # For group chats, extract @bot mention and clean the text
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

                # Schedule async handling on the main event loop.
                # This callback runs in lark SDK's background thread.
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

        event_handler = lark.EventDispatcherHandler.builder(
            "",  # Not needed for WebSocket mode
            "",  # Not needed for WebSocket mode
        ).register_p2_im_message_receive_v1(
            _handle_message_receive
        ).build()

        return event_handler

    async def _connect_ws(self) -> bool:
        """
        Create and start a fresh WebSocket client. Returns True on success.

        Isolated so that the watchdog can call it for reconnection.
        """
        import lark_oapi as lark

        self._status = ChannelStatus.CONNECTING

        event_handler = self._build_event_handler()

        self._ws_client = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.WARNING,
        )

        # Start WebSocket in a background thread.
        # lark SDK captures asyncio event loop at module-import time;
        # give the thread its own loop and patch the SDK's reference.
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
            finally:
                # Always mark disconnected so the watchdog can pick it up
                self._status = ChannelStatus.DISCONNECTED

        self._ws_task = self._loop.run_in_executor(None, _run_ws)

        # Poll for WebSocket handshake completion (up to 8 seconds)
        poll_interval = 0.5
        max_wait = 8.0
        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            if self._ws_client and self._ws_client._conn is not None:
                break

        if self._ws_client and self._ws_client._conn is not None:
            self._status = ChannelStatus.CONNECTED
            self._consecutive_failures = 0
            logger.info(
                "Feishu WebSocket connected",
                extra={"handshake_seconds": round(elapsed, 1)},
            )
            return True

        self._status = ChannelStatus.ERROR
        self._consecutive_failures += 1
        logger.warning(
            "Feishu WebSocket handshake timeout",
            extra={
                "timeout_seconds": max_wait,
                "consecutive_failures": self._consecutive_failures,
            },
        )
        return False

    def _is_ws_healthy(self) -> bool:
        """Check whether the WebSocket connection is still alive."""
        if self._ws_client is None:
            return False
        conn = getattr(self._ws_client, "_conn", None)
        if conn is None:
            return False
        # lark SDK's _conn has a .closed property on the underlying websocket
        if hasattr(conn, "closed") and conn.closed:
            return False
        return True

    async def _watchdog_loop(self) -> None:
        """
        Periodically check WebSocket health and reconnect if needed.

        Uses exponential backoff capped at ``_MAX_RECONNECT_BACKOFF``.
        """
        while self._should_run:
            try:
                await asyncio.sleep(self._HEALTH_CHECK_INTERVAL)

                if not self._should_run:
                    break

                if self._is_ws_healthy():
                    # Connection is fine
                    if self._consecutive_failures > 0:
                        logger.info(
                            "Feishu WebSocket recovered",
                            extra={"previous_failures": self._consecutive_failures},
                        )
                        self._consecutive_failures = 0
                    continue

                # Connection lost — attempt reconnect
                delay = min(
                    self._INITIAL_RECONNECT_DELAY * (2 ** self._consecutive_failures),
                    self._MAX_RECONNECT_BACKOFF,
                )
                logger.warning(
                    "Feishu WebSocket disconnected, reconnecting",
                    extra={
                        "consecutive_failures": self._consecutive_failures,
                        "backoff_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)

                if not self._should_run:
                    break

                success = await self._connect_ws()
                if success:
                    logger.info("Feishu WebSocket reconnected successfully")
                else:
                    logger.warning(
                        "Feishu WebSocket reconnect failed, will retry",
                        extra={"consecutive_failures": self._consecutive_failures},
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Feishu watchdog unexpected error",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                await asyncio.sleep(self._HEALTH_CHECK_INTERVAL)

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
        """Stop the Feishu WebSocket client and watchdog."""
        self._should_run = False

        # Cancel watchdog first
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None

        # lark SDK WebSocket client doesn't have a clean stop method;
        # the connection will be closed when the process exits.
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
