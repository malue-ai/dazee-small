"""
向量数据库抽象基类

定义统一的向量存储接口，支持多种后端实现
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class VectorSearchResult:
    """
    向量搜索结果
    
    Attributes:
        id: 文档ID
        score: 相似度得分 (0-1，越高越相似)
        content: 文档内容
        metadata: 元数据
    """
    id: str
    score: float
    content: str
    metadata: Dict[str, Any]


class VectorStore(ABC):
    """
    向量存储抽象基类
    
    定义统一的向量操作接口
    """
    
    @abstractmethod
    async def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        metric: str = "cosine"
    ) -> bool:
        """
        创建集合/索引
        
        Args:
            name: 集合名称
            dimension: 向量维度 (OpenAI: 1536, Claude: 1024)
            metric: 距离度量 (cosine/euclidean/dot_product)
            
        Returns:
            是否创建成功
        """
        pass
    
    @abstractmethod
    async def insert(
        self,
        collection: str,
        vectors: List[List[float]],
        documents: List[str],
        ids: Optional[List[str]] = None,
        metadata: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """
        插入向量
        
        Args:
            collection: 集合名称
            vectors: 向量列表
            documents: 文档内容列表
            ids: 文档ID列表（可选，自动生成）
            metadata: 元数据列表
            
        Returns:
            插入的文档ID列表
        """
        pass
    
    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        """
        向量相似度搜索
        
        Args:
            collection: 集合名称
            query_vector: 查询向量
            top_k: 返回结果数量
            filter: 元数据过滤条件
            
        Returns:
            搜索结果列表
        """
        pass
    
    @abstractmethod
    async def delete(
        self,
        collection: str,
        ids: List[str]
    ) -> int:
        """
        删除向量
        
        Args:
            collection: 集合名称
            ids: 要删除的文档ID列表
            
        Returns:
            删除的数量
        """
        pass
    
    @abstractmethod
    async def delete_collection(self, name: str) -> bool:
        """
        删除集合
        
        Args:
            name: 集合名称
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def get_collection_stats(self, name: str) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Args:
            name: 集合名称
            
        Returns:
            统计信息 (count, dimension, etc.)
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass

