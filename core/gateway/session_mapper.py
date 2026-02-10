"""
Session mapper

Maps channel-specific identifiers to ZenFlux internal identifiers:
- channel:sender_id  → user_id
- channel:chat_id    → conversation_id

Mappings are cached in-memory. On restart, new conversations are created
and re-cached on the first message from each channel chat.
"""

from typing import Dict, Optional

from logger import get_logger

logger = get_logger("gateway.session_mapper")

# In-memory mapping cache (channel_key → conversation_id)
# Populated lazily, persisted via ChatService conversation creation
_conversation_cache: Dict[str, str] = {}


def build_user_id(channel: str, sender_id: str) -> str:
    """
    Build a ZenFlux user_id from channel + platform sender ID.

    Currently all gateway channels map to the unified "local" user,
    so conversations from Telegram / Feishu / Web share the same history.

    Args:
        channel: channel identifier, e.g. "telegram"
        sender_id: platform user ID

    Returns:
        ZenFlux user_id (always "local" for single-user mode)
    """
    return "local"


def build_conversation_key(channel: str, chat_id: str, thread_id: Optional[str] = None) -> str:
    """
    Build a conversation lookup key from channel context.

    Format: "{channel}:{chat_id}" or "{channel}:{chat_id}:{thread_id}"

    Args:
        channel: channel identifier
        chat_id: platform conversation / chat / group ID
        thread_id: optional thread ID within the conversation

    Returns:
        conversation lookup key
    """
    parts = [channel, chat_id]
    if thread_id:
        parts.append(thread_id)
    return ":".join(parts)


def get_cached_conversation_id(conversation_key: str) -> Optional[str]:
    """
    Look up a cached conversation_id by conversation key.

    Args:
        conversation_key: key from build_conversation_key()

    Returns:
        ZenFlux conversation_id or None if not cached
    """
    return _conversation_cache.get(conversation_key)


def cache_conversation_id(conversation_key: str, conversation_id: str) -> None:
    """
    Cache a conversation_key → conversation_id mapping.

    Args:
        conversation_key: key from build_conversation_key()
        conversation_id: ZenFlux internal conversation_id
    """
    _conversation_cache[conversation_key] = conversation_id
    logger.debug(
        "Conversation mapping cached",
        extra={"key": conversation_key, "conversation_id": conversation_id},
    )


def clear_cache() -> None:
    """Clear the conversation cache."""
    _conversation_cache.clear()
