"""
向量数据库工厂

根据配置创建对应的向量存储实例
"""

import os
from typing import Optional

from logger import get_logger
from infra.vector.base import VectorStore

logger = get_logger("infra.vector")

# 单例
_vector_store: Optional[VectorStore] = None


async def create_vector_store(backend: str = None) -> Optional[VectorStore]:
    """
    创建向量存储实例
    
    Args:
        backend: 后端类型 (milvus/qdrant/pinecone/tencent)
                 默认从环境变量 VECTOR_BACKEND 读取
                 
    Returns:
        VectorStore 实例，未配置时返回 None
    """
    backend = backend or os.getenv("VECTOR_BACKEND", "").lower()
    
    if not backend:
        logger.warning("⚠️ 未配置 VECTOR_BACKEND，向量数据库功能不可用")
        return None
    
    try:
        if backend == "milvus":
            from infra.vector.milvus import MilvusVectorStore
            host = os.getenv("MILVUS_HOST", "localhost")
            port = int(os.getenv("MILVUS_PORT", "19530"))
            return await MilvusVectorStore.create(host=host, port=port)
        
        elif backend == "qdrant":
            from infra.vector.qdrant import QdrantVectorStore
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            return await QdrantVectorStore.create(host=host, port=port)
        
        elif backend == "pinecone":
            from infra.vector.pinecone import PineconeVectorStore
            api_key = os.getenv("PINECONE_API_KEY")
            environment = os.getenv("PINECONE_ENVIRONMENT")
            return await PineconeVectorStore.create(
                api_key=api_key,
                environment=environment
            )
        
        elif backend == "tencent":
            from infra.vector.tencent import TencentVectorStore
            # 腾讯云向量数据库配置
            return await TencentVectorStore.create()
        
        else:
            logger.error(f"❌ 不支持的向量数据库后端: {backend}")
            return None
            
    except ImportError as e:
        logger.warning(f"⚠️ 向量数据库依赖未安装: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ 创建向量存储失败: {e}")
        return None


async def get_vector_store() -> Optional[VectorStore]:
    """
    获取向量存储实例（单例）
    
    Returns:
        VectorStore 实例
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = await create_vector_store()
    return _vector_store

