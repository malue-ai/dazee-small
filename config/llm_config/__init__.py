"""
LLM 配置管理模块

统一管理项目中所有 LLM 调用点的超参数配置

使用示例：
    from config.llm_config import get_llm_profile
    
    # 获取配置
    profile = get_llm_profile("semantic_inference")
    
    # 创建 LLM 服务
    from core.llm import create_llm_service
    llm = create_llm_service(**profile)

模块结构：
    - profiles.yaml: LLM 配置文件
    - loader.py: 配置加载器
    - __init__.py: 模块导出接口
    - README.md: 使用文档
    - profiles.example.yaml: 配置示例
"""

from .loader import (
    get_llm_profile,
    list_profiles,
    reload_config,
    get_llm_profile_from_env,
)

__all__ = [
    "get_llm_profile",
    "list_profiles",
    "reload_config",
    "get_llm_profile_from_env",
]

__version__ = "1.0.0"
