"""
LLM 配置加载器

所有 LLM Profile 配置统一在实例 config.yaml 的 llm_profiles 段管理。
实例加载时通过 set_instance_profiles() 注入，后续各模块通过
get_llm_profile() 获取。

使用示例：
    from config.llm_config import get_llm_profile

    profile = await get_llm_profile("intent_analyzer")

    from core.llm import create_llm_service
    llm = create_llm_service(**profile)
"""

from typing import Dict, Any, List

from logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 全局状态（由 instance_loader 注入）
# ============================================================

_profiles: Dict[str, Dict[str, Any]] = {}


def set_instance_profiles(profiles: Dict[str, Dict[str, Any]]) -> None:
    """
    注入实例 LLM Profiles（由 instance_loader 在加载时调用）

    Args:
        profiles: 实例 config.yaml 的 llm_profiles 段
    """
    global _profiles
    _profiles = profiles or {}
    logger.info(
        f"✅ LLM Profiles 已加载: {len(_profiles)} 个 "
        f"({', '.join(_profiles.keys())})"
    )


def clear_instance_profiles() -> None:
    """清除已注入的 profiles（用于测试或实例重载）"""
    global _profiles
    _profiles = {}


async def get_llm_profile(profile_name: str, **overrides) -> Dict[str, Any]:
    """
    获取指定的 LLM Profile 配置

    当 profile 缺少 provider/model 时（实例加载时未设置 agent.provider），
    自动从 ModelRegistry 已激活模型中填充，确保不会 fallback 到硬编码默认值。

    Args:
        profile_name: Profile 名称（如 "intent_analyzer"）
        **overrides: 调用方覆盖参数

    Returns:
        LLM 配置字典，可直接传给 create_llm_service()

    Raises:
        KeyError: Profile 不存在
    """
    if profile_name not in _profiles:
        available = ", ".join(_profiles.keys()) if _profiles else "(空)"
        raise KeyError(
            f"LLM Profile '{profile_name}' 不存在。\n"
            f"请在实例 config.yaml 的 llm_profiles 中配置。\n"
            f"当前可用: {available}"
        )

    profile = _profiles[profile_name].copy()
    profile.pop("description", None)
    profile.pop("tier", None)  # tier is a resolution hint, not an LLMConfig param

    # Auto-fill missing provider/model from activated models.
    # This handles the case where the instance was loaded before the user
    # activated a model (e.g. first-time user guide flow).
    if "provider" not in profile or "model" not in profile:
        try:
            from core.llm.model_registry import ModelRegistry

            activated = ModelRegistry.list_activated()
            if activated:
                first = activated[0]
                if "provider" not in profile:
                    profile["provider"] = first.provider
                if "model" not in profile:
                    profile["model"] = first.model_name
                if "api_key_env" not in profile:
                    profile["api_key_env"] = first.api_key_env
                logger.debug(
                    f"Profile '{profile_name}' 缺少 provider/model，"
                    f"已从已激活模型填充: {first.provider}/{first.model_name}"
                )
        except Exception as e:
            logger.warning(
                f"自动填充 profile '{profile_name}' 的 provider/model 失败: {e}"
            )

    if overrides:
        profile.update(overrides)

    return profile


async def list_profiles() -> Dict[str, str]:
    """列出所有可用的 LLM Profile"""
    return {
        name: cfg.get("description", cfg.get("model", ""))
        for name, cfg in _profiles.items()
    }


async def reload_config():
    """No-op，保持接口兼容。Profiles 由实例加载时注入。"""
    logger.debug("reload_config: profiles 由实例加载注入，无需重新加载文件")


# ============================================================
# 导出
# ============================================================

__all__ = [
    "get_llm_profile",
    "set_instance_profiles",
    "clear_instance_profiles",
    "list_profiles",
    "reload_config",
]
