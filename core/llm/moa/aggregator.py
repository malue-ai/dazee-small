"""
MoA 响应聚合器

V8.0 新增

职责：
- Aggregate-and-Synthesize 响应聚合
- 批判性评估多个模型的响应
- 综合优点生成最佳答案

聚合策略：
- CRITICAL_SYNTHESIS: 批判性综合（默认）
- BEST_OF_N: 选择最佳响应
- CONSENSUS: 共识聚合
- WEIGHTED_MERGE: 加权合并
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


class AggregationStrategy(Enum):
    """聚合策略"""

    CRITICAL_SYNTHESIS = "critical_synthesis"  # 批判性综合
    BEST_OF_N = "best_of_n"  # 选择最佳
    CONSENSUS = "consensus"  # 共识聚合
    WEIGHTED_MERGE = "weighted_merge"  # 加权合并


@dataclass
class AggregatedResponse:
    """聚合响应"""

    content: str  # 聚合后的内容
    strategy: AggregationStrategy  # 使用的策略
    source_count: int  # 源响应数量
    selected_sources: List[int] = field(default_factory=list)  # 选中的源索引
    confidence: float = 0.0  # 置信度
    reasoning: Optional[str] = None  # 聚合推理过程

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content[:500] + "..." if len(self.content) > 500 else self.content,
            "strategy": self.strategy.value,
            "source_count": self.source_count,
            "selected_sources": self.selected_sources,
            "confidence": self.confidence,
        }


class MoAAggregator:
    """
    MoA 响应聚合器

    功能：
    1. 批判性评估多个模型的响应
    2. 识别各响应的优点和不足
    3. 综合生成最佳答案

    使用方式：
        aggregator = MoAAggregator(llm_service=llm)

        result = await aggregator.aggregate(
            responses=[...],
            strategy=AggregationStrategy.CRITICAL_SYNTHESIS,
            context={"task_type": "task_decomposition"}
        )
    """

    # 聚合提示词模板
    AGGREGATE_PROMPT_TEMPLATE = """你是一个专业的 AI 响应聚合专家。你的任务是批判性地评估多个 AI 模型的响应，综合它们的优点，生成一个最佳答案。

## 原始任务
{original_task}

## 任务类型
{task_type}

## 多个模型的响应

{responses_section}

## 聚合要求

请按以下步骤进行聚合：

1. **分析每个响应**
   - 识别每个响应的核心观点
   - 评估其准确性和完整性
   - 找出独特的见解或遗漏

2. **批判性综合**
   - 比较各响应的差异
   - 识别共识和分歧
   - 权衡各方观点

3. **生成最佳答案**
   - 综合各响应的优点
   - 补充遗漏的重要内容
   - 确保答案完整准确

## 输出格式

请直接输出综合后的最佳答案。如果需要，可以先用 <reasoning> 标签包裹你的分析过程，然后输出最终答案。

<reasoning>
（分析过程，可选）
</reasoning>

（最终综合答案）
"""

    BEST_OF_N_PROMPT_TEMPLATE = """你是一个专业的 AI 响应评估专家。请从以下多个响应中选择最佳的一个。

## 原始任务
{original_task}

## 候选响应

{responses_section}

## 评估标准
1. 准确性：答案是否正确
2. 完整性：是否涵盖所有重要方面
3. 清晰度：表达是否清晰易懂
4. 实用性：是否可直接使用

## 输出格式
请输出以下 JSON：
```json
{{
    "selected_index": 0,
    "reason": "选择原因",
    "confidence": 0.0-1.0
}}
```
"""

    def __init__(
        self,
        llm_service: Any = None,
        default_strategy: AggregationStrategy = AggregationStrategy.CRITICAL_SYNTHESIS,
    ):
        """
        初始化聚合器

        Args:
            llm_service: LLM 服务
            default_strategy: 默认聚合策略
        """
        self.llm_service = llm_service
        self.default_strategy = default_strategy

        logger.info(f"✅ MoAAggregator 初始化: " f"strategy={default_strategy.value}")

    async def aggregate(
        self,
        responses: List[Dict[str, Any]],
        original_task: str = "",
        task_type: str = "general",
        strategy: Optional[AggregationStrategy] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AggregatedResponse:
        """
        聚合多个响应

        Args:
            responses: 响应列表，每个响应包含 {"content": "...", "model": "..."}
            original_task: 原始任务描述
            task_type: 任务类型
            strategy: 聚合策略（可选，使用默认策略）
            context: 额外上下文

        Returns:
            AggregatedResponse: 聚合结果
        """
        strategy = strategy or self.default_strategy
        context = context or {}

        # 过滤有效响应
        valid_responses = [r for r in responses if r.get("content")]

        if not valid_responses:
            return AggregatedResponse(
                content="",
                strategy=strategy,
                source_count=0,
                confidence=0.0,
            )

        if len(valid_responses) == 1:
            # 只有一个响应，直接返回
            return AggregatedResponse(
                content=valid_responses[0]["content"],
                strategy=strategy,
                source_count=1,
                selected_sources=[0],
                confidence=0.7,
            )

        logger.info(
            f"🔄 开始聚合: strategy={strategy.value}, " f"source_count={len(valid_responses)}"
        )

        # 根据策略选择聚合方法
        if strategy == AggregationStrategy.CRITICAL_SYNTHESIS:
            return await self._critical_synthesis(valid_responses, original_task, task_type)
        elif strategy == AggregationStrategy.BEST_OF_N:
            return await self._best_of_n(valid_responses, original_task)
        elif strategy == AggregationStrategy.CONSENSUS:
            return await self._consensus(valid_responses, original_task, task_type)
        elif strategy == AggregationStrategy.WEIGHTED_MERGE:
            return await self._weighted_merge(valid_responses, context)
        else:
            # 默认使用批判性综合
            return await self._critical_synthesis(valid_responses, original_task, task_type)

    async def _critical_synthesis(
        self,
        responses: List[Dict[str, Any]],
        original_task: str,
        task_type: str,
    ) -> AggregatedResponse:
        """批判性综合聚合"""
        if not self.llm_service:
            # 没有 LLM，退回到简单合并
            return self._simple_merge(responses)

        # 构建响应部分
        responses_section = self._build_responses_section(responses)

        # 构建提示词
        prompt = self.AGGREGATE_PROMPT_TEMPLATE.format(
            original_task=original_task or "（未提供）",
            task_type=task_type,
            responses_section=responses_section,
        )

        try:
            response = await self.llm_service.create_message_async(
                messages=[{"role": "user", "content": prompt}],
                system="你是一个专业的 AI 响应聚合专家。",
            )

            content = response.content
            reasoning = None

            # 解析 reasoning
            if "<reasoning>" in content and "</reasoning>" in content:
                reasoning_start = content.index("<reasoning>") + len("<reasoning>")
                reasoning_end = content.index("</reasoning>")
                reasoning = content[reasoning_start:reasoning_end].strip()
                content = content[reasoning_end + len("</reasoning>") :].strip()

            return AggregatedResponse(
                content=content,
                strategy=AggregationStrategy.CRITICAL_SYNTHESIS,
                source_count=len(responses),
                selected_sources=list(range(len(responses))),
                confidence=0.85,
                reasoning=reasoning,
            )

        except Exception as e:
            logger.warning(f"⚠️ 批判性综合失败: {e}")
            return self._simple_merge(responses)

    async def _best_of_n(
        self,
        responses: List[Dict[str, Any]],
        original_task: str,
    ) -> AggregatedResponse:
        """选择最佳响应"""
        if not self.llm_service:
            # 没有 LLM，选择第一个
            return AggregatedResponse(
                content=responses[0]["content"],
                strategy=AggregationStrategy.BEST_OF_N,
                source_count=len(responses),
                selected_sources=[0],
                confidence=0.6,
            )

        # 构建响应部分
        responses_section = self._build_responses_section(responses)

        # 构建提示词
        prompt = self.BEST_OF_N_PROMPT_TEMPLATE.format(
            original_task=original_task or "（未提供）",
            responses_section=responses_section,
        )

        try:
            response = await self.llm_service.create_message_async(
                messages=[{"role": "user", "content": prompt}],
                system="你是一个专业的 AI 响应评估专家。请严格按照 JSON 格式输出。",
            )

            # 解析 JSON
            import json

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())
            selected_index = result.get("selected_index", 0)
            confidence = result.get("confidence", 0.7)

            if selected_index < 0 or selected_index >= len(responses):
                selected_index = 0

            return AggregatedResponse(
                content=responses[selected_index]["content"],
                strategy=AggregationStrategy.BEST_OF_N,
                source_count=len(responses),
                selected_sources=[selected_index],
                confidence=confidence,
                reasoning=result.get("reason"),
            )

        except Exception as e:
            logger.warning(f"⚠️ Best-of-N 选择失败: {e}")
            return AggregatedResponse(
                content=responses[0]["content"],
                strategy=AggregationStrategy.BEST_OF_N,
                source_count=len(responses),
                selected_sources=[0],
                confidence=0.5,
            )

    async def _consensus(
        self,
        responses: List[Dict[str, Any]],
        original_task: str,
        task_type: str,
    ) -> AggregatedResponse:
        """共识聚合"""
        # 简化实现：使用批判性综合，但强调共识
        return await self._critical_synthesis(responses, original_task, task_type)

    async def _weighted_merge(
        self,
        responses: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> AggregatedResponse:
        """加权合并"""
        # 简化实现：根据模型权重选择
        weights = context.get("weights", {})

        # 找出权重最高的响应
        max_weight = 0
        best_index = 0

        for i, resp in enumerate(responses):
            model = resp.get("model", "")
            weight = weights.get(model, 1.0)
            if weight > max_weight:
                max_weight = weight
                best_index = i

        return AggregatedResponse(
            content=responses[best_index]["content"],
            strategy=AggregationStrategy.WEIGHTED_MERGE,
            source_count=len(responses),
            selected_sources=[best_index],
            confidence=0.7,
        )

    def _simple_merge(self, responses: List[Dict[str, Any]]) -> AggregatedResponse:
        """简单合并（当 LLM 不可用时）"""
        # 选择最长的响应（启发式：通常更完整）
        best_index = 0
        max_length = 0

        for i, resp in enumerate(responses):
            content = resp.get("content", "")
            if len(content) > max_length:
                max_length = len(content)
                best_index = i

        return AggregatedResponse(
            content=responses[best_index]["content"],
            strategy=AggregationStrategy.CRITICAL_SYNTHESIS,
            source_count=len(responses),
            selected_sources=[best_index],
            confidence=0.5,
        )

    def _build_responses_section(self, responses: List[Dict[str, Any]]) -> str:
        """构建响应部分"""
        parts = []
        for i, resp in enumerate(responses):
            model = resp.get("model", f"Model {i+1}")
            content = resp.get("content", "")
            parts.append(f"### 响应 {i+1} ({model})\n{content}\n")
        return "\n".join(parts)


def create_moa_aggregator(
    llm_service: Any = None,
    default_strategy: AggregationStrategy = AggregationStrategy.CRITICAL_SYNTHESIS,
) -> MoAAggregator:
    """
    创建 MoA 聚合器

    Args:
        llm_service: LLM 服务
        default_strategy: 默认聚合策略

    Returns:
        MoAAggregator 实例
    """
    return MoAAggregator(
        llm_service=llm_service,
        default_strategy=default_strategy,
    )
