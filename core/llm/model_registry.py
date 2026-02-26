"""
全局模型注册中心

提供按模型维度的注册和管理，与 LLMRegistry（Provider 维度）配合使用。
支持用户自定义模型的 YAML 持久化（config/custom_models.yaml）。

双层架构：
- Provider 层（LLMRegistry）：定义"如何调用"（服务类 + 适配器）
- Model 层（ModelRegistry）：定义"具体配置"（endpoint、能力、类型）

使用方式：
```python
from core.llm.model_registry import ModelRegistry, ModelType

# 通过模型名创建服务
llm = ModelRegistry.create_service("gpt-4o")
embedder = ModelRegistry.create_service("bge-m3")

# 查询可用模型
llm_models = ModelRegistry.list_models(model_type=ModelType.LLM)
embedding_models = ModelRegistry.list_models(model_type=ModelType.EMBEDDING)
```
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import aiofiles
import yaml

from logger import get_logger

if TYPE_CHECKING:
    from .base import BaseLLMService

logger = get_logger("llm.model_registry")


# ============================================================
# 枚举定义
# ============================================================


class ModelType(Enum):
    """
    模型类型

    用于区分不同用途的模型，便于查询和管理。
    """

    LLM = "llm"  # 纯文本大语言模型
    VLM = "vlm"  # 视觉语言模型（支持图像输入）
    EMBEDDING = "embedding"  # 嵌入模型
    RERANK = "rerank"  # 重排序模型
    TTS = "tts"  # 文本转语音
    STT = "stt"  # 语音转文本
    AUDIO = "audio"  # 音频理解/生成


class AdapterType(Enum):
    """
    适配器类型

    决定消息格式转换方式，不同 Provider 可能使用相同的适配器。
    例如：Qwen 使用 OpenAI 兼容接口，所以 adapter=OPENAI。
    """

    OPENAI = "openai"  # OpenAI 兼容格式（OpenAI、Qwen、DeepSeek 等）
    CLAUDE = "claude"  # Anthropic Claude 格式
    GEMINI = "gemini"  # Google Gemini 格式


# ============================================================
# 数据类
# ============================================================


@dataclass
class ModelPricing:
    """
    模型定价信息（美元 / 百万 token）

    用于实时费用估算和 HITL 费用预警。
    None 表示免费或未知（如私有化部署）。
    """

    input_per_million: Optional[float] = None  # 输入 $/M tokens
    output_per_million: Optional[float] = None  # 输出 $/M tokens
    cache_read_per_million: Optional[float] = None  # 缓存读取 $/M tokens
    cache_write_per_million: Optional[float] = None  # 缓存写入 $/M tokens

    @property
    def is_free(self) -> bool:
        """Whether pricing is zero or unknown (private deployment)."""
        return (
            not self.input_per_million
            and not self.output_per_million
        )

    def estimate_cost(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> Optional[float]:
        """
        Estimate cost in USD based on token counts.

        Returns:
            Estimated cost in USD, or None if pricing is unknown.
        """
        if self.is_free:
            return None

        cost = 0.0
        if self.input_per_million:
            cost += input_tokens * self.input_per_million / 1_000_000
        if self.output_per_million:
            cost += output_tokens * self.output_per_million / 1_000_000
        if self.cache_read_per_million:
            cost += cache_read_tokens * self.cache_read_per_million / 1_000_000
        if self.cache_write_per_million:
            cost += cache_write_tokens * self.cache_write_per_million / 1_000_000
        return cost


@dataclass
class ModelCapabilities:
    """
    模型能力配置

    描述模型支持的功能和限制。
    """

    supports_tools: bool = True  # 是否支持工具调用
    supports_vision: bool = False  # 是否支持图像输入
    supports_thinking: bool = False  # 是否支持深度思考（Claude/Qwen）
    supports_audio: bool = False  # 是否支持音频输入
    supports_streaming: bool = True  # 是否支持流式输出
    max_tokens: int = 4096  # 最大输出 token 数
    max_input_tokens: Optional[int] = None  # 最大输入 token 数（None 表示未知）


@dataclass
class ModelConfig:
    """
    模型配置

    定义单个模型的完整配置信息。

    Attributes:
        model_name: 模型名称（如 "gpt-4o", "qwen3-max"）
        model_type: 模型类型（LLM, VLM, EMBEDDING 等）
        adapter: 适配器类型（决定消息格式）
        base_url: API 端点
        api_key_env: API Key 环境变量名
        provider: Provider 名称（引用 LLMRegistry）
        display_name: 显示名称（可选）
        description: 模型描述（可选）
        capabilities: 模型能力配置
        extra_config: 额外配置（Provider 特有参数）
    """

    model_name: str
    model_type: ModelType
    adapter: AdapterType
    base_url: str
    api_key_env: str
    provider: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    pricing: ModelPricing = field(default_factory=ModelPricing)
    extra_config: Dict[str, Any] = field(default_factory=dict)
    is_custom: bool = False  # True = user-registered via API, persisted to YAML


@dataclass
class ActivatedModelEntry:
    """
    Activated model entry.

    Tracks a model that the user has configured with an API key.
    """

    model_name: str
    api_key: str  # actual API key value
    base_url: Optional[str] = None  # override catalog default
    activated_at: str = ""  # ISO timestamp

    # For custom models not in the catalog
    provider: Optional[str] = None
    model_type: Optional[str] = None
    adapter: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    pricing: Optional[Dict[str, Any]] = None


# ============================================================
# ModelRegistry
# ============================================================


class ModelRegistry:
    """
    全局模型注册中心

    双层架构：
    1. 支持目录（_models）：系统知道的所有模型（preset + custom），定义能力和配置
    2. 激活列表（_activated）：用户配置了 API Key 的模型，实际可用

    与 LLMRegistry 的关系：
    - LLMRegistry 注册 Provider（服务类 + 适配器）
    - ModelRegistry 注册 Model（具体配置），引用 Provider
    - 创建服务时：ModelRegistry 获取配置 → 调用 LLMRegistry 创建服务
    """

    _models: Dict[str, ModelConfig] = {}
    _activated: Dict[str, ActivatedModelEntry] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, config: ModelConfig) -> None:
        """
        注册模型

        Args:
            config: 模型配置
        """
        model_name = config.model_name.lower()

        if model_name in cls._models:
            logger.warning(f"⚠️ 模型 '{config.model_name}' 已注册，将被覆盖")

        cls._models[model_name] = config
        logger.debug(
            f"✅ 注册模型: {config.model_name} "
            f"(type={config.model_type.value}, provider={config.provider})"
        )

    @classmethod
    def get(cls, model_name: str) -> Optional[ModelConfig]:
        """
        获取模型配置

        Args:
            model_name: 模型名称

        Returns:
            模型配置，不存在则返回 None
        """
        cls._ensure_initialized()
        return cls._models.get(model_name.lower())

    @classmethod
    def create_service(
        cls, model_name: str, api_key: Optional[str] = None, **kwargs
    ) -> "BaseLLMService":
        """
        通过模型名创建 LLM 服务

        Args:
            model_name: 模型名称
            api_key: API Key（可选，默认从环境变量读取）
            **kwargs: 其他配置参数（覆盖默认值）

        Returns:
            LLM 服务实例

        Raises:
            ValueError: 模型未注册
        """
        cls._ensure_initialized()

        config = cls.get(model_name)
        if not config:
            available = ", ".join(cls._models.keys())
            raise ValueError(f"未知的模型: '{model_name}'。" f"可用的模型: {available}")

        # 获取 API Key
        effective_api_key = api_key or os.getenv(config.api_key_env)

        # 通过 LLMRegistry 创建服务
        from .registry import LLMRegistry

        # 优先使用用户激活时保存的自定义 base_url，否则使用目录默认值
        effective_base_url = config.base_url
        entry = cls.get_activated_entry(model_name)
        if entry and entry.base_url:
            effective_base_url = entry.base_url

        # 合并配置
        service_kwargs = {
            "base_url": effective_base_url,
            "max_tokens": config.capabilities.max_tokens,
            **config.extra_config,
            **kwargs,
        }

        # 处理特殊能力
        if config.capabilities.supports_thinking:
            service_kwargs.setdefault("enable_thinking", True)

        return LLMRegistry.create_service(
            provider=config.provider,
            model=config.model_name,
            api_key=effective_api_key,
            **service_kwargs,
        )

    @classmethod
    def list_models(
        cls,
        model_type: Optional[ModelType] = None,
        provider: Optional[str] = None,
        adapter: Optional[AdapterType] = None,
    ) -> List[ModelConfig]:
        """
        列出模型

        Args:
            model_type: 按类型过滤
            provider: 按 Provider 过滤
            adapter: 按适配器过滤

        Returns:
            符合条件的模型配置列表
        """
        cls._ensure_initialized()

        models = list(cls._models.values())

        if model_type:
            models = [m for m in models if m.model_type == model_type]

        if provider:
            models = [m for m in models if m.provider.lower() == provider.lower()]

        if adapter:
            models = [m for m in models if m.adapter == adapter]

        return models

    @classmethod
    def list_model_names(
        cls,
        model_type: Optional[ModelType] = None,
    ) -> List[str]:
        """
        列出模型名称

        Args:
            model_type: 按类型过滤

        Returns:
            模型名称列表
        """
        models = cls.list_models(model_type=model_type)
        return [m.model_name for m in models]

    @classmethod
    def is_registered(cls, model_name: str) -> bool:
        """
        检查模型是否已注册

        Args:
            model_name: 模型名称

        Returns:
            是否已注册
        """
        cls._ensure_initialized()
        return model_name.lower() in cls._models

    @classmethod
    def get_model_info(cls, model_name: str) -> Dict[str, Any]:
        """
        获取模型详细信息

        Args:
            model_name: 模型名称

        Returns:
            模型信息字典
        """
        config = cls.get(model_name)
        if not config:
            raise ValueError(f"未知的模型: '{model_name}'")

        return {
            "model_name": config.model_name,
            "model_type": config.model_type.value,
            "adapter": config.adapter.value,
            "provider": config.provider,
            "base_url": config.base_url,
            "api_key_env": config.api_key_env,
            "display_name": config.display_name or config.model_name,
            "description": config.description,
            "capabilities": {
                "supports_tools": config.capabilities.supports_tools,
                "supports_vision": config.capabilities.supports_vision,
                "supports_thinking": config.capabilities.supports_thinking,
                "supports_audio": config.capabilities.supports_audio,
                "supports_streaming": config.capabilities.supports_streaming,
                "max_tokens": config.capabilities.max_tokens,
                "max_input_tokens": config.capabilities.max_input_tokens,
            },
            "pricing": {
                "input_per_million": config.pricing.input_per_million,
                "output_per_million": config.pricing.output_per_million,
                "cache_read_per_million": config.pricing.cache_read_per_million,
                "cache_write_per_million": config.pricing.cache_write_per_million,
                "is_free": config.pricing.is_free,
            },
        }

    # ============================================================
    # 激活层（Activated Models）
    # ============================================================

    @classmethod
    def activate_model(
        cls,
        model_name: str,
        api_key: str,
        base_url: Optional[str] = None,
        *,
        provider: Optional[str] = None,
        model_type: Optional[str] = None,
        adapter: Optional[str] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        pricing: Optional[Dict[str, Any]] = None,
    ) -> ActivatedModelEntry:
        """
        Activate a model by providing an API key.

        If the model exists in the catalog, only api_key (and optional
        base_url override) are needed. For custom models not in the catalog,
        provider/adapter/model_type are required and the model is also
        added to the catalog.

        Args:
            model_name: Model identifier.
            api_key: Actual API key value.
            base_url: Override the catalog default URL.
            provider: Required for custom models.
            model_type: Required for custom models.
            adapter: Required for custom models.

        Returns:
            The activated model entry.
        """
        from datetime import datetime

        cls._ensure_initialized()
        key = model_name.lower()

        catalog_config = cls._models.get(key)

        # If not in catalog, register as custom model first
        if not catalog_config:
            if not provider:
                raise ValueError(
                    f"模型 '{model_name}' 不在支持目录中，"
                    f"必须提供 provider 字段"
                )
            # Build catalog entry from activation params
            caps = ModelCapabilities(
                **(capabilities or {})
            ) if capabilities else ModelCapabilities()
            price = ModelPricing(
                **(pricing or {})
            ) if pricing else ModelPricing()

            catalog_config = ModelConfig(
                model_name=model_name,
                model_type=ModelType(model_type or "llm"),
                adapter=AdapterType(adapter or "openai"),
                base_url=base_url or "",
                api_key_env=f"{provider.upper()}_API_KEY",
                provider=provider,
                display_name=display_name,
                description=description,
                capabilities=caps,
                pricing=price,
                is_custom=True,
            )
            cls._models[key] = catalog_config
            logger.info(
                f"📝 自定义模型已加入目录: {model_name} "
                f"(provider={provider})"
            )

        # Set API key in environment
        os.environ[catalog_config.api_key_env] = api_key

        # Create activated entry
        entry = ActivatedModelEntry(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            activated_at=datetime.now().isoformat(),
            provider=catalog_config.provider,
            model_type=catalog_config.model_type.value,
            adapter=catalog_config.adapter.value,
            display_name=display_name,
            description=description,
            capabilities=capabilities,
            pricing=pricing,
        )
        cls._activated[key] = entry

        logger.info(f"✅ 模型已激活: {model_name} (provider={catalog_config.provider})")
        return entry

    @classmethod
    def activate_provider_models(
        cls,
        provider: str,
        api_key: str,
        base_url: Optional[str] = None,
    ) -> List[ActivatedModelEntry]:
        """
        Batch-activate all catalog models for a given provider.

        Args:
            provider: Provider name (e.g. "qwen", "claude", "openai").
            api_key: Actual API key value (shared by all models of this provider).
            base_url: Optional base URL override.

        Returns:
            List of newly activated model entries.
        """
        from datetime import datetime

        cls._ensure_initialized()

        catalog_models = cls.list_models(provider=provider)
        if not catalog_models:
            logger.warning(f"⚠️ Provider '{provider}' 在目录中没有模型")
            return []

        # Set API key env once (all models of a provider share the same env var)
        env_var = catalog_models[0].api_key_env
        os.environ[env_var] = api_key

        activated = []
        now = datetime.now().isoformat()

        for config in catalog_models:
            key = config.model_name.lower()

            entry = ActivatedModelEntry(
                model_name=config.model_name,
                api_key=api_key,
                base_url=base_url,
                activated_at=now,
                provider=config.provider,
                model_type=config.model_type.value,
                adapter=config.adapter.value,
            )
            cls._activated[key] = entry
            activated.append(entry)

        logger.info(
            f"✅ 批量激活 {len(activated)} 个模型 (provider={provider})"
        )
        return activated

    @classmethod
    def deactivate_model(cls, model_name: str) -> bool:
        """
        Deactivate a model (remove API key config).

        Returns:
            True if model was deactivated, False if not found.
        """
        cls._ensure_initialized()
        key = model_name.lower()

        entry = cls._activated.pop(key, None)
        if not entry:
            return False

        # Clear env var
        catalog_config = cls._models.get(key)
        if catalog_config:
            os.environ.pop(catalog_config.api_key_env, None)

        logger.info(f"🗑️ 模型已停用: {model_name}")
        return True

    @classmethod
    def is_activated(cls, model_name: str) -> bool:
        """Check if a model is activated."""
        cls._ensure_initialized()
        return model_name.lower() in cls._activated

    @classmethod
    def list_activated(
        cls,
        provider: Optional[str] = None,
    ) -> List[ModelConfig]:
        """
        List activated models (with catalog info merged).

        Returns ModelConfig objects for each activated model.
        """
        cls._ensure_initialized()

        results = []
        for key, entry in cls._activated.items():
            config = cls._models.get(key)
            if not config:
                continue
            if provider and config.provider.lower() != provider.lower():
                continue
            results.append(config)
        return results

    @classmethod
    def get_activated_entry(cls, model_name: str) -> Optional[ActivatedModelEntry]:
        """Get activated entry for a model."""
        cls._ensure_initialized()
        return cls._activated.get(model_name.lower())

    # ============================================================
    # 初始化 & 重置
    # ============================================================

    @classmethod
    def _ensure_initialized(cls) -> None:
        """
        确保 Registry 已初始化（加载预置模型 + 自定义模型 + 激活模型）
        """
        if cls._initialized:
            return

        # 加载预置模型
        _register_preset_models()

        # 加载用户自定义模型（从 YAML 持久化文件）
        custom_count = cls._load_custom_models()
        if custom_count > 0:
            logger.info(f"📦 已加载 {custom_count} 个用户自定义模型")

        # 加载用户激活的模型（从 YAML 持久化文件）
        activated_count = cls._load_activated_models()
        if activated_count > 0:
            logger.info(f"🔑 已加载 {activated_count} 个已激活模型")

        cls._initialized = True
        logger.info(
            f"✅ ModelRegistry 初始化完成，"
            f"目录 {len(cls._models)} 个模型，"
            f"已激活 {len(cls._activated)} 个"
        )

    @classmethod
    def reset(cls) -> None:
        """
        重置 Registry（仅用于测试）
        """
        cls._models.clear()
        cls._activated.clear()
        cls._initialized = False

    # ============================================================
    # 持久化（YAML）
    # ============================================================

    @classmethod
    def _get_custom_models_path(cls) -> Path:
        """
        Get path to the custom models YAML file.

        Uses the user data directory to keep persistence across restarts.
        """
        from utils.app_paths import get_user_data_dir

        config_dir = get_user_data_dir() / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "custom_models.yaml"

    @classmethod
    def _model_config_to_dict(cls, config: ModelConfig) -> Dict[str, Any]:
        """Serialize a ModelConfig to a plain dict for YAML output."""
        return {
            "model_name": config.model_name,
            "model_type": config.model_type.value,
            "adapter": config.adapter.value,
            "base_url": config.base_url,
            "api_key_env": config.api_key_env,
            "provider": config.provider,
            "display_name": config.display_name,
            "description": config.description,
            "capabilities": {
                "supports_tools": config.capabilities.supports_tools,
                "supports_vision": config.capabilities.supports_vision,
                "supports_thinking": config.capabilities.supports_thinking,
                "supports_audio": config.capabilities.supports_audio,
                "supports_streaming": config.capabilities.supports_streaming,
                "max_tokens": config.capabilities.max_tokens,
                "max_input_tokens": config.capabilities.max_input_tokens,
            },
            "pricing": {
                "input_per_million": config.pricing.input_per_million,
                "output_per_million": config.pricing.output_per_million,
                "cache_read_per_million": config.pricing.cache_read_per_million,
                "cache_write_per_million": config.pricing.cache_write_per_million,
            },
            "extra_config": config.extra_config or {},
        }

    @classmethod
    def _dict_to_model_config(cls, data: Dict[str, Any]) -> ModelConfig:
        """Deserialize a plain dict from YAML into a ModelConfig."""
        caps_data = data.get("capabilities", {})
        pricing_data = data.get("pricing", {})

        return ModelConfig(
            model_name=data["model_name"],
            model_type=ModelType(data.get("model_type", "llm")),
            adapter=AdapterType(data.get("adapter", "openai")),
            base_url=data["base_url"],
            api_key_env=data["api_key_env"],
            provider=data["provider"],
            display_name=data.get("display_name"),
            description=data.get("description"),
            capabilities=ModelCapabilities(
                supports_tools=caps_data.get("supports_tools", True),
                supports_vision=caps_data.get("supports_vision", False),
                supports_thinking=caps_data.get("supports_thinking", False),
                supports_audio=caps_data.get("supports_audio", False),
                supports_streaming=caps_data.get("supports_streaming", True),
                max_tokens=caps_data.get("max_tokens", 4096),
                max_input_tokens=caps_data.get("max_input_tokens"),
            ),
            pricing=ModelPricing(
                input_per_million=pricing_data.get("input_per_million"),
                output_per_million=pricing_data.get("output_per_million"),
                cache_read_per_million=pricing_data.get("cache_read_per_million"),
                cache_write_per_million=pricing_data.get("cache_write_per_million"),
            ),
            extra_config=data.get("extra_config", {}),
            is_custom=True,
        )

    @classmethod
    def _load_custom_models(cls) -> int:
        """
        Load custom models from YAML file (synchronous, called during init).

        Returns:
            Number of custom models loaded.
        """
        path = cls._get_custom_models_path()
        if not path.exists():
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data.get("models"), list):
                return 0

            count = 0
            for model_data in data["models"]:
                try:
                    config = cls._dict_to_model_config(model_data)
                    cls._models[config.model_name.lower()] = config
                    count += 1
                except Exception as e:
                    logger.warning(
                        f"⚠️ 加载自定义模型失败 "
                        f"(name={model_data.get('model_name', '?')}): {e}"
                    )
            return count

        except Exception as e:
            logger.error(f"❌ 读取自定义模型文件失败: {e}", exc_info=True)
            return 0

    @classmethod
    async def save_custom_models(cls) -> None:
        """
        Persist all custom models (is_custom=True) to YAML file.

        Called after register/unregister operations.
        """
        custom_models = [
            cls._model_config_to_dict(m)
            for m in cls._models.values()
            if m.is_custom
        ]

        path = cls._get_custom_models_path()
        content = yaml.dump(
            {"models": custom_models},
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(
            f"💾 已保存 {len(custom_models)} 个自定义模型到 {path}"
        )

    # ============================================================
    # 激活模型持久化（YAML）
    # ============================================================

    @classmethod
    def _get_activated_models_path(cls) -> Path:
        """Get path to activated_models.yaml."""
        from utils.app_paths import get_user_data_dir

        config_dir = get_user_data_dir() / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "activated_models.yaml"

    @classmethod
    def _load_activated_models(cls) -> int:
        """
        Load activated models from YAML (synchronous, called at init).

        Also sets API keys in environment variables.

        Returns:
            Number of activated models loaded.
        """
        path = cls._get_activated_models_path()
        if not path.exists():
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data.get("models"), list):
                return 0

            count = 0
            for item in data["models"]:
                try:
                    name = item["model_name"]
                    api_key = item.get("api_key", "")
                    key = name.lower()

                    entry = ActivatedModelEntry(
                        model_name=name,
                        api_key=api_key,
                        base_url=item.get("base_url"),
                        activated_at=item.get("activated_at", ""),
                        provider=item.get("provider"),
                        model_type=item.get("model_type"),
                        adapter=item.get("adapter"),
                        display_name=item.get("display_name"),
                        description=item.get("description"),
                        capabilities=item.get("capabilities"),
                        pricing=item.get("pricing"),
                    )
                    cls._activated[key] = entry

                    # If model not in catalog, register as custom
                    if key not in cls._models and entry.provider:
                        caps_data = entry.capabilities or {}
                        pricing_data = entry.pricing or {}
                        config = ModelConfig(
                            model_name=name,
                            model_type=ModelType(entry.model_type or "llm"),
                            adapter=AdapterType(entry.adapter or "openai"),
                            base_url=entry.base_url or "",
                            api_key_env=f"{entry.provider.upper()}_API_KEY",
                            provider=entry.provider,
                            display_name=entry.display_name,
                            description=entry.description,
                            capabilities=ModelCapabilities(**caps_data) if caps_data else ModelCapabilities(),
                            pricing=ModelPricing(**pricing_data) if pricing_data else ModelPricing(),
                            is_custom=True,
                        )
                        cls._models[key] = config

                    # Set API key in environment
                    catalog = cls._models.get(key)
                    if catalog and api_key:
                        os.environ[catalog.api_key_env] = api_key

                    count += 1
                except Exception as e:
                    logger.warning(
                        f"⚠️ 加载激活模型失败 "
                        f"(name={item.get('model_name', '?')}): {e}"
                    )
            return count

        except Exception as e:
            logger.error(f"❌ 读取激活模型文件失败: {e}", exc_info=True)
            return 0

    @classmethod
    async def save_activated_models(cls) -> None:
        """
        Persist all activated models to YAML.

        Called after activate/deactivate operations.
        API keys are stored in the file (local-only, gitignored).
        """
        entries = []
        for entry in cls._activated.values():
            item: Dict[str, Any] = {
                "model_name": entry.model_name,
                "api_key": entry.api_key,
                "activated_at": entry.activated_at,
            }
            if entry.base_url:
                item["base_url"] = entry.base_url
            # For custom models, store full config
            if entry.provider:
                item["provider"] = entry.provider
            if entry.model_type:
                item["model_type"] = entry.model_type
            if entry.adapter:
                item["adapter"] = entry.adapter
            if entry.display_name:
                item["display_name"] = entry.display_name
            if entry.description:
                item["description"] = entry.description
            if entry.capabilities:
                item["capabilities"] = entry.capabilities
            if entry.pricing:
                item["pricing"] = entry.pricing
            entries.append(item)

        path = cls._get_activated_models_path()
        content = yaml.dump(
            {"models": entries},
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(f"💾 已保存 {len(entries)} 个激活模型到 {path}")


# ============================================================
# 预置模型注册
# ============================================================


def _register_preset_models() -> None:
    """
    注册预置模型

    在 ModelRegistry 初始化时自动调用。
    """
    # ==================== OpenAI 系列 ====================

    _OPENAI_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        provider="openai",
    )

    # --- GPT-5 family ---

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-5.2",
            model_type=ModelType.VLM,
            display_name="GPT-5.2",
            description="OpenAI 最新旗舰，编码和智能体任务最强",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=100000, max_input_tokens=1000000,
            ),
            pricing=ModelPricing(input_per_million=1.75, output_per_million=14.0,
                                 cache_read_per_million=0.175),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-5.1",
            model_type=ModelType.VLM,
            display_name="GPT-5.1",
            description="GPT-5 系列高性能推理模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=100000, max_input_tokens=1000000,
            ),
            pricing=ModelPricing(input_per_million=1.25, output_per_million=10.0,
                                 cache_read_per_million=0.125),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-5",
            model_type=ModelType.VLM,
            display_name="GPT-5",
            description="GPT-5 系列推理模型，编码和智能体任务",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=100000, max_input_tokens=1000000,
            ),
            pricing=ModelPricing(input_per_million=1.25, output_per_million=10.0,
                                 cache_read_per_million=0.125),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-5-mini",
            model_type=ModelType.VLM,
            display_name="GPT-5 Mini",
            description="GPT-5 高性价比版本",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=100000, max_input_tokens=1000000,
            ),
            pricing=ModelPricing(input_per_million=0.25, output_per_million=2.0,
                                 cache_read_per_million=0.025),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-5-nano",
            model_type=ModelType.VLM,
            display_name="GPT-5 Nano",
            description="GPT-5 最低成本版本",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=16384, max_input_tokens=1000000,
            ),
            pricing=ModelPricing(input_per_million=0.05, output_per_million=0.40,
                                 cache_read_per_million=0.005),
            **_OPENAI_COMMON,
        )
    )

    # --- GPT-4.1 family ---

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4.1",
            model_type=ModelType.VLM,
            display_name="GPT-4.1",
            description="最强非推理模型，1M 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=32768, max_input_tokens=1047576,
            ),
            pricing=ModelPricing(input_per_million=2.0, output_per_million=8.0,
                                 cache_read_per_million=0.50),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4.1-mini",
            model_type=ModelType.VLM,
            display_name="GPT-4.1 Mini",
            description="GPT-4.1 轻量版，1M 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=32768, max_input_tokens=1047576,
            ),
            pricing=ModelPricing(input_per_million=0.40, output_per_million=1.60,
                                 cache_read_per_million=0.10),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4.1-nano",
            model_type=ModelType.VLM,
            display_name="GPT-4.1 Nano",
            description="GPT-4.1 最低成本版，1M 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=16384, max_input_tokens=1047576,
            ),
            pricing=ModelPricing(input_per_million=0.10, output_per_million=0.40,
                                 cache_read_per_million=0.025),
            **_OPENAI_COMMON,
        )
    )

    # --- o-series (reasoning) ---

    ModelRegistry.register(
        ModelConfig(
            model_name="o3",
            model_type=ModelType.VLM,
            display_name="o3",
            description="OpenAI 推理模型，编码/数学/科学最强",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=100000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(input_per_million=2.0, output_per_million=8.0,
                                 cache_read_per_million=0.50),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="o4-mini",
            model_type=ModelType.VLM,
            display_name="o4-mini",
            description="高性价比推理模型，数学/编码/视觉",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=100000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(input_per_million=1.10, output_per_million=4.40,
                                 cache_read_per_million=0.275),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="o3-mini",
            model_type=ModelType.LLM,
            display_name="o3-mini",
            description="o3 轻量版推理模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=65536, max_input_tokens=200000,
            ),
            pricing=ModelPricing(input_per_million=1.10, output_per_million=4.40,
                                 cache_read_per_million=0.55),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="o1",
            model_type=ModelType.VLM,
            display_name="o1",
            description="OpenAI 首代推理模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=100000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(input_per_million=15.0, output_per_million=60.0,
                                 cache_read_per_million=7.50),
            **_OPENAI_COMMON,
        )
    )

    # --- GPT-4o family ---

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4o",
            model_type=ModelType.VLM,
            display_name="GPT-4o",
            description="快速智能多模态模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=16384, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=2.5, output_per_million=10.0,
                                 cache_read_per_million=1.25),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4o-mini",
            model_type=ModelType.VLM,
            display_name="GPT-4o Mini",
            description="GPT-4o 轻量版本",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=16384, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.15, output_per_million=0.60,
                                 cache_read_per_million=0.075),
            **_OPENAI_COMMON,
        )
    )

    # --- GPT Audio (Omni) ---

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-audio",
            model_type=ModelType.AUDIO,
            display_name="GPT Audio",
            description="OpenAI 全模态音频模型，支持音频输入/输出",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_audio=True,
                max_tokens=16384, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=2.5, output_per_million=10.0),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4o-audio-preview",
            model_type=ModelType.AUDIO,
            display_name="GPT-4o Audio Preview",
            description="GPT-4o 音频预览版，支持音频输入/输出",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_audio=True,
                max_tokens=16384, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=2.5, output_per_million=10.0),
            **_OPENAI_COMMON,
        )
    )

    # --- Legacy ---

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4-turbo",
            model_type=ModelType.VLM,
            display_name="GPT-4 Turbo",
            description="GPT-4 Turbo with Vision（旧版）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=4096, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=10.0, output_per_million=30.0),
            **_OPENAI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-3.5-turbo",
            model_type=ModelType.LLM,
            display_name="GPT-3.5 Turbo",
            description="旧版快速模型（Legacy）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=False,
                max_tokens=4096, max_input_tokens=16385,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=1.50),
            **_OPENAI_COMMON,
        )
    )

    # ==================== Claude 系列 ====================

    _CLAUDE_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.CLAUDE,
        base_url="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        provider="claude",
    )

    # --- Claude 4.5 / 4.6 (latest) ---

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-sonnet-4-5-20250929",
            model_type=ModelType.VLM,
            display_name="Claude Sonnet 4.5",
            description="Anthropic 最强智能体与编码模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=64000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=3.0, output_per_million=15.0,
                cache_read_per_million=0.30, cache_write_per_million=3.75,
            ),
            **_CLAUDE_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-opus-4-6",
            model_type=ModelType.VLM,
            display_name="Claude Opus 4.6",
            description="Anthropic 最强模型（2026.02）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=64000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=15.0, output_per_million=75.0,
                cache_read_per_million=1.50, cache_write_per_million=18.75,
            ),
            **_CLAUDE_COMMON,
        )
    )

    # --- Claude 4 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-sonnet-4-20250514",
            model_type=ModelType.VLM,
            display_name="Claude Sonnet 4",
            description="Claude 4 系列均衡模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=64000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=3.0, output_per_million=15.0,
                cache_read_per_million=0.30, cache_write_per_million=3.75,
            ),
            **_CLAUDE_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-opus-4-20250514",
            model_type=ModelType.VLM,
            display_name="Claude Opus 4",
            description="Claude 4 系列旗舰模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=32000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=15.0, output_per_million=75.0,
                cache_read_per_million=1.50, cache_write_per_million=18.75,
            ),
            **_CLAUDE_COMMON,
        )
    )

    # --- Claude 3.5 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-3-5-sonnet-20241022",
            model_type=ModelType.VLM,
            display_name="Claude 3.5 Sonnet",
            description="Claude 3.5 系列均衡模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=8192, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=3.0, output_per_million=15.0,
                cache_read_per_million=0.30, cache_write_per_million=3.75,
            ),
            **_CLAUDE_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-3-5-haiku-20241022",
            model_type=ModelType.VLM,
            display_name="Claude 3.5 Haiku",
            description="Claude 3.5 快速模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=8192, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=0.80, output_per_million=4.0,
                cache_read_per_million=0.08, cache_write_per_million=1.0,
            ),
            **_CLAUDE_COMMON,
        )
    )

    # --- Claude 3 (Legacy) ---

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-3-opus-20240229",
            model_type=ModelType.VLM,
            display_name="Claude 3 Opus",
            description="Claude 3 系列旗舰模型（Legacy）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=4096, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=15.0, output_per_million=75.0,
                cache_read_per_million=1.50, cache_write_per_million=18.75,
            ),
            **_CLAUDE_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-3-haiku-20240307",
            model_type=ModelType.VLM,
            display_name="Claude 3 Haiku",
            description="Claude 3 快速模型（Legacy）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=4096, max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=0.25, output_per_million=1.25,
                cache_read_per_million=0.03, cache_write_per_million=0.30,
            ),
            **_CLAUDE_COMMON,
        )
    )

    # ==================== Qwen 系列 ====================

    _QWEN_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.OPENAI,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        provider="qwen",
    )

    # --- Qwen3 旗舰 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-max",
            model_type=ModelType.LLM,
            display_name="Qwen3-Max",
            description="阿里云旗舰模型，262K 上下文，Coding 76.7 / GPQA 76.4",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=65536, max_input_tokens=258048,
            ),
            pricing=ModelPricing(input_per_million=1.20, output_per_million=6.00,
                                 cache_read_per_million=0.24),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-max-thinking",
            model_type=ModelType.LLM,
            display_name="Qwen3-Max-Thinking",
            description="阿里云最强推理模型 (2026.01)，对标 GPT-5.2-Thinking / Claude-Opus-4.5",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=65536, max_input_tokens=258048,
            ),
            pricing=ModelPricing(input_per_million=1.20, output_per_million=6.00,
                                 cache_read_per_million=0.24),
            **_QWEN_COMMON,
        )
    )

    # --- Qwen3 Coder 系列 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-coder-plus",
            model_type=ModelType.LLM,
            display_name="Qwen3-Coder-Plus",
            description="Qwen3 代码专精模型，128K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=65536, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=1.00, output_per_million=5.00,
                                 cache_read_per_million=0.10),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-coder-flash",
            model_type=ModelType.LLM,
            display_name="Qwen3-Coder-Flash",
            description="Qwen3 代码快速模型，128K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=65536, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.30, output_per_million=1.50,
                                 cache_read_per_million=0.08),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-coder-next",
            model_type=ModelType.LLM,
            display_name="Qwen3-Coder-Next",
            description="Qwen3 最新代码模型 (2026.02)，262K 上下文，GPQA 73.7",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=65536, max_input_tokens=262144,
            ),
            pricing=ModelPricing(input_per_million=0.07, output_per_million=0.30,
                                 cache_read_per_million=0.035),
            **_QWEN_COMMON,
        )
    )

    # --- Qwen3 Next 系列 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-next-80b-a3b-instruct",
            model_type=ModelType.LLM,
            display_name="Qwen3-Next-80B Instruct",
            description="Qwen3 Next 高性能模型，262K 上下文，Coding 68.4",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=False,
                max_tokens=65536, max_input_tokens=262144,
            ),
            pricing=ModelPricing(input_per_million=0.09, output_per_million=1.10),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-next-80b-a3b-thinking",
            model_type=ModelType.LLM,
            display_name="Qwen3-Next-80B Thinking",
            description="Qwen3 Next 深度推理模型，128K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=65536, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.15, output_per_million=1.20),
            **_QWEN_COMMON,
        )
    )

    # --- Qwen3 VL（视觉）系列 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-vl-plus",
            model_type=ModelType.VLM,
            display_name="Qwen3-VL-Plus",
            description="Qwen3 视觉旗舰，262K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=65536, max_input_tokens=262144,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=1.50),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-vl-235b-a22b-instruct",
            model_type=ModelType.VLM,
            display_name="Qwen3-VL-235B Instruct",
            description="Qwen3 旗舰视觉模型，262K 上下文，Coding 59.4",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=65536, max_input_tokens=262144,
            ),
            pricing=ModelPricing(input_per_million=0.20, output_per_million=0.88,
                                 cache_read_per_million=0.11),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-vl-235b-a22b-thinking",
            model_type=ModelType.VLM,
            display_name="Qwen3-VL-235B Thinking",
            description="Qwen3 旗舰视觉推理模型，262K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=65536, max_input_tokens=262144,
            ),
            pricing=ModelPricing(input_per_million=0.45, output_per_million=3.50),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-vl-32b-instruct",
            model_type=ModelType.VLM,
            display_name="Qwen3-VL-32B Instruct",
            description="Qwen3 视觉模型 32B，262K 上下文，Coding 51.4",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=65536, max_input_tokens=262144,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=1.50),
            **_QWEN_COMMON,
        )
    )

    # --- Qwen 经典系列（Qwen-Plus / Turbo / Max / QwQ）---

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-plus",
            model_type=ModelType.LLM,
            display_name="Qwen-Plus",
            description="阿里云通用模型，131K 上下文，性价比高",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=33000, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=0.40, output_per_million=1.20,
                                 cache_read_per_million=0.16),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-turbo",
            model_type=ModelType.LLM,
            display_name="Qwen-Turbo",
            description="阿里云低成本快速模型，1M 超长上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=8192, max_input_tokens=1000000,
            ),
            pricing=ModelPricing(input_per_million=0.05, output_per_million=0.20,
                                 cache_read_per_million=0.02),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-max",
            model_type=ModelType.LLM,
            display_name="Qwen-Max",
            description="Qwen2.5 旗舰模型，32K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=False,
                max_tokens=16384, max_input_tokens=32768,
            ),
            pricing=ModelPricing(input_per_million=1.60, output_per_million=6.40,
                                 cache_read_per_million=0.64),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwq-plus",
            model_type=ModelType.LLM,
            display_name="QwQ-Plus",
            description="Qwen 推理模型，Coding 63.1 / GPQA 59.3",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=33000, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=0.40, output_per_million=1.20),
            **_QWEN_COMMON,
        )
    )

    # --- Qwen Omni（全模态音频）系列 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-omni-turbo",
            model_type=ModelType.AUDIO,
            display_name="Qwen-Omni-Turbo",
            description="阿里云全模态模型，支持音频/视觉输入输出",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_audio=True,
                max_tokens=33000, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=0.80, output_per_million=3.20),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-omni-flash",
            model_type=ModelType.AUDIO,
            display_name="Qwen3-Omni-Flash",
            description="Qwen3 全模态快速模型，支持音频/视觉输入输出",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_audio=True,
                max_tokens=33000, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=0.30, output_per_million=1.50),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-audio-turbo",
            model_type=ModelType.AUDIO,
            display_name="Qwen-Audio-Turbo",
            description="阿里云音频理解模型",
            capabilities=ModelCapabilities(
                supports_tools=False, supports_vision=False, supports_audio=True,
                max_tokens=8192, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=0.40, output_per_million=1.20),
            **_QWEN_COMMON,
        )
    )

    # --- Qwen VL 经典 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-vl-max",
            model_type=ModelType.VLM,
            display_name="Qwen-VL-Max",
            description="阿里云视觉语言旗舰，131K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=33000, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=0.80, output_per_million=3.20),
            **_QWEN_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-vl-plus",
            model_type=ModelType.VLM,
            display_name="Qwen-VL-Plus",
            description="阿里云视觉语言模型（轻量）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=8192, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=0.21, output_per_million=0.63),
            **_QWEN_COMMON,
        )
    )

    # ==================== GLM（智谱AI）系列 ====================

    _GLM_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.OPENAI,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPUAI_API_KEY",
        provider="glm",
    )

    # --- GLM-5 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-5",
            model_type=ModelType.LLM,
            display_name="GLM-5",
            description="744B MoE 旗舰（激活 40B），200K 上下文，Coding/Agent 开源 SOTA",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=128000, max_input_tokens=200000,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=2.00),
            **_GLM_COMMON,
        )
    )

    # --- GLM-4.7 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.7",
            model_type=ModelType.LLM,
            display_name="GLM-4.7",
            description="智谱上一代旗舰模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=2.00),
            **_GLM_COMMON,
        )
    )

    # --- GLM-4.6 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.6",
            model_type=ModelType.LLM,
            display_name="GLM-4.6",
            description="智谱上一代旗舰模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=2.00),
            **_GLM_COMMON,
        )
    )

    # --- GLM-4.5 系列 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.5",
            model_type=ModelType.LLM,
            display_name="GLM-4.5",
            description="355B MoE 旗舰，128K 上下文，Agent/Coding 最强",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.20, output_per_million=1.10),
            **_GLM_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.5-air",
            model_type=ModelType.LLM,
            display_name="GLM-4.5-Air",
            description="106B MoE 轻量旗舰，高性价比",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.08, output_per_million=0.40),
            **_GLM_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.5-x",
            model_type=ModelType.LLM,
            display_name="GLM-4.5-X",
            description="高性能加速版，超快响应",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=2.00),
            **_GLM_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.5-airx",
            model_type=ModelType.LLM,
            display_name="GLM-4.5-AirX",
            description="轻量加速版，低延迟高并发",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.10, output_per_million=0.50),
            **_GLM_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.5-flash",
            model_type=ModelType.LLM,
            display_name="GLM-4.5-Flash",
            description="免费快速模型，Coding/Agent/Reasoning",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.0, output_per_million=0.0),
            **_GLM_COMMON,
        )
    )

    # --- GLM 视觉模型 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.6v",
            model_type=ModelType.VLM,
            display_name="GLM-4.6V",
            description="智谱视觉语言模型（GLM-4.6 视觉版）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.50, output_per_million=2.00),
            **_GLM_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="glm-4.5v",
            model_type=ModelType.VLM,
            display_name="GLM-4.5V",
            description="智谱视觉语言模型（GLM-4.5 视觉版）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                supports_streaming=True,
                max_tokens=96000, max_input_tokens=128000,
            ),
            pricing=ModelPricing(input_per_million=0.20, output_per_million=1.10),
            **_GLM_COMMON,
        )
    )

    # ==================== Gemini 系列 ====================

    _GEMINI_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.GEMINI,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GOOGLE_API_KEY",
        provider="gemini",
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gemini-2.5-pro",
            model_type=ModelType.VLM,
            display_name="Gemini 2.5 Pro",
            description="Google 旗舰推理模型，支持多模态",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=65536, max_input_tokens=1048576,
            ),
            pricing=ModelPricing(input_per_million=1.25, output_per_million=10.0),
            **_GEMINI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gemini-2.5-flash",
            model_type=ModelType.VLM,
            display_name="Gemini 2.5 Flash",
            description="Google 高性价比快速模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=65536, max_input_tokens=1048576,
            ),
            pricing=ModelPricing(input_per_million=0.15, output_per_million=0.60),
            **_GEMINI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gemini-2.5-flash-native-audio",
            model_type=ModelType.AUDIO,
            display_name="Gemini 2.5 Flash Native Audio",
            description="Google 全模态音频模型，支持音频/视频输入输出",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_audio=True,
                max_tokens=65536, max_input_tokens=1048576,
            ),
            pricing=ModelPricing(input_per_million=0.15, output_per_million=0.60),
            **_GEMINI_COMMON,
        )
    )

    # ==================== DeepSeek 系列 ====================

    _DEEPSEEK_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.OPENAI,
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        provider="deepseek",
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="deepseek-chat",
            model_type=ModelType.LLM,
            display_name="DeepSeek Chat (V3)",
            description="DeepSeek 对话模型，64K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=False,
                max_tokens=8192, max_input_tokens=64000,
            ),
            pricing=ModelPricing(
                input_per_million=0.27, output_per_million=1.10,
                cache_read_per_million=0.07,
            ),
            **_DEEPSEEK_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="deepseek-reasoner",
            model_type=ModelType.LLM,
            display_name="DeepSeek Reasoner (R1)",
            description="DeepSeek 推理模型，支持 CoT",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=64000, max_input_tokens=64000,
            ),
            pricing=ModelPricing(
                input_per_million=0.55, output_per_million=2.19,
                cache_read_per_million=0.14,
            ),
            **_DEEPSEEK_COMMON,
        )
    )

    # ==================== Kimi (Moonshot) 系列 ====================

    _KIMI_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.OPENAI,
        base_url="https://api.moonshot.cn/v1",
        api_key_env="MOONSHOT_API_KEY",
        provider="kimi",
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="kimi-k2.5",
            model_type=ModelType.VLM,
            display_name="Kimi K2.5",
            description="Kimi 迄今最全能模型，原生多模态，支持视觉与文本、思考与非思考，256K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=True,
                max_tokens=33000, max_input_tokens=262144,
            ),
            pricing=ModelPricing(
                input_per_million=0.56, output_per_million=2.92,
                cache_read_per_million=0.10,
            ),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="kimi-k2-0905-preview",
            model_type=ModelType.LLM,
            display_name="Kimi K2 0905",
            description="Kimi K2 升级版，更强 Agentic Coding 与上下文理解，256K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=16384, max_input_tokens=262144,
            ),
            pricing=ModelPricing(
                input_per_million=0.56, output_per_million=2.22,
                cache_read_per_million=0.14,
            ),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="kimi-k2-0711-preview",
            model_type=ModelType.LLM,
            display_name="Kimi K2 0711",
            description="Kimi K2 基础模型，MoE 1T 参数，128K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=16384, max_input_tokens=131072,
            ),
            pricing=ModelPricing(
                input_per_million=0.56, output_per_million=2.22,
                cache_read_per_million=0.14,
            ),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="kimi-k2-turbo-preview",
            model_type=ModelType.LLM,
            display_name="Kimi K2 Turbo",
            description="Kimi K2 高速版，输出最高 100 tok/s，对标最新 K2，256K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=16384, max_input_tokens=262144,
            ),
            pricing=ModelPricing(
                input_per_million=1.11, output_per_million=8.06,
                cache_read_per_million=0.14,
            ),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="kimi-k2-thinking",
            model_type=ModelType.LLM,
            display_name="Kimi K2 Thinking",
            description="Kimi K2 深度推理模型，通用 Agentic + 推理能力，256K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=16384, max_input_tokens=262144,
            ),
            pricing=ModelPricing(
                input_per_million=0.56, output_per_million=2.22,
                cache_read_per_million=0.14,
            ),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="kimi-k2-thinking-turbo",
            model_type=ModelType.LLM,
            display_name="Kimi K2 Thinking Turbo",
            description="Kimi K2 深度推理高速版，适合需要深度推理且追求高速的场景，256K 上下文",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                max_tokens=16384, max_input_tokens=262144,
            ),
            pricing=ModelPricing(
                input_per_million=1.11, output_per_million=8.06,
                cache_read_per_million=0.14,
            ),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="moonshot-v1-128k-vision-preview",
            model_type=ModelType.VLM,
            display_name="Moonshot v1 128K Vision",
            description="Moonshot AI 多模态视觉模型，支持图片理解（128K）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=True, supports_thinking=False,
                max_tokens=8192, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=1.39, output_per_million=4.17),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="moonshot-v1-128k",
            model_type=ModelType.LLM,
            display_name="Moonshot v1 128K",
            description="Moonshot AI 长上下文模型（128K）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=False,
                max_tokens=8192, max_input_tokens=131072,
            ),
            pricing=ModelPricing(input_per_million=1.39, output_per_million=4.17),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="moonshot-v1-32k",
            model_type=ModelType.LLM,
            display_name="Moonshot v1 32K",
            description="Moonshot AI 标准模型（32K）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=False,
                max_tokens=8192, max_input_tokens=32768,
            ),
            pricing=ModelPricing(input_per_million=0.69, output_per_million=2.78),
            **_KIMI_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="moonshot-v1-8k",
            model_type=ModelType.LLM,
            display_name="Moonshot v1 8K",
            description="Moonshot AI 轻量模型（8K）",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=False,
                max_tokens=4096, max_input_tokens=8192,
            ),
            pricing=ModelPricing(input_per_million=0.28, output_per_million=1.39),
            **_KIMI_COMMON,
        )
    )

    # ==================== MiniMax 系列（Anthropic API 兼容） ====================

    _MINIMAX_COMMON: Dict[str, Any] = dict(
        adapter=AdapterType.CLAUDE,
        base_url="https://api.minimaxi.com/anthropic",
        api_key_env="MINIMAX_API_KEY",
        provider="minimax",
    )

    # --- MiniMax M2.5 系列 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="MiniMax-M2.5",
            model_type=ModelType.LLM,
            display_name="MiniMax M2.5",
            description="MiniMax 最新旗舰模型，编码与智能体任务 SOTA，~60 tps",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=32768, max_input_tokens=204800,
            ),
            pricing=ModelPricing(input_per_million=0.30, output_per_million=1.10),
            **_MINIMAX_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="MiniMax-M2.5-highspeed",
            model_type=ModelType.LLM,
            display_name="MiniMax M2.5 Highspeed",
            description="MiniMax M2.5 极速版，性能不变，~100 tps",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=32768, max_input_tokens=204800,
            ),
            pricing=ModelPricing(input_per_million=0.30, output_per_million=1.10),
            **_MINIMAX_COMMON,
        )
    )

    # --- MiniMax M2 系列 ---

    ModelRegistry.register(
        ModelConfig(
            model_name="MiniMax-M2.1",
            model_type=ModelType.LLM,
            display_name="MiniMax M2.1",
            description="MiniMax 旗舰模型，多语言编程，~60 tps",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=32768,
            ),
            pricing=ModelPricing(input_per_million=0.15, output_per_million=1.10),
            **_MINIMAX_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="MiniMax-M2.1-lightning",
            model_type=ModelType.LLM,
            display_name="MiniMax M2.1 Lightning",
            description="MiniMax 极速版，~100 tps",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=32768,
            ),
            pricing=ModelPricing(input_per_million=0.10, output_per_million=0.70),
            **_MINIMAX_COMMON,
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="MiniMax-M2",
            model_type=ModelType.LLM,
            display_name="MiniMax M2",
            description="MiniMax Agent/Coding 专精模型",
            capabilities=ModelCapabilities(
                supports_tools=True, supports_vision=False, supports_thinking=True,
                supports_streaming=True,
                max_tokens=32768,
            ),
            pricing=ModelPricing(input_per_million=0.15, output_per_million=1.10),
            **_MINIMAX_COMMON,
        )
    )

    logger.debug(f"📦 预置模型注册完成: {len(ModelRegistry._models)} 个模型")
