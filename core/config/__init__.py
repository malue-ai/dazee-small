"""
统一配置加载模块

支持：
1. 全局配置加载（config/xxx.yaml）
2. 实例级配置覆盖（instances/xxx/config.yaml）
3. 配置缓存

设计原则（LLM-First）：
- 配置只提供默认值
- 规则由提示词定义
- 代码不做硬编码判断
"""

from core.config.loader import (
    ConfigLoader,
    get_config_loader,
    load_capabilities_config,
    load_prompt_config,
)

__all__ = [
    "ConfigLoader",
    "get_config_loader",
    "load_prompt_config",
    "load_capabilities_config",
]
