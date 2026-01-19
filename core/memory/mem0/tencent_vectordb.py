"""
腾讯云 VectorDB 适配器

将腾讯云向量数据库适配为 Mem0 VectorStore 接口

腾讯云 VectorDB SDK 接口说明：
- query(limit, document_ids, retrieve_vector) -> List[Dict]  每个 Dict: {id, score, data}
- search(vectors, params, limit, retrieve_vector) -> List[List[Dict]]  嵌套列表
- upsert(documents) -> Dict  {code, msg, affectedCount}
- delete(document_ids) -> Dict  {code, msg, affectedCount}
- collection 属性: collection_name, description, documentCount, shardNum, replicaNum, indexes
"""

from typing import List, Dict, Optional, Any
import uuid
import json
import tcvectordb
from tcvectordb.model.enum import FieldType, IndexType, MetricType, ReadConsistency
from tcvectordb.model.index import Index, VectorIndex, FilterIndex, HNSWParams
from tcvectordb.model.document import Document, SearchParams
from mem0.vector_stores.base import VectorStoreBase
from logger import get_logger

logger = get_logger("zenflux.mem0.tencent_vectordb")


class OutputData:
    """
    搜索结果数据结构
    
    与 Mem0 的 VectorStore 接口兼容
    """
    
    def __init__(self, id: str, score: float, payload: Dict) -> None:
        self.id = id
        self.score = score
        self.payload = payload or {}


class TencentVectorDB(VectorStoreBase):
    """
    腾讯云向量数据库适配器
    
    实现 Mem0 VectorStoreBase 接口，适配腾讯云 VectorDB SDK
    
    Args:
        url: 腾讯云VectorDB访问地址
        username: 用户名（通常为 root）
        api_key: API密钥
        database_name: 数据库名称
        collection_name: 集合名称
        embedding_model_dims: 向量维度（默认1536，对应OpenAI text-embedding-3-small）
        metric_type: 相似度度量类型（COSINE/L2/IP）
        timeout: 超时时间（秒）
    """
    
    def __init__(
        self,
        url: str,
        username: str,
        api_key: str,
        database_name: str = "mem0_db",
        collection_name: str = "mem0_collection",
        embedding_model_dims: int = 1536,
        metric_type: str = "COSINE",
        timeout: int = 30
    ):
        self.url = url
        self.username = username
        self.api_key = api_key
        self.database_name = database_name
        self.collection_name = collection_name
        self.embedding_model_dims = embedding_model_dims
        self.metric_type = metric_type
        self.timeout = timeout
        
        self.client = None
        self.db = None
        self.collection = None
        
        # 初始化客户端和数据库/集合
        self._init_client()
        self._init_database()
        self._init_collection()
    
    def _init_client(self) -> None:
        """初始化客户端连接"""
        try:
            self.client = tcvectordb.RPCVectorDBClient(
                url=self.url,
                username=self.username,
                key=self.api_key,
                read_consistency=ReadConsistency.EVENTUAL_CONSISTENCY,
                timeout=self.timeout
            )
            logger.info(f"[TencentVectorDB] 客户端创建成功: {self.url}")
        except Exception as e:
            logger.error(f"[TencentVectorDB] 客户端创建失败: {e}")
            raise
    
    def _init_database(self) -> None:
        """初始化数据库"""
        try:
            dbs = self.client.list_databases()
            db_names = [db.database_name for db in dbs]
            
            if self.database_name not in db_names:
                logger.info(f"[TencentVectorDB] 创建数据库: {self.database_name}")
                self.db = self.client.create_database(database_name=self.database_name)
            else:
                self.db = self.client.database(self.database_name)
                logger.info(f"[TencentVectorDB] 使用已存在的数据库: {self.database_name}")
        except Exception as e:
            logger.error(f"[TencentVectorDB] 数据库初始化失败: {e}")
            raise
    
    def _init_collection(self) -> None:
        """初始化集合"""
        try:
            collections = self.db.list_collections()
            col_names = [col.collection_name for col in collections]
            
            if self.collection_name not in col_names:
                logger.info(f"[TencentVectorDB] 创建集合: {self.collection_name}")
                self.create_col(
                    name=self.collection_name,
                    vector_size=self.embedding_model_dims,
                    distance=self.metric_type
                )
            else:
                self.collection = self.db.collection(self.collection_name)
                logger.info(f"[TencentVectorDB] 使用已存在的集合: {self.collection_name}")
        except Exception as e:
            logger.error(f"[TencentVectorDB] 集合初始化失败: {e}")
            raise
    
    # ==================== Mem0 VectorStoreBase 接口实现 ====================
    
    def create_col(self, name: str, vector_size: int, distance: str) -> None:
        """
        创建集合
        
        Args:
            name: 集合名称
            vector_size: 向量维度
            distance: 距离度量（COSINE/L2/IP）
        """
        try:
            metric_map = {
                "COSINE": MetricType.COSINE,
                "L2": MetricType.L2,
                "IP": MetricType.IP
            }
            metric_type = metric_map.get(distance.upper(), MetricType.COSINE)
            
            index = Index(
                FilterIndex(
                    name='id',
                    field_type=FieldType.String,
                    index_type=IndexType.PRIMARY_KEY
                ),
                VectorIndex(
                    name='vector',
                    dimension=vector_size,
                    index_type=IndexType.HNSW,
                    metric_type=metric_type,
                    params=HNSWParams(m=16, efconstruction=200)
                ),
                FilterIndex(
                    name='data',
                    field_type=FieldType.String,
                    index_type=IndexType.FILTER
                )
            )
            
            # 腾讯云单机版实例要求 replicas=0
            self.collection = self.db.create_collection(
                name=name,
                shard=1,
                replicas=0,
                description=f'Mem0 memory collection: {name}',
                index=index
            )
            
            logger.info(f"[TencentVectorDB] 集合创建成功: {name}")
            
        except Exception as e:
            logger.error(f"[TencentVectorDB] 创建集合失败: {e}")
            raise
    
    def insert(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None
    ):
        """
        插入向量
        
        Args:
            vectors: 向量列表
            payloads: 元数据列表（存储为 JSON 字符串）
            ids: ID列表（如果不提供则自动生成 UUID）
        """
        try:
            if not ids:
                ids = [str(uuid.uuid4()) for _ in vectors]
            
            if not payloads:
                payloads = [{}] * len(vectors)
            
            documents = []
            for vector, payload, doc_id in zip(vectors, payloads, ids):
                doc = Document(
                    id=doc_id,
                    vector=vector,
                    data=json.dumps(payload, ensure_ascii=False)
                )
                documents.append(doc)
            
            result = self.collection.upsert(documents=documents)
            affected = result.get('affectedCount', 0) if isinstance(result, dict) else len(documents)
            logger.debug(f"[TencentVectorDB] 插入成功: {affected} 条")
            
        except Exception as e:
            logger.error(f"[TencentVectorDB] 插入失败: {e}")
            raise
    
    def search(
        self,
        query: str,
        vectors: List[List[float]],
        limit: int = 5,
        filters: Optional[Dict] = None
    ) -> List[OutputData]:
        """
        搜索相似向量
        
        腾讯云 search 返回: [[{id, score, data}, ...], ...]
        
        Args:
            query: 查询文本（未使用，Mem0 传入）
            vectors: 查询向量（可能是单个向量或向量列表）
            limit: 返回数量
            filters: 过滤条件（TODO: 支持）
            
        Returns:
            OutputData 列表
        """
        try:
            results = []
            
            if not vectors:
                return results
            
            # 兼容单个向量（一维）和向量列表（二维）
            if vectors and isinstance(vectors[0], (int, float)):
                vectors = [vectors]
            
            search_params = SearchParams(ef=200)
            search_result = self.collection.search(
                vectors=vectors,
                params=search_params,
                limit=limit,
                retrieve_vector=False
            )
            
            # 解析 [[{id, score, data}, ...], ...]
            for inner_list in search_result:
                for doc in inner_list:
                    doc_id = doc.get('id', '')
                    doc_score = doc.get('score', 0.0)
                    doc_data = doc.get('data', '{}')
                    
                    try:
                        payload = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
                    except json.JSONDecodeError:
                        payload = {}
                    
                    results.append(OutputData(
                        id=doc_id,
                        score=doc_score,
                        payload=payload
                    ))
            
            logger.debug(f"[TencentVectorDB] 搜索完成: {len(results)} 条结果")
            return results
            
        except Exception as e:
            logger.error(f"[TencentVectorDB] 搜索失败: {e}")
            raise
    
    def delete(self, vector_id: str) -> None:
        """
        删除向量
        
        Args:
            vector_id: 向量ID
        """
        try:
            result = self.collection.delete(document_ids=[vector_id])
            logger.debug(f"[TencentVectorDB] 删除成功: {vector_id}")
        except Exception as e:
            logger.error(f"[TencentVectorDB] 删除失败: {e}")
            raise
    
    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict] = None
    ):
        """
        更新向量（使用 upsert 实现）
        
        Args:
            vector_id: 向量ID
            vector: 新向量（可选）
            payload: 新元数据（可选）
        """
        try:
            if vector is not None and payload is not None:
                doc = Document(
                    id=vector_id,
                    vector=vector,
                    data=json.dumps(payload, ensure_ascii=False)
                )
                self.collection.upsert(documents=[doc])
                logger.debug(f"[TencentVectorDB] 更新成功: {vector_id}")
            elif payload is not None:
                # 只更新 payload，需要先获取原向量
                existing = self.get(vector_id)
                if existing:
                    # 腾讯云需要向量才能 upsert，这里使用占位向量
                    logger.warning(f"[TencentVectorDB] 仅更新payload需要原向量，跳过: {vector_id}")
        except Exception as e:
            logger.error(f"[TencentVectorDB] 更新失败: {e}")
            raise
    
    def get(self, vector_id: str) -> Optional[OutputData]:
        """
        根据ID获取向量
        
        腾讯云 query(document_ids) 返回: [{id, score, data}, ...]
        
        Args:
            vector_id: 向量ID
            
        Returns:
            OutputData 或 None
        """
        try:
            result = self.collection.query(
                document_ids=[vector_id],
                retrieve_vector=False
            )
            
            # result 是 List[Dict]
            if result and len(result) > 0:
                doc = result[0]
                doc_data = doc.get('data', '{}')
                
                try:
                    payload = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
                except json.JSONDecodeError:
                    payload = {}
                
                return OutputData(
                    id=doc.get('id', ''),
                    score=doc.get('score', 1.0),
                    payload=payload
                )
            return None
            
        except Exception as e:
            logger.error(f"[TencentVectorDB] 获取失败: {e}")
            return None
    
    def list(
        self,
        filters: Optional[Dict] = None,
        limit: Optional[int] = None
    ) -> List[OutputData]:
        """
        列出所有记忆
        
        腾讯云 query(limit) 返回: [{id, score, data}, ...]
        
        Args:
            filters: 过滤条件（TODO: 支持）
            limit: 限制数量
            
        Returns:
            OutputData 列表
        """
        try:
            result = self.collection.query(
                limit=limit or 100,
                retrieve_vector=False
            )
            
            results = []
            # result 是 List[Dict]
            for doc in result:
                doc_data = doc.get('data', '{}')
                
                try:
                    payload = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
                except json.JSONDecodeError:
                    payload = {}
                
                results.append(OutputData(
                    id=doc.get('id', ''),
                    score=doc.get('score', 1.0),
                    payload=payload
                ))
            
            logger.debug(f"[TencentVectorDB] 列出记忆: {len(results)} 条")
            return results
            
        except Exception as e:
            logger.error(f"[TencentVectorDB] 列出记忆失败: {e}")
            return []
    
    # ==================== 集合管理接口 ====================
    
    def list_cols(self) -> List[str]:
        """列出所有集合名称"""
        try:
            collections = self.db.list_collections()
            return [col.collection_name for col in collections]
        except Exception as e:
            logger.error(f"[TencentVectorDB] 列出集合失败: {e}")
            return []
    
    def delete_col(self) -> None:
        """删除当前集合"""
        try:
            self.db.drop_collection(self.collection_name)
            logger.info(f"[TencentVectorDB] 删除集合成功: {self.collection_name}")
        except Exception as e:
            logger.error(f"[TencentVectorDB] 删除集合失败: {e}")
            raise
    
    def col_info(self) -> Dict[str, Any]:
        """
        获取集合信息
        
        使用 collection 对象的属性而非 describe_collection
        """
        try:
            return {
                "name": self.collection.collection_name,
                "description": getattr(self.collection, 'description', '') or '',
                "document_count": getattr(self.collection, 'documentCount', 0),
                "shard_num": getattr(self.collection, 'shardNum', 1),
                "replica_num": getattr(self.collection, 'replicaNum', 0),
            }
        except Exception as e:
            logger.error(f"[TencentVectorDB] 获取集合信息失败: {e}")
            return {"name": self.collection_name}
    
    def count(self) -> int:
        """获取文档数量"""
        try:
            # 使用 collection.count() 方法
            result = self.collection.count()
            if isinstance(result, dict):
                return result.get('count', 0)
            return int(result) if result else 0
        except Exception as e:
            logger.error(f"[TencentVectorDB] 获取文档数量失败: {e}")
            return 0
    
    def truncate(self) -> None:
        """清空集合（保留结构，删除所有数据）"""
        try:
            self.db.truncate_collection(self.collection_name)
            logger.info(f"[TencentVectorDB] 清空集合成功: {self.collection_name}")
        except Exception as e:
            logger.error(f"[TencentVectorDB] 清空集合失败: {e}")
            raise
    
    def reset(self) -> None:
        """重置集合（删除后重建）"""
        try:
            logger.info(f"[TencentVectorDB] 重置集合: {self.collection_name}")
            self.delete_col()
            self.create_col(
                name=self.collection_name,
                vector_size=self.embedding_model_dims,
                distance=self.metric_type
            )
        except Exception as e:
            logger.error(f"[TencentVectorDB] 重置集合失败: {e}")
            raise
