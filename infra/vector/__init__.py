"""
向量数据库模块

提供向量存储和相似度检索能力，支持：
- Milvus (推荐，开源自托管)
- Qdrant (轻量级，推荐开发环境)
- Pinecone (SaaS，生产环境)
- 腾讯云向量数据库 (国内云)

使用场景：
- RAG 知识库检索
- 语义搜索
- 用户画像向量化
- 长期记忆存储
"""

from infra.vector.base import VectorStore, VectorSearchResult
from infra.vector.factory import create_vector_store, get_vector_store

__all__ = [
    "VectorStore",
    "VectorSearchResult",
    "create_vector_store",
    "get_vector_store",
]

