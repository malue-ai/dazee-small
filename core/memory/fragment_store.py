"""
FragmentMemory persistent store.

Stores extracted 10-dimension FragmentMemory objects in SQLite for
PersonaBuilder and BehaviorAnalyzer to query historical fragments.

Storage location: data/instances/{name}/store/fragments.db
Separate from memory_fts.db (search index) and instance.db (conversations).
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from sqlalchemy import Column, Float, String, Text, text as sa_text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from logger import get_logger

logger = get_logger("memory.fragment_store")

# Engine cache (class-level, shared across instances with same DB path)
_engine_cache: Dict[str, AsyncEngine] = {}


class FragmentStore:
    """
    SQLite-backed persistent store for FragmentMemory objects.

    Stores the full 10-dimension extraction results so that
    PersonaBuilder and BehaviorAnalyzer can query historical fragments
    by user_id and time range.
    """

    def __init__(self, instance_name: Optional[str] = None):
        inst = instance_name or os.getenv("AGENT_INSTANCE", "default")
        from utils.app_paths import get_instance_store_dir
        self._store_dir = get_instance_store_dir(inst)
        self._db_path = self._store_dir / "fragments.db"
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._table_ready = False

    async def _ensure_engine(self) -> None:
        """Lazy-init SQLite engine and create table if needed."""
        if self._table_ready:
            return

        cache_key = str(self._db_path)
        engine = _engine_cache.get(cache_key)
        if engine is None:
            from infra.local_store.engine import create_local_engine
            engine = create_local_engine(
                db_dir=str(self._store_dir),
                db_name="fragments.db",
                use_null_pool=True,
            )
            _engine_cache[cache_key] = engine

        self._engine = engine
        self._session_factory = async_sessionmaker(
            engine, expire_on_commit=False
        )

        # Create table if not exists
        async with engine.begin() as conn:
            await conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS fragments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    hints_json TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """))
            await conn.execute(sa_text("""
                CREATE INDEX IF NOT EXISTS idx_fragments_user_time
                ON fragments (user_id, timestamp DESC)
            """))

        self._table_ready = True
        logger.info(f"FragmentStore ready: {self._db_path}")

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
        await self._ensure_engine()

        # Serialize non-None hints into a compact JSON blob
        hints = {}
        for field_name in (
            "identity_hint", "task_hint", "time_hint", "emotion_hint",
            "relation_hint", "todo_hint", "preference_hint",
            "topic_hint", "constraint_hint", "tool_hint", "goal_hint",
        ):
            val = getattr(fragment, field_name, None)
            if val is not None:
                hints[field_name] = asdict(val)

        metadata = fragment.metadata if isinstance(fragment.metadata, dict) else {}

        async with self._get_session() as session:
            await session.execute(
                sa_text("""
                    INSERT OR REPLACE INTO fragments
                    (id, user_id, session_id, timestamp, confidence,
                     hints_json, metadata_json, created_at)
                    VALUES
                    (:id, :user_id, :session_id, :timestamp, :confidence,
                     :hints_json, :metadata_json, :created_at)
                """),
                {
                    "id": fragment.id,
                    "user_id": fragment.user_id,
                    "session_id": fragment.session_id,
                    "timestamp": fragment.timestamp.isoformat(),
                    "confidence": fragment.confidence,
                    "hints_json": json.dumps(hints, ensure_ascii=False),
                    "metadata_json": json.dumps(metadata, ensure_ascii=False),
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
        await self._ensure_engine()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        async with self._get_session() as session:
            result = await session.execute(
                sa_text("""
                    SELECT id, user_id, session_id, timestamp, confidence,
                           hints_json, metadata_json, created_at
                    FROM fragments
                    WHERE user_id = :user_id AND timestamp >= :cutoff
                    ORDER BY timestamp DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "cutoff": cutoff, "limit": limit},
            )
            rows = result.fetchall()

        fragments = []
        for row in rows:
            try:
                hints = json.loads(row[5]) if row[5] else {}
                metadata = json.loads(row[6]) if row[6] else {}
                fragments.append({
                    "id": row[0],
                    "user_id": row[1],
                    "session_id": row[2],
                    "timestamp": row[3],
                    "confidence": row[4],
                    "hints": hints,
                    "metadata": metadata,
                    "created_at": row[7],
                })
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning(f"Failed to parse fragment row: {e}")

        return fragments

    async def count_since(self, user_id: str, since: datetime) -> int:
        """Count fragments created since a given time (for trigger conditions)."""
        await self._ensure_engine()

        async with self._get_session() as session:
            result = await session.execute(
                sa_text("""
                    SELECT COUNT(*) FROM fragments
                    WHERE user_id = :user_id AND created_at >= :since
                """),
                {"user_id": user_id, "since": since.isoformat()},
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
