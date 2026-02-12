"""
SKILL.md frontmatter parser.

Centralizes the repeated pattern of parsing YAML frontmatter from SKILL.md files.
Used by: skill loader, dynamic_loader, skill_prompt_builder, routers/skills.py.
"""

from typing import Optional

import yaml

from logger import get_logger

logger = get_logger(__name__)


def parse_skill_frontmatter(content: str) -> Optional[dict]:
    """
    Parse YAML frontmatter from SKILL.md content.

    Expects content starting with ``---`` delimiter:
        ---
        name: my_skill
        description: ...
        ---
        # Markdown body ...

    Args:
        content: Full text of SKILL.md file.

    Returns:
        Parsed frontmatter dict, or None if not found / invalid.
    """
    if not content or not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        meta = yaml.safe_load(parts[1])
        return meta if isinstance(meta, dict) else None
    except yaml.YAMLError as e:
        logger.debug(f"YAML frontmatter parse failed: {e}")
        return None
