"""
Persona Build Task — conditional user persona construction.

Triggered: after every chat response (fire-and-forget, same as memory_flush).
Execution: conditional — only runs when enough new fragments have accumulated
or enough time has passed since last build.

This task reads persisted FragmentMemory objects from fragment_store,
runs PersonaBuilder to construct/update the UserPersona, and caches
the result to disk for PersonaInjector to read during context injection.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

import aiofiles

from logger import get_logger

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.persona_build")

# Trigger conditions (avoid over-computation)
_MIN_NEW_FRAGMENTS = 3  # Need >= N new fragments since last build
_MIN_BUILD_INTERVAL_MINUTES = 60  # At least N minutes between builds
_ANALYSIS_DAYS = 7  # Analyze fragments from last N days


def _get_cache_path(instance_name: Optional[str] = None) -> Path:
    """Get persona cache file path."""
    from utils.app_paths import get_instance_store_dir
    inst = instance_name or os.getenv("AGENT_INSTANCE", "default")
    return get_instance_store_dir(inst) / "persona_cache.json"


async def _load_cache(cache_path: Path) -> Dict[str, Any]:
    """Load cached persona metadata (last build time, etc.)."""
    if not cache_path.exists():
        return {}
    try:
        async with aiofiles.open(cache_path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())
    except Exception:
        return {}


async def _save_cache(cache_path: Path, data: Dict[str, Any]) -> None:
    """Save persona + metadata to cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(cache_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, default=str))


@background_task("persona_build")
async def persona_build_task(
    ctx: "TaskContext", service: "BackgroundTaskService"
) -> None:
    """
    Conditionally build/update user persona from accumulated fragments.

    Trigger conditions (all must pass):
    1. >= _MIN_NEW_FRAGMENTS new fragments since last build
    2. >= _MIN_BUILD_INTERVAL_MINUTES since last build

    When conditions are not met, exits immediately (< 1ms).
    """
    if not ctx.user_id:
        return

    cache_path = _get_cache_path()
    cache = await _load_cache(cache_path)

    # Check time interval
    last_build_str = cache.get("last_build_time")
    if last_build_str:
        try:
            last_build = datetime.fromisoformat(last_build_str)
            if datetime.now() - last_build < timedelta(
                minutes=_MIN_BUILD_INTERVAL_MINUTES
            ):
                logger.debug(
                    "Persona build skipped: too soon since last build "
                    f"({_MIN_BUILD_INTERVAL_MINUTES}min interval)"
                )
                return
        except (ValueError, TypeError):
            pass

    # Check fragment count
    try:
        from core.memory.fragment_store import get_fragment_store
        store = get_fragment_store()
        since = datetime.fromisoformat(last_build_str) if last_build_str else (
            datetime.now() - timedelta(days=_ANALYSIS_DAYS)
        )
        new_count = await store.count_since(ctx.user_id, since)
        if new_count < _MIN_NEW_FRAGMENTS:
            logger.debug(
                f"Persona build skipped: only {new_count} new fragments "
                f"(need >= {_MIN_NEW_FRAGMENTS})"
            )
            return
    except Exception as e:
        logger.warning(f"Fragment count check failed: {e}")
        return

    # Conditions met — build persona
    logger.info(
        f"Persona build triggered: {new_count} new fragments, "
        f"user={ctx.user_id}"
    )

    try:
        await _do_persona_build(ctx.user_id, cache_path)
    except Exception as e:
        logger.warning(f"Persona build failed (non-fatal): {e}")


async def _do_persona_build(user_id: str, cache_path: Path) -> None:
    """Actual persona build logic."""
    from core.memory.fragment_store import get_fragment_store

    # Load recent fragments
    store = get_fragment_store()
    raw_fragments = await store.query_recent(
        user_id=user_id, days=_ANALYSIS_DAYS, limit=50
    )

    if not raw_fragments:
        logger.debug("No fragments to build persona from")
        return

    # Convert raw dicts to FragmentMemory objects for PersonaBuilder
    from core.memory.mem0.schemas.fragment import FragmentMemory
    fragments = _dicts_to_fragments(raw_fragments)

    if not fragments:
        return

    # Build persona using existing PersonaBuilder
    from core.memory.mem0.update.persona_builder import get_persona_builder
    builder = get_persona_builder()

    persona = await builder.build_persona(
        user_id=user_id,
        fragments=fragments,
    )

    # Generate prompt text
    prompt_text = persona.to_prompt_text()

    # Save to cache
    cache_data = {
        "last_build_time": datetime.now().isoformat(),
        "user_id": user_id,
        "fragment_count": len(fragments),
        "persona_prompt": prompt_text,
        "persona_summary": {
            "inferred_role": persona.inferred_role,
            "role_confidence": persona.role_confidence,
            "mood": persona.mood,
            "stress_level": persona.stress_level,
            "response_format": persona.response_format,
        },
    }
    await _save_cache(cache_path, cache_data)

    logger.info(
        f"Persona built: user={user_id}, fragments={len(fragments)}, "
        f"role={persona.inferred_role}, prompt_chars={len(prompt_text)}"
    )


def _dicts_to_fragments(raw_list: list) -> list:
    """Convert fragment_store query results to FragmentMemory objects."""
    from datetime import datetime as dt

    from core.memory.mem0.schemas.fragment import (
        ConstraintHint,
        DayOfWeek,
        EmotionHint,
        FragmentMemory,
        GoalHint,
        IdentityHint,
        PreferenceHint,
        RelationHint,
        TaskHint,
        TimeHint,
        TimeSlot,
        TodoHint,
        ToolHint,
        TopicHint,
    )

    HINT_CLASSES = {
        "identity_hint": IdentityHint,
        "task_hint": TaskHint,
        "time_hint": TimeHint,
        "emotion_hint": EmotionHint,
        "relation_hint": RelationHint,
        "todo_hint": TodoHint,
        "preference_hint": PreferenceHint,
        "topic_hint": TopicHint,
        "constraint_hint": ConstraintHint,
        "tool_hint": ToolHint,
        "goal_hint": GoalHint,
    }

    fragments = []
    for row in raw_list:
        try:
            hints = row.get("hints", {})
            kwargs = {}
            for field_name, cls in HINT_CLASSES.items():
                data = hints.get(field_name)
                if data and isinstance(data, dict):
                    try:
                        kwargs[field_name] = cls(**data)
                    except (TypeError, ValueError):
                        pass

            ts_str = row.get("timestamp", "")
            timestamp = dt.fromisoformat(ts_str) if ts_str else dt.now()

            fragment = FragmentMemory(
                id=row["id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                message="",  # Not stored in fragment_store (too large)
                timestamp=timestamp,
                time_slot=TimeSlot.MORNING,  # Approximate
                day_of_week=DayOfWeek.MONDAY,  # Approximate
                confidence=row.get("confidence", 0.0),
                metadata=row.get("metadata", {}),
                **kwargs,
            )
            fragments.append(fragment)
        except Exception as e:
            logger.debug(f"Failed to reconstruct fragment: {e}")

    return fragments
