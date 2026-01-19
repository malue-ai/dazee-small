"""
Mem0 配置模块

职责：
- Qdrant 向量存储配置
- LLM/Embedder 配置
- 环境变量管理

设计原则：
- 配置与实现分离
- 支持环境变量覆盖
- 提供合理默认值
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class QdrantConfig:
    """Qdrant 向量数据库配置"""
    
    # 连接配置
    url: Optional[str] = field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("QDRANT_API_KEY")
    )
    
    # 集合配置
    collection_name: str = field(
        default_factory=lambda: os.getenv("MEM0_COLLECTION_NAME", "mem0_memories")
    )
    embedding_model_dims: int = 1536  # OpenAI text-embedding-3-small 默认维度
    
    # 性能配置
    on_disk: bool = True  # 使用磁盘存储以支持大规模数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于 Mem0 配置）"""
        config = {
            "collection_name": self.collection_name,
            "embedding_model_dims": self.embedding_model_dims,
            "on_disk": self.on_disk,
        }
        if self.url:
            config["url"] = self.url
        if self.api_key:
            config["api_key"] = self.api_key
        return config


@dataclass
class TencentVectorDBConfig:
    """腾讯云向量数据库配置"""
    
    # 连接配置
    url: str = field(
        default_factory=lambda: os.getenv("TENCENT_VDB_URL", "http://localhost:8100")
    )
    username: str = field(
        default_factory=lambda: os.getenv("TENCENT_VDB_USERNAME", "root")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("TENCENT_VDB_API_KEY", "")
    )
    
    # 数据库/集合配置
    database_name: str = field(
        default_factory=lambda: os.getenv("TENCENT_VDB_DATABASE", "mem0_db")
    )
    collection_name: str = field(
        default_factory=lambda: os.getenv("MEM0_COLLECTION_NAME", "mem0_collection")
    )
    embedding_model_dims: int = 1536  # OpenAI text-embedding-3-small 默认维度
    
    # 向量索引配置
    metric_type: str = "COSINE"  # COSINE/L2/IP
    timeout: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "url": self.url,
            "username": self.username,
            "api_key": self.api_key,
            "database_name": self.database_name,
            "collection_name": self.collection_name,
            "embedding_model_dims": self.embedding_model_dims,
            "metric_type": self.metric_type,
            "timeout": self.timeout,
        }


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
    
    provider: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "openai")
    )
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
    
    provider: str = field(
        default_factory=lambda: os.getenv("MEM0_LLM_PROVIDER", "anthropic")
    )
    model: str = field(
        default_factory=lambda: os.getenv(
            "MEM0_LLM_MODEL", 
            "claude-sonnet-4-5-20250929"  # 默认使用 Claude
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
        
        # 关键：Anthropic 不允许 temperature + top_p 同时设置
        # 只设置 temperature=0，Mem0 就不会加 top_p
        if self.provider == "anthropic":
            config["temperature"] = 0.0
        
        return config


@dataclass
class Mem0Config:
    """
    Mem0 完整配置
    
    整合所有子配置，提供统一的配置入口
    
    使用示例：
        # 使用 Qdrant（默认）
        config = Mem0Config()
        
        # 使用腾讯云 VectorDB
        config = Mem0Config(vector_store_provider="tencent")
        
        mem0_dict = config.to_mem0_config()
        memory = Memory(config=mem0_dict)
    """
    
    # 向量存储提供商选择
    vector_store_provider: str = field(
        default_factory=lambda: os.getenv("VECTOR_STORE_PROVIDER", "qdrant")
    )
    
    # 子配置
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    tencent: TencentVectorDBConfig = field(default_factory=TencentVectorDBConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    
    # Mem0 特性配置
    version: str = "v1.1"  # Mem0 版本
    
    # 搜索配置
    default_search_limit: int = 10  # 默认搜索返回数量
    
    def to_mem0_config(self) -> Dict[str, Any]:
        """
        转换为 Mem0 Memory 构造函数所需的配置格式
        
        Returns:
            Mem0 兼容的配置字典
        """
        # 根据 provider 选择向量存储配置
        if self.vector_store_provider == "tencent":
            vector_store_config = {
                "provider": "custom",  # Mem0 的自定义provider
                "config": self.tencent.to_dict()
            }
        else:
            vector_store_config = {
                "provider": "qdrant",
                "config": self.qdrant.to_dict()
            }
        
        return {
            "version": self.version,
            "vector_store": vector_store_config,
            "embedder": {
                "provider": self.embedder.provider,
                "config": self.embedder.to_dict()
            },
            "llm": {
                "provider": self.llm.provider,
                "config": self.llm.to_dict()
            }
        }
    
    @classmethod
    def from_env(cls) -> "Mem0Config":
        """
        从环境变量创建配置
        
        环境变量：
        - QDRANT_URL: Qdrant 服务地址
        - QDRANT_API_KEY: Qdrant API 密钥（可选）
        - MEM0_COLLECTION_NAME: 集合名称
        - OPENAI_API_KEY: OpenAI API 密钥
        - EMBEDDING_MODEL: Embedding 模型名称
        - MEM0_LLM_MODEL: Mem0 内部使用的 LLM 模型
        
        Returns:
            配置好的 Mem0Config 实例
        """
        return cls(
            qdrant=QdrantConfig(),
            embedder=EmbedderConfig(),
            llm=LLMConfig()
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

