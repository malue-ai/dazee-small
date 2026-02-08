"""
Memory Flush Task — session-level personalized memory extraction

Triggered: after every chat response (fire-and-forget, never blocks user)

Strategy: session-level batch extraction
- Per-message: zero cost, no LLM calls
- Per-session: one LLM call extracts all 10-dimension hints from full conversation
- Quick pre-filter: skip trivial conversations (< 50 chars or single short turn)

This is the bridge between conversations and "越用越懂你".
"""

from typing import TYPE_CHECKING, Dict, List

from logger import get_logger

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.memory_flush")

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


@background_task("memory_flush")
async def memory_flush_task(
    ctx: "TaskContext", service: "BackgroundTaskService"
) -> None:
    """
    Extract and persist personalized memory from the conversation.

    Session-level: collects all messages, one LLM call extracts all hints.
    Fire-and-forget: runs after response is sent, does not block user.
    """
    if not ctx.user_id or not ctx.session_id:
        logger.debug("Skipping memory flush (no user_id or session_id)")
        return

    # Build full conversation messages from context
    messages = []
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

        mgr = InstanceMemoryManager(
            user_id=ctx.user_id,
            mem0_enabled=True,
        )

        await mgr.flush(ctx.session_id, messages)
        logger.info(
            f"Memory flush completed: session={ctx.session_id[:8]}..., "
            f"messages={len(messages)}"
        )
    except Exception as e:
        logger.warning(f"Memory flush failed (non-fatal): {e}")
