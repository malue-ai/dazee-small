"""
上下文融合引擎

职责：
1. 合并多个数据源的结果
2. 去重（相似内容）
3. 重排序（按相关性）
4. 控制总数量（Token 预算）
"""
from typing import List, Dict, Any
import logging

from core.context.provider import ContextType

logger = logging.getLogger(__name__)


class FusionEngine:
    """
    上下文融合引擎
    
    支持多种融合策略：
    - weighted_merge: 加权合并（默认）
    - round_robin: 轮询策略
    """
    
    def __init__(self, max_contexts: int = 10):
        """
        Args:
            max_contexts: 最多返回的上下文数量
        """
        self.max_contexts = max_contexts
        
        # 数据源权重（可配置）
        self.source_weights = {
            ContextType.KNOWLEDGE: 1.0,   # 知识库权重最高
            ContextType.MEMORY: 0.9,      # 用户记忆权重也很高
        }
        
        logger.info(
            f"FusionEngine initialized: max_contexts={max_contexts}, "
            f"weights={self.source_weights}"
        )
    
    def fuse(
        self,
        context_map: Dict[ContextType, List[Dict[str, Any]]],
        strategy: str = "weighted_merge"
    ) -> List[Dict[str, Any]]:
        """
        融合多个数据源的上下文
        
        Args:
            context_map: 各数据源的检索结果
            strategy: 融合策略（weighted_merge/round_robin）
            
        Returns:
            融合后的上下文列表（已排序、去重）
        """
        logger.info(
            f"FusionEngine.fuse: strategy={strategy}, "
            f"sources={list(context_map.keys())}, "
            f"total_contexts={sum(len(v) for v in context_map.values())}"
        )
        
        if strategy == "weighted_merge":
            result = self._weighted_merge(context_map)
        elif strategy == "round_robin":
            result = self._round_robin(context_map)
        else:
            logger.warning(f"未知的融合策略: {strategy}，使用默认策略 weighted_merge")
            result = self._weighted_merge(context_map)
        
        logger.info(f"FusionEngine.fuse: returned {len(result)} contexts")
        return result
    
    def _weighted_merge(
        self,
        context_map: Dict[ContextType, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        加权合并策略
        
        流程：
        1. 给每个上下文计算加权分数 = score * source_weight
        2. 按加权分数排序
        3. 去重（相似内容）
        4. 返回 Top-K
        """
        all_contexts = []
        
        # 1. 收集所有上下文，计算加权分数
        for source_type, contexts in context_map.items():
            weight = self.source_weights.get(source_type, 1.0)
            for ctx in contexts:
                ctx["weighted_score"] = ctx.get("score", 1.0) * weight
                all_contexts.append(ctx)
        
        # 2. 按加权分数排序
        all_contexts.sort(key=lambda x: x["weighted_score"], reverse=True)
        
        # 3. 去重（基于内容相似度）
        unique_contexts = self._deduplicate(all_contexts)
        
        # 4. 返回 Top-K
        return unique_contexts[:self.max_contexts]
    
    def _deduplicate(
        self,
        contexts: List[Dict[str, Any]],
        similarity_threshold: float = 0.9
    ) -> List[Dict[str, Any]]:
        """
        去重（移除相似的上下文）
        
        使用简单的文本相似度判断（可以升级为向量相似度）
        
        Args:
            contexts: 上下文列表
            similarity_threshold: 相似度阈值（0-1）
            
        Returns:
            去重后的上下文列表
        """
        unique = []
        for ctx in contexts:
            is_duplicate = False
            for existing in unique:
                # 简单判断：内容相似度（Jaccard）
                similarity = self._text_similarity(
                    ctx["content"],
                    existing["content"]
                )
                if similarity > similarity_threshold:
                    is_duplicate = True
                    logger.debug(
                        f"去重: {ctx['content'][:30]}... 与 "
                        f"{existing['content'][:30]}... 相似度={similarity:.2f}"
                    )
                    break
            
            if not is_duplicate:
                unique.append(ctx)
        
        logger.debug(f"去重: {len(contexts)} -> {len(unique)}")
        return unique
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        计算文本相似度（Jaccard）
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度（0-1）
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def _round_robin(
        self,
        context_map: Dict[ContextType, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        轮询策略（每个数据源轮流取一条）
        
        适用场景：希望保证各数据源都有代表性
        
        Args:
            context_map: 各数据源的检索结果
            
        Returns:
            融合后的上下文列表
        """
        result = []
        iterators = {
            source: iter(contexts)
            for source, contexts in context_map.items()
        }
        
        while len(result) < self.max_contexts and iterators:
            for source in list(iterators.keys()):
                try:
                    ctx = next(iterators[source])
                    result.append(ctx)
                    if len(result) >= self.max_contexts:
                        break
                except StopIteration:
                    # 该数据源已耗尽
                    del iterators[source]
        
        return result
    
    def set_weights(self, weights: Dict[ContextType, float]):
        """
        设置数据源权重
        
        Args:
            weights: {ContextType: weight}
        """
        self.source_weights.update(weights)
        logger.info(f"权重已更新: {self.source_weights}")
