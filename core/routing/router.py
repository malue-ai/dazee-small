"""
智能体路由器（Agent Router）V10.1 统一语义版

路由决策流程：
1. 接收用户请求
2. 调用 IntentAnalyzer 分析意图
3. 直接使用 intent.agent_type 作为执行策略

架构原则：
- agent_type 统一为执行策略：rvr | rvr-b | multi
- 使用 is_multi_agent property 判断是否多智能体
- 不再使用 "single"/"multi" 的二元语义

使用方式：
    router = AgentRouter(llm_service=claude, prompt_cache=cache)

    decision = await router.route(
        user_query="帮我分析这份数据",
        conversation_history=[...]
    )

    # V10.1: agent_type 是执行策略
    if decision.is_multi_agent:
        await multi_agent.execute(...)
    else:
        # decision.agent_type 是 "rvr" 或 "rvr-b"
        await agent.execute(strategy=decision.agent_type)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.routing.types import Complexity, IntentResult
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class RoutingDecision:
    """
    路由决策结果（V10.1 统一语义版）

    Attributes:
        agent_type: 执行策略（"rvr" | "rvr-b" | "multi"）
        intent: 意图分析结果
        user_query: 原始用户查询
        conversation_history: 对话历史
        context: 额外上下文

    V10.1 变更：
    - agent_type 统一为执行策略语义，不再是 "single"/"multi"
    - 使用 is_multi_agent property 判断是否多智能体
    """

    agent_type: str = "rvr"  # rvr | rvr-b | multi
    intent: Optional[IntentResult] = None
    user_query: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_multi_agent(self) -> bool:
        """是否使用多智能体"""
        return self.agent_type == "multi"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_type": self.agent_type,
            "intent": self.intent.to_dict() if self.intent else None,
            "user_query": self.user_query,
            "has_history": len(self.conversation_history) > 0,
            "context": self.context,
        }

    def to_agent_context(self) -> Dict[str, Any]:
        """转换为智能体上下文"""
        return {
            "user_query": self.user_query,
            "conversation_history": self.conversation_history,
            "intent_result": self.intent,
            "routing_context": self.context,
        }

    @property
    def complexity(self):
        """复杂度（从 intent 获取，向后兼容）"""
        return self.intent.complexity if self.intent else Complexity.MEDIUM


class AgentRouter:
    """
    智能体路由器（V10.1 统一语义版）

    策略：直接使用 LLM 输出的 agent_type 作为执行策略
    - agent_type: rvr | rvr-b | multi
    - 无需 ComplexityScorer
    - 无需 complexity_score 阈值判断

    使用方式：
        router = AgentRouter(llm_service=claude)
        decision = await router.route(user_query, conversation_history)

        # V10.1: 使用 is_multi_agent 判断
        if decision.is_multi_agent:
            await multi_agent.execute(decision.to_agent_context())
        else:
            await agent.execute(strategy=decision.agent_type)
    """

    def __init__(self, llm_service=None, prompt_cache=None, enable_llm: bool = True):
        """
        初始化路由器

        Args:
            llm_service: LLM 服务（用于意图分析）
            prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
            enable_llm: 是否启用 LLM 分析
        """
        self.llm_service = llm_service
        self.prompt_cache = prompt_cache
        self.enable_llm = enable_llm
        self._intent_analyzer = None

    @property
    def intent_analyzer(self):
        """获取意图分析器（延迟初始化）"""
        if self._intent_analyzer is None:
            from core.routing.intent_analyzer import IntentAnalyzer

            self._intent_analyzer = IntentAnalyzer(
                llm_service=self.llm_service,
                enable_llm=self.enable_llm,
                prompt_cache=self.prompt_cache,
            )
        return self._intent_analyzer

    async def route(
        self,
        user_query: Any,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        tracker=None,
    ) -> RoutingDecision:
        """
        执行路由决策

        流程：
        1. 意图分析（IntentAnalyzer）
        2. 直接使用 intent.agent_type 进行路由
        3. 返回路由决策

        Args:
            user_query: 用户查询（支持 str 或多模态 list）
            conversation_history: 对话历史
            user_id: 用户ID
            tracker: UsageTracker 实例（可选）

        Returns:
            RoutingDecision: 路由决策
        """
        conversation_history = conversation_history or []

        query_text = user_query if isinstance(user_query, str) else str(user_query)[:100]
        logger.info(f"开始路由决策: query={query_text[:50]}...")

        # 1. 构建消息列表
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": user_query})

        # 2. 意图分析
        intent = await self.intent_analyzer.analyze(messages, tracker=tracker)

        # 3. 直接使用 intent.agent_type 作为执行策略
        strategy = intent.agent_type  # rvr | rvr-b | multi
        is_multi = intent.is_multi_agent
        routing_reason = f"执行策略: {strategy}"

        logger.info(
            f"路由决策: strategy={strategy}, "
            f"is_multi={is_multi}, "
            f"complexity={intent.complexity.value}"
        )

        # 4. 预算检查（仅多智能体）
        budget_check_passed = True
        budget_warning = None

        if is_multi:
            budget_check_passed, budget_warning, strategy = await self._check_budget(
                user_id, strategy
            )

        return RoutingDecision(
            agent_type=strategy,
            intent=intent,
            user_query=user_query,
            conversation_history=conversation_history,
            context={
                "user_id": user_id,
                "routing_reason": routing_reason,
                "budget_check_passed": budget_check_passed,
                "budget_warning": budget_warning,
            },
        )

    async def _check_budget(self, user_id: Optional[str], strategy: str) -> tuple:
        """
        检查多智能体预算

        Args:
            user_id: 用户 ID
            strategy: 当前策略 (multi)

        Returns:
            (budget_check_passed, budget_warning, final_strategy)
        """
        try:
            import os

            from core.monitoring import get_token_budget

            token_budget = get_token_budget()
            user_tier = os.getenv("QOS_LEVEL", "PRO").upper()

            estimated_tokens = token_budget.estimate_tokens_for_multi_agent(
                base_tokens=50_000, num_workers=3
            )

            budget_result = await token_budget.check_budget(
                user_tier=user_tier,
                agent_type="multi",
                estimated_tokens=estimated_tokens,
                session_id=user_id,
            )

            if not budget_result.allowed:
                logger.warning(f"预算不足，降级到 rvr-b: {budget_result.reason}")
                return False, budget_result.reason, "rvr-b"  # 降级到 rvr-b 而非 "single"

            return True, budget_result.warning, strategy

        except Exception as e:
            logger.warning(f"预算检查失败: {e}，继续使用 {strategy}")
            return True, None, strategy

    async def route_with_override(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        force_strategy: Optional[str] = None,
    ) -> RoutingDecision:
        """
        带强制覆盖的路由决策（用于测试）

        Args:
            user_query: 用户查询
            conversation_history: 对话历史
            force_strategy: 强制执行策略 ("rvr" | "rvr-b" | "multi")
        """
        decision = await self.route(user_query, conversation_history)

        if force_strategy in ["rvr", "rvr-b", "multi"]:
            decision.agent_type = force_strategy
            decision.context["override"] = True
            logger.warning(f"路由决策被覆盖为: {force_strategy}")

        return decision
