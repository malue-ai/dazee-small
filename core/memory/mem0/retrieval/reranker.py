"""
Mem0 记忆重排序器

职责：
- 对向量检索召回的记忆进行二次排序
- 使用 LLM 评估记忆与查询的相关性
- 返回最相关的 Top-K 记忆

设计原则：
- 先召回更多候选（如30条），再精选（如5条）
- 使用小模型（Haiku）控制成本和延迟
- 支持异步调用
"""

import json
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("memory.mem0.reranker")


# ==================== Reranker Prompt ====================

RERANK_PROMPT = """你是一个记忆相关性评估专家。请评估以下记忆与用户查询的相关性。

用户查询: {query}

候选记忆:
{memories}

请为每条记忆评分（1-10分），并按相关性从高到低排序。

评分标准:
- 10分: 直接回答用户问题，包含关键信息
- 7-9分: 高度相关，提供有用上下文
- 4-6分: 部分相关，可能有帮助
- 1-3分: 不太相关或无关

输出 JSON 格式（只输出 JSON，不要其他文字）:
[
    {{"index": 0, "score": 9, "reason": "直接提到了用户询问的人名"}},
    {{"index": 2, "score": 7, "reason": "包含相关事件背景"}},
    ...
]

按 score 从高到低排序，只返回 score >= 5 的记忆。"""


class LLMReranker:
    """
    基于 LLM 的记忆重排序器

    流程:
    1. 向量检索召回 N 条候选（如 30 条）
    2. LLM 评估每条记忆与查询的相关性
    3. 返回 Top-K 最相关记忆（如 5 条）

    使用方法:
        reranker = LLMReranker()
        reranked = await reranker.rerank(query, candidates, top_k=5)
    """

    def __init__(self, llm_service=None) -> None:
        """
        初始化 Reranker

        Args:
            llm_service: LLM 服务实例（可选，默认使用 Haiku）
        """
        self._llm = llm_service

    async def _get_llm(self) -> Any:
        """Get LLM service (lazy-loaded via profile)."""
        if self._llm is None:
            try:
                from config.llm_config import get_llm_profile
                from core.llm import create_llm_service

                profile = await get_llm_profile("reranker")
                self._llm = create_llm_service(**profile)
                logger.info(f"[Reranker] LLM 初始化: model={profile.get('model')}")
            except Exception as e:
                logger.error(f"[Reranker] LLM 初始化失败: {e}", exc_info=True)
                raise
        return self._llm

    async def rerank(
        self, query: str, memories: List[Dict[str, Any]], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        对记忆进行重排序

        Args:
            query: 用户查询
            memories: 候选记忆列表，每个记忆包含 memory 字段
            top_k: 返回的最大记忆数

        Returns:
            重排序后的记忆列表（最相关的在前）
        """
        if not memories:
            return []

        if len(memories) <= top_k:
            # 候选数量不足，直接返回
            logger.debug(f"[Reranker] 候选数量 {len(memories)} <= top_k {top_k}，跳过重排序")
            return memories

        try:
            # 格式化记忆为编号列表
            memory_texts = []
            for i, mem in enumerate(memories):
                content = mem.get("memory", "")
                if content:
                    memory_texts.append(f"[{i}] {content}")

            if not memory_texts:
                return memories[:top_k]

            # 构建 Prompt
            prompt = RERANK_PROMPT.format(query=query, memories="\n".join(memory_texts))

            # 调用 LLM（Profile 驱动，懒加载）
            llm = await self._get_llm()
            from core.llm import Message

            response = await llm.create_message_async(
                messages=[Message(role="user", content=prompt)],
                system="你是记忆相关性评估专家，只输出 JSON 格式结果。",
            )

            # 解析响应
            result_text = response.content.strip()

            # 提取 JSON（处理可能的 markdown 代码块）
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            rankings = json.loads(result_text)

            # 按分数排序，返回 Top-K
            reranked = []
            for item in rankings[:top_k]:
                idx = item.get("index", 0)
                if 0 <= idx < len(memories):
                    mem = memories[idx].copy()
                    mem["rerank_score"] = item.get("score", 0)
                    mem["rerank_reason"] = item.get("reason", "")
                    reranked.append(mem)

            logger.info(f"[Reranker] 重排序完成: {len(memories)} 候选 -> {len(reranked)} 结果")
            return reranked

        except json.JSONDecodeError as e:
            logger.warning(f"[Reranker] JSON 解析失败: {e}，返回原始结果")
            return memories[:top_k]
        except Exception as e:
            logger.error(f"[Reranker] 重排序失败: {e}，返回原始结果")
            return memories[:top_k]


# ==================== 便捷函数 ====================

_reranker_instance: Optional[LLMReranker] = None


def get_reranker() -> LLMReranker:
    """获取 Reranker 单例"""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = LLMReranker()
    return _reranker_instance


def reset_reranker() -> None:
    """重置 Reranker 单例（用于测试）"""
    global _reranker_instance
    _reranker_instance = None
