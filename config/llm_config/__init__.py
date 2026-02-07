"""
LLM 配置管理模块

所有 LLM Profile 统一在实例 config.yaml 的 llm_profiles 段配置。
实例加载时通过 set_instance_profiles() 注入。

使用示例：
    from config.llm_config import get_llm_profile

    profile = await get_llm_profile("intent_analyzer")

    from core.llm import create_llm_service
    llm = create_llm_service(**profile)
"""

from .loader import (
    get_llm_profile,
    set_instance_profiles,
    clear_instance_profiles,
    list_profiles,
    reload_config,
)

__all__ = [
    "get_llm_profile",
    "set_instance_profiles",
    "clear_instance_profiles",
    "list_profiles",
    "reload_config",
]
