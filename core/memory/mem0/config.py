"""
Mem0 配置模块

职责：
- LLM/Embedder 配置
- 向量存储配置（sqlite-vec）
- 环境变量管理

设计原则：
- 配置与实现分离
- 支持环境变量覆盖
- 100% 本地，零外部服务依赖
- Embedding 自动检测：用户填哪家 API Key，就用哪家的 embedding 模型（无感）
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from logger import get_logger

_logger = get_logger("memory.mem0.config")

# ==================== 自动检测配置 ====================
#
# 按优先级排列。当 provider 为空或 "auto" 时，遍历对应列表，
# 找到第一个有 API Key 的厂商即使用其服务。
#
# DashScope (阿里云) 兼容 OpenAI 接口，Mem0 侧 provider 填 "openai"
# 配合 base_url 指向 DashScope 端点即可。

EMBEDDING_AUTO_DETECT: List[Dict[str, Any]] = [
    {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "provider": "openai",
        "model": "text-embedding-3-small",
        "dims": 1536,
    },
    {
        "name": "DashScope (Qwen)",
        "env_key": "DASHSCOPE_API_KEY",
        "provider": "openai",  # OpenAI-compatible API
        "model": "text-embedding-v3",
        "dims": 1024,
    },
    {
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "provider": "google",
        "model": "text-embedding-004",
        "dims": 768,
    },
]

LLM_AUTO_DETECT: List[Dict[str, Any]] = [
    {
        "name": "Anthropic (Claude)",
        "env_key": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
    },
    {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "provider": "openai",
        "model": "gpt-4o-mini",
    },
    {
        "name": "DashScope (Qwen)",
        "env_key": "DASHSCOPE_API_KEY",
        "provider": "openai",  # OpenAI-compatible API
        "model": "qwen-plus",
    },
    {
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "provider": "gemini",
        "model": "gemini-2.0-flash",
    },
]


def _resolve_base_url(env_key: str) -> Optional[str]:
    """
    Resolve embedding API base_url for a given provider.

    Reuses the same endpoint configuration as the corresponding LLM service,
    avoiding hardcoded URLs.
    """
    if env_key == "OPENAI_API_KEY":
        return os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")

    if env_key == "DASHSCOPE_API_KEY":
        # Follow Qwen LLM service's endpoint (QwenRegions)
        try:
            from core.llm.qwen import QwenRegions
            region = os.getenv("DASHSCOPE_REGION", "singapore")
            return QwenRegions.MAPPING.get(region, QwenRegions.SINGAPORE)
        except ImportError:
            return None

    return None


@dataclass
class EmbedderConfig:
    """
    Embedder 配置

    支持的模式：
    - auto: 自动检测可用 API Key，按优先级选择 (推荐，默认)
    - openai: OpenAI Embedding
    - google: Google Gemini Embedding
    - huggingface: Hugging Face Embedding
    - ollama: 本地 Ollama Embedding
    """

    provider: str = field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "auto"))
    model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "")
    )
    api_key: Optional[str] = field(default=None)
    base_url: Optional[str] = field(default=None)
    dims: int = 1536  # Auto-resolved in __post_init__

    def __post_init__(self) -> None:
        """Initialize: auto-detect or resolve explicit provider."""
        if self.api_key is not None:
            # Caller provided everything explicitly
            return

        if self.provider == "auto":
            self._auto_detect()
        else:
            self._resolve_explicit_provider()

    def _auto_detect(self) -> None:
        """Auto-detect best embedding provider from available API keys."""
        for candidate in EMBEDDING_AUTO_DETECT:
            api_key = os.getenv(candidate["env_key"])
            if api_key:
                self.provider = candidate["provider"]
                self.api_key = api_key
                if not self.model:
                    self.model = candidate["model"]
                self.dims = candidate["dims"]
                self.base_url = _resolve_base_url(candidate["env_key"])
                _logger.info(
                    f"Embedding 自动检测: {candidate['name']} "
                    f"(model={self.model}, dims={self.dims}, "
                    f"base_url={self.base_url or 'default'})"
                )
                return

        # No provider found — will fail gracefully at runtime
        _logger.warning("Embedding 自动检测: 未找到可用的 API Key，向量记忆不可用")
        if not self.model:
            self.model = "text-embedding-3-small"
        self.provider = "openai"  # Fallback, will error on use

    def _resolve_explicit_provider(self) -> None:
        """Resolve config for an explicitly set provider."""
        if self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.base_url:
                self.base_url = _resolve_base_url("OPENAI_API_KEY")
            if not self.model:
                self.model = "text-embedding-3-small"
            self.dims = 1536
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not self.model:
                self.model = "text-embedding-004"
            self.dims = 768
        elif self.provider == "huggingface":
            self.api_key = os.getenv("HUGGINGFACE_API_KEY")
        elif self.provider == "ollama":
            self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def to_dict(self) -> Dict[str, Any]:
        """转换为 mem0 BaseEmbedderConfig 接受的字典格式。

        mem0 使用 provider-specific 的 base_url 参数名：
        - openai → openai_base_url
        - ollama → ollama_base_url
        """
        config = {"model": self.model}
        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            if self.provider == "ollama":
                config["ollama_base_url"] = self.base_url
            else:
                # openai / openai-compatible (e.g. DashScope)
                config["openai_base_url"] = self.base_url
        return config


@dataclass
class LLMConfig:
    """
    LLM 配置（用于 Mem0 内部 fact extraction）

    支持的模式：
    - auto: 自动检测可用 API Key，按优先级选择 (推荐，默认)
    - anthropic: Claude
    - openai: GPT 系列
    - gemini: Google Gemini
    - ollama: 本地模型
    """

    provider: str = field(default_factory=lambda: os.getenv("MEM0_LLM_PROVIDER", "auto"))
    model: str = field(
        default_factory=lambda: os.getenv("MEM0_LLM_MODEL", "")
    )
    api_key: Optional[str] = field(default=None)
    base_url: Optional[str] = field(default=None)

    def __post_init__(self) -> None:
        """Initialize: auto-detect or resolve explicit provider."""
        if self.api_key is not None:
            return

        if self.provider in ("auto", ""):
            self._auto_detect()
        else:
            self._resolve_explicit_provider()

    def _auto_detect(self) -> None:
        """Auto-detect best LLM provider from available API keys."""
        for candidate in LLM_AUTO_DETECT:
            api_key = os.getenv(candidate["env_key"])
            if api_key:
                self.provider = candidate["provider"]
                self.api_key = api_key
                if not self.model:
                    self.model = candidate["model"]
                self.base_url = _resolve_base_url(candidate["env_key"])
                _logger.info(
                    f"Mem0 LLM 自动检测: {candidate['name']} "
                    f"(model={self.model}, "
                    f"base_url={self.base_url or 'default'})"
                )
                return

        _logger.warning("Mem0 LLM 自动检测: 未找到可用的 API Key，记忆提取不可用")
        if not self.model:
            self.model = "gpt-4o-mini"
        self.provider = "openai"  # Fallback, will error on use

    def _resolve_explicit_provider(self) -> None:
        """Resolve config for an explicitly set provider."""
        if self.provider == "anthropic":
            self.api_key = os.getenv("ANTHROPIC_API_KEY")
        elif self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.base_url:
                self.base_url = _resolve_base_url("OPENAI_API_KEY")
        elif self.provider in ("google", "gemini"):
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        elif self.provider == "ollama":
            self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def to_dict(self) -> Dict[str, Any]:
        """转换为 mem0 BaseLlmConfig 接受的字典格式。

        mem0 使用 provider-specific 的 base_url 参数名：
        - openai → openai_base_url
        - ollama → ollama_base_url

        注意：Anthropic 不允许同时设置 temperature 和 top_p，
        这里只设置 temperature，让 Mem0 不传 top_p。
        """
        config = {
            "model": self.model,
            "temperature": 0,  # 只设置 temperature，不设置 top_p
        }
        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            if self.provider == "ollama":
                config["ollama_base_url"] = self.base_url
            else:
                # openai / openai-compatible
                config["openai_base_url"] = self.base_url

        # Anthropic 不允许 temperature + top_p 同时设置
        if self.provider == "anthropic":
            config["temperature"] = 0.0

        return config


def _default_instance_name() -> str:
    """Get current instance name from environment."""
    return os.getenv("AGENT_INSTANCE", "default")


@dataclass
class Mem0Config:
    """
    Mem0 完整配置

    整合所有子配置，向量存储固定使用 sqlite-vec（本地）。
    所有存储路径按 instance_name 隔离。

    使用示例：
        config = Mem0Config(instance_name="xiaodazi")
        pool = Mem0MemoryPool(config)
    """

    # Instance isolation — all DB paths are scoped by this name
    instance_name: str = field(default_factory=_default_instance_name)

    # 向量存储配置 — collection_name auto-prefixed with instance_name
    collection_name: str = field(
        default_factory=lambda: os.getenv("MEM0_COLLECTION_NAME", "mem0_memories")
    )
    # 0 = auto-resolve from embedder.dims (recommended)
    embedding_model_dims: int = 0

    # 子配置
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Mem0 特性配置
    version: str = "v1.1"  # Mem0 版本

    # 搜索配置
    default_search_limit: int = 10  # 默认搜索返回数量

    def __post_init__(self):
        """Ensure collection_name is instance-scoped, dims auto-resolved."""
        prefix = f"{self.instance_name}_"
        if not self.collection_name.startswith(prefix):
            self.collection_name = f"{prefix}{self.collection_name}"

        # Auto-resolve embedding dimensions from detected provider
        if self.embedding_model_dims == 0:
            self.embedding_model_dims = self.embedder.dims

    @property
    def db_path(self) -> str:
        """Instance-scoped vector DB path."""
        from utils.app_paths import get_instance_store_dir

        return str(get_instance_store_dir(self.instance_name) / "mem0_vectors.db")

    @property
    def history_db_name(self) -> str:
        """Instance-scoped history DB filename."""
        return f"{self.instance_name}_mem0_history.db"

    @classmethod
    def from_env(cls) -> "Mem0Config":
        """
        从环境变量创建配置

        环境变量：
        - AGENT_INSTANCE: 实例名称（隔离关键）
        - MEM0_COLLECTION_NAME: 集合名称
        - OPENAI_API_KEY: OpenAI API 密钥（Embedding 使用）
        - EMBEDDING_MODEL: Embedding 模型名称
        - MEM0_LLM_MODEL: Mem0 内部使用的 LLM 模型
        - MEM0_LLM_PROVIDER: Mem0 内部 LLM 提供商

        Returns:
            配置好的 Mem0Config 实例
        """
        return cls(
            instance_name=_default_instance_name(),
            embedder=EmbedderConfig(),
            llm=LLMConfig(),
        )


# ==================== 全局配置单例 ====================

_global_config: Optional[Mem0Config] = None


def get_mem0_config() -> Mem0Config:
    """
    获取全局 Mem0 配置（单例）

    Returns:
        全局配置实例
    """
    global _global_config
    if _global_config is None:
        _global_config = Mem0Config.from_env()
    return _global_config


def set_mem0_config(config: Optional[Mem0Config]) -> None:
    """
    设置全局 Mem0 配置

    传入 None 清除缓存，下次 get_mem0_config() 时重新创建
    （用于 API Key 变更后触发 embedding provider 重新检测）。

    Args:
        config: 新的配置实例，或 None 清除缓存
    """
    global _global_config
    _global_config = config
