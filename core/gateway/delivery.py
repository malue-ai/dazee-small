"""
Delivery service

Handles outbound message delivery: chunking long messages,
format adaptation, and dispatching to the correct channel adapter.
"""

from typing import List, Optional

from logger import get_logger

from core.gateway.channel import ChannelAdapter

logger = get_logger("gateway.delivery")

# Per-platform message length limits (characters)
CHANNEL_MAX_LENGTH = {
    "telegram": 4096,
    "feishu": 30000,
    "slack": 40000,
    "discord": 2000,
    "wechat": 2048,
}

DEFAULT_MAX_LENGTH = 4000


def split_message(text: str, max_length: int) -> List[str]:
    """
    Split a long message into chunks that fit within platform limits.

    Prefers splitting at paragraph or sentence boundaries.

    Args:
        text: full message text
        max_length: maximum characters per chunk

    Returns:
        list of text chunks
    """
    if not text:
        return []
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to split at paragraph boundary (double newline)
        split_idx = remaining.rfind("\n\n", 0, max_length)
        if split_idx > max_length // 4:
            chunks.append(remaining[:split_idx])
            remaining = remaining[split_idx:].lstrip("\n")
            continue

        # Try to split at single newline
        split_idx = remaining.rfind("\n", 0, max_length)
        if split_idx > max_length // 4:
            chunks.append(remaining[:split_idx])
            remaining = remaining[split_idx:].lstrip("\n")
            continue

        # Try to split at sentence boundary
        for sep in ("。", ". ", "！", "! ", "？", "? "):
            split_idx = remaining.rfind(sep, 0, max_length)
            if split_idx > max_length // 4:
                split_idx += len(sep)
                chunks.append(remaining[:split_idx])
                remaining = remaining[split_idx:].lstrip()
                break
        else:
            # Hard split at max_length
            chunks.append(remaining[:max_length])
            remaining = remaining[max_length:]

    return chunks


async def deliver_text(
    adapter: ChannelAdapter,
    channel_id: str,
    to: str,
    text: str,
    thread_id: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> None:
    """
    Deliver a text response to a channel, auto-chunking if needed.

    Args:
        adapter: channel adapter to send through
        channel_id: channel identifier (for length lookup)
        to: target conversation ID
        text: full response text
        thread_id: optional thread ID
        reply_to: optional message ID to reply to
    """
    if not text:
        logger.warning("Empty text, skipping delivery", extra={"channel": channel_id})
        return

    max_length = CHANNEL_MAX_LENGTH.get(channel_id, DEFAULT_MAX_LENGTH)
    chunks = split_message(text, max_length)

    logger.info(
        "Delivering response",
        extra={
            "channel": channel_id,
            "to": to,
            "total_length": len(text),
            "chunks": len(chunks),
        },
    )

    for i, chunk in enumerate(chunks):
        try:
            await adapter.send_text(
                to=to,
                text=chunk,
                thread_id=thread_id,
                # Only reply to the original message for the first chunk
                reply_to=reply_to if i == 0 else None,
            )
        except Exception as e:
            logger.error(
                "Failed to deliver chunk",
                extra={
                    "channel": channel_id,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
