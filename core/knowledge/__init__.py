"""
本地知识检索模块

Level 1: FTS5 全文搜索（零配置，内置）
Level 2: 混合搜索 FTS5 + sqlite-vec 语义搜索（可选，支持 OpenAI / 本地模型）
"""

from core.knowledge.embeddings import (
    EmbeddingProvider,
    GGUFEmbeddingProvider,
    LocalEmbeddingProvider,
    ModelNotAvailableError,
    OpenAIEmbeddingProvider,
    SentenceTransformerProvider,
    create_embedding_provider,
    download_gguf_model,
    get_models_dir,
    is_gguf_model_downloaded,
    normalize_l2,
)
from core.knowledge.file_indexer import FileIndexer
from core.knowledge.local_search import LocalKnowledgeManager, SearchResult

__all__ = [
    "LocalKnowledgeManager",
    "FileIndexer",
    "SearchResult",
    "EmbeddingProvider",
    "GGUFEmbeddingProvider",
    "SentenceTransformerProvider",
    "OpenAIEmbeddingProvider",
    "LocalEmbeddingProvider",
    "ModelNotAvailableError",
    "create_embedding_provider",
    "download_gguf_model",
    "is_gguf_model_downloaded",
    "get_models_dir",
    "normalize_l2",
]
