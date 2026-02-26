"""
Memory Flush Task — session-level personalized memory extraction

Triggered: after every chat response (fire-and-forget, never blocks user)

Strategy: session-level batch extraction
- Per-message: zero cost, no LLM calls
- Per-session: one LLM call extracts all 10-dimension hints from full conversation
- Quick pre-filter: skip trivial conversations (< 30 total chars)

Concurrency: merge-queue model.
- Same conversation_id: multiple flush requests merge into ONE (last-write-wins)
- Different conversation_ids: processed sequentially (no concurrent DB writes)
- No request is silently dropped (unlike the old global-lock-skip model)

This is the bridge between conversations and "越用越懂你".
"""

import asyncio
from typing import TYPE_CHECKING, Dict, List, Optional

from logger import get_logger

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.memory_flush")

# Quick pre-filter thresholds (format validation, not semantic judgment)
# Chinese is ~3x denser than English: 30 Chinese chars ≈ 90 English words
_MIN_TOTAL_CHARS = 30  # Skip conversations with < 30 chars total (user + assistant)

# ==================== Merge Queue ====================
# Replaces the old global lock + skip model.
# Same conversation_id merges into one pending flush (dedup).
# Different conversation_ids queue up and run sequentially (no drop).

_pending_flushes: Dict[str, "TaskContext"] = {}
_flush_queue: asyncio.Queue = asyncio.Queue()
_worker_started = False
_worker_lock = asyncio.Lock()  # Protects _worker_started flag


def _should_skip(messages: List[Dict]) -> str:
    """
    Quick pre-filter: skip trivial conversations that won't yield
    useful memory fragments. Returns skip reason or empty string.

    Only checks TOTAL conversation length (user + assistant combined).
    Does NOT filter by user message length alone — short user messages
    (e.g., setting a nickname or asking about identity) can carry
    high-value info that must be persisted to MEMORY.md.
    The LLM extractor handles "nothing useful" cases by returning
    empty long_term_memories.
    """
    if not messages:
        return "no messages"

    user_msgs = [m for m in messages if m.get("role") == "user"]
    if not user_msgs:
        return "no user messages"

    total_chars = sum(len(m.get("content", "")) for m in messages)
    if total_chars < _MIN_TOTAL_CHARS:
        return f"too short ({total_chars} chars < {_MIN_TOTAL_CHARS})"

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
    Enqueue a memory flush request.

    Same conversation_id: merges with pending request (latest ctx wins,
    so the flush uses the most complete conversation history).
    Different conversation_ids: queued for sequential processing.

    A background worker drains the queue — no request is dropped.
    """
    if not ctx.user_id or not ctx.session_id:
        logger.debug("Skipping memory flush (no user_id or session_id)")
        return

    conv_id = ctx.conversation_id

    # Merge: if same conversation already pending, update to latest context
    if conv_id in _pending_flushes:
        _pending_flushes[conv_id] = ctx
        logger.debug(
            f"Memory flush merged: conversation={conv_id[:8]}... "
            f"(updated to latest context)"
        )
        return

    # Enqueue new conversation
    _pending_flushes[conv_id] = ctx
    await _flush_queue.put(conv_id)
    logger.info(
        f"Memory flush enqueued: conversation={conv_id[:8]}..., "
        f"queue_size={_flush_queue.qsize()}"
    )

    # Ensure worker is running
    await _ensure_flush_worker()


async def _ensure_flush_worker() -> None:
    """Start the background flush worker if not already running."""
    global _worker_started
    async with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        asyncio.create_task(_flush_worker())
        logger.info("Memory flush worker started")


async def _flush_worker() -> None:
    """
    Background worker that drains the flush queue sequentially.

    Processes one conversation at a time. When a conversation_id is
    dequeued, takes the LATEST context from _pending_flushes (which
    may have been updated by merge since enqueue).
    """
    global _worker_started
    try:
        while True:
            try:
                # Wait for next item, timeout 30s to allow graceful shutdown
                conv_id = await asyncio.wait_for(
                    _flush_queue.get(), timeout=30.0
                )
            except asyncio.TimeoutError:
                # No work for 30s — check if queue is truly empty and exit
                if _flush_queue.empty() and not _pending_flushes:
                    logger.debug("Memory flush worker idle, exiting")
                    break
                continue

            # Take the latest context (may have been merged/updated)
            ctx = _pending_flushes.pop(conv_id, None)
            if not ctx:
                continue

            try:
                await _do_memory_flush(ctx)
            except Exception as e:
                logger.warning(
                    f"Memory flush failed for conversation "
                    f"{conv_id[:8]}...: {e}"
                )
            finally:
                _flush_queue.task_done()
    finally:
        async with _worker_lock:
            _worker_started = False
        logger.info("Memory flush worker stopped")


async def _do_memory_flush(ctx: "TaskContext") -> None:
    """Actual flush logic — processes one conversation."""
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
        from core.memory.instance_memory import get_instance_memory_manager

        from utils.memory_config import load_memory_config
        mem_cfg = await load_memory_config()

        mgr = get_instance_memory_manager(
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
