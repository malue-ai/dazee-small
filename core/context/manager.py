"""
上下文管理器（统一入口）

这是 Ragie 和 Mem0 的统一框架：
- 不再区分"知识库"和"记忆"
- 都是上下文数据源
- 统一检索、融合、注入

使用方式：
    context_mgr = ContextManager()
    
    # 获取上下文并注入提示词
    enhanced_prompt = await context_mgr.get_enhanced_prompt(
        base_prompt="你是一个智能助手",
        query="推荐一些适合我的书",
        user_id="user_123"
    )
"""
from typing import List, Dict, Any, Optional
import logging

from core.context.retriever import ContextRetriever
from core.context.fusion import FusionEngine
from core.context.injector import ContextInjector
from core.context.provider import ContextType

logger = logging.getLogger(__name__)


class ContextManager:
    """
    上下文管理器（统一入口）
    
    核心理念：
    - Ragie 和 Mem0 本质相同：都是为 LLM 提供上下文的数据源
    - 统一接口使得系统易于扩展和测试
    - 完整流程：检索 → 融合 → 注入
    
    架构：
        ContextManager
        ├── ContextRetriever（检索器）
        │   ├── KnowledgeProvider (Ragie)
        │   ├── MemoryProvider (Mem0)
        │   └── HistoryProvider (DB)
        ├── FusionEngine（融合引擎）
        │   ├── 加权合并
        │   ├── 去重
        │   └── 重排序
        └── ContextInjector（注入器）
            └── 生成最终 Prompt
    """
    
    def __init__(
        self,
        max_contexts: int = 10,
        max_tokens: int = 2000
    ):
        """
        Args:
            max_contexts: 融合后最多保留的上下文数量
            max_tokens: 上下文最大 Token 数量
        """
        self.retriever = ContextRetriever()
        self.fusion_engine = FusionEngine(max_contexts=max_contexts)
        self.injector = ContextInjector(max_tokens=max_tokens)
        
        logger.info(
            f"ContextManager initialized: max_contexts={max_contexts}, "
            f"max_tokens={max_tokens}"
        )
    
    async def get_enhanced_prompt(
        self,
        base_prompt: str,
        query: str,
        user_id: str,
        intent: Dict[str, Any] = None,
        conversation_id: str = None,
        fusion_strategy: str = "weighted_merge",
        format_style: str = "structured"
    ) -> str:
        """
        获取增强后的提示词（核心方法）
        
        完整流程：
        1. 根据意图决定检索哪些数据源
        2. 并发检索所有数据源
        3. 融合结果（去重、重排序）
        4. 注入到提示词
        
        Args:
            base_prompt: 基础系统提示词
            query: 用户查询
            user_id: 用户ID
            intent: 意图分析结果（可选）
            conversation_id: 会话ID（可选）
            fusion_strategy: 融合策略（weighted_merge/round_robin）
            format_style: 格式化风格（structured/narrative）
            
        Returns:
            增强后的系统提示词
        """
        logger.info(
            f"ContextManager.get_enhanced_prompt: query={query[:50]}, "
            f"user_id={user_id}, conversation_id={conversation_id}"
        )
        
        # 1. 根据意图决定数据源
        sources = self._determine_sources(intent)
        
        # 2. 检索上下文
        filters = {"conversation_id": conversation_id} if conversation_id else None
        context_map = await self.retriever.retrieve(
            query=query,
            user_id=user_id,
            sources=sources,
            top_k_per_source=5,
            filters=filters
        )
        
        # 3. 融合结果
        fused_contexts = self.fusion_engine.fuse(
            context_map=context_map,
            strategy=fusion_strategy
        )
        
        # 4. 注入到提示词
        enhanced_prompt = self.injector.inject(
            base_prompt=base_prompt,
            contexts=fused_contexts,
            format_style=format_style
        )
        
        logger.info("ContextManager.get_enhanced_prompt: 完成")
        return enhanced_prompt
    
    def _determine_sources(
        self,
        intent: Dict[str, Any] = None
    ) -> List[ContextType]:
        """
        根据意图决定检索哪些数据源
        
        策略：
        - 默认：全部数据源
        - 如果意图明确不需要个性化：只用知识库
        - 如果意图是回顾历史：优先历史对话
        
        Args:
            intent: 意图分析结果
                {
                    "needs_personalization": True,
                    "needs_knowledge": True,
                    "needs_history": True
                }
        
        Returns:
            要检索的数据源列表
        """
        if intent is None:
            # 默认：全部数据源（仅需要检索的）
            sources = [
                ContextType.KNOWLEDGE,
                ContextType.MEMORY,
            ]
            logger.debug("使用默认数据源: Knowledge + Memory")
            return sources
        
        # 根据意图标签决定
        needs_personalization = intent.get("needs_personalization", True)
        needs_knowledge = intent.get("needs_knowledge", True)
        
        sources = []
        
        if needs_knowledge:
            sources.append(ContextType.KNOWLEDGE)
        
        if needs_personalization:
            sources.append(ContextType.MEMORY)
        
        logger.debug(
            f"根据意图决定数据源: {[s.value for s in sources]}, "
            f"intent={intent}"
        )
        return sources
    
    async def update_context(
        self,
        user_id: str,
        source_type: ContextType,
        data: Dict[str, Any]
    ) -> bool:
        """
        更新上下文数据
        
        使用场景：
        - 对话结束后，更新 Mem0 记忆
        - 用户上传文档到知识库
        - 保存历史消息
        
        Args:
            user_id: 用户ID
            source_type: 数据源类型（KNOWLEDGE/MEMORY/HISTORY）
            data: 更新数据
            
        Returns:
            是否成功
        """
        success = await self.retriever.update(user_id, source_type, data)
        logger.info(
            f"ContextManager.update_context: {source_type.value}, "
            f"user_id={user_id}, success={success}"
        )
        return success
    
    async def health_check(self) -> Dict[str, bool]:
        """
        健康检查所有数据源
        
        Returns:
            {
                "knowledge": True,
                "memory": True,
                "history": True
            }
        """
        health_status = await self.retriever.health_check()
        all_healthy = all(health_status.values())
        logger.info(
            f"ContextManager.health_check: {health_status}, "
            f"all_healthy={all_healthy}"
        )
        return health_status
    
    def set_fusion_weights(self, weights: Dict[ContextType, float]):
        """
        设置融合引擎的数据源权重
        
        Args:
            weights: {ContextType: weight}
                例如：{
                    ContextType.KNOWLEDGE: 1.0,
                    ContextType.MEMORY: 0.8,
                    ContextType.HISTORY: 0.6
                }
        """
        self.fusion_engine.set_weights(weights)
        logger.info(f"ContextManager.set_fusion_weights: {weights}")


# 全局单例（可选）
_context_manager_instance = None


def get_context_manager() -> ContextManager:
    """
    获取全局 ContextManager 单例
    
    Returns:
        ContextManager 实例
    """
    global _context_manager_instance
    if _context_manager_instance is None:
        _context_manager_instance = ContextManager()
    return _context_manager_instance
