"""
LLM 服务统一注册中心

提供 LLM Provider 的集中注册和管理，避免分散的 if-elif 链。

使用方式：
```python
# 在各 Provider 文件末尾注册
from core.llm.registry import LLMRegistry

LLMRegistry.register(
    name="claude",
    service_class=ClaudeLLMService,
    adaptor_class=ClaudeAdaptor,
    default_model="claude-sonnet-4-5-20250929",
    api_key_env="ANTHROPIC_API_KEY"
)

# 创建服务时
llm = LLMRegistry.create_service("claude", model="claude-sonnet-4-5")
adaptor = LLMRegistry.get_adaptor("claude")
```
"""

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from logger import get_logger

if TYPE_CHECKING:
    from .adaptor import BaseAdaptor
    from .base import BaseLLMService, LLMConfig

logger = get_logger("llm.registry")


@dataclass
class ProviderConfig:
    """Provider 配置"""

    name: str  # Provider 名称
    service_class: Type["BaseLLMService"]  # 服务类
    adaptor_class: Type["BaseAdaptor"]  # 适配器类
    default_model: str  # 默认模型
    api_key_env: str  # API Key 环境变量名
    config_class: Optional[Type["LLMConfig"]] = None  # 配置类（可选）

    # 额外元数据
    display_name: Optional[str] = None  # 显示名称
    description: Optional[str] = None  # 描述
    supported_features: List[str] = None  # 支持的功能列表


class LLMRegistry:
    """
    LLM 服务统一注册中心

    职责：
    1. 集中管理所有 LLM Provider 的注册
    2. 提供统一的服务创建接口
    3. 提供统一的适配器获取接口

    设计原则：
    - 单一注册点：每个 Provider 只需在自己的文件中注册一次
    - 延迟导入：避免循环依赖
    - 类型安全：使用 dataclass 定义配置
    """

    _providers: Dict[str, ProviderConfig] = {}
    _initialized: bool = False

    @classmethod
    def register(
        cls,
        name: str,
        service_class: Type["BaseLLMService"],
        adaptor_class: Type["BaseAdaptor"],
        default_model: str,
        api_key_env: str,
        config_class: Optional[Type["LLMConfig"]] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        supported_features: Optional[List[str]] = None,
    ) -> None:
        """
        注册 LLM Provider

        Args:
            name: Provider 名称（如 "claude", "openai", "qwen"）
            service_class: 服务实现类
            adaptor_class: 适配器类
            default_model: 默认模型名称
            api_key_env: API Key 环境变量名
            config_class: 配置类（可选，默认使用 LLMConfig）
            display_name: 显示名称（可选）
            description: 描述（可选）
            supported_features: 支持的功能列表（可选）
        """
        name_lower = name.lower()

        if name_lower in cls._providers:
            logger.warning(f"⚠️ Provider '{name}' 已注册，将被覆盖")

        cls._providers[name_lower] = ProviderConfig(
            name=name_lower,
            service_class=service_class,
            adaptor_class=adaptor_class,
            default_model=default_model,
            api_key_env=api_key_env,
            config_class=config_class,
            display_name=display_name or name,
            description=description,
            supported_features=supported_features or [],
        )

        logger.debug(f"✅ 注册 LLM Provider: {name} (model={default_model})")

    @classmethod
    def create_service(
        cls, provider: str, model: Optional[str] = None, api_key: Optional[str] = None, **kwargs
    ) -> "BaseLLMService":
        """
        创建 LLM 服务实例

        Args:
            provider: Provider 名称
            model: 模型名称（可选，使用默认值）
            api_key: API Key（可选，从环境变量读取）
            **kwargs: 其他配置参数

        Returns:
            LLM 服务实例

        Raises:
            ValueError: 未知的 Provider
        """
        # 确保已初始化
        cls._ensure_initialized()

        provider_lower = provider.lower()

        if provider_lower not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"未知的 LLM Provider: '{provider}'。" f"可用的 Provider: {available}")

        config = cls._providers[provider_lower]

        # 获取模型（默认值优先级：参数 > 注册配置）
        effective_model = model or config.default_model

        # 获取 API Key（优先级：参数 > 环境变量）
        effective_api_key = api_key or os.getenv(config.api_key_env)

        # 获取配置类
        from .base import LLMConfig, LLMProvider

        config_class = config.config_class or LLMConfig

        # 构建配置
        llm_config = config_class(
            provider=LLMProvider(provider_lower),
            model=effective_model,
            api_key=effective_api_key,
            **kwargs,
        )

        # 创建服务实例
        return config.service_class(llm_config)

    @classmethod
    def get_adaptor(cls, provider: str) -> "BaseAdaptor":
        """
        获取 Provider 对应的适配器实例

        Args:
            provider: Provider 名称

        Returns:
            适配器实例

        Raises:
            ValueError: 未知的 Provider
        """
        # 确保已初始化
        cls._ensure_initialized()

        provider_lower = provider.lower()

        if provider_lower not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"未知的 LLM Provider: '{provider}'。" f"可用的 Provider: {available}")

        config = cls._providers[provider_lower]
        return config.adaptor_class()

    @classmethod
    def get_default_model(cls, provider: str) -> str:
        """
        获取 Provider 的默认模型

        Args:
            provider: Provider 名称

        Returns:
            默认模型名称
        """
        cls._ensure_initialized()
        provider_lower = provider.lower()

        if provider_lower not in cls._providers:
            raise ValueError(f"未知的 LLM Provider: '{provider}'")

        return cls._providers[provider_lower].default_model

    @classmethod
    def get_api_key_env(cls, provider: str) -> str:
        """
        获取 Provider 的 API Key 环境变量名

        Args:
            provider: Provider 名称

        Returns:
            环境变量名
        """
        cls._ensure_initialized()
        provider_lower = provider.lower()

        if provider_lower not in cls._providers:
            raise ValueError(f"未知的 LLM Provider: '{provider}'")

        return cls._providers[provider_lower].api_key_env

    @classmethod
    def list_providers(cls) -> List[str]:
        """
        列出所有已注册的 Provider

        Returns:
            Provider 名称列表
        """
        cls._ensure_initialized()
        return list(cls._providers.keys())

    @classmethod
    def get_provider_info(cls, provider: str) -> Dict[str, Any]:
        """
        获取 Provider 详细信息

        Args:
            provider: Provider 名称

        Returns:
            Provider 信息字典
        """
        cls._ensure_initialized()
        provider_lower = provider.lower()

        if provider_lower not in cls._providers:
            raise ValueError(f"未知的 LLM Provider: '{provider}'")

        config = cls._providers[provider_lower]
        return {
            "name": config.name,
            "display_name": config.display_name,
            "default_model": config.default_model,
            "api_key_env": config.api_key_env,
            "description": config.description,
            "supported_features": config.supported_features,
        }

    @classmethod
    def is_registered(cls, provider: str) -> bool:
        """
        检查 Provider 是否已注册

        Args:
            provider: Provider 名称

        Returns:
            是否已注册
        """
        cls._ensure_initialized()
        return provider.lower() in cls._providers

    @classmethod
    def _ensure_initialized(cls) -> None:
        """
        确保 Registry 已初始化（触发所有 Provider 的注册）

        通过导入各个 Provider 模块来触发它们的 register() 调用
        """
        if cls._initialized:
            return

        # 导入所有 Provider 模块以触发注册
        # 这些导入会执行各模块末尾的 LLMRegistry.register() 调用
        try:
            from . import claude  # noqa: F401
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入 claude 模块: {e}")

        try:
            from . import openai  # noqa: F401
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入 openai 模块: {e}")

        try:
            from . import gemini  # noqa: F401
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入 gemini 模块: {e}")

        try:
            from . import qwen  # noqa: F401
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入 qwen 模块: {e}")

        try:
            from . import deepseek  # noqa: F401
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入 deepseek 模块: {e}")

        try:
            from . import glm  # noqa: F401
        except ImportError as e:
            logger.warning(f"⚠️ 无法导入 glm 模块: {e}")

        cls._initialized = True
        logger.info(f"✅ LLM Registry 初始化完成，已注册 {len(cls._providers)} 个 Provider")

    @classmethod
    def reset(cls) -> None:
        """
        重置 Registry（仅用于测试）
        """
        cls._providers.clear()
        cls._initialized = False
