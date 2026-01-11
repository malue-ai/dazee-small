"""
图数据库模块

提供图结构存储和查询能力，支持：
- Neo4j (推荐，功能最全)
- ArangoDB (多模型，文档+图)
- Amazon Neptune (AWS 托管)

使用场景：
- 知识图谱存储
- 实体关系管理
- 用户社交关系
- 复杂关联查询
"""

from infra.graph.base import GraphStore, Node, Relationship, GraphQueryResult
from infra.graph.factory import create_graph_store, get_graph_store

__all__ = [
    "GraphStore",
    "Node",
    "Relationship",
    "GraphQueryResult",
    "create_graph_store",
    "get_graph_store",
]

