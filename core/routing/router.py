"""
智能体路由器（Agent Router）V11.0 小搭子桌面端简化版

路由决策流程：
1. 接收用户请求
2. 调用 IntentAnalyzer 分析意图（complexity、skip_memory、is_follow_up）
3. 固定返回 rvr-b 执行策略

架构原则（V11.0）：
- 小搭子固定使用 RVR-B 执行策略
- 不需要 agent_type 选择（无 rvr/rvr-b/multi 三选一）
- IntentAnalyzer 仅负责 complexity 和 skip_memory 判断

使用方式：
    router = AgentRouter(llm_service=claude, prompt_cache=cache)

    decision = await router.route(
        user_query="帮我分析这份数据",
        conversation_history=[...]
    )

    # 固定 rvr-b
    await agent.execute(strategy="rvr-b")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.routing.types import Complexity, IntentResult
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class RoutingDecision:
    """
    路由决策结果（V11.0 简化版）

    Attributes:
        intent: 意图分析结果
        user_query: 原始用户查询
        conversation_history: 对话历史
        context: 额外上下文
    """

    intent: Optional[IntentResult] = None
    user_query: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def agent_type(self) -> str:
        """执行策略（固定 rvr-b）"""
        return "rvr-b"

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
    智能体路由器（V11.0 小搭子简化版）

    策略：固定使用 RVR-B 执行策略，IntentAnalyzer 仅判断 complexity 和 skip_memory

    使用方式：
        router = AgentRouter(llm_service=claude)
        decision = await router.route(user_query, conversation_history)
        await agent.execute(strategy="rvr-b")
    """

    def __init__(
        self,
        llm_service=None,
        prompt_cache=None,
        enable_llm: bool = True,
        fast_mode: bool = False,
        semantic_cache_threshold: Optional[float] = None,
        simplified_output: bool = True,
    ):
        """
        初始化路由器

        Args:
            llm_service: LLM 服务（用于意图分析）
            prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
            enable_llm: 是否启用 LLM 分析
            fast_mode: 意图分析快速模式
            semantic_cache_threshold: 意图语义缓存命中阈值
            simplified_output: 意图输出简化
        """
        self.llm_service = llm_service
        self.prompt_cache = prompt_cache
        self.enable_llm = enable_llm
        self.fast_mode = fast_mode
        self.semantic_cache_threshold = semantic_cache_threshold
        self.simplified_output = simplified_output
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
                fast_mode=self.fast_mode,
                semantic_cache_threshold=self.semantic_cache_threshold,
                simplified_output=self.simplified_output,
            )
        return self._intent_analyzer

    async def route(
        self,
        user_query: Any,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        tracker=None,
        current_step_hint: Optional[str] = None,
    ) -> RoutingDecision:
        """
        执行路由决策

        流程：
        1. 意图分析（IntentAnalyzer）
        2. 固定返回 rvr-b 策略
        3. 返回路由决策

        Args:
            user_query: 用户查询（支持 str 或多模态 list）
            conversation_history: 对话历史
            user_id: 用户ID
            tracker: UsageTracker 实例（可选）
            current_step_hint: Current plan step title for Step-Aware
                skill group selection.

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
        intent = await self.intent_analyzer.analyze(
            messages, tracker=tracker, current_step_hint=current_step_hint
        )

        logger.info(
            f"路由决策: strategy=rvr-b (固定), "
            f"complexity={intent.complexity.value}, "
            f"skip_memory={intent.skip_memory}"
        )

        return RoutingDecision(
            intent=intent,
            user_query=user_query,
            conversation_history=conversation_history,
            context={
                "user_id": user_id,
                "routing_reason": "固定 RVR-B 执行策略",
            },
        )
