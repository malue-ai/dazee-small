"""
RAG 管道优化模块

优化方向：
1. 检索参数优化（top_k、相似度阈值、重排序）
2. 增量索引管理（文档更新、向量同步）
3. 缓存策略（热点查询缓存、结果预计算）
4. 质量评估（检索召回率、相关性评分）

架构位置：core/context/rag_optimization.py
依赖：utils/ragie_client.py, services/mem0_service.py
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum

from logger import get_logger

logger = get_logger(__name__)


class IndexStatus(str, Enum):
    """索引状态"""
    PENDING = "pending"       # 等待索引
    INDEXING = "indexing"     # 索引中
    INDEXED = "indexed"       # 已索引
    FAILED = "failed"         # 索引失败
    OUTDATED = "outdated"     # 索引过期


@dataclass
class RAGConfig:
    """RAG 管道配置"""
    # 检索参数
    default_top_k: int = 5
    max_top_k: int = 20
    similarity_threshold: float = 0.1      # Ragie score 范围通常 0.1-0.3
    
    # 重排序配置
    enable_reranking: bool = True
    reranker_model: str = "cross-encoder"  # cross-encoder / bge-reranker
    rerank_top_k: int = 3                  # 重排序后保留数量
    
    # 缓存配置
    enable_cache: bool = True
    cache_ttl_seconds: int = 300           # 缓存 5 分钟
    max_cache_size: int = 1000             # 最大缓存条目
    
    # 增量索引配置
    incremental_batch_size: int = 100      # 批量索引大小
    index_delay_seconds: int = 60          # 索引延迟（去抖动）
    
    # 质量控制
    min_relevance_score: float = 0.1
    max_context_length: int = 8000         # 最大上下文长度（字符）


@dataclass
class DocumentIndexRecord:
    """文档索引记录"""
    document_id: str
    user_id: str
    source: str                 # "ragie" / "mem0"
    status: IndexStatus = IndexStatus.PENDING
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    indexed_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    
    # 索引信息
    chunk_count: int = 0
    vector_dimension: int = 0
    error_message: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


class IncrementalIndexManager:
    """
    增量索引管理器
    
    功能：
    1. 追踪文档变更，触发增量索引
    2. 批量处理索引任务
    3. 监控索引状态和进度
    4. 处理索引失败和重试
    """
    
    def __init__(self, config: Optional[RAGConfig] = None) -> None:
        self.config = config or RAGConfig()
        
        # 索引队列（内存）
        self._pending_queue: List[DocumentIndexRecord] = []
        self._index_records: Dict[str, DocumentIndexRecord] = {}
        
        # 统计信息
        self._stats = {
            "total_indexed": 0,
            "total_failed": 0,
            "total_pending": 0,
            "last_batch_time": None,
        }
        
        logger.info(
            f"✅ IncrementalIndexManager 初始化: "
            f"batch_size={self.config.incremental_batch_size}, "
            f"delay={self.config.index_delay_seconds}s"
        )
    
    def queue_document(
        self,
        document_id: str,
        user_id: str,
        source: str = "ragie",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentIndexRecord:
        """
        将文档加入索引队列
        
        Args:
            document_id: 文档 ID
            user_id: 用户 ID
            source: 数据源（ragie / mem0）
            metadata: 额外元数据
            
        Returns:
            DocumentIndexRecord 记录
        """
        # 检查是否已存在
        existing = self._index_records.get(document_id)
        if existing and existing.status == IndexStatus.INDEXING:
            logger.debug(f"文档 {document_id} 正在索引中，跳过")
            return existing
        
        # 创建记录
        record = DocumentIndexRecord(
            document_id=document_id,
            user_id=user_id,
            source=source,
            status=IndexStatus.PENDING,
            metadata=metadata or {},
        )
        
        self._index_records[document_id] = record
        self._pending_queue.append(record)
        self._stats["total_pending"] += 1
        
        logger.info(f"📝 文档已加入索引队列: {document_id} (source={source})")
        
        return record
    
    def get_pending_batch(self) -> List[DocumentIndexRecord]:
        """
        获取待处理的批次
        
        Returns:
            待索引的文档记录列表
        """
        batch_size = self.config.incremental_batch_size
        batch = self._pending_queue[:batch_size]
        
        # 更新状态
        for record in batch:
            record.status = IndexStatus.INDEXING
        
        return batch
    
    def mark_indexed(
        self,
        document_id: str,
        chunk_count: int = 0,
        vector_dimension: int = 0
    ):
        """
        标记文档已索引
        
        Args:
            document_id: 文档 ID
            chunk_count: 分块数量
            vector_dimension: 向量维度
        """
        record = self._index_records.get(document_id)
        if record:
            record.status = IndexStatus.INDEXED
            record.indexed_at = datetime.now()
            record.chunk_count = chunk_count
            record.vector_dimension = vector_dimension
            
            # 从队列移除
            self._pending_queue = [
                r for r in self._pending_queue 
                if r.document_id != document_id
            ]
            
            self._stats["total_indexed"] += 1
            self._stats["total_pending"] -= 1
            
            logger.info(f"✅ 文档索引完成: {document_id}, chunks={chunk_count}")
    
    def mark_failed(
        self,
        document_id: str,
        error_message: str
    ):
        """
        标记文档索引失败
        
        Args:
            document_id: 文档 ID
            error_message: 错误信息
        """
        record = self._index_records.get(document_id)
        if record:
            record.status = IndexStatus.FAILED
            record.error_message = error_message
            
            self._stats["total_failed"] += 1
            self._stats["total_pending"] -= 1
            
            logger.warning(f"❌ 文档索引失败: {document_id}, error={error_message}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            **self._stats,
            "pending_count": len(self._pending_queue),
            "total_records": len(self._index_records),
        }
    
    def get_outdated_documents(
        self,
        max_age: timedelta = timedelta(days=7)
    ) -> List[DocumentIndexRecord]:
        """
        获取过期文档（需要重新索引）
        
        Args:
            max_age: 最大索引年龄
            
        Returns:
            过期的文档记录列表
        """
        cutoff = datetime.now() - max_age
        outdated = []
        
        for record in self._index_records.values():
            if record.status == IndexStatus.INDEXED:
                if record.indexed_at and record.indexed_at < cutoff:
                    record.status = IndexStatus.OUTDATED
                    outdated.append(record)
        
        return outdated


class RAGQualityEvaluator:
    """
    RAG 质量评估器
    
    评估指标：
    1. 检索召回率（Recall）
    2. 相关性评分（Relevance）
    3. 响应时间（Latency）
    4. 答案准确率（Accuracy）
    """
    
    def __init__(self) -> None:
        self._evaluation_records: List[Dict[str, Any]] = []
    
    def record_retrieval(
        self,
        query: str,
        results: List[Dict[str, Any]],
        latency_ms: int,
        user_id: str,
        source: str = "ragie"
    ):
        """
        记录一次检索
        
        Args:
            query: 查询文本
            results: 检索结果
            latency_ms: 延迟（毫秒）
            user_id: 用户 ID
            source: 数据源
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "query": query[:100],  # 截断
            "result_count": len(results),
            "avg_score": sum(r.get("score", 0) for r in results) / len(results) if results else 0,
            "max_score": max(r.get("score", 0) for r in results) if results else 0,
            "latency_ms": latency_ms,
            "user_id": user_id,
            "source": source,
        }
        
        self._evaluation_records.append(record)
        
        # 保留最近 1000 条
        if len(self._evaluation_records) > 1000:
            self._evaluation_records = self._evaluation_records[-1000:]
    
    def get_metrics(self, last_n: int = 100) -> Dict[str, Any]:
        """
        获取评估指标
        
        Args:
            last_n: 最近 N 条记录
            
        Returns:
            评估指标字典
        """
        records = self._evaluation_records[-last_n:]
        
        if not records:
            return {"error": "无评估数据"}
        
        return {
            "total_queries": len(records),
            "avg_result_count": sum(r["result_count"] for r in records) / len(records),
            "avg_relevance_score": sum(r["avg_score"] for r in records) / len(records),
            "avg_latency_ms": sum(r["latency_ms"] for r in records) / len(records),
            "p95_latency_ms": sorted(r["latency_ms"] for r in records)[int(len(records) * 0.95)],
            "empty_result_rate": sum(1 for r in records if r["result_count"] == 0) / len(records),
        }


# ============================================================
# 全局实例
# ============================================================

_index_manager: Optional[IncrementalIndexManager] = None
_quality_evaluator: Optional[RAGQualityEvaluator] = None


def get_index_manager() -> IncrementalIndexManager:
    """获取增量索引管理器"""
    global _index_manager
    if _index_manager is None:
        _index_manager = IncrementalIndexManager()
    return _index_manager


def get_quality_evaluator() -> RAGQualityEvaluator:
    """获取 RAG 质量评估器"""
    global _quality_evaluator
    if _quality_evaluator is None:
        _quality_evaluator = RAGQualityEvaluator()
    return _quality_evaluator
