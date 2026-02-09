"""
配置加载器

支持全局配置和实例级配置覆盖。

使用方式：
    # 获取全局配置
    config = get_config_loader()
    prompt_config = config.get_prompt_config()

    # 获取带实例覆盖的配置
    config = get_config_loader(instance_name="client_agent")
    prompt_config = config.get_prompt_config()  # 已合并实例覆盖
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
import yaml

logger = logging.getLogger(__name__)

# 配置目录路径（统一使用 app_paths，兼容打包环境）
from utils.app_paths import get_bundle_dir

CONFIG_DIR = get_bundle_dir() / "config"
INSTANCES_DIR = get_bundle_dir() / "instances"


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """
    深度合并两个字典，override 覆盖 base

    Args:
        base: 基础配置
        override: 覆盖配置

    Returns:
        合并后的配置
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


async def _load_yaml(path: Path) -> Dict[str, Any]:
    """加载 YAML 文件"""
    if not path.exists():
        return {}

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
            return yaml.safe_load(content) or {}
    except Exception as e:
        logger.warning(f"加载配置文件失败 {path}: {e}")
        return {}


class ConfigLoader:
    """
    统一配置加载器

    支持：
    - 全局配置加载
    - 实例级配置覆盖
    - 配置缓存
    """

    _instances: Dict[str, "ConfigLoader"] = {}

    def __init__(self, instance_name: Optional[str] = None):
        """
        Args:
            instance_name: 实例名称（如 "client_agent"），为 None 时只加载全局配置
        """
        self.instance_name = instance_name
        self._cache: Dict[str, Dict] = {}

        # 实例配置路径
        if instance_name:
            self.instance_dir = INSTANCES_DIR / instance_name
            self.instance_config_path = self.instance_dir / "config.yaml"
        else:
            self.instance_dir = None
            self.instance_config_path = None

    @classmethod
    def get_instance(cls, instance_name: Optional[str] = None) -> "ConfigLoader":
        """获取配置加载器单例"""
        key = instance_name or "_global_"
        if key not in cls._instances:
            cls._instances[key] = cls(instance_name)
        return cls._instances[key]

    async def _get_instance_config(self) -> Dict[str, Any]:
        """获取实例配置"""
        if not self.instance_config_path:
            return {}
        return await _load_yaml(self.instance_config_path)

    async def _get_merged_config(self, config_name: str) -> Dict[str, Any]:
        """
        获取合并后的配置

        优先级：实例配置 > 全局配置

        Args:
            config_name: 配置名称（如 "prompt_config", "capabilities"）

        Returns:
            合并后的配置
        """
        cache_key = f"{config_name}_{self.instance_name or 'global'}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # 加载全局配置
        global_config_path = CONFIG_DIR / f"{config_name}.yaml"
        global_config = await _load_yaml(global_config_path)

        # 加载实例配置中对应部分
        instance_config = await self._get_instance_config()
        instance_override = instance_config.get(config_name, {})

        # 合并
        merged = _deep_merge(global_config, instance_override)

        # 缓存
        self._cache[cache_key] = merged

        logger.debug(
            f"配置加载: {config_name}, "
            f"全局: {len(global_config)} keys, "
            f"实例覆盖: {len(instance_override)} keys"
        )

        return merged

    async def get_prompt_config(self) -> Dict[str, Any]:
        """获取提示词配置"""
        return await self._get_merged_config("prompt_config")

    async def get_capabilities_config(self) -> Dict[str, Any]:
        """获取能力配置"""
        return await self._get_merged_config("capabilities")

    async def get_llm_profiles(self) -> Dict[str, Any]:
        """获取 LLM 配置"""
        return await self._get_merged_config("llm_config/profiles")

    async def get_size_limits(self) -> Dict[str, Any]:
        """获取提示词大小限制"""
        config = await self.get_prompt_config()
        return config.get("size_limits", {})

    async def get_module_complexity_map(self) -> Dict[str, Any]:
        """获取模块复杂度映射"""
        config = await self.get_prompt_config()
        return config.get("module_complexity_map", {})

    async def get_tool_selection_config(self) -> Dict[str, Any]:
        """获取工具选择配置"""
        config = await self.get_capabilities_config()
        return config.get("tool_selection", {})

    def clear_cache(self):
        """清除配置缓存"""
        self._cache.clear()
        logger.debug(f"配置缓存已清除: {self.instance_name or 'global'}")


# 便捷函数


def get_config_loader(instance_name: Optional[str] = None) -> ConfigLoader:
    """获取配置加载器"""
    return ConfigLoader.get_instance(instance_name)


async def load_prompt_config(instance_name: Optional[str] = None) -> Dict[str, Any]:
    """加载提示词配置"""
    return await get_config_loader(instance_name).get_prompt_config()


async def load_capabilities_config(instance_name: Optional[str] = None) -> Dict[str, Any]:
    """加载能力配置"""
    return await get_config_loader(instance_name).get_capabilities_config()
