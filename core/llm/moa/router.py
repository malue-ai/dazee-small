"""
自适应 MoA 路由器

V8.0 新增

职责：
- 识别关键决策点
- 决定是否启用多模型协作
- 协调多模型并行调用
- 成本监控和动态调整

关键决策点：
- 任务分解：分解质量影响全局
- 复杂工具选择：避免选错工具
- 质量评审：避免单模型偏见
- 回溯决策：关键恢复决策

设计原则：
- 选择性启用：普通对话使用单模型，关键决策使用 MoA
- 成本可控：监控并限制 MoA 调用频率
- 可配置：支持决策点级别的开关
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


class MoADecisionPoint(Enum):
    """MoA 决策点类型"""

    TASK_DECOMPOSITION = "task_decomposition"  # 任务分解
    TOOL_SELECTION = "tool_selection"  # 复杂工具选择
    QUALITY_REVIEW = "quality_review"  # 质量评审
    BACKTRACK_DECISION = "backtrack_decision"  # 回溯决策
    INTENT_ANALYSIS = "intent_analysis"  # 意图分析
    PLAN_VALIDATION = "plan_validation"  # Plan 验证


@dataclass
class MoAConfig:
    """MoA 配置"""

    enabled: bool = True  # 总开关
    max_proposers: int = 2  # 最大提议者数量
    timeout_seconds: int = 30  # 超时时间

    # 决策点级别开关
    enabled_decision_points: Dict[MoADecisionPoint, bool] = field(
        default_factory=lambda: {
            MoADecisionPoint.TASK_DECOMPOSITION: True,
            MoADecisionPoint.TOOL_SELECTION: True,
            MoADecisionPoint.QUALITY_REVIEW: True,
            MoADecisionPoint.BACKTRACK_DECISION: True,
            MoADecisionPoint.INTENT_ANALYSIS: False,  # 默认关闭
            MoADecisionPoint.PLAN_VALIDATION: False,  # 默认关闭
        }
    )

    # 成本控制
    max_moa_calls_per_session: int = 10  # 每会话最大 MoA 调用次数
    cost_threshold_usd: float = 0.5  # 成本阈值（美元）

    # 复杂度阈值（只有复杂度超过阈值才启用 MoA）
    complexity_thresholds: Dict[MoADecisionPoint, int] = field(
        default_factory=lambda: {
            MoADecisionPoint.TASK_DECOMPOSITION: 6,  # 复杂度 >= 6
            MoADecisionPoint.TOOL_SELECTION: 5,  # 复杂度 >= 5
            MoADecisionPoint.QUALITY_REVIEW: 7,  # 复杂度 >= 7
            MoADecisionPoint.BACKTRACK_DECISION: 0,  # 总是启用
            MoADecisionPoint.INTENT_ANALYSIS: 8,
            MoADecisionPoint.PLAN_VALIDATION: 7,
        }
    )


@dataclass
class MoAResult:
    """MoA 调用结果"""

    decision_point: MoADecisionPoint
    used_moa: bool  # 是否实际使用了 MoA
    proposer_responses: List[Dict[str, Any]]  # 提议者响应
    aggregated_response: Optional[str]  # 聚合后的响应
    selected_response_index: int = 0  # 选中的响应索引
    confidence: float = 0.0  # 置信度
    cost_usd: float = 0.0  # 本次调用成本
    latency_ms: int = 0  # 延迟（毫秒）
    skip_reason: Optional[str] = None  # 跳过 MoA 的原因

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_point": self.decision_point.value,
            "used_moa": self.used_moa,
            "proposer_count": len(self.proposer_responses),
            "selected_response_index": self.selected_response_index,
            "confidence": self.confidence,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "skip_reason": self.skip_reason,
        }


class AdaptiveMoARouter:
    """
    自适应 MoA 路由器

    功能：
    1. 识别关键决策点并决定是否启用 MoA
    2. 协调多模型并行调用
    3. 将多个响应传递给 Aggregator 进行聚合
    4. 成本监控和动态调整

    使用方式：
        router = AdaptiveMoARouter(
            proposer_llms=[llm1, llm2],
            aggregator_llm=aggregator_llm
        )

        result = await router.route(
            decision_point=MoADecisionPoint.TASK_DECOMPOSITION,
            prompt="分解任务: ...",
            context={"complexity": 7}
        )
    """

    def __init__(
        self,
        proposer_llms: List[Any] = None,
        aggregator_llm: Any = None,
        config: MoAConfig = None,
    ):
        """
        初始化 MoA 路由器

        Args:
            proposer_llms: 提议者 LLM 服务列表
            aggregator_llm: 聚合器 LLM 服务
            config: MoA 配置
        """
        self.proposer_llms = proposer_llms or []
        self.aggregator_llm = aggregator_llm
        self.config = config or MoAConfig()

        # 会话级统计
        self._session_stats: Dict[str, Dict[str, Any]] = {}

        logger.info(
            f"✅ AdaptiveMoARouter 初始化: "
            f"proposers={len(self.proposer_llms)}, "
            f"enabled={self.config.enabled}"
        )

    def should_use_moa(
        self,
        decision_point: MoADecisionPoint,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """
        判断是否应该使用 MoA

        Args:
            decision_point: 决策点类型
            session_id: 会话 ID
            context: 上下文（可包含 complexity）

        Returns:
            (should_use, reason): 是否使用及原因
        """
        context = context or {}

        # 检查总开关
        if not self.config.enabled:
            return False, "MoA 总开关关闭"

        # 检查是否有足够的提议者
        if len(self.proposer_llms) < 2:
            return False, "提议者 LLM 数量不足"

        # 检查决策点是否启用
        if not self.config.enabled_decision_points.get(decision_point, False):
            return False, f"决策点 {decision_point.value} 未启用"

        # 检查会话级调用次数限制
        stats = self._get_session_stats(session_id)
        if stats["moa_calls"] >= self.config.max_moa_calls_per_session:
            return False, f"已达会话 MoA 调用上限 ({self.config.max_moa_calls_per_session})"

        # 检查成本限制
        if stats["total_cost_usd"] >= self.config.cost_threshold_usd:
            return False, f"已达成本阈值 (${self.config.cost_threshold_usd})"

        # 检查复杂度阈值
        complexity = context.get("complexity", 5)
        threshold = self.config.complexity_thresholds.get(decision_point, 5)
        if complexity < threshold:
            return False, f"复杂度 {complexity} 低于阈值 {threshold}"

        return True, "满足 MoA 启用条件"

    async def route(
        self,
        decision_point: MoADecisionPoint,
        prompt: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        fallback_llm: Any = None,
    ) -> MoAResult:
        """
        路由决策：决定是否使用 MoA 并执行

        Args:
            decision_point: 决策点类型
            prompt: 用户提示
            session_id: 会话 ID
            context: 上下文
            system_prompt: 系统提示词
            fallback_llm: 回退 LLM（当不使用 MoA 时）

        Returns:
            MoAResult: 路由结果
        """
        import time

        start_time = time.time()

        context = context or {}

        # 判断是否使用 MoA
        should_use, reason = self.should_use_moa(decision_point, session_id, context)

        if not should_use:
            logger.info(f"⏭️ 跳过 MoA [{decision_point.value}]: {reason}")

            # 使用回退 LLM
            if fallback_llm:
                try:
                    response = await fallback_llm.create_message_async(
                        messages=[{"role": "user", "content": prompt}],
                        system=system_prompt,
                    )
                    return MoAResult(
                        decision_point=decision_point,
                        used_moa=False,
                        proposer_responses=[{"content": response.content}],
                        aggregated_response=response.content,
                        skip_reason=reason,
                        latency_ms=int((time.time() - start_time) * 1000),
                    )
                except Exception as e:
                    logger.warning(f"⚠️ 回退 LLM 调用失败: {e}")

            return MoAResult(
                decision_point=decision_point,
                used_moa=False,
                proposer_responses=[],
                aggregated_response=None,
                skip_reason=reason,
            )

        logger.info(f"🔄 启用 MoA [{decision_point.value}]: {reason}")

        # 执行 MoA 调用
        try:
            result = await self._execute_moa(
                decision_point=decision_point,
                prompt=prompt,
                system_prompt=system_prompt,
                context=context,
            )

            # 更新统计
            self._update_session_stats(session_id, result)

            result.latency_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"✅ MoA 完成 [{decision_point.value}]: "
                f"proposers={len(result.proposer_responses)}, "
                f"confidence={result.confidence:.2f}, "
                f"latency={result.latency_ms}ms"
            )

            return result

        except Exception as e:
            logger.error(f"❌ MoA 执行失败: {e}")

            # 回退到单模型
            if fallback_llm:
                try:
                    response = await fallback_llm.create_message_async(
                        messages=[{"role": "user", "content": prompt}],
                        system=system_prompt,
                    )
                    return MoAResult(
                        decision_point=decision_point,
                        used_moa=False,
                        proposer_responses=[{"content": response.content}],
                        aggregated_response=response.content,
                        skip_reason=f"MoA 失败，回退: {str(e)}",
                        latency_ms=int((time.time() - start_time) * 1000),
                    )
                except Exception as e2:
                    logger.error(f"❌ 回退 LLM 也失败: {e2}")

            return MoAResult(
                decision_point=decision_point,
                used_moa=False,
                proposer_responses=[],
                aggregated_response=None,
                skip_reason=f"MoA 执行失败: {str(e)}",
            )

    async def _execute_moa(
        self,
        decision_point: MoADecisionPoint,
        prompt: str,
        system_prompt: Optional[str],
        context: Dict[str, Any],
    ) -> MoAResult:
        """
        执行 MoA 调用

        Args:
            decision_point: 决策点
            prompt: 用户提示
            system_prompt: 系统提示词
            context: 上下文

        Returns:
            MoAResult: 执行结果
        """
        # 1. 并行调用所有提议者
        proposer_tasks = []
        for i, llm in enumerate(self.proposer_llms[: self.config.max_proposers]):
            task = self._call_proposer(llm, prompt, system_prompt, i)
            proposer_tasks.append(task)

        # 带超时的并行调用
        try:
            proposer_results = await asyncio.wait_for(
                asyncio.gather(*proposer_tasks, return_exceptions=True),
                timeout=self.config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ MoA 超时 ({self.config.timeout_seconds}s)")
            proposer_results = []

        # 处理结果
        proposer_responses = []
        total_cost = 0.0

        for i, result in enumerate(proposer_results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ 提议者 {i} 失败: {result}")
                proposer_responses.append(
                    {
                        "index": i,
                        "content": None,
                        "error": str(result),
                    }
                )
            else:
                proposer_responses.append(result)
                total_cost += result.get("cost_usd", 0)

        # 过滤有效响应
        valid_responses = [r for r in proposer_responses if r.get("content")]

        if not valid_responses:
            return MoAResult(
                decision_point=decision_point,
                used_moa=True,
                proposer_responses=proposer_responses,
                aggregated_response=None,
                skip_reason="所有提议者都失败",
                cost_usd=total_cost,
            )

        # 2. 聚合响应
        if len(valid_responses) == 1:
            # 只有一个有效响应，直接使用
            aggregated = valid_responses[0]["content"]
            confidence = 0.7
        else:
            # 使用聚合器
            aggregated, confidence = await self._aggregate_responses(
                decision_point=decision_point,
                prompt=prompt,
                responses=valid_responses,
            )

        return MoAResult(
            decision_point=decision_point,
            used_moa=True,
            proposer_responses=proposer_responses,
            aggregated_response=aggregated,
            confidence=confidence,
            cost_usd=total_cost,
        )

    async def _call_proposer(
        self, llm: Any, prompt: str, system_prompt: Optional[str], index: int
    ) -> Dict[str, Any]:
        """调用单个提议者"""
        try:
            response = await llm.create_message_async(
                messages=[{"role": "user", "content": prompt}],
                system=system_prompt,
            )

            return {
                "index": index,
                "content": response.content,
                "model": getattr(response, "model", "unknown"),
                "cost_usd": getattr(response, "cost_usd", 0),
            }
        except Exception as e:
            logger.warning(f"⚠️ 提议者 {index} 调用失败: {e}")
            raise

    async def _aggregate_responses(
        self,
        decision_point: MoADecisionPoint,
        prompt: str,
        responses: List[Dict[str, Any]],
    ) -> tuple[str, float]:
        """
        聚合多个响应

        Args:
            decision_point: 决策点
            prompt: 原始提示
            responses: 提议者响应列表

        Returns:
            (aggregated_response, confidence): 聚合响应和置信度
        """
        if not self.aggregator_llm:
            # 没有聚合器，选择第一个响应
            return responses[0]["content"], 0.6

        # 构建聚合提示词
        aggregate_prompt = self._build_aggregate_prompt(
            decision_point=decision_point,
            original_prompt=prompt,
            responses=responses,
        )

        try:
            response = await self.aggregator_llm.create_message_async(
                messages=[{"role": "user", "content": aggregate_prompt}],
                system="你是一个专业的响应聚合器。请批判性地评估多个模型的响应，综合它们的优点，生成一个最佳答案。",
            )

            return response.content, 0.85

        except Exception as e:
            logger.warning(f"⚠️ 聚合失败，使用第一个响应: {e}")
            return responses[0]["content"], 0.6

    def _build_aggregate_prompt(
        self,
        decision_point: MoADecisionPoint,
        original_prompt: str,
        responses: List[Dict[str, Any]],
    ) -> str:
        """构建聚合提示词"""
        prompt_parts = [
            f"## 原始任务\n{original_prompt}\n",
            f"## 决策类型\n{decision_point.value}\n",
            "## 多个模型的响应\n",
        ]

        for i, resp in enumerate(responses):
            model = resp.get("model", f"Model {i+1}")
            content = resp.get("content", "")
            prompt_parts.append(f"### 响应 {i+1} ({model})\n{content}\n")

        prompt_parts.append(
            """
## 聚合要求
请批判性地评估以上响应：
1. 识别每个响应的优点和不足
2. 综合各响应的优点
3. 生成一个最佳的综合答案

直接输出综合后的最佳答案，不需要解释过程。
"""
        )

        return "\n".join(prompt_parts)

    def _get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取会话统计"""
        if session_id not in self._session_stats:
            self._session_stats[session_id] = {
                "moa_calls": 0,
                "total_cost_usd": 0.0,
                "decision_points": {},
            }
        return self._session_stats[session_id]

    def _update_session_stats(self, session_id: str, result: MoAResult):
        """更新会话统计"""
        stats = self._get_session_stats(session_id)
        stats["moa_calls"] += 1
        stats["total_cost_usd"] += result.cost_usd

        dp = result.decision_point.value
        if dp not in stats["decision_points"]:
            stats["decision_points"][dp] = 0
        stats["decision_points"][dp] += 1

    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取会话统计（公开接口）"""
        return self._get_session_stats(session_id).copy()

    def clear_session_stats(self, session_id: str):
        """清除会话统计"""
        if session_id in self._session_stats:
            del self._session_stats[session_id]


def create_moa_router(
    proposer_llms: List[Any] = None,
    aggregator_llm: Any = None,
    config: MoAConfig = None,
) -> AdaptiveMoARouter:
    """
    创建 MoA 路由器

    Args:
        proposer_llms: 提议者 LLM 列表
        aggregator_llm: 聚合器 LLM
        config: MoA 配置

    Returns:
        AdaptiveMoARouter 实例
    """
    return AdaptiveMoARouter(
        proposer_llms=proposer_llms,
        aggregator_llm=aggregator_llm,
        config=config,
    )
