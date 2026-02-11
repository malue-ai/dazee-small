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
from typing import TYPE_CHECKING

from logger import get_logger

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.playbook_extraction")

# Minimum thresholds for extraction (format checks, not semantic judgment)
_MIN_ASSISTANT_CHARS = 100  # Skip if assistant response is too short
_MIN_USER_CHARS = 10  # Skip if user message is trivial


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
            await asyncio.sleep(1)  # Wait for DB commit
            result = await ctx.conversation_service.list_messages(
                ctx.conversation_id, limit=5, order="desc"
            )
            msgs = result.get("items", []) if isinstance(result, dict) else []
            for msg in msgs:
                role = getattr(msg, "role", None)
                if role == "assistant":
                    content = getattr(msg, "content", "")
                    # Content is stored as JSON string of blocks
                    blocks = content
                    if isinstance(content, str) and content.startswith("["):
                        try:
                            blocks = json.loads(content)
                        except (json.JSONDecodeError, ValueError):
                            pass
                    if isinstance(blocks, list):
                        texts = []
                        for b in blocks:
                            if isinstance(b, dict):
                                if b.get("type") == "text":
                                    texts.append(b.get("text", ""))
                                elif b.get("type") == "thinking":
                                    texts.append(b.get("thinking", ""))
                        if texts:
                            ctx.assistant_response = " ".join(texts)
                            break
                    elif isinstance(content, str) and content:
                        ctx.assistant_response = content
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

        result = await ctx.conversation_service.list_messages(
            ctx.conversation_id, limit=50
        )
        messages = result.get("items", []) if isinstance(result, dict) else []
        if not messages:
            logger.debug("Playbook extraction skipped: no messages in DB")
            return

        # Check if session had meaningful tool usage
        tool_calls = []
        for msg in messages:
            content = getattr(msg, "content", "")
            # Parse JSON string content into blocks
            blocks = content
            if isinstance(content, str) and content.startswith("["):
                try:
                    blocks = json.loads(content)
                except (ValueError, json.JSONDecodeError):
                    blocks = content
            if isinstance(blocks, list):
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls.append(block.get("name", "unknown"))
            elif isinstance(content, str) and "tool_use" in content:
                tool_calls.append("unknown_tool")

        if not tool_calls:
            logger.debug("Playbook extraction skipped: no tool calls in session")
            return

        # Build a lightweight SessionReward (without full RewardAttribution)
        from dataclasses import dataclass, field
        from typing import List

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
            session_reward, use_llm=False  # Use simple extraction, avoid extra LLM cost
        )

        if entry:
            logger.info(
                f"Playbook extracted: id={entry.id}, name={entry.name}, "
                f"tools={len(tool_calls)}"
            )

            # Emit suggestion event for frontend
            if ctx.event_manager:
                try:
                    from core.events.broadcaster import EventBroadcaster

                    broadcaster = EventBroadcaster(ctx.event_manager)
                    strategy_summary = (
                        f"工具序列: {' → '.join(tool_calls[:5])}"
                        if tool_calls
                        else entry.description
                    )
                    await broadcaster.emit_playbook_suggestion(
                        session_id=ctx.session_id,
                        playbook_id=entry.id,
                        name=entry.name,
                        description=entry.description,
                        strategy_summary=strategy_summary,
                    )
                    logger.info(f"Playbook suggestion emitted: {entry.id}")
                except Exception as e:
                    logger.warning(f"Failed to emit playbook suggestion: {e}")
        else:
            logger.debug("Playbook extraction returned None (below threshold)")

    except Exception as e:
        # Learning task: failure should never impact user experience
        logger.warning(f"Playbook extraction failed (non-critical): {e}", exc_info=True)
