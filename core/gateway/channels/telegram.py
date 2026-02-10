"""
Telegram channel adapter

Uses python-telegram-bot (v21+) with long polling.
No public IP required.
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

    Config params:
        bot_token: Telegram Bot API token (from @BotFather)
        allowed_users: list of allowed user IDs (empty = allow all)
        allowed_groups: list of allowed group IDs (empty = allow all)
    """

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

    @property
    def id(self) -> str:
        return "telegram"

    @property
    def display_name(self) -> str:
        return "Telegram"

    def get_status(self) -> ChannelStatus:
        return self._status

    async def start(self, on_message: OnMessageCallback) -> None:
        """Start Telegram bot with long polling."""
        try:
            from telegram import Update
            from telegram.ext import (
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
        self._status = ChannelStatus.CONNECTING

        logger.info("Starting Telegram channel (long polling)")

        # Build application
        self._application = (
            ApplicationBuilder()
            .token(self._bot_token)
            .build()
        )

        # Register handler for all text messages
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

        self._application.add_handler(
            MessageHandler(filters.TEXT | filters.CAPTION, _handle_message)
        )

        # Initialize and start (manual mode, not run_polling)
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=["message"],
        )

        self._status = ChannelStatus.CONNECTED
        logger.info("Telegram channel started (long polling)")

    async def _safe_handle(self, msg: InboundMessage) -> None:
        """Safely invoke on_message callback with error handling."""
        try:
            if self._on_message:
                await self._on_message(msg)
        except Exception as e:
            logger.error(
                "Error handling Telegram message",
                extra={"message_id": msg.message_id, "error": str(e)},
                exc_info=True,
            )

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._application:
            try:
                if self._application.updater and self._application.updater.running:
                    await self._application.updater.stop()
                if self._application.running:
                    await self._application.stop()
                await self._application.shutdown()
            except Exception as e:
                logger.warning("Error stopping Telegram", extra={"error": str(e)})

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
