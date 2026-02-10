"""
Shared memory config loader.

Centralizes the repeated pattern of loading memory.yaml from the current
instance's config directory. Uses aiofiles for async I/O compliance.

All callers that previously did:
    _cfg_path = get_instances_dir() / _inst / "config" / "memory.yaml"
    with open(_cfg_path) as f: ...
should now call load_memory_config() instead.
"""

import os
from dataclasses import dataclass
from typing import Optional

import aiofiles
import yaml

from logger import get_logger
from utils.app_paths import get_instances_dir

logger = get_logger(__name__)


@dataclass
class MemoryConfig:
    """Parsed memory configuration from memory.yaml."""

    enabled: bool = True
    mem0_enabled: bool = True
    semantic_enabled: bool = False


async def load_memory_config(
    instance_name: Optional[str] = None,
) -> MemoryConfig:
    """
    Load memory config from the instance's memory.yaml (async).

    Args:
        instance_name: Instance name. Defaults to AGENT_INSTANCE env var.

    Returns:
        MemoryConfig with parsed values, or defaults on any failure.
    """
    inst = instance_name or os.getenv("AGENT_INSTANCE", "default")
    cfg_path = get_instances_dir() / inst / "config" / "memory.yaml"

    if not cfg_path.exists():
        return MemoryConfig()

    try:
        async with aiofiles.open(cfg_path, mode="r", encoding="utf-8") as f:
            content = await f.read()
        raw = yaml.safe_load(content) or {}
        mem_section = raw.get("memory", {})
        return MemoryConfig(
            enabled=mem_section.get("enabled", True),
            mem0_enabled=mem_section.get("mem0_enabled", True),
            semantic_enabled=mem_section.get("semantic_enabled", False),
        )
    except Exception as e:
        logger.warning(f"Failed to load memory config from {cfg_path}: {e}")
        return MemoryConfig()
