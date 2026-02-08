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
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class EmbedderConfig:
    """
    Embedder 配置

    支持的提供商：
    - openai: OpenAI Embedding (推荐)
    - google: Google PaLM Embedding
    - huggingface: Hugging Face Embedding
    - ollama: 本地 Ollama Embedding
    """

    provider: str = field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "openai"))
    model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    )
    api_key: Optional[str] = field(default=None)
    base_url: Optional[str] = field(default=None)  # 用于 Ollama 等本地服务

    def __post_init__(self) -> None:
        """初始化后处理：根据 provider 设置 api_key"""
        if self.api_key is None:
            if self.provider == "openai":
                self.api_key = os.getenv("OPENAI_API_KEY")
                if not self.base_url:
                    self.base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
            elif self.provider == "google":
                self.api_key = os.getenv("GOOGLE_API_KEY")
            elif self.provider == "huggingface":
                self.api_key = os.getenv("HUGGINGFACE_API_KEY")
            elif self.provider == "ollama":
                self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        config = {"model": self.model}
        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            config["base_url"] = self.base_url
        return config


@dataclass
class LLMConfig:
    """
    LLM 配置（用于 Mem0 内部 fact extraction）

    支持的提供商：
    - anthropic: Claude (推荐)
    - openai: GPT 系列
    - google: Gemini
    - ollama: 本地模型
    """

    provider: str = field(default_factory=lambda: os.getenv("MEM0_LLM_PROVIDER", "anthropic"))
    model: str = field(
        default_factory=lambda: os.getenv(
            "MEM0_LLM_MODEL", "claude-sonnet-4-5-20250929"  # 默认使用 Claude
        )
    )
    api_key: Optional[str] = field(default=None)
    base_url: Optional[str] = field(default=None)

    def __post_init__(self) -> None:
        """初始化后处理：根据 provider 设置 api_key"""
        if self.api_key is None:
            if self.provider == "anthropic":
                self.api_key = os.getenv("ANTHROPIC_API_KEY")
            elif self.provider == "openai":
                self.api_key = os.getenv("OPENAI_API_KEY")
                if not self.base_url:
                    self.base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
            elif self.provider == "google":
                self.api_key = os.getenv("GOOGLE_API_KEY")
            elif self.provider == "ollama":
                self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式

        注意：Anthropic 不允许同时设置 temperature 和 top_p
        这里只设置 temperature，让 Mem0 不传 top_p
        """
        config = {
            "model": self.model,
            "temperature": 0,  # 只设置 temperature，不设置 top_p
        }
        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            config["base_url"] = self.base_url

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
    embedding_model_dims: int = 1536  # OpenAI text-embedding-3-small 默认维度

    # 子配置
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Mem0 特性配置
    version: str = "v1.1"  # Mem0 版本

    # 搜索配置
    default_search_limit: int = 10  # 默认搜索返回数量

    def __post_init__(self):
        """Ensure collection_name is instance-scoped."""
        prefix = f"{self.instance_name}_"
        if not self.collection_name.startswith(prefix):
            self.collection_name = f"{prefix}{self.collection_name}"

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


def set_mem0_config(config: Mem0Config) -> None:
    """
    设置全局 Mem0 配置

    Args:
        config: 新的配置实例
    """
    global _global_config
    _global_config = config
