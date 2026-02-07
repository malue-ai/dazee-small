"""
全局模型注册中心

提供按模型维度的注册和管理，与 LLMRegistry（Provider 维度）配合使用。

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
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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


# ============================================================
# ModelRegistry
# ============================================================


class ModelRegistry:
    """
    全局模型注册中心

    职责：
    1. 管理所有已注册模型的配置
    2. 提供按模型名创建服务的接口
    3. 提供按类型查询模型的接口

    与 LLMRegistry 的关系：
    - LLMRegistry 注册 Provider（服务类 + 适配器）
    - ModelRegistry 注册 Model（具体配置），引用 Provider
    - 创建服务时：ModelRegistry 获取配置 → 调用 LLMRegistry 创建服务
    """

    _models: Dict[str, ModelConfig] = {}
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

        # 合并配置
        service_kwargs = {
            "base_url": config.base_url,
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

    @classmethod
    def _ensure_initialized(cls) -> None:
        """
        确保 Registry 已初始化（加载预置模型）
        """
        if cls._initialized:
            return

        # 加载预置模型
        _register_preset_models()

        cls._initialized = True
        logger.info(f"✅ ModelRegistry 初始化完成，已注册 {len(cls._models)} 个模型")

    @classmethod
    def reset(cls) -> None:
        """
        重置 Registry（仅用于测试）
        """
        cls._models.clear()
        cls._initialized = False


# ============================================================
# 预置模型注册
# ============================================================


def _register_preset_models() -> None:
    """
    注册预置模型

    在 ModelRegistry 初始化时自动调用。
    """
    # ==================== OpenAI 系列 ====================

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4o",
            model_type=ModelType.VLM,
            adapter=AdapterType.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            provider="openai",
            display_name="GPT-4o",
            description="OpenAI 最新旗舰模型，支持视觉",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=True,
                supports_thinking=False,
                max_tokens=16384,
                max_input_tokens=128000,
            ),
            pricing=ModelPricing(
                input_per_million=2.5,
                output_per_million=10.0,
            ),
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4o-mini",
            model_type=ModelType.VLM,
            adapter=AdapterType.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            provider="openai",
            display_name="GPT-4o Mini",
            description="GPT-4o 的轻量版本",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=True,
                supports_thinking=False,
                max_tokens=16384,
                max_input_tokens=128000,
            ),
            pricing=ModelPricing(
                input_per_million=0.15,
                output_per_million=0.60,
            ),
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="gpt-4-turbo",
            model_type=ModelType.VLM,
            adapter=AdapterType.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            provider="openai",
            display_name="GPT-4 Turbo",
            description="GPT-4 Turbo with Vision",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=True,
                supports_thinking=False,
                max_tokens=4096,
                max_input_tokens=128000,
            ),
            pricing=ModelPricing(
                input_per_million=10.0,
                output_per_million=30.0,
            ),
        )
    )

    # ==================== Claude 系列 ====================

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-sonnet-4-5-20250929",
            model_type=ModelType.VLM,
            adapter=AdapterType.CLAUDE,
            base_url="https://api.anthropic.com",
            api_key_env="ANTHROPIC_API_KEY",
            provider="claude",
            display_name="Claude Sonnet 4.5",
            description="Anthropic 最强智能体与编码模型",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=True,
                supports_thinking=True,
                max_tokens=128000,
                max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=3.0,
                output_per_million=15.0,
                cache_read_per_million=0.30,
                cache_write_per_million=3.75,
            ),
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-opus-4-20250514",
            model_type=ModelType.VLM,
            adapter=AdapterType.CLAUDE,
            base_url="https://api.anthropic.com",
            api_key_env="ANTHROPIC_API_KEY",
            provider="claude",
            display_name="Claude Opus 4",
            description="Anthropic 最强模型",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=True,
                supports_thinking=True,
                max_tokens=64000,
                max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=15.0,
                output_per_million=75.0,
                cache_read_per_million=1.50,
                cache_write_per_million=18.75,
            ),
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="claude-haiku-3-5-20241022",
            model_type=ModelType.VLM,
            adapter=AdapterType.CLAUDE,
            base_url="https://api.anthropic.com",
            api_key_env="ANTHROPIC_API_KEY",
            provider="claude",
            display_name="Claude Haiku 3.5",
            description="Claude 快速模型",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=True,
                supports_thinking=False,
                max_tokens=8192,
                max_input_tokens=200000,
            ),
            pricing=ModelPricing(
                input_per_million=0.80,
                output_per_million=4.0,
                cache_read_per_million=0.08,
                cache_write_per_million=1.0,
            ),
        )
    )

    # ==================== Qwen 系列 ====================

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen3-max",
            model_type=ModelType.LLM,
            adapter=AdapterType.OPENAI,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            api_key_env="DASHSCOPE_API_KEY",
            provider="qwen",
            display_name="通义千问 Qwen3-Max",
            description="阿里云旗舰模型，对标 Claude Sonnet",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=False,
                supports_thinking=True,
                max_tokens=65536,
                max_input_tokens=258048,
            ),
            # Qwen3-Max: ¥2/M input, ¥8/M output → ~$0.28/$1.10 per M
            pricing=ModelPricing(
                input_per_million=0.28,
                output_per_million=1.10,
            ),
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-plus",
            model_type=ModelType.LLM,
            adapter=AdapterType.OPENAI,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            api_key_env="DASHSCOPE_API_KEY",
            provider="qwen",
            display_name="通义千问 Qwen-Plus",
            description="阿里云快速模型",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=False,
                supports_thinking=True,
                max_tokens=32768,
                max_input_tokens=131072,
            ),
            # Qwen-Plus: ¥0.8/M input, ¥2/M output → ~$0.11/$0.28 per M
            pricing=ModelPricing(
                input_per_million=0.11,
                output_per_million=0.28,
            ),
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="qwen-vl-max",
            model_type=ModelType.VLM,
            adapter=AdapterType.OPENAI,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            api_key_env="DASHSCOPE_API_KEY",
            provider="qwen",
            display_name="通义千问 VL-Max",
            description="阿里云视觉语言模型",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=True,
                supports_thinking=False,
                max_tokens=32768,
            ),
            # Qwen-VL-Max: ¥3/M input, ¥8/M output → ~$0.41/$1.10 per M
            pricing=ModelPricing(
                input_per_million=0.41,
                output_per_million=1.10,
            ),
        )
    )

    # ==================== DeepSeek 系列 ====================

    ModelRegistry.register(
        ModelConfig(
            model_name="deepseek-chat",
            model_type=ModelType.LLM,
            adapter=AdapterType.OPENAI,
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            provider="openai",  # DeepSeek 使用 OpenAI 兼容接口
            display_name="DeepSeek Chat",
            description="DeepSeek 对话模型",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=False,
                supports_thinking=False,
                max_tokens=8192,
                max_input_tokens=64000,
            ),
            pricing=ModelPricing(
                input_per_million=0.27,
                output_per_million=1.10,
                cache_read_per_million=0.07,
            ),
        )
    )

    ModelRegistry.register(
        ModelConfig(
            model_name="deepseek-reasoner",
            model_type=ModelType.LLM,
            adapter=AdapterType.OPENAI,
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            provider="openai",
            display_name="DeepSeek Reasoner",
            description="DeepSeek 推理模型（R1）",
            capabilities=ModelCapabilities(
                supports_tools=True,
                supports_vision=False,
                supports_thinking=True,
                max_tokens=8192,
                max_input_tokens=64000,
            ),
            pricing=ModelPricing(
                input_per_million=0.55,
                output_per_million=2.19,
                cache_read_per_million=0.14,
            ),
        )
    )

    logger.debug(f"📦 预置模型注册完成: {len(ModelRegistry._models)} 个模型")
