"""
图数据库工厂

根据配置创建对应的图存储实例
"""

import os
from typing import Optional

from logger import get_logger
from infra.graph.base import GraphStore

logger = get_logger("infra.graph")

# 单例
_graph_store: Optional[GraphStore] = None


async def create_graph_store(backend: str = None) -> Optional[GraphStore]:
    """
    创建图存储实例
    
    Args:
        backend: 后端类型 (neo4j/arangodb/neptune)
                 默认从环境变量 GRAPH_BACKEND 读取
                 
    Returns:
        GraphStore 实例，未配置时返回 None
    """
    backend = backend or os.getenv("GRAPH_BACKEND", "").lower()
    
    if not backend:
        logger.warning("⚠️ 未配置 GRAPH_BACKEND，图数据库功能不可用")
        return None
    
    try:
        if backend == "neo4j":
            from infra.graph.neo4j import Neo4jGraphStore
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "")
            database = os.getenv("NEO4J_DATABASE", "neo4j")
            return await Neo4jGraphStore.create(
                uri=uri,
                user=user,
                password=password,
                database=database
            )
        
        elif backend == "arangodb":
            from infra.graph.arangodb import ArangoGraphStore
            host = os.getenv("ARANGO_HOST", "localhost")
            port = int(os.getenv("ARANGO_PORT", "8529"))
            database = os.getenv("ARANGO_DATABASE", "_system")
            return await ArangoGraphStore.create(
                host=host,
                port=port,
                database=database
            )
        
        elif backend == "neptune":
            from infra.graph.neptune import NeptuneGraphStore
            endpoint = os.getenv("NEPTUNE_ENDPOINT")
            return await NeptuneGraphStore.create(endpoint=endpoint)
        
        else:
            logger.error(f"❌ 不支持的图数据库后端: {backend}")
            return None
            
    except ImportError as e:
        logger.warning(f"⚠️ 图数据库依赖未安装: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ 创建图存储失败: {e}")
        return None


async def get_graph_store() -> Optional[GraphStore]:
    """
    获取图存储实例（单例）
    
    Returns:
        GraphStore 实例
    """
    global _graph_store
    if _graph_store is None:
        _graph_store = await create_graph_store()
    return _graph_store

