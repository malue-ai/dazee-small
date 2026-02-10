"""
Unified YAML loading utilities.

Provides async and sync YAML loading with consistent error handling.
Replaces scattered `yaml.safe_load(open(...)) or {}` patterns across the codebase.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Union

import aiofiles
import yaml

from logger import get_logger

logger = get_logger(__name__)


async def load_yaml_async(
    path: Union[str, Path],
    default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Load a YAML file asynchronously with consistent error handling.

    Args:
        path: Path to the YAML file.
        default: Default value if file doesn't exist or parsing fails.

    Returns:
        Parsed YAML dict, or default on failure.
    """
    if default is None:
        default = {}

    path = Path(path)
    if not path.exists():
        return default

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        return yaml.safe_load(content) or default
    except Exception as e:
        logger.warning(f"Failed to load YAML from {path}: {e}")
        return default


def load_yaml_sync(
    path: Union[str, Path],
    default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Load a YAML file synchronously with consistent error handling.

    Use only for startup-time / init-time loading where async is not available.

    Args:
        path: Path to the YAML file.
        default: Default value if file doesn't exist or parsing fails.

    Returns:
        Parsed YAML dict, or default on failure.
    """
    if default is None:
        default = {}

    path = Path(path)
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or default
    except Exception as e:
        logger.warning(f"Failed to load YAML from {path}: {e}")
        return default
