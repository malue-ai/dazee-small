"""
LLM 配置加载器

从 profiles.yaml 加载 LLM 超参数配置，提供给各模块使用

使用示例：
    from config.llm_config import get_llm_profile
    
    # 获取配置（同步版本，推荐在初始化时使用）
    profile = get_llm_profile("semantic_inference")
    
    # 创建 LLM 服务
    from core.llm import create_llm_service
    llm = create_llm_service(**profile)
    
    # 异步版本
    profile = await get_llm_profile_async("semantic_inference")
"""

import os
import yaml
import aiofiles
from typing import Dict, Any, Optional
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 配置加载
# ============================================================

# 全局缓存（避免重复读取文件）
_config_cache: Optional[Dict[str, Any]] = None


def _get_config_file_path() -> Path:
    """获取配置文件路径"""
    return Path(__file__).parent / "profiles.yaml"


def _load_config_sync() -> Dict[str, Any]:
    """
    同步加载 profiles.yaml 配置文件
    
    Returns:
        配置字典
        
    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: 配置文件格式错误
    """
    global _config_cache
    
    # 使用缓存
    if _config_cache is not None:
        return _config_cache
    
    config_file = _get_config_file_path()
    
    if not config_file.exists():
        raise FileNotFoundError(
            f"LLM 配置文件不存在: {config_file}\n"
            f"请创建配置文件或参考 config/llm_config/profiles.example.yaml 示例"
        )
    
    # 同步读取配置
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        if not config or "profiles" not in config:
            raise ValueError("配置文件格式错误：缺少 'profiles' 字段")
        
        _config_cache = config
        logger.info(f"✅ LLM 配置已加载: {len(config['profiles'])} 个 Profile")
        return config
        
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"配置文件格式错误: {e}")


async def _load_config_async() -> Dict[str, Any]:
    """
    异步加载 profiles.yaml 配置文件
    
    Returns:
        配置字典
        
    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: 配置文件格式错误
    """
    global _config_cache
    
    # 使用缓存
    if _config_cache is not None:
        return _config_cache
    
    config_file = _get_config_file_path()
    
    if not config_file.exists():
        raise FileNotFoundError(
            f"LLM 配置文件不存在: {config_file}\n"
            f"请创建配置文件或参考 config/llm_config/profiles.example.yaml 示例"
        )
    
    # 异步读取配置
    try:
        async with aiofiles.open(config_file, "r", encoding="utf-8") as f:
            content = await f.read()
            config = yaml.safe_load(content)
        
        if not config or "profiles" not in config:
            raise ValueError("配置文件格式错误：缺少 'profiles' 字段")
        
        _config_cache = config
        logger.info(f"✅ LLM 配置已加载: {len(config['profiles'])} 个 Profile")
        return config
        
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"配置文件格式错误: {e}")


def get_llm_profile(profile_name: str, **overrides) -> Dict[str, Any]:
    """
    同步获取指定的 LLM Profile 配置
    
    推荐在初始化、同步上下文中使用此函数。
    配置会被缓存，后续调用不会重复读取文件。
    
    Args:
        profile_name: Profile 名称（如 "semantic_inference"）
        **overrides: 覆盖参数（如 max_tokens=1000）
        
    Returns:
        LLM 配置字典，可直接传给 create_llm_service()
        
    Raises:
        KeyError: Profile 不存在
        
    Example:
        # 使用默认配置
        profile = get_llm_profile("semantic_inference")
        llm = create_llm_service(**profile)
        
        # 覆盖部分参数
        profile = get_llm_profile("semantic_inference", max_tokens=1000)
        llm = create_llm_service(**profile)
    """
    config = _load_config_sync()
    profiles = config["profiles"]
    
    if profile_name not in profiles:
        available = ", ".join(profiles.keys())
        raise KeyError(
            f"LLM Profile '{profile_name}' 不存在\n"
            f"可用的 Profile: {available}"
        )
    
    # 获取 Profile 配置
    profile = profiles[profile_name].copy()
    
    # 移除 description 字段（不传给 LLM Service）
    profile.pop("description", None)
    
    # 应用覆盖参数
    if overrides:
        profile.update(overrides)
        logger.debug(f"🔧 Profile '{profile_name}' 已覆盖参数: {list(overrides.keys())}")
    
    return profile


async def get_llm_profile_async(profile_name: str, **overrides) -> Dict[str, Any]:
    """
    异步获取指定的 LLM Profile 配置
    
    在异步上下文中使用，如果配置已缓存则直接返回。
    
    Args:
        profile_name: Profile 名称（如 "semantic_inference"）
        **overrides: 覆盖参数（如 max_tokens=1000）
        
    Returns:
        LLM 配置字典，可直接传给 create_llm_service()
        
    Raises:
        KeyError: Profile 不存在
        
    Example:
        # 使用默认配置
        profile = await get_llm_profile_async("semantic_inference")
        llm = create_llm_service(**profile)
        
        # 覆盖部分参数
        profile = await get_llm_profile_async("semantic_inference", max_tokens=1000)
        llm = create_llm_service(**profile)
    """
    config = await _load_config_async()
    profiles = config["profiles"]
    
    if profile_name not in profiles:
        available = ", ".join(profiles.keys())
        raise KeyError(
            f"LLM Profile '{profile_name}' 不存在\n"
            f"可用的 Profile: {available}"
        )
    
    # 获取 Profile 配置
    profile = profiles[profile_name].copy()
    
    # 移除 description 字段（不传给 LLM Service）
    profile.pop("description", None)
    
    # 应用覆盖参数
    if overrides:
        profile.update(overrides)
        logger.debug(f"🔧 Profile '{profile_name}' 已覆盖参数: {list(overrides.keys())}")
    
    return profile


def list_profiles() -> Dict[str, str]:
    """
    列出所有可用的 LLM Profile（同步版本）
    
    Returns:
        {profile_name: description} 字典
        
    Example:
        profiles = list_profiles()
        for name, desc in profiles.items():
            print(f"{name}: {desc}")
    """
    config = _load_config_sync()
    profiles = config["profiles"]
    
    return {
        name: profile.get("description", "无描述")
        for name, profile in profiles.items()
    }


async def list_profiles_async() -> Dict[str, str]:
    """
    列出所有可用的 LLM Profile（异步版本）
    
    Returns:
        {profile_name: description} 字典
        
    Example:
        profiles = await list_profiles_async()
        for name, desc in profiles.items():
            print(f"{name}: {desc}")
    """
    config = await _load_config_async()
    profiles = config["profiles"]
    
    return {
        name: profile.get("description", "无描述")
        for name, profile in profiles.items()
    }


def reload_config():
    """
    重新加载配置文件（同步版本）
    
    用于配置文件修改后，无需重启进程即可生效
    
    Example:
        # 修改 profiles.yaml 后
        from config.llm_config import reload_config
        reload_config()
    """
    global _config_cache
    _config_cache = None
    _load_config_sync()
    logger.info("🔄 LLM 配置已重新加载")


async def reload_config_async():
    """
    重新加载配置文件（异步版本）
    
    用于配置文件修改后，无需重启进程即可生效
    
    Example:
        # 修改 profiles.yaml 后
        from config.llm_config import reload_config_async
        await reload_config_async()
    """
    global _config_cache
    _config_cache = None
    await _load_config_async()
    logger.info("🔄 LLM 配置已重新加载")


# ============================================================
# 环境变量覆盖（可选）
# ============================================================

def get_llm_profile_from_env(
    profile_name: str,
    env_prefix: str = "LLM_"
) -> Dict[str, Any]:
    """
    从环境变量获取 LLM Profile，支持覆盖（同步版本）
    
    环境变量命名规则：
    - LLM_<PROFILE_NAME>_MODEL=claude-sonnet-4-5-20250929
    - LLM_<PROFILE_NAME>_MAX_TOKENS=8192
    - LLM_<PROFILE_NAME>_TEMPERATURE=0.5
    
    Args:
        profile_name: Profile 名称
        env_prefix: 环境变量前缀（默认 "LLM_"）
        
    Returns:
        LLM 配置字典（合并环境变量覆盖）
        
    Example:
        # 环境变量：LLM_SEMANTIC_INFERENCE_MAX_TOKENS=1000
        profile = get_llm_profile_from_env("semantic_inference")
        # profile["max_tokens"] 将是 1000
    """
    # 获取基础配置（同步）
    profile = get_llm_profile(profile_name)
    
    # 构建环境变量前缀
    env_key_prefix = f"{env_prefix}{profile_name.upper()}_"
    
    # 支持的环境变量覆盖
    env_mappings = {
        f"{env_key_prefix}MODEL": "model",
        f"{env_key_prefix}MAX_TOKENS": "max_tokens",
        f"{env_key_prefix}TEMPERATURE": "temperature",
        f"{env_key_prefix}ENABLE_THINKING": "enable_thinking",
        f"{env_key_prefix}THINKING_BUDGET": "thinking_budget",
        f"{env_key_prefix}TIMEOUT": "timeout",
        f"{env_key_prefix}MAX_RETRIES": "max_retries",
    }
    
    # 应用环境变量覆盖
    overrides = {}
    for env_key, config_key in env_mappings.items():
        env_value = os.getenv(env_key)
        if env_value is not None:
            # 类型转换
            if config_key in ["max_tokens", "thinking_budget", "max_retries"]:
                overrides[config_key] = int(env_value)
            elif config_key in ["temperature", "timeout"]:
                overrides[config_key] = float(env_value)
            elif config_key == "enable_thinking":
                overrides[config_key] = env_value.lower() in ("true", "1", "yes")
            else:
                overrides[config_key] = env_value
    
    if overrides:
        profile.update(overrides)
        logger.info(f"🌍 Profile '{profile_name}' 已应用环境变量覆盖: {list(overrides.keys())}")
    
    return profile


# ============================================================
# 导出
# ============================================================

__all__ = [
    # 同步版本（推荐）
    "get_llm_profile",
    "list_profiles",
    "reload_config",
    "get_llm_profile_from_env",
    # 异步版本
    "get_llm_profile_async",
    "list_profiles_async",
    "reload_config_async",
]
