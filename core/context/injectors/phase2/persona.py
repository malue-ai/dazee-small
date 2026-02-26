"""
PersonaInjector — user persona context injection.

Reads the cached UserPersona (built by persona_build background task)
and injects it as a <user_persona> block in the user context message.

Complements UserMemoryInjector:
- UserMemoryInjector: factual memory (MEMORY.md, user-editable)
- PersonaInjector: inferred persona (system-generated, behavioral insights)

Cache strategy: SESSION (reads from disk cache, < 1ms, no LLM cost).
Injection phase: Phase 2 - User Context Message.
Priority: 80 (below UserMemoryInjector at 90, above PlaybookHint at 70).
"""

import json
import os
from pathlib import Path
from typing import Optional

import aiofiles

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.persona")

# Max chars for persona injection (budget control)
_MAX_PERSONA_CHARS = 800


class PersonaInjector(BaseInjector):
    """
    Injects cached UserPersona into the user context message.

    The persona is pre-built by the persona_build background task
    and cached as JSON on disk. This injector just reads the cache
    — no LLM calls, no computation.
    """

    @property
    def name(self) -> str:
        return "persona"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT

    @property
    def cache_strategy(self) -> CacheStrategy:
        return CacheStrategy.SESSION

    @property
    def priority(self) -> int:
        # Below UserMemoryInjector (90), above PlaybookHint (70)
        return 80

    async def should_inject(self, context: InjectionContext) -> bool:
        """Inject if user_id is present and persona cache exists."""
        if not context.user_id:
            return False
        # Skip if intent says skip_memory (persona is also user-specific)
        intent = context.intent
        if intent and getattr(intent, "skip_memory", False):
            return False
        return True

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """Read persona from disk cache and inject."""
        persona_text = await self._load_cached_persona()

        if not persona_text:
            logger.debug("No cached persona, skipping injection")
            return InjectionResult()

        # Budget control
        if len(persona_text) > _MAX_PERSONA_CHARS:
            persona_text = persona_text[:_MAX_PERSONA_CHARS] + "\n..."

        logger.info(f"PersonaInjector: {len(persona_text)} chars")
        return InjectionResult(content=persona_text, xml_tag="user_persona")

    @staticmethod
    async def _load_cached_persona() -> Optional[str]:
        """Load persona prompt text from disk cache."""
        try:
            from utils.app_paths import get_instance_store_dir
            inst = os.getenv("AGENT_INSTANCE", "default")
            cache_path = get_instance_store_dir(inst) / "persona_cache.json"

            if not cache_path.exists():
                return None

            async with aiofiles.open(
                cache_path, "r", encoding="utf-8"
            ) as f:
                data = json.loads(await f.read())

            prompt = data.get("persona_prompt", "")
            if not prompt or len(prompt.strip()) < 10:
                return None

            return prompt

        except Exception as e:
            logger.debug(f"Failed to load persona cache: {e}")
            return None
