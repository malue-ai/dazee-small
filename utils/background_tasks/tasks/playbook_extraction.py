"""
Playbook Extraction Task — auto-extract reusable strategies from successful sessions

Triggered: after every chat response (fire-and-forget, learning task)

Strategy:
- Quick pre-filter: skip trivial or failed sessions
- Build a lightweight SessionReward from conversation metadata
- Call PlaybookManager.extract_from_session() to create DRAFT playbook
- Emit playbook_suggestion event for frontend confirmation

This closes the "learn from success" loop:
  successful session → extract strategy → user confirms → Playbook approved → future injection
"""

import asyncio
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.playbook_extraction")

# Minimum thresholds for extraction (format checks, not semantic judgment)
_MIN_ASSISTANT_CHARS = 100  # Skip if assistant response is too short
_MIN_USER_CHARS = 10  # Skip if user message is trivial

# DB retry settings for waiting on async persistence
_DB_RETRY_ATTEMPTS = 3
_DB_RETRY_INTERVAL_S = 0.5  # 0.5s → 1.0s → 1.5s (total max ~3s)


# ==================== 公用辅助函数 ====================


def _parse_content_blocks(content: Any) -> List[Dict[str, Any]]:
    """
    Parse message content into a list of block dicts.

    Handles:
    - JSON string of blocks: '[{"type":"text","text":"..."},...]'
    - Already-parsed list of dicts
    - Plain string (returns as-is wrapped in a text block)

    Returns:
        List of block dicts, each with at least a "type" key.
    """
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]

    if isinstance(content, str):
        if content.startswith("["):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return [b for b in parsed if isinstance(b, dict)]
            except (json.JSONDecodeError, ValueError):
                pass
        # Plain string → wrap as text block
        if content.strip():
            return [{"type": "text", "text": content}]

    return []


def _extract_text_from_blocks(blocks: List[Dict[str, Any]]) -> str:
    """Extract readable text from parsed content blocks."""
    texts = []
    for b in blocks:
        btype = b.get("type", "")
        if btype == "text":
            texts.append(b.get("text", ""))
        elif btype == "thinking":
            texts.append(b.get("thinking", ""))
    return " ".join(t for t in texts if t)


def _extract_tool_calls_from_blocks(blocks: List[Dict[str, Any]]) -> List[str]:
    """Extract tool call names from parsed content blocks."""
    tools = []
    for b in blocks:
        if b.get("type") == "tool_use":
            tools.append(b.get("name", "unknown"))
    return tools


def _get_items_from_result(result: Any) -> list:
    """Safely extract items list from list_messages result."""
    if result is None:
        return []
    if isinstance(result, dict):
        return result.get("items", [])
    if hasattr(result, "items"):
        items = result.items
        return items if isinstance(items, list) else []
    return []


def _should_skip(ctx: "TaskContext") -> str:
    """
    Quick pre-filter: skip sessions unlikely to yield useful strategies.
    Returns skip reason or empty string.
    """
    if not ctx.assistant_response:
        return "no assistant response"

    if len(ctx.assistant_response) < _MIN_ASSISTANT_CHARS:
        return f"assistant response too short ({len(ctx.assistant_response)} chars)"

    if len(ctx.user_message) < _MIN_USER_CHARS:
        return f"user message too short ({len(ctx.user_message)} chars)"

    return ""


async def _fetch_messages_with_retry(
    conversation_service: Any,
    conversation_id: str,
    limit: int = 50,
    order: Optional[str] = None,
) -> list:
    """
    Fetch messages from DB with retry (handles async persistence delay).
    """
    kwargs: Dict[str, Any] = {"limit": limit}
    if order:
        kwargs["order"] = order

    for attempt in range(1, _DB_RETRY_ATTEMPTS + 1):
        result = await conversation_service.list_messages(conversation_id, **kwargs)
        items = _get_items_from_result(result)
        if items:
            return items
        # Wait with increasing interval before retry
        await asyncio.sleep(_DB_RETRY_INTERVAL_S * attempt)

    return []


@background_task("playbook_extraction")
async def playbook_extraction_task(
    ctx: "TaskContext", service: "BackgroundTaskService"
) -> None:
    """
    Extract reusable playbook strategies from successful sessions.

    Flow:
    1. Pre-filter trivial sessions
    2. Fetch conversation messages to check for tool usage
    3. Build lightweight SessionReward
    4. Call PlaybookManager.extract_from_session()
    5. Emit playbook_suggestion event if extraction succeeds
    """
    # If assistant_response is empty (e.g. accumulator only had thinking/tool blocks),
    # try to extract from conversation messages in DB
    if not ctx.assistant_response and ctx.conversation_service and ctx.conversation_id:
        try:
            msgs = await _fetch_messages_with_retry(
                ctx.conversation_service, ctx.conversation_id,
                limit=5, order="desc",
            )
            for msg in msgs:
                role = getattr(msg, "role", None)
                if role == "assistant":
                    content = getattr(msg, "content", "")
                    blocks = _parse_content_blocks(content)
                    text = _extract_text_from_blocks(blocks)
                    if text:
                        ctx.assistant_response = text
                        break
        except Exception as e:
            logger.debug(f"Failed to fetch assistant response from messages: {e}")

    skip_reason = _should_skip(ctx)
    if skip_reason:
        logger.debug(f"Playbook extraction skipped: {skip_reason}")
        return

    try:
        # Fetch conversation messages to check for tool calls
        if not ctx.conversation_service:
            logger.debug("Playbook extraction skipped: no conversation_service")
            return

        messages = await _fetch_messages_with_retry(
            ctx.conversation_service, ctx.conversation_id, limit=50,
        )
        if not messages:
            logger.debug("Playbook extraction skipped: no messages in DB")
            return

        # Check if session had meaningful tool usage
        tool_calls = []
        for msg in messages:
            content = getattr(msg, "content", "")
            blocks = _parse_content_blocks(content)
            tool_calls.extend(_extract_tool_calls_from_blocks(blocks))

        if not tool_calls:
            logger.debug("Playbook extraction skipped: no tool calls in session")
            return

        # Build a lightweight SessionReward (without full RewardAttribution)
        from dataclasses import dataclass, field

        @dataclass
        class LightweightStepReward:
            action: str
            reward: float = 0.8
            is_critical: bool = False
            success: bool = True

        @dataclass
        class LightweightSessionReward:
            session_id: str
            total_reward: float = 0.8
            success: bool = True
            step_rewards: list = field(default_factory=list)
            task_type: str = "general"
            execution_strategy: str = "rvr-b"

        step_rewards = [
            LightweightStepReward(action=f"tool:{name}")
            for name in tool_calls
        ]

        session_reward = LightweightSessionReward(
            session_id=ctx.session_id,
            total_reward=0.8,  # Default reward for completed sessions with tools
            success=True,
            step_rewards=step_rewards,
        )

        # Create PlaybookManager and extract
        from core.playbook.manager import create_playbook_manager

        manager = create_playbook_manager()
        await manager.load_all_async()

        entry = await manager.extract_from_session(
            session_reward,
            use_llm=False,
            user_query=ctx.user_message,  # Preserve semantic info for Mem0 matching
        )

        if entry:
            logger.info(
                f"Playbook extracted: id={entry.id}, name={entry.name}, "
                f"tools={len(tool_calls)}"
            )

            # Push suggestion via WebSocket long connection (bypasses closed event stream)
            try:
                strategy_summary = (
                    f"工具序列: {' → '.join(tool_calls[:5])}"
                    if tool_calls
                    else entry.description
                )
                pushed = await _push_via_websocket(
                    event_name="playbook_suggestion",
                    payload={
                        "type": "playbook_suggestion",
                        "data": {
                            "playbook_id": entry.id,
                            "name": entry.name,
                            "description": entry.description,
                            "strategy_summary": strategy_summary,
                        },
                        "conversation_id": ctx.conversation_id,
                        "message_id": ctx.message_id,
                    },
                )
                if pushed:
                    logger.info(f"Playbook suggestion emitted via WebSocket: {entry.id}")
                else:
                    logger.warning(
                        f"Playbook suggestion WebSocket push failed "
                        f"(no active connections?): {entry.id}"
                    )
            except Exception as e:
                logger.warning(f"Failed to emit playbook suggestion: {e}")
        else:
            logger.debug("Playbook extraction returned None (below threshold)")

    except Exception as e:
        # Learning task: failure should never impact user experience
        logger.warning(f"Playbook extraction failed (non-critical): {e}", exc_info=True)


async def _push_via_websocket(event_name: str, payload: dict) -> bool:
    """Push event to all active WebSocket connections.

    Background tasks run after message_stop, so the chat event stream
    is already closed. This helper broadcasts via the persistent
    WebSocket ConnectionManager instead.

    Lazy imports to avoid circular dependencies.
    """
    try:
        from routers.websocket import get_connection_manager

        mgr = get_connection_manager()
        await mgr.broadcast_notification(event_name, payload)
        return mgr.active_count > 0
    except Exception as e:
        logger.warning(f"WebSocket push failed: {e}")
        return False
