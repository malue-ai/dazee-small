"""
统一工具注册配置加载器

优先从 config/capabilities.yaml 的 tool_classification 读取，
如果不存在则回退到 config/tool_registry.yaml（向后兼容）。

使用方式：
    from core.tool.registry_config import (
        get_core_tools,
        get_frequent_tools,
        get_tool_categories,
    )

    core_tools = get_core_tools()
"""

from pathlib import Path
from typing import Dict, List, Set

import aiofiles
import yaml

from logger import get_logger
from utils.app_paths import get_config_dir

logger = get_logger("core.tool.registry_config")

# 配置文件路径（使用统一路径管理器）
_CAPABILITIES_PATH = get_config_dir() / "capabilities.yaml"
_LEGACY_CONFIG_PATH = get_config_dir() / "tool_registry.yaml"

# 缓存配置（避免重复读取文件）
_config_cache: Dict = None


async def _load_config() -> Dict:
    """
    加载配置文件（带缓存）

    优先从 capabilities.yaml 的 tool_classification 读取，
    如果不存在则回退到 tool_registry.yaml。

    Returns:
        配置字典
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    # 1. 尝试从 capabilities.yaml 读取
    if _CAPABILITIES_PATH.exists():
        try:
            async with aiofiles.open(_CAPABILITIES_PATH, "r", encoding="utf-8") as f:
                content = await f.read()
                caps_config = yaml.safe_load(content) or {}

            tool_classification = caps_config.get("tool_classification", {})
            if tool_classification:
                # 转换格式以保持兼容
                _config_cache = {
                    "core_tools": _extract_core_tools_from_capabilities(caps_config),
                    "frequent_tools": tool_classification.get("frequent_tools", []),
                    "tool_categories": tool_classification.get("categories", {}),
                }
                logger.debug(f"✅ 从 capabilities.yaml 加载工具分类配置")
                return _config_cache
        except Exception as e:
            logger.warning(f"从 capabilities.yaml 读取 tool_classification 失败: {e}")

    # 2. 回退到 tool_registry.yaml（向后兼容）
    if _LEGACY_CONFIG_PATH.exists():
        try:
            async with aiofiles.open(_LEGACY_CONFIG_PATH, "r", encoding="utf-8") as f:
                content = await f.read()
                _config_cache = yaml.safe_load(content) or {}
            logger.debug(f"✅ 从 tool_registry.yaml 加载工具分类配置（回退）")
            return _config_cache
        except Exception as e:
            logger.error(f"❌ 加载 tool_registry.yaml 失败: {e}")

    logger.warning("⚠️ 未找到工具分类配置文件")
    _config_cache = {}
    return _config_cache


def _extract_core_tools_from_capabilities(caps_config: Dict) -> List[str]:
    """
    从 capabilities.yaml 提取 Level 1 核心工具

    Args:
        caps_config: capabilities.yaml 配置

    Returns:
        核心工具名称列表
    """
    core_tools = []
    for cap in caps_config.get("capabilities", []):
        if cap.get("level") == 1:
            core_tools.append(cap.get("name"))
    return core_tools


async def reload_config() -> None:
    """
    重新加载配置（清除缓存）

    用于配置文件修改后刷新
    """
    global _config_cache
    _config_cache = None
    await _load_config()
    logger.info("🔄 工具注册配置已重新加载")


async def get_core_tools() -> List[str]:
    """
    获取核心工具列表（Level 1，始终启用）

    Returns:
        核心工具名称列表
    """
    config = await _load_config()
    return config.get("core_tools", []).copy()


async def get_frequent_tools() -> List[str]:
    """
    获取常用工具列表（不延迟加载）

    Returns:
        常用工具名称列表
    """
    config = await _load_config()
    return config.get("frequent_tools", []).copy()


async def get_tool_categories() -> Dict[str, List[str]]:
    """
    获取工具类别映射（简写展开）

    Returns:
        类别名称 -> 工具名称列表
    """
    config = await _load_config()
    return config.get("tool_categories", {}).copy()


# 导出列表
__all__ = [
    "get_core_tools",
    "get_frequent_tools",
    "get_tool_categories",
    "reload_config",
]
