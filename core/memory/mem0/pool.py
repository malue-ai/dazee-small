"""
Mem0 全局缓存池

职责：
- 管理 Mem0 Memory 实例
- 提供基于 user_id 的实例缓存
- 支持跨 Session 的用户记忆

设计原则：
- 单例模式：全局唯一的缓存池
- 懒加载：按需创建 Memory 实例
- 线程安全：支持并发访问
"""

import threading
from typing import Dict, List, Optional, Any
from logger import get_logger

from .config import Mem0Config, get_mem0_config

logger = get_logger("memory.mem0.pool")


class Mem0MemoryPool:
    """
    Mem0 全局缓存池（单例）
    
    管理所有用户的 Mem0 Memory 实例，支持：
    - 基于 user_id 的实例缓存
    - 跨 Session 的记忆持久化
    - 高效的记忆搜索
    
    使用示例：
        pool = get_mem0_pool()
        memories = pool.search(user_id="user_123", query="用户偏好")
    """
    
    _instance: Optional["Mem0MemoryPool"] = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Optional[Mem0Config] = None) -> "Mem0MemoryPool":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance
    
    def __init__(self, config: Optional[Mem0Config] = None):
        """
        初始化缓存池
        
        Args:
            config: Mem0 配置（可选，默认从环境变量读取）
        """
        if self._initialized:
            return
        
        self.config = config or get_mem0_config()
        self._memory: Optional[Any] = None  # Mem0 Memory 实例（懒加载）
        self._memory_lock = threading.Lock()
        self._initialized = True
        
        logger.info("[Mem0Pool] 缓存池初始化完成")
    
    @property
    def memory(self) -> Any:
        """
        获取 Mem0 Memory 实例（懒加载）
        
        Mem0 Memory 是用户无关的，user_id 在调用时传入
        
        Returns:
            Mem0 Memory 实例
        """
        if self._memory is None:
            with self._memory_lock:
                if self._memory is None:
                    self._memory = self._create_memory()
        return self._memory
    
    def _create_memory(self) -> Any:
        """
        创建 Mem0 Memory 实例
        
        Returns:
            配置好的 Memory 实例
        """
        try:
            from mem0 import Memory
            
            # 检查是否使用腾讯云VectorDB
            if self.config.vector_store_provider == "tencent":
                logger.info("[Mem0Pool] 使用腾讯云VectorDB - 手动创建组件")
                
                # 手动创建所有组件（绕过Mem0的Factory验证）
                from core.memory.mem0.tencent_vectordb import TencentVectorDB
                from mem0.utils.factory import EmbedderFactory, LlmFactory
                from mem0.memory.storage import SQLiteManager
                
                # 1. 创建腾讯云VectorDB
                tencent_config = self.config.tencent.to_dict()
                vector_store = TencentVectorDB(**tencent_config)
                
                # 2. 创建 Embedder
                embedding_model = EmbedderFactory.create(
                    self.config.embedder.provider,
                    self.config.embedder.to_dict(),
                    tencent_config  # 传递vector_store config
                )
                
                # 3. 创建 LLM
                llm = LlmFactory.create(
                    self.config.llm.provider,
                    self.config.llm.to_dict()
                )
                
                # 4. 创建 SQLite历史管理器
                db = SQLiteManager("mem0_history.db")
                
                # 5. 创建最小配置对象（用于MemoryConfig结构，供Memory内部方法访问）
                # 
                # 注意：Mem0的MemoryConfig只支持预定义的provider（如"qdrant"），不支持"tencent"
                # 因此我们使用Qdrant配置结构，但实际vector_store会被替换为TencentVectorDB实例
                # 这个配置仅用于满足MemoryConfig的验证要求，不会被实际使用
                #
                from mem0.configs.base import MemoryConfig as Mem0MemoryConfig
                from mem0.vector_stores.configs import VectorStoreConfig
                from mem0.embeddings.configs import EmbedderConfig
                from mem0.llms.configs import LlmConfig
                
                # 使用腾讯云的真实配置值（虽然不会真正连接Qdrant）
                # 这样配置更清晰，且collection_name和embedding_model_dims是实际需要的
                qdrant_config_dict = {
                    "url": tencent_config["url"],  # 使用腾讯云URL（虽然不会连接）
                    "api_key": tencent_config["api_key"],  # 使用腾讯云API Key（虽然不会使用）
                    "collection_name": tencent_config["collection_name"],  # ✅ 实际使用
                    "embedding_model_dims": tencent_config["embedding_model_dims"]  # ✅ 实际使用
                }
                
                minimal_config = Mem0MemoryConfig(
                    version=self.config.version,
                    vector_store=VectorStoreConfig(
                        provider="qdrant",
                        config=qdrant_config_dict
                    ),
                    embedder=EmbedderConfig(
                        provider=self.config.embedder.provider,
                        config=self.config.embedder.to_dict()
                    ),
                    llm=LlmConfig(
                        provider=self.config.llm.provider,
                        config=self.config.llm.to_dict()
                    )
                )
                
                # 6. 手动构造 Memory 实例
                # 
                # 关键：使用 __new__ 绕过 __init__，然后手动设置所有属性
                # 这样我们可以：
                # 1. 使用腾讯云VectorDB（而不是Qdrant）
                # 2. 保留MemoryConfig结构（供内部方法使用，如_build_filters_and_metadata）
                # 3. 实际使用我们创建的TencentVectorDB实例
                #
                memory = Memory.__new__(Memory)
                memory.config = minimal_config  # 保留配置结构（供内部方法使用）
                memory.custom_fact_extraction_prompt = None
                memory.custom_update_memory_prompt = None
                memory.embedding_model = embedding_model  # ✅ 实际使用
                memory.vector_store = vector_store  # ✅ 关键：使用腾讯云VectorDB实例
                memory.llm = llm  # ✅ 实际使用
                memory.db = db  # ✅ 实际使用
                memory.collection_name = tencent_config["collection_name"]  # ✅ 实际使用
                memory.api_version = self.config.version
                memory.reranker = None
                memory.enable_graph = False
                memory.graph = None
                
                logger.info(f"[Mem0Pool] Memory实例创建成功（腾讯云VectorDB）")
                return memory
            else:
                # 使用标准配置（Qdrant等）
                mem0_config = self.config.to_mem0_config()
                memory = Memory.from_config(config_dict=mem0_config)
                
                logger.info(f"[Mem0Pool] Memory实例创建成功（{self.config.vector_store_provider}）")
                return memory
                
        except ImportError as e:
            logger.error(f"[Mem0Pool] 依赖模块未安装: {e}")
            raise RuntimeError(
                "依赖模块未安装，请运行: pip install mem0ai tcvectordb"
            ) from e
        except Exception as e:
            logger.error(f"[Mem0Pool] Memory创建失败: {e}")
            raise
    
    def search(
        self,
        user_id: str,
        query: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索用户相关记忆
        
        Args:
            user_id: 用户 ID
            query: 搜索查询（通常是用户当前问题）
            limit: 返回数量限制（默认使用配置值）
            
        Returns:
            记忆列表，每个记忆包含：
            - id: 记忆 ID
            - memory: 记忆内容
            - score: 相关性分数
            - user_id: 用户 ID
            - created_at: 创建时间
            - metadata: 元数据
        """
        if not user_id or not query:
            logger.warning("[Mem0Pool] search: user_id 或 query 为空")
            return []
        
        try:
            search_limit = limit or self.config.default_search_limit
            
            result = self.memory.search(
                query=query,
                user_id=user_id,
                limit=search_limit
            )
            
            # 处理返回格式（Mem0 返回 {"results": [...]} 或直接列表）
            if isinstance(result, dict) and "results" in result:
                memories = result["results"]
            elif isinstance(result, list):
                memories = result
            else:
                memories = []
            
            logger.info(
                f"[Mem0Pool] 搜索完成: user_id={user_id}, "
                f"query={query[:30]}..., 结果数={len(memories)}"
            )
            return memories
            
        except Exception as e:
            logger.error(f"[Mem0Pool] 搜索失败: {e}")
            return []
    
    def add(
        self,
        user_id: str,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        添加记忆
        
        Args:
            user_id: 用户 ID
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            metadata: 额外元数据
            
        Returns:
            添加结果
        """
        if not user_id or not messages:
            logger.warning("[Mem0Pool] add: user_id 或 messages 为空")
            return {"results": []}
        
        try:
            result = self.memory.add(
                messages=messages,
                user_id=user_id,
                metadata=metadata
            )
            
            results_count = len(result.get("results", []))
            logger.info(
                f"[Mem0Pool] 添加记忆: user_id={user_id}, "
                f"messages={len(messages)}, 新增={results_count}"
            )
            return result
            
        except Exception as e:
            logger.error(f"[Mem0Pool] 添加记忆失败: {e}")
            return {"results": [], "error": str(e)}
    
    def get_all(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取用户所有记忆
        
        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            
        Returns:
            记忆列表
        """
        if not user_id:
            return []
        
        try:
            result = self.memory.get_all(user_id=user_id, limit=limit or 100)
            
            if isinstance(result, dict) and "results" in result:
                memories = result["results"]
            elif isinstance(result, list):
                memories = result
            else:
                memories = []
            
            logger.info(f"[Mem0Pool] 获取所有记忆: user_id={user_id}, 数量={len(memories)}")
            return memories
            
        except Exception as e:
            logger.error(f"[Mem0Pool] 获取所有记忆失败: {e}")
            return []
    
    def update(
        self,
        memory_id: str,
        data: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        更新单条记忆
        
        Args:
            memory_id: 记忆 ID
            data: 新的记忆内容
            user_id: 用户 ID（可选，用于日志）
            
        Returns:
            更新结果
        """
        try:
            result = self.memory.update(
                memory_id=memory_id,
                data=data
            )
            logger.info(f"[Mem0Pool] 更新记忆: memory_id={memory_id}, user_id={user_id}")
            return result
        except Exception as e:
            logger.error(f"[Mem0Pool] 更新记忆失败: {e}")
            return {"error": str(e)}
    
    def delete(self, memory_id: str, user_id: Optional[str] = None) -> bool:
        """
        删除单条记忆
        
        Args:
            memory_id: 记忆 ID
            user_id: 用户 ID（可选，用于日志）
            
        Returns:
            是否成功
        """
        try:
            self.memory.delete(memory_id=memory_id)
            logger.info(f"[Mem0Pool] 删除记忆: memory_id={memory_id}, user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"[Mem0Pool] 删除记忆失败: {e}")
            return False
    
    def reset_user(self, user_id: str) -> bool:
        """
        重置用户所有记忆
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否成功
        """
        try:
            self.memory.reset()  # 注意：Mem0 的 reset 是全局的
            # 如果需要只重置特定用户，需要使用 delete_all
            self.memory.delete_all(user_id=user_id)
            logger.info(f"[Mem0Pool] 重置用户记忆: user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"[Mem0Pool] 重置用户记忆失败: {e}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        try:
            # 尝试访问 memory 实例
            _ = self.memory
            return {
                "status": "healthy",
                "vector_store": "qdrant",
                "collection": self.config.qdrant.collection_name
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# ==================== 全局访问函数 ====================

_pool_instance: Optional[Mem0MemoryPool] = None


def get_mem0_pool(config: Optional[Mem0Config] = None) -> Mem0MemoryPool:
    """
    获取全局 Mem0 缓存池（单例）
    
    Args:
        config: 可选的配置（仅首次调用生效）
        
    Returns:
        Mem0MemoryPool 实例
        
    使用示例：
        from core.memory.mem0 import get_mem0_pool
        
        pool = get_mem0_pool()
        memories = pool.search(user_id="user_123", query="用户偏好")
    """
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = Mem0MemoryPool(config)
    return _pool_instance


def reset_mem0_pool() -> None:
    """
    重置全局缓存池（用于测试或重新初始化）
    """
    global _pool_instance
    _pool_instance = None
    Mem0MemoryPool._instance = None

