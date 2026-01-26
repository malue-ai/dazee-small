"""
统一工具注册配置加载器

从 config/tool_registry.yaml 加载工具分类配置，提供统一的访问接口。

使用方式：
    from core.tool.registry_config import (
        get_core_tools,
        get_sandbox_tools,
        get_frequent_tools,
        get_tool_categories,
    )
    
    core_tools = get_core_tools()
    sandbox_tools = get_sandbox_tools()
"""

from pathlib import Path
from typing import List, Dict, Set
import yaml

from logger import get_logger

logger = get_logger("core.tool.registry_config")

# 配置文件路径（指向 config/tool_registry.yaml）
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "tool_registry.yaml"

# 缓存配置（避免重复读取文件）
_config_cache: Dict = None


def _load_config() -> Dict:
    """
    加载配置文件（带缓存）
    
    Returns:
        配置字典
    """
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    if not _CONFIG_PATH.exists():
        logger.warning(f"⚠️ 工具注册配置文件不存在: {_CONFIG_PATH}")
        _config_cache = {}
        return _config_cache
    
    try:
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            _config_cache = yaml.safe_load(f) or {}
        logger.debug(f"✅ 工具注册配置已加载: {_CONFIG_PATH}")
    except Exception as e:
        logger.error(f"❌ 加载工具注册配置失败: {e}")
        _config_cache = {}
    
    return _config_cache


def reload_config() -> None:
    """
    重新加载配置（清除缓存）
    
    用于配置文件修改后刷新
    """
    global _config_cache
    _config_cache = None
    _load_config()
    logger.info("🔄 工具注册配置已重新加载")


def get_core_tools() -> List[str]:
    """
    获取核心工具列表（Level 1，始终启用）
    
    Returns:
        核心工具名称列表
    """
    config = _load_config()
    return config.get("core_tools", []).copy()


def get_sandbox_tools() -> Set[str]:
    """
    获取沙盒工具集合（需要注入 conversation_id）
    
    Returns:
        沙盒工具名称集合
    """
    config = _load_config()
    return set(config.get("sandbox_tools", []))


def get_frequent_tools() -> List[str]:
    """
    获取常用工具列表（不延迟加载）
    
    Returns:
        常用工具名称列表
    """
    config = _load_config()
    return config.get("frequent_tools", []).copy()


def get_tool_categories() -> Dict[str, List[str]]:
    """
    获取工具类别映射（简写展开）
    
    Returns:
        类别名称 -> 工具名称列表
    """
    config = _load_config()
    return config.get("tool_categories", {}).copy()


# 导出列表
__all__ = [
    "get_core_tools",
    "get_sandbox_tools",
    "get_frequent_tools",
    "get_tool_categories",
    "reload_config",
]
