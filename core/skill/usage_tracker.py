# -*- coding: utf-8 -*-
"""
Skill usage tracker — zero-overhead adaptive ranking.

Tracks which Skills are used most, enabling prompt injection ordering
that prioritizes frequently-used Skills. Design:

  - In-memory cache: read once at startup, write-back on record()
  - Async file write: non-blocking, never delays Agent response
  - Instance-scoped: data/instances/{name}/skill_usage.json
  - No background threads, no polling
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.app_paths import get_instance_data_dir

logger = logging.getLogger(__name__)


class SkillUsageTracker:
    """
    Track Skill usage frequency for adaptive prompt ordering.

    Usage data structure per skill:
        {"count": int, "last_used": float, "successes": int, "failures": int}
    """

    def __init__(self, instance_name: Optional[str] = None):
        self._instance = instance_name or os.getenv("AGENT_INSTANCE", "default")
        self._data: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
        self._dirty = False

    @property
    def _file_path(self) -> Path:
        return get_instance_data_dir(self._instance) / "skill_usage.json"

    def _ensure_loaded(self) -> None:
        """Lazy-load from disk on first access."""
        if self._loaded:
            return
        self._loaded = True
        try:
            if self._file_path.exists():
                self._data = json.loads(self._file_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"Failed to load skill usage data: {e}")
            self._data = {}

    async def record(self, skill_name: str, success: bool) -> None:
        """
        Record a Skill usage event. Async file write, non-blocking.

        Called by ToolExecutor after tool execution completes.
        """
        self._ensure_loaded()

        entry = self._data.setdefault(skill_name, {
            "count": 0, "last_used": 0.0, "successes": 0, "failures": 0,
        })
        entry["count"] += 1
        entry["last_used"] = time.time()
        if success:
            entry["successes"] += 1
        else:
            entry["failures"] += 1

        self._dirty = True

        # Async write-back (best-effort, don't block)
        try:
            import aiofiles
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self._file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self._data, ensure_ascii=False, indent=2))
            self._dirty = False
        except Exception as e:
            logger.debug(f"Failed to persist skill usage: {e}")

    def get_usage_score(self, skill_name: str) -> float:
        """
        Calculate a usage score for ranking.

        Score = count * 0.7 + recency * 0.3
        recency = 1.0 if used within 24h, decays to 0.0 over 30 days.
        """
        self._ensure_loaded()

        entry = self._data.get(skill_name)
        if not entry:
            return 0.0

        count = entry.get("count", 0)
        last_used = entry.get("last_used", 0.0)

        # Normalize count (cap at 100 for scoring purposes)
        count_score = min(count, 100) / 100.0

        # Recency: 1.0 if within 24h, linear decay to 0 over 30 days
        age_seconds = time.time() - last_used
        age_days = age_seconds / 86400.0
        recency_score = max(0.0, 1.0 - age_days / 30.0)

        return count_score * 0.7 + recency_score * 0.3

    def sort_skills(self, skills: list) -> list:
        """
        Sort SkillEntry list by usage frequency.

        Skills with higher usage scores come first.
        Never-used skills retain their original relative order at the end.
        """
        self._ensure_loaded()

        if not self._data:
            return skills  # Cold start: keep default order

        used = []
        unused = []
        for skill in skills:
            name = skill.name if hasattr(skill, "name") else str(skill)
            if name in self._data:
                used.append(skill)
            else:
                unused.append(skill)

        # Sort used skills by score descending
        used.sort(
            key=lambda s: self.get_usage_score(
                s.name if hasattr(s, "name") else str(s)
            ),
            reverse=True,
        )

        return used + unused


# Module-level singleton (per-process, lazy)
_tracker: Optional[SkillUsageTracker] = None


def get_usage_tracker(instance_name: Optional[str] = None) -> SkillUsageTracker:
    """Get or create the singleton usage tracker."""
    global _tracker
    if _tracker is None:
        _tracker = SkillUsageTracker(instance_name)
    return _tracker
