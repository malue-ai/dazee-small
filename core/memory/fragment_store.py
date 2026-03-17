"""
FragmentMemory persistent store.

Stores extracted 10-dimension FragmentMemory objects in SQLite for
PersonaBuilder and BehaviorAnalyzer to query historical fragments.

Uses the main shared engine (zenflux.db) via get_local_session_factory().
Fragments are isolated by instance_id.
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from logger import get_logger

logger = get_logger("memory.fragment_store")


def _to_jsonable(value: Any) -> Any:
    """Recursively convert common non-JSON types to JSON-safe values."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    return value


def _safe_json_dumps(payload: Any) -> str:
    """Serialize payload to JSON with best-effort fallback for unknown objects."""
    return json.dumps(_to_jsonable(payload), ensure_ascii=False, default=str)


class FragmentStore:
    """
    SQLite-backed persistent store for FragmentMemory objects.

    Uses the main shared engine (zenflux.db). Stores the full 10-dimension
    extraction results so that PersonaBuilder and BehaviorAnalyzer can
    query historical fragments by user_id and time range.
    """

    def __init__(self, instance_name: Optional[str] = None):
        self._instance_name = instance_name or os.getenv("AGENT_INSTANCE", "default")
        self._session_factory: Optional[async_sessionmaker] = None
        self._ready = False

    async def _ensure_ready(self) -> None:
        """Lazy-init session factory from main engine."""
        if self._ready:
            return
        from infra.local_store.engine import get_local_session_factory

        self._session_factory = await get_local_session_factory()
        self._ready = True
        logger.debug(f"FragmentStore ready: instance={self._instance_name}")

    def _get_session(self) -> AsyncSession:
        """Get a new async session."""
        if not self._session_factory:
            raise RuntimeError("FragmentStore not initialized")
        return self._session_factory()

    async def save(self, fragment: Any) -> None:
        """
        Persist a FragmentMemory to SQLite.

        Serializes the 10 hint fields into a single JSON blob.
        Only stores hints that are not None.

        Args:
            fragment: FragmentMemory dataclass instance.
        """
        await self._ensure_ready()

        # Serialize non-None hints into a compact JSON blob
        hints = {}
        for field_name in (
            "identity_hint",
            "task_hint",
            "time_hint",
            "emotion_hint",
            "relation_hint",
            "todo_hint",
            "preference_hint",
            "topic_hint",
            "constraint_hint",
            "tool_hint",
            "goal_hint",
        ):
            val = getattr(fragment, field_name, None)
            if val is not None:
                hints[field_name] = _to_jsonable(asdict(val))

        metadata = (
            _to_jsonable(fragment.metadata)
            if isinstance(fragment.metadata, dict)
            else {}
        )

        async with self._get_session() as session:
            await session.execute(
                sa_text("""
                    INSERT OR REPLACE INTO fragments
                    (id, instance_id, user_id, session_id, timestamp, confidence,
                     hints_json, metadata_json, created_at)
                    VALUES
                    (:id, :instance_id, :user_id, :session_id, :timestamp, :confidence,
                     :hints_json, :metadata_json, :created_at)
                """),
                {
                    "id": fragment.id,
                    "instance_id": self._instance_name,
                    "user_id": fragment.user_id,
                    "session_id": fragment.session_id,
                    "timestamp": fragment.timestamp.isoformat(),
                    "confidence": fragment.confidence,
                    "hints_json": _safe_json_dumps(hints),
                    "metadata_json": _safe_json_dumps(metadata),
                    "created_at": fragment.created_at.isoformat(),
                },
            )
            await session.commit()

        logger.debug(
            f"Fragment saved: id={fragment.id[:12]}, "
            f"hints={len(hints)}, confidence={fragment.confidence:.2f}"
        )

    async def query_recent(
        self,
        user_id: str,
        days: int = 7,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Query recent fragments for a user.

        Returns raw dicts with deserialized hints_json.
        Used by PersonaBuilder and BehaviorAnalyzer.

        Args:
            user_id: User identifier.
            days: Look back N days.
            limit: Max fragments to return.

        Returns:
            List of fragment dicts, ordered by timestamp DESC.
        """
        await self._ensure_ready()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with self._get_session() as session:
            result = await session.execute(
                sa_text("""
                    SELECT id, user_id, session_id, timestamp, confidence,
                           hints_json, metadata_json, created_at
                    FROM fragments
                    WHERE instance_id = :instance_id AND user_id = :user_id
                      AND timestamp >= :cutoff
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """),
                {
                    "instance_id": self._instance_name,
                    "user_id": user_id,
                    "cutoff": cutoff,
                    "limit": limit,
                },
            )
            rows = result.fetchall()

        fragments = []
        for row in rows:
            try:
                hints = json.loads(row[5]) if row[5] else {}
                metadata = json.loads(row[6]) if row[6] else {}
                fragments.append(
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "session_id": row[2],
                        "timestamp": row[3],
                        "confidence": row[4],
                        "hints": hints,
                        "metadata": metadata,
                        "created_at": row[7],
                    }
                )
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning(f"Failed to parse fragment row: {e}")

        return fragments

    async def count_since(self, user_id: str, since: datetime) -> int:
        """Count fragments created since a given time (for trigger conditions)."""
        await self._ensure_ready()

        async with self._get_session() as session:
            result = await session.execute(
                sa_text("""
                    SELECT COUNT(*) FROM fragments
                    WHERE instance_id = :instance_id AND user_id = :user_id
                      AND created_at >= :since
                """),
                {
                    "instance_id": self._instance_name,
                    "user_id": user_id,
                    "since": since.isoformat(),
                },
            )
            return result.scalar() or 0


# ==================== Singleton ====================

_store_cache: Dict[str, FragmentStore] = {}


def get_fragment_store(instance_name: Optional[str] = None) -> FragmentStore:
    """Get or create a cached FragmentStore."""
    inst = instance_name or os.getenv("AGENT_INSTANCE", "default")
    if inst not in _store_cache:
        _store_cache[inst] = FragmentStore(instance_name=inst)
    return _store_cache[inst]
