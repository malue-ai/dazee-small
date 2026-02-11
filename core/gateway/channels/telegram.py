"""
Telegram channel adapter

Uses python-telegram-bot (v21+) with long polling.
No public IP required.

Includes automatic reconnection: a background watchdog task checks
polling health every ``_HEALTH_CHECK_INTERVAL`` seconds and restarts
the application when the connection is lost.
"""

import asyncio
import time
from typing import Any, List, Optional

from logger import get_logger

from core.gateway.channel import OnMessageCallback
from core.gateway.types import (
    ChannelStatus,
    ConversationInfo,
    InboundMessage,
    MediaAttachment,
    Sender,
)

logger = get_logger("gateway.channels.telegram")


class TelegramChannel:
    """
    Telegram bot adapter using long polling.

    Includes automatic reconnection: a background watchdog task checks
    polling health every ``_HEALTH_CHECK_INTERVAL`` seconds and
    restarts the polling when the connection is lost.

    Config params:
        bot_token: Telegram Bot API token (from @BotFather)
        allowed_users: list of allowed user IDs (empty = allow all)
        allowed_groups: list of allowed group IDs (empty = allow all)
    """

    _HEALTH_CHECK_INTERVAL = 30  # seconds between health checks
    _MAX_RECONNECT_BACKOFF = 120  # max backoff between reconnect attempts
    _INITIAL_RECONNECT_DELAY = 5  # first reconnect wait

    def __init__(self, config: dict) -> None:
        self._bot_token: str = config["bot_token"]
        self._allowed_users: List[str] = [
            str(uid) for uid in config.get("allowed_users", [])
        ]
        self._allowed_groups: List[str] = [
            str(gid) for gid in config.get("allowed_groups", [])
        ]
        self._application = None
        self._status: ChannelStatus = ChannelStatus.DISCONNECTED
        self._on_message: Optional[OnMessageCallback] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._should_run: bool = False
        self._consecutive_failures: int = 0

    @property
    def id(self) -> str:
        return "telegram"

    @property
    def display_name(self) -> str:
        return "Telegram"

    def get_status(self) -> ChannelStatus:
        return self._status

    async def start(self, on_message: OnMessageCallback) -> None:
        """Start Telegram bot with long polling and health watchdog."""
        try:
            from telegram import Update  # noqa: F401
            from telegram.ext import (  # noqa: F401
                Application,
                ApplicationBuilder,
                MessageHandler,
                filters,
            )
        except ImportError:
            raise ImportError(
                "python-telegram-bot is required for Telegram channel. "
                "Install it with: pip install python-telegram-bot>=21.0"
            )

        self._on_message = on_message
        self._should_run = True

        logger.info("Starting Telegram channel (long polling)")

        # Initial connection
        await self._connect_polling()

        # Start health watchdog (auto-reconnect on failure)
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop(), name="telegram_watchdog"
        )

    def _build_message_handler(self):
        """Build the Telegram message handler function."""
        from telegram import Update
        from telegram.ext import MessageHandler, filters

        async def _handle_message(update: Update, context: Any) -> None:
            """Convert Telegram Update to InboundMessage and forward."""
            if not update.message:
                return

            message = update.message
            user = message.from_user

            # Access control
            user_id_str = str(user.id)
            if self._allowed_users and user_id_str not in self._allowed_users:
                logger.debug(
                    "Telegram user not in allowed list",
                    extra={"user_id": user_id_str},
                )
                return

            chat = message.chat
            chat_id_str = str(chat.id)
            if chat.type != "private" and self._allowed_groups:
                if chat_id_str not in self._allowed_groups:
                    logger.debug(
                        "Telegram group not in allowed list",
                        extra={"chat_id": chat_id_str},
                    )
                    return

            # Determine conversation type
            if chat.type == "private":
                conv_type = "dm"
            elif chat.type in ("group", "supergroup"):
                conv_type = "group"
            else:
                conv_type = "channel"

            # Build InboundMessage
            name_parts = [user.first_name or ""]
            if user.last_name:
                name_parts.append(user.last_name)

            inbound = InboundMessage(
                message_id=str(message.message_id),
                channel="telegram",
                sender=Sender(
                    id=user_id_str,
                    name=" ".join(name_parts).strip() or None,
                    username=user.username,
                ),
                conversation=ConversationInfo(
                    id=chat_id_str,
                    type=conv_type,
                    thread_id=(
                        str(message.message_thread_id) if message.message_thread_id else None
                    ),
                    title=getattr(chat, "title", None),
                ),
                text=message.text or message.caption,
                timestamp=float(message.date.timestamp()) if message.date else time.time(),
            )

            # Process in a task to avoid blocking the polling loop
            asyncio.create_task(self._safe_handle(inbound))

        return MessageHandler(filters.TEXT | filters.CAPTION, _handle_message)

    async def _connect_polling(self) -> bool:
        """
        Create and start a fresh Application with polling. Returns True on success.

        Isolated so that the watchdog can call it for reconnection.
        """
        from telegram.ext import ApplicationBuilder

        self._status = ChannelStatus.CONNECTING

        try:
            # Build a fresh application for each (re)connection
            self._application = (
                ApplicationBuilder()
                .token(self._bot_token)
                .build()
            )

            self._application.add_handler(self._build_message_handler())

            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message"],
            )

            self._status = ChannelStatus.CONNECTED
            self._consecutive_failures = 0
            logger.info("Telegram channel started (long polling)")
            return True

        except Exception as e:
            self._status = ChannelStatus.ERROR
            self._consecutive_failures += 1
            logger.warning(
                "Telegram polling start failed",
                extra={
                    "error": str(e),
                    "consecutive_failures": self._consecutive_failures,
                },
            )
            return False

    def _is_polling_healthy(self) -> bool:
        """Check whether the Telegram polling updater is still running."""
        if self._application is None:
            return False
        if not self._application.running:
            return False
        updater = self._application.updater
        if updater is None or not updater.running:
            return False
        return True

    async def _watchdog_loop(self) -> None:
        """
        Periodically check polling health and reconnect if needed.

        Uses exponential backoff capped at ``_MAX_RECONNECT_BACKOFF``.
        """
        while self._should_run:
            try:
                await asyncio.sleep(self._HEALTH_CHECK_INTERVAL)

                if not self._should_run:
                    break

                if self._is_polling_healthy():
                    # Connection is fine
                    if self._consecutive_failures > 0:
                        logger.info(
                            "Telegram polling recovered",
                            extra={"previous_failures": self._consecutive_failures},
                        )
                        self._consecutive_failures = 0
                    continue

                # Polling lost — attempt reconnect
                delay = min(
                    self._INITIAL_RECONNECT_DELAY * (2 ** self._consecutive_failures),
                    self._MAX_RECONNECT_BACKOFF,
                )
                logger.warning(
                    "Telegram polling stopped, reconnecting",
                    extra={
                        "consecutive_failures": self._consecutive_failures,
                        "backoff_seconds": delay,
                    },
                )

                # Tear down the old application cleanly before reconnecting
                await self._teardown_application()

                await asyncio.sleep(delay)

                if not self._should_run:
                    break

                success = await self._connect_polling()
                if success:
                    logger.info("Telegram polling reconnected successfully")
                else:
                    logger.warning(
                        "Telegram polling reconnect failed, will retry",
                        extra={"consecutive_failures": self._consecutive_failures},
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Telegram watchdog unexpected error",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                await asyncio.sleep(self._HEALTH_CHECK_INTERVAL)

    # Maximum time allowed for processing a single inbound message (seconds).
    # Prevents a stuck Agent from blocking all subsequent messages.
    _MESSAGE_TIMEOUT = 300  # 5 minutes

    async def _safe_handle(self, msg: InboundMessage) -> None:
        """Safely invoke on_message callback with timeout and error handling."""
        try:
            if self._on_message:
                await asyncio.wait_for(
                    self._on_message(msg), timeout=self._MESSAGE_TIMEOUT
                )
        except asyncio.TimeoutError:
            logger.error(
                "Telegram message processing timed out",
                extra={
                    "message_id": msg.message_id,
                    "timeout_seconds": self._MESSAGE_TIMEOUT,
                },
            )
        except Exception as e:
            logger.error(
                "Error handling Telegram message",
                extra={"message_id": msg.message_id, "error": str(e)},
                exc_info=True,
            )

    async def _teardown_application(self) -> None:
        """Gracefully tear down the current application (used before reconnect)."""
        if self._application is None:
            return

        try:
            if self._application.updater and self._application.updater.running:
                await self._application.updater.stop()
            if self._application.running:
                await self._application.stop()
            await self._application.shutdown()
        except Exception as e:
            logger.warning(
                "Error tearing down Telegram application",
                extra={"error": str(e)},
            )
        finally:
            self._application = None

    async def stop(self) -> None:
        """Stop the Telegram bot and watchdog."""
        self._should_run = False

        # Cancel watchdog first
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None

        await self._teardown_application()

        self._status = ChannelStatus.DISCONNECTED
        logger.info("Telegram channel stopped")

    async def send_text(
        self,
        to: str,
        text: str,
        thread_id: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> None:
        """Send a text message via Telegram."""
        if not self._application or not self._application.bot:
            raise RuntimeError("Telegram bot not started")

        kwargs = {}
        if thread_id:
            kwargs["message_thread_id"] = int(thread_id)
        if reply_to:
            kwargs["reply_to_message_id"] = int(reply_to)

        await self._application.bot.send_message(
            chat_id=int(to),
            text=text,
            **kwargs,
        )

    async def send_media(
        self,
        to: str,
        media: Any,
        caption: str = "",
    ) -> None:
        """Send media via Telegram."""
        if not self._application or not self._application.bot:
            raise RuntimeError("Telegram bot not started")

        if isinstance(media, MediaAttachment):
            if media.type == "image" and media.url:
                await self._application.bot.send_photo(
                    chat_id=int(to),
                    photo=media.url,
                    caption=caption or None,
                )
            elif media.url:
                await self._application.bot.send_document(
                    chat_id=int(to),
                    document=media.url,
                    caption=caption or None,
                )
