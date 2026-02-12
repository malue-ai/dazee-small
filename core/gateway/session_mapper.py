"""
Session mapper

Maps channel-specific identifiers to ZenFlux internal identifiers:
- channel:sender_id  → user_id
- channel:chat_id    → conversation_id

Conversation mappings use two layers:
- L1: in-memory cache (fast path)
- L2: instance-scoped JSON persistence (survives restart)
"""

import asyncio
import os
from pathlib import Path
from typing import Dict, Optional

from logger import get_logger
from utils.app_paths import get_instance_store_dir
from utils.json_file_store import JsonFileStore

logger = get_logger("gateway.session_mapper")

_STORE_FILE_NAME = "gateway_conversation_map.json"

# In-memory mapping cache (conversation_key -> conversation_id)
_conversation_cache: Dict[str, str] = {}
_store: Optional[JsonFileStore] = None
_store_loaded: bool = False
_store_lock: Optional[asyncio.Lock] = None


def _default_store_data() -> Dict[str, object]:
    return {
        "version": 1,
        "conversation_map": {},
    }


def _get_store_lock() -> asyncio.Lock:
    global _store_lock
    if _store_lock is None:
        _store_lock = asyncio.Lock()
    return _store_lock


def _normalize_segment(value: Optional[str]) -> Optional[str]:
    """Normalize key segments to avoid cache-key drift."""
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.lower() in {"none", "null"}:
        return None
    return normalized


def _get_store_path() -> Path:
    instance_name = os.getenv("AGENT_INSTANCE", "default")
    return get_instance_store_dir(instance_name) / _STORE_FILE_NAME


def _get_store() -> JsonFileStore:
    global _store
    if _store is None:
        _store = JsonFileStore(
            path=_get_store_path(),
            default_factory=_default_store_data,
        )
    return _store


async def _ensure_store_loaded() -> None:
    global _store_loaded

    if _store_loaded:
        return

    async with _get_store_lock():
        if _store_loaded:
            return

        try:
            data = await _get_store().read_async()
            stored_map = data.get("conversation_map", {})
            if isinstance(stored_map, dict):
                loaded_count = 0
                for raw_key, raw_value in stored_map.items():
                    key = _normalize_segment(str(raw_key))
                    value = _normalize_segment(str(raw_value))
                    if key and value:
                        _conversation_cache[key] = value
                        loaded_count += 1
                logger.info(
                    "Gateway conversation mappings loaded",
                    extra={
                        "count": loaded_count,
                        "store_path": str(_get_store_path()),
                    },
                )
            _store_loaded = True
        except Exception as e:
            # Keep service available even if persistence fails.
            logger.warning(
                "Failed to load gateway conversation mappings",
                extra={"error": str(e), "store_path": str(_get_store_path())},
            )
            _store_loaded = True


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
    normalized_channel = _normalize_segment(channel) or "unknown"
    normalized_chat_id = _normalize_segment(chat_id) or "unknown"
    normalized_thread_id = _normalize_segment(thread_id)

    parts = [normalized_channel, normalized_chat_id]
    if normalized_thread_id:
        parts.append(normalized_thread_id)
    return ":".join(parts)


def get_cached_conversation_id(conversation_key: str) -> Optional[str]:
    """
    Look up a cached conversation_id by conversation key.

    Args:
        conversation_key: key from build_conversation_key()

    Returns:
        ZenFlux conversation_id or None if not cached
    """
    normalized_key = _normalize_segment(conversation_key)
    if not normalized_key:
        return None
    return _conversation_cache.get(normalized_key)


async def get_conversation_id(conversation_key: str) -> Optional[str]:
    """
    Resolve conversation_id from cache/persistent mapping.

    Args:
        conversation_key: key from build_conversation_key()

    Returns:
        ZenFlux conversation_id or None if missing
    """
    normalized_key = _normalize_segment(conversation_key)
    if not normalized_key:
        return None

    cached = _conversation_cache.get(normalized_key)
    if cached:
        return cached

    await _ensure_store_loaded()
    return _conversation_cache.get(normalized_key)


def cache_conversation_id(conversation_key: str, conversation_id: str) -> None:
    """
    Cache a conversation_key → conversation_id mapping.

    Args:
        conversation_key: key from build_conversation_key()
        conversation_id: ZenFlux internal conversation_id
    """
    normalized_key = _normalize_segment(conversation_key)
    normalized_conversation_id = _normalize_segment(conversation_id)
    if not normalized_key or not normalized_conversation_id:
        return

    _conversation_cache[normalized_key] = normalized_conversation_id
    logger.debug(
        "Conversation mapping cached",
        extra={"key": normalized_key, "conversation_id": normalized_conversation_id},
    )


async def persist_conversation_id(conversation_key: str, conversation_id: str) -> None:
    """
    Cache and persist conversation mapping.

    Args:
        conversation_key: key from build_conversation_key()
        conversation_id: ZenFlux internal conversation_id
    """
    normalized_key = _normalize_segment(conversation_key)
    normalized_conversation_id = _normalize_segment(conversation_id)
    if not normalized_key or not normalized_conversation_id:
        return

    _conversation_cache[normalized_key] = normalized_conversation_id
    await _ensure_store_loaded()

    async with _get_store_lock():
        def _mutate(data: Dict[str, object]) -> None:
            raw_map = data.get("conversation_map", {})
            if not isinstance(raw_map, dict):
                raw_map = {}
            raw_map[normalized_key] = normalized_conversation_id
            data["version"] = 1
            data["conversation_map"] = raw_map

        await _get_store().update_async(_mutate)

    logger.info(
        "Conversation mapping persisted",
        extra={"key": normalized_key, "conversation_id": normalized_conversation_id},
    )


def clear_cache() -> None:
    """Clear the conversation cache."""
    global _store_loaded
    _conversation_cache.clear()
    _store_loaded = False
