"""
LLM 配置加载器

从 profiles.yaml 加载 LLM 超参数配置，提供给各模块使用

使用示例：
    from config.llm_config import get_llm_profile
    
    # 获取配置
    profile = get_llm_profile("semantic_inference")
    
    # 创建 LLM 服务
    from core.llm import create_llm_service
    llm = create_llm_service(**profile)
"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 配置加载
# ============================================================

# 全局缓存（避免重复读取文件）
_config_cache: Optional[Dict[str, Any]] = None
_global_override_cache: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """
    加载 profiles.yaml 配置文件
    
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
    
    # 查找配置文件（在 llm_config 子目录下）
    config_file = Path(__file__).parent / "profiles.yaml"
    
    if not config_file.exists():
        raise FileNotFoundError(
            f"LLM 配置文件不存在: {config_file}\n"
            f"请创建配置文件或参考 config/llm_config/profiles.example.yaml 示例"
        )
    
    # 读取配置
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


def _apply_env_overrides(
    profile: Dict[str, Any],
    profile_name: str,
    env_prefix: str = "LLM_"
) -> Dict[str, Any]:
    """
    应用环境变量覆盖
    """
    env_key_prefix = f"{env_prefix}{profile_name.upper()}_"
    
    env_mappings = {
        f"{env_key_prefix}MODEL": ("model", str),
        f"{env_key_prefix}MAX_TOKENS": ("max_tokens", int),
        f"{env_key_prefix}TEMPERATURE": ("temperature", float),
        f"{env_key_prefix}ENABLE_THINKING": ("enable_thinking", lambda v: v.lower() in ("true", "1", "yes")),
        f"{env_key_prefix}THINKING_BUDGET": ("thinking_budget", int),
        f"{env_key_prefix}TIMEOUT": ("timeout", float),
        f"{env_key_prefix}MAX_RETRIES": ("max_retries", int),
        f"{env_key_prefix}PROVIDER": ("provider", str),
        f"{env_key_prefix}BASE_URL": ("base_url", str),
        f"{env_key_prefix}API_KEY_ENV": ("api_key_env", str),
        f"{env_key_prefix}API_KEY": ("api_key", str),
        f"{env_key_prefix}COMPAT": ("compat", str),
    }
    
    overrides = {}
    for env_key, (config_key, cast_type) in env_mappings.items():
        env_value = os.getenv(env_key)
        if env_value is None:
            continue
        try:
            overrides[config_key] = cast_type(env_value)
        except ValueError:
            logger.warning(f"⚠️ 环境变量 {env_key} 值无效，已忽略")
    
    if overrides:
        profile.update(overrides)
        logger.info(f"🌍 Profile '{profile_name}' 已应用环境变量覆盖: {list(overrides.keys())}")
    
    return profile


def _get_global_config_path() -> Optional[Path]:
    """
    获取全局配置文件路径（config.yaml）
    """
    path_value = (
        os.getenv("LLM_GLOBAL_CONFIG_PATH")
        or os.getenv("ZENFLUX_CONFIG_PATH")
        or os.getenv("INSTANCE_CONFIG_PATH")
    )
    if path_value:
        return Path(path_value)
    
    instance_name = (
        os.getenv("ZENFLUX_INSTANCE")
        or os.getenv("INSTANCE_NAME")
        or os.getenv("AGENT_INSTANCE")
    )
    if not instance_name:
        return None
    
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "instances" / instance_name / "config.yaml"


def _load_global_override_from_config() -> Dict[str, Any]:
    """
    从 config.yaml 读取全局 LLM 切换配置
    """
    global _global_override_cache
    if _global_override_cache is not None:
        return _global_override_cache
    
    config_path = _get_global_config_path()
    if not config_path or not config_path.exists():
        _global_override_cache = {}
        return _global_override_cache
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"⚠️ 读取全局 config.yaml 失败: {e}")
        _global_override_cache = {}
        return _global_override_cache
    
    override = raw.get("llm_global", {}) if isinstance(raw, dict) else {}
    if not override or not override.get("enabled", False):
        _global_override_cache = {}
        return _global_override_cache
    
    _global_override_cache = override
    logger.info(f"✅ 已加载全局 LLM 覆盖配置: {config_path}")
    return _global_override_cache


def _apply_global_overrides(profile: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    """
    应用全局一键切换覆盖（用于全局切换 Provider）
    
    说明：
    - LLM_FORCE_PROVIDER / LLM_GLOBAL_PROVIDER 可一键切换全局 Provider
    - 若未显式指定 model，将按角色默认模型映射
    """
    provider = os.getenv("LLM_FORCE_PROVIDER") or os.getenv("LLM_GLOBAL_PROVIDER")
    global_override = {}
    if not provider:
        global_override = _load_global_override_from_config()
        provider = str(global_override.get("provider", "")).lower() if global_override else ""
    
    if not provider:
        return profile
    
    provider = provider.strip().lower()
    overrides: Dict[str, Any] = {"provider": provider}
    
    # 模型映射（未指定时）
    model = os.getenv("LLM_FORCE_MODEL") or os.getenv("LLM_GLOBAL_MODEL")
    if not model:
        model_map = global_override.get("model_map", {}) if global_override else {}
        if isinstance(model_map, dict):
            model = model_map.get(profile_name) or model_map.get("default")
        if provider == "qwen":
            if profile_name == "intent_analyzer":
                model = "qwen-plus"
            else:
                model = "qwen-max"
    if model:
        overrides["model"] = model
    
    # base_url（未指定时）
    base_url = os.getenv("LLM_FORCE_BASE_URL") or os.getenv("LLM_GLOBAL_BASE_URL")
    if not base_url and provider == "qwen":
        base_url = (
            (global_override.get("base_url") if global_override else None)
            or os.getenv("QWEN_BASE_URL")
            or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
    if base_url:
        overrides["base_url"] = base_url
    
    # api_key_env（未指定时）
    api_key_env = os.getenv("LLM_FORCE_API_KEY_ENV") or os.getenv("LLM_GLOBAL_API_KEY_ENV")
    if not api_key_env and provider == "qwen":
        api_key_env = (global_override.get("api_key_env") if global_override else None) or "QWEN_API_KEY"
    if api_key_env:
        overrides["api_key_env"] = api_key_env
    
    # compat（未指定时）
    compat = os.getenv("LLM_FORCE_COMPAT") or os.getenv("LLM_GLOBAL_COMPAT")
    if not compat and provider == "qwen":
        compat = (global_override.get("compat") if global_override else None) or "qwen"
    if compat:
        overrides["compat"] = compat
    
    profile.update(overrides)
    source = "env" if (os.getenv("LLM_FORCE_PROVIDER") or os.getenv("LLM_GLOBAL_PROVIDER")) else "config.yaml"
    logger.warning(
        f"🚨 Profile '{profile_name}' 启用全局覆盖({source}): {list(overrides.keys())}"
    )
    
    return profile


def get_llm_profile(
    profile_name: str,
    env_prefix: str = "LLM_",
    **overrides
) -> Dict[str, Any]:
    """
    获取指定的 LLM Profile 配置
    
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
    config = _load_config()
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
    
    # 环境变量覆盖（用于手动切换）
    profile = _apply_env_overrides(profile, profile_name, env_prefix=env_prefix)
    # 全局一键切换覆盖（最高优先级）
    return _apply_global_overrides(profile, profile_name)


def list_profiles() -> Dict[str, str]:
    """
    列出所有可用的 LLM Profile
    
    Returns:
        {profile_name: description} 字典
        
    Example:
        profiles = list_profiles()
        for name, desc in profiles.items():
            print(f"{name}: {desc}")
    """
    config = _load_config()
    profiles = config["profiles"]
    
    return {
        name: profile.get("description", "无描述")
        for name, profile in profiles.items()
    }


def reload_config():
    """
    重新加载配置文件
    
    用于配置文件修改后，无需重启进程即可生效
    
    Example:
        # 修改 profiles.yaml 后
        from config.llm_config import reload_config
        reload_config()
    """
    global _config_cache, _global_override_cache
    _config_cache = None
    _global_override_cache = None
    _load_config()
    logger.info("🔄 LLM 配置已重新加载")


# ============================================================
# 环境变量覆盖（可选）
# ============================================================

def get_llm_profile_from_env(
    profile_name: str,
    env_prefix: str = "LLM_"
) -> Dict[str, Any]:
    """
    从环境变量获取 LLM Profile，支持覆盖
    
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
    # 直接复用统一入口（已包含环境变量覆盖）
    return get_llm_profile(profile_name, env_prefix=env_prefix)


# ============================================================
# 🆕 V7.10 健康探测配置
# ============================================================

def get_health_probe_config() -> Dict[str, Any]:
    """
    获取健康探测配置
    
    配置优先级：
    1. 环境变量（最高优先级）
    2. profiles.yaml 中的 health_probe 配置
    3. 默认值
    
    🆕 V7.11 条件探测策略：
    - request_probe.enabled 已废弃（条件探测自动根据后台健康状态决定）
    - 后台健康 → 自动跳过请求级探测（零延迟）
    - 后台不健康 → 自动执行请求级探测确认
    
    环境变量：
    - LLM_PROBE_TIMEOUT: 条件探测超时（覆盖 request_probe.timeout_seconds）
    - LLM_HEALTH_PROBE_ENABLED: 后台探测开关（覆盖 background_probe.enabled）
    - LLM_HEALTH_PROBE_INTERVAL: 后台探测间隔（覆盖 background_probe.interval_seconds）
    - LLM_HEALTH_PROBE_TIMEOUT: 后台探测超时（覆盖 background_probe.timeout_seconds）
    - LLM_HEALTH_PROBE_PROFILES: 后台探测 Profile 列表（逗号分隔）
    
    Returns:
        健康探测配置字典
        
    Example:
        config = get_health_probe_config()
        # config = {
        #     "request_probe": {
        #         "timeout_seconds": 5.0,
        #         "max_retries": 1
        #         # 注意：V7.11 移除 enabled，改为条件探测策略
        #     },
        #     "background_probe": {
        #         "enabled": True,
        #         "interval_seconds": 30,
        #         "timeout_seconds": 10,
        #         "profiles": ["main_agent", "intent_analyzer", ...]
        #     }
        # }
    """
    config = _load_config()
    
    # 获取 YAML 配置（如果存在）
    yaml_config = config.get("health_probe", {})
    
    # 默认值（V7.11：移除 request_probe.enabled，改为条件探测策略）
    default_config = {
        "request_probe": {
            # V7.11：enabled 已废弃，条件探测自动根据后台健康状态决定
            "timeout_seconds": 5.0,
            "max_retries": 1,
        },
        "background_probe": {
            "enabled": True,
            "interval_seconds": 30,
            "timeout_seconds": 10,
            "profiles": ["main_agent", "intent_analyzer", "lead_agent", "worker_agent", "critic_agent"],
        }
    }
    
    # 合并 YAML 配置
    result = default_config.copy()
    if yaml_config:
        if "request_probe" in yaml_config:
            result["request_probe"].update(yaml_config["request_probe"])
        if "background_probe" in yaml_config:
            result["background_probe"].update(yaml_config["background_probe"])
    
    # 应用环境变量覆盖（最高优先级）
    # 条件探测配置（V7.11：移除 LLM_PROBE_ENABLED，改为条件探测策略）
    env_probe_timeout = os.getenv("LLM_PROBE_TIMEOUT")
    if env_probe_timeout is not None:
        try:
            result["request_probe"]["timeout_seconds"] = float(env_probe_timeout)
        except ValueError:
            pass
    
    # 后台探测
    env_health_enabled = os.getenv("LLM_HEALTH_PROBE_ENABLED")
    if env_health_enabled is not None:
        result["background_probe"]["enabled"] = env_health_enabled.lower() in ("true", "1", "yes")
    
    env_health_interval = os.getenv("LLM_HEALTH_PROBE_INTERVAL")
    if env_health_interval is not None:
        try:
            result["background_probe"]["interval_seconds"] = int(env_health_interval)
        except ValueError:
            pass
    
    env_health_timeout = os.getenv("LLM_HEALTH_PROBE_TIMEOUT")
    if env_health_timeout is not None:
        try:
            result["background_probe"]["timeout_seconds"] = float(env_health_timeout)
        except ValueError:
            pass
    
    env_health_profiles = os.getenv("LLM_HEALTH_PROBE_PROFILES")
    if env_health_profiles:
        result["background_probe"]["profiles"] = [
            p.strip() for p in env_health_profiles.split(",") if p.strip()
        ]
    
    return result


# ============================================================
# 导出
# ============================================================

__all__ = [
    "get_llm_profile",
    "list_profiles",
    "reload_config",
    "get_llm_profile_from_env",
    "get_health_probe_config",
]
