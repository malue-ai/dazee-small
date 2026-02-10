"""
Memory Flush Task — session-level personalized memory extraction

Triggered: after every chat response (fire-and-forget, never blocks user)

Strategy: session-level batch extraction
- Per-message: zero cost, no LLM calls
- Per-session: one LLM call extracts all 10-dimension hints from full conversation
- Quick pre-filter: skip trivial conversations (< 50 chars or single short turn)

Concurrency: global lock ensures only ONE flush runs at a time.
If a previous flush is still running, the new one is skipped entirely.
This prevents concurrent Mem0/SQLite writes that cause lock contention
and mem0=FAIL cascades observed in multi-turn conversations.

This is the bridge between conversations and "越用越懂你".
"""

import asyncio
from typing import TYPE_CHECKING, Dict, List

from logger import get_logger

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.memory_flush")

# Global lock: at most ONE memory flush runs at a time.
# Prevents concurrent Mem0/SQLite writes that cause "database is locked"
# and wasted embedding inference when multiple sessions flush simultaneously.
_flush_lock = asyncio.Lock()

# Quick pre-filter thresholds (format validation, not semantic judgment)
# Chinese is ~3x denser than English: 30 Chinese chars ≈ 90 English words
_MIN_TOTAL_CHARS = 30  # Skip conversations with < 30 chars total
_MIN_SINGLE_TURN_CHARS = 15  # Skip single-turn with user msg < 15 chars


def _should_skip(messages: List[Dict]) -> str:
    """
    Quick pre-filter: skip trivial conversations that won't yield
    useful memory fragments. Returns skip reason or empty string.

    These are format/length checks (allowed by LLM-First rules),
    not semantic judgment.
    """
    if not messages:
        return "no messages"

    user_msgs = [m for m in messages if m.get("role") == "user"]
    if not user_msgs:
        return "no user messages"

    total_chars = sum(len(m.get("content", "")) for m in messages)
    if total_chars < _MIN_TOTAL_CHARS:
        return f"too short ({total_chars} chars < {_MIN_TOTAL_CHARS})"

    if len(user_msgs) == 1 and len(user_msgs[0].get("content", "")) < _MIN_SINGLE_TURN_CHARS:
        return f"single short turn ({len(user_msgs[0].get('content', ''))} chars)"

    return ""


async def _load_full_conversation(conversation_id: str) -> List[Dict]:
    """Load full conversation messages from DB for memory extraction.

    Returns list of {"role": "user"/"assistant", "content": str} dicts.
    Returns empty list on failure (caller falls back to single-turn).
    """
    if not conversation_id:
        return []
    try:
        import json
        from services.conversation_service import ConversationService
        svc = ConversationService()
        result = await svc.get_conversation_messages(
            conversation_id=conversation_id, limit=100, order="asc"
        )
        raw_msgs = result.get("messages", [])
        messages = []
        for m in raw_msgs:
            # raw_msgs may be Message (Pydantic) objects or dicts;
            # use getattr() for attribute access with dict fallback.
            role = m.role if hasattr(m, "role") else m.get("role", "")
            if role not in ("user", "assistant"):
                continue
            # content is stored as JSON array of blocks; extract text parts
            content_raw = m.content if hasattr(m, "content") else m.get("content", "")
            if isinstance(content_raw, str):
                try:
                    blocks = json.loads(content_raw)
                    if isinstance(blocks, list):
                        text_parts = [
                            b.get("text", "") for b in blocks
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        content = "\n".join(text_parts)
                    else:
                        content = content_raw
                except (json.JSONDecodeError, TypeError):
                    content = content_raw
            else:
                content = str(content_raw)
            if content.strip():
                messages.append({"role": role, "content": content})
        if messages:
            logger.info(
                f"Loaded {len(messages)} messages from conversation "
                f"{conversation_id[:8]}... for memory flush"
            )
        return messages
    except Exception as e:
        logger.warning(f"Failed to load conversation history: {e}")
        return []


@background_task("memory_flush")
async def memory_flush_task(
    ctx: "TaskContext", service: "BackgroundTaskService"
) -> None:
    """
    Extract and persist personalized memory from the conversation.

    Session-level: collects all messages, one LLM call extracts all hints.
    Fire-and-forget: runs after response is sent, does not block user.

    Concurrency: skips immediately if a previous flush is still running.
    """
    if not ctx.user_id or not ctx.session_id:
        logger.debug("Skipping memory flush (no user_id or session_id)")
        return

    # Non-blocking trylock: skip if previous flush is still running
    if _flush_lock.locked():
        logger.info(
            "Memory flush skipped: previous flush still running "
            f"(session={ctx.session_id[:8]}...)"
        )
        return

    async with _flush_lock:
        await _do_memory_flush(ctx)


async def _do_memory_flush(ctx: "TaskContext") -> None:
    """Actual flush logic, called under _flush_lock."""
    # Load FULL conversation history (not just last turn).
    # This is critical: if user discusses style preferences in turn 1 but turn 2
    # is just "write an article", flush from only turn 2 misses the style info.
    messages = await _load_full_conversation(ctx.conversation_id)
    if not messages:
        # Fallback to single-turn context if DB load fails
        if ctx.user_message:
            messages.append({"role": "user", "content": ctx.user_message})
        if ctx.assistant_response:
            messages.append({"role": "assistant", "content": ctx.assistant_response})

    # Quick pre-filter: skip trivial conversations
    skip_reason = _should_skip(messages)
    if skip_reason:
        logger.debug(f"Skipping memory flush: {skip_reason}")
        return

    try:
        from core.memory.instance_memory import InstanceMemoryManager

        from utils.memory_config import load_memory_config
        mem_cfg = await load_memory_config()

        mgr = InstanceMemoryManager(
            user_id=ctx.user_id,
            mem0_enabled=mem_cfg.mem0_enabled,
            enabled=mem_cfg.enabled,
        )

        await mgr.flush(ctx.session_id, messages)
        logger.info(
            f"Memory flush completed: session={ctx.session_id[:8]}..., "
            f"messages={len(messages)}"
        )
    except Exception as e:
        logger.warning(f"Memory flush failed (non-fatal): {e}")
