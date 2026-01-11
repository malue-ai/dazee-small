"""
图数据库抽象基类

定义统一的图存储接口，支持多种后端实现
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Node:
    """
    图节点
    
    Attributes:
        id: 节点ID
        labels: 标签列表 (如 ["Person", "Developer"])
        properties: 属性字典
    """
    id: str
    labels: List[str]
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Relationship:
    """
    图关系/边
    
    Attributes:
        id: 关系ID
        type: 关系类型 (如 "KNOWS", "WORKS_AT")
        start_node_id: 起始节点ID
        end_node_id: 结束节点ID
        properties: 属性字典
    """
    id: str
    type: str
    start_node_id: str
    end_node_id: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphQueryResult:
    """
    图查询结果
    
    Attributes:
        nodes: 节点列表
        relationships: 关系列表
        raw: 原始查询结果
    """
    nodes: List[Node] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    raw: Any = None


class GraphStore(ABC):
    """
    图存储抽象基类
    
    定义统一的图操作接口
    """
    
    # ==================== 节点操作 ====================
    
    @abstractmethod
    async def create_node(
        self,
        labels: List[str],
        properties: Dict[str, Any],
        node_id: Optional[str] = None
    ) -> Node:
        """
        创建节点
        
        Args:
            labels: 标签列表
            properties: 属性字典
            node_id: 节点ID（可选，自动生成）
            
        Returns:
            创建的节点
        """
        pass
    
    @abstractmethod
    async def get_node(self, node_id: str) -> Optional[Node]:
        """
        获取节点
        
        Args:
            node_id: 节点ID
            
        Returns:
            节点对象，不存在返回 None
        """
        pass
    
    @abstractmethod
    async def update_node(
        self,
        node_id: str,
        properties: Dict[str, Any]
    ) -> Optional[Node]:
        """
        更新节点属性
        
        Args:
            node_id: 节点ID
            properties: 要更新的属性
            
        Returns:
            更新后的节点
        """
        pass
    
    @abstractmethod
    async def delete_node(self, node_id: str) -> bool:
        """
        删除节点
        
        Args:
            node_id: 节点ID
            
        Returns:
            是否删除成功
        """
        pass
    
    # ==================== 关系操作 ====================
    
    @abstractmethod
    async def create_relationship(
        self,
        start_node_id: str,
        end_node_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> Relationship:
        """
        创建关系
        
        Args:
            start_node_id: 起始节点ID
            end_node_id: 结束节点ID
            relationship_type: 关系类型
            properties: 关系属性
            
        Returns:
            创建的关系
        """
        pass
    
    @abstractmethod
    async def get_relationships(
        self,
        node_id: str,
        relationship_type: Optional[str] = None,
        direction: str = "both"  # "in" | "out" | "both"
    ) -> List[Relationship]:
        """
        获取节点的关系
        
        Args:
            node_id: 节点ID
            relationship_type: 关系类型过滤
            direction: 方向 (in/out/both)
            
        Returns:
            关系列表
        """
        pass
    
    @abstractmethod
    async def delete_relationship(self, relationship_id: str) -> bool:
        """
        删除关系
        
        Args:
            relationship_id: 关系ID
            
        Returns:
            是否删除成功
        """
        pass
    
    # ==================== 查询操作 ====================
    
    @abstractmethod
    async def query(
        self,
        cypher: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> GraphQueryResult:
        """
        执行 Cypher 查询（Neo4j 原生查询语言）
        
        Args:
            cypher: Cypher 查询语句
            parameters: 查询参数
            
        Returns:
            查询结果
        """
        pass
    
    @abstractmethod
    async def find_nodes_by_label(
        self,
        label: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[Node]:
        """
        按标签查找节点
        
        Args:
            label: 节点标签
            filters: 属性过滤条件
            limit: 返回数量限制
            
        Returns:
            节点列表
        """
        pass
    
    @abstractmethod
    async def find_shortest_path(
        self,
        start_node_id: str,
        end_node_id: str,
        relationship_types: Optional[List[str]] = None,
        max_depth: int = 10
    ) -> Optional[GraphQueryResult]:
        """
        查找最短路径
        
        Args:
            start_node_id: 起始节点ID
            end_node_id: 结束节点ID
            relationship_types: 允许的关系类型
            max_depth: 最大深度
            
        Returns:
            路径结果（包含节点和关系）
        """
        pass
    
    # ==================== 批量操作 ====================
    
    @abstractmethod
    async def batch_create_nodes(
        self,
        nodes: List[Dict[str, Any]]
    ) -> List[Node]:
        """
        批量创建节点
        
        Args:
            nodes: 节点数据列表 [{"labels": [...], "properties": {...}}, ...]
            
        Returns:
            创建的节点列表
        """
        pass
    
    @abstractmethod
    async def batch_create_relationships(
        self,
        relationships: List[Dict[str, Any]]
    ) -> List[Relationship]:
        """
        批量创建关系
        
        Args:
            relationships: 关系数据列表
            
        Returns:
            创建的关系列表
        """
        pass
    
    # ==================== 连接管理 ====================
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass

