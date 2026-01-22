"""
智能体路由器（Agent Router）

🆕 V7.0: Prompt-First 重构 - 复杂度评分由 LLM 直接输出

决策使用单智能体还是多智能体：
1. 接收用户请求
2. 调用 IntentAnalyzer 分析意图（包含 complexity_score）
3. 基于 intent.complexity_score 进行路由决策
4. 返回路由决策（包含意图和复杂度信息）

架构原则：
- 路由决策在服务层（ChatService）完成
- SimpleAgent 和 MultiAgent 是平级的，都接收路由结果
- 两个框架不互相调用
- 🆕 V7.0: ComplexityScorer 保留向后兼容，但优先使用 LLM 输出的 complexity_score

使用方式：
    router = AgentRouter(llm_service=claude, prompt_cache=cache)
    
    decision = await router.route(
        user_query="帮我分析这份数据并生成报告",
        conversation_history=[...],
        user_id="user_123"
    )
    
    if decision.agent_type == "single":
        result = await simple_agent.chat(decision.to_agent_context())
    else:
        result = await multi_agent.execute(decision.to_agent_context())
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from core.agent.types import IntentResult
# 🆕 V7.0: ComplexityScorer 保留向后兼容，但优先使用 LLM 输出的 complexity_score
from core.routing.complexity_scorer import ComplexityScorer, ComplexityScore, ComplexityLevel
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class RoutingDecision:
    """
    路由决策结果
    
    包含意图分析和复杂度评估的完整结果，
    供单智能体或多智能体框架使用。
    
    Attributes:
        agent_type: 推荐的智能体类型（"single" 或 "multi"）
        intent: 意图分析结果
        complexity: 复杂度评分结果
        user_query: 原始用户查询
        conversation_history: 对话历史
        context: 额外上下文
    """
    agent_type: str = "single"
    intent: Optional[IntentResult] = None
    complexity: Optional[ComplexityScore] = None
    user_query: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_type": self.agent_type,
            "intent": self.intent.to_dict() if hasattr(self.intent, 'to_dict') else self._intent_to_dict(),
            "complexity": self.complexity.to_dict() if self.complexity else None,
            "user_query": self.user_query,
            "has_history": len(self.conversation_history) > 0,
            "context": self.context,
        }
    
    def _intent_to_dict(self) -> Optional[Dict[str, Any]]:
        """将 IntentResult 转换为字典"""
        if not self.intent:
            return None
        return {
            "task_type": self.intent.task_type.value,
            "complexity": self.intent.complexity.value,
            "needs_plan": self.intent.needs_plan,
            "needs_multi_agent": self.intent.needs_multi_agent,
            "is_follow_up": self.intent.is_follow_up,
            "skip_memory_retrieval": self.intent.skip_memory_retrieval,
        }
    
    def to_agent_context(self) -> Dict[str, Any]:
        """
        转换为智能体上下文
        
        用于传递给 SimpleAgent 或 MultiAgent
        """
        return {
            "user_query": self.user_query,
            "conversation_history": self.conversation_history,
            "intent_result": self.intent,
            "complexity_score": self.complexity,
            "routing_context": self.context,
        }


class AgentRouter:
    """
    智能体路由器
    
    负责分析用户意图并决定使用哪个智能体框架。
    
    使用方式：
        router = AgentRouter(llm_service=claude)
        decision = await router.route(user_query, conversation_history)
        
        # 根据决策结果调用对应的智能体
        if decision.agent_type == "single":
            await simple_agent.chat(decision.to_agent_context())
        else:
            await multi_agent.execute(decision.to_agent_context())
    """
    
    def __init__(
        self,
        llm_service=None,
        prompt_cache=None,
        enable_llm: bool = True,
        complexity_threshold: float = 5.0
    ):
        """
        初始化路由器
        
        Args:
            llm_service: LLM 服务（用于意图分析）
            prompt_cache: InstancePromptCache（获取缓存的意图识别提示词）
            enable_llm: 是否启用 LLM 分析
            complexity_threshold: 复杂度阈值（超过则使用多智能体）
        """
        self.llm_service = llm_service
        self.prompt_cache = prompt_cache
        self.enable_llm = enable_llm
        self.complexity_threshold = complexity_threshold
        
        # 初始化复杂度评分器
        self.complexity_scorer = ComplexityScorer()
        
        # 意图分析器（延迟初始化，避免循环依赖）
        self._intent_analyzer = None
    
    @property
    def intent_analyzer(self):
        """
        获取意图分析器（延迟初始化）
        
        使用现有的 IntentAnalyzer，但作为共享模块
        """
        if self._intent_analyzer is None:
            from core.routing.intent_analyzer import IntentAnalyzer  # 🆕 从共享层导入
            self._intent_analyzer = IntentAnalyzer(
                llm_service=self.llm_service,
                enable_llm=self.enable_llm,
                prompt_cache=self.prompt_cache
            )
        return self._intent_analyzer
    
    async def route(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        previous_intent: Optional[IntentResult] = None
    ) -> RoutingDecision:
        """
        执行路由决策
        
        🆕 V7.0: Prompt-First 重构
        流程：
        1. 意图分析（IntentAnalyzer）- 包含 complexity_score
        2. 优先使用 intent.complexity_score 进行路由决策
        3. 返回路由决策
        
        Args:
            user_query: 用户查询
            conversation_history: 对话历史
            user_id: 用户ID（用于个性化路由）
            previous_intent: 上一轮意图结果（用于追问场景）
            
        Returns:
            RoutingDecision: 路由决策
        """
        conversation_history = conversation_history or []
        
        logger.info(f"🔀 开始路由决策: query={user_query[:50]}...")
        
        # 1. 构建消息列表用于意图分析
        messages = conversation_history.copy()
        messages.append({"role": "user", "content": user_query})
        
        # 2. 意图分析（🆕 V7.0: 包含 complexity_score）
        if previous_intent:
            intent = await self.intent_analyzer.analyze_with_context(
                messages, previous_intent
            )
        else:
            intent = await self.intent_analyzer.analyze(messages)
        
        # 3. 🆕 V7.0: 优先使用 LLM 输出的 complexity_score
        # 如果 LLM 返回了有效的 complexity_score，直接使用
        # 否则 fallback 到 ComplexityScorer（向后兼容）
        
        use_llm_score = hasattr(intent, 'complexity_score') and intent.complexity_score is not None
        
        if use_llm_score:
            # 🆕 V7.0: 使用 LLM 直接输出的 complexity_score
            score = intent.complexity_score
            complexity = self._build_complexity_from_intent(intent)
            logger.info(f"🆕 V7.0: 使用 LLM 输出的 complexity_score={score:.1f}")
        else:
            # Fallback: 使用 ComplexityScorer（向后兼容）
            complexity = self.complexity_scorer.score(intent, conversation_history)
            score = complexity.score
            logger.info(f"⚠️ Fallback: 使用 ComplexityScorer score={score:.1f}")
        
        # 4. 路由决策
        # 决策逻辑：
        # - 意图分析明确需要多智能体 → 使用多智能体
        # - 复杂度评分超过阈值 → 使用多智能体
        # - 🆕 V7.1: 检查预算是否足够
        # - 其他情况 → 使用单智能体
        
        # 🚫 临时禁用多智能体（待稳定后移除此代码块）
        agent_type = "single"
        routing_reason = "多智能体暂时禁用"
        logger.info("🔀 路由决策: 单智能体（多智能体暂时禁用）")
        
        # 以下代码暂时禁用，待多智能体稳定后恢复
        # if intent.needs_multi_agent:
        #     agent_type = "multi"
        #     routing_reason = "意图分析建议多智能体协作"
        #     logger.info("🔀 初步路由决策: 多智能体（意图分析建议）")
        # elif score > self.complexity_threshold:
        #     agent_type = "multi"
        #     routing_reason = f"复杂度 {score:.1f} > 阈值 {self.complexity_threshold}"
        #     logger.info(f"🔀 初步路由决策: 多智能体（复杂度 {score:.1f} > {self.complexity_threshold}）")
        # else:
        #     agent_type = "single"
        #     routing_reason = f"复杂度 {score:.1f} <= 阈值 {self.complexity_threshold}"
        #     logger.info(f"🔀 路由决策: 单智能体（复杂度 {score:.1f}）")
        
        # 🆕 V7.1: 如果选择多智能体，检查预算是否足够
        budget_check_passed = True
        budget_warning = None
        
        if agent_type == "multi":
            from core.monitoring import get_token_budget
            import os
            
            token_budget = get_token_budget()
            
            # 获取用户等级（从环境变量或默认）
            user_tier = os.getenv("QOS_LEVEL", "PRO").upper()
            
            # 估算多智能体的 token 消耗
            # 基于 Anthropic 实践：~15× 单智能体
            base_tokens = 50_000  # 单智能体平均消耗
            num_workers = 3  # 默认 worker 数量
            estimated_tokens = token_budget.estimate_tokens_for_multi_agent(
                base_tokens=base_tokens,
                num_workers=num_workers
            )
            
            # 检查预算
            budget_result = await token_budget.check_budget(
                user_tier=user_tier,
                agent_type="multi",
                estimated_tokens=estimated_tokens,
                session_id=user_id  # 使用 user_id 作为 session_id
            )
            
            if not budget_result.allowed:
                # 预算不足，降级到单智能体
                logger.warning(
                    f"💰 预算不足，降级到单智能体: {budget_result.reason}"
                )
                agent_type = "single"
                routing_reason = f"预算限制（{budget_result.reason}），降级到单智能体"
                budget_check_passed = False
            elif budget_result.warning:
                # 预算告警，但仍然允许
                logger.warning(f"💰 {budget_result.warning}")
                budget_warning = budget_result.warning
        
        decision = RoutingDecision(
            agent_type=agent_type,
            intent=intent,
            complexity=complexity,
            user_query=user_query,
            conversation_history=conversation_history,
            context={
                "user_id": user_id,
                "routing_reason": routing_reason,
                "score_source": "llm" if use_llm_score else "complexity_scorer",  # 🆕 V7.0
                "budget_check_passed": budget_check_passed,  # 🆕 V7.1: 预算检查结果
                "budget_warning": budget_warning,  # 🆕 V7.1: 预算告警
            }
        )
        
        return decision
    
    def _build_complexity_from_intent(self, intent: IntentResult) -> ComplexityScore:
        """
        🆕 V7.0: 从 IntentResult 构建 ComplexityScore（用于向后兼容）
        
        Args:
            intent: 意图分析结果
            
        Returns:
            ComplexityScore: 复杂度评分结果
        """
        score = intent.complexity_score
        
        # 根据 score 确定 level
        if score <= 3.0:
            level = ComplexityLevel.SIMPLE
            recommended = "single"
        elif score <= 5.0:
            level = ComplexityLevel.MEDIUM
            recommended = "single"
        else:
            level = ComplexityLevel.COMPLEX
            recommended = "multi"
        
        return ComplexityScore(
            score=score,
            level=level,
            dimensions={"llm_score": score},
            reasoning=f"LLM 直接输出 (score={score:.1f})",
            recommended_agent=recommended,
        )
    
    async def route_with_override(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        force_agent_type: Optional[str] = None
    ) -> RoutingDecision:
        """
        带强制覆盖的路由决策
        
        用于测试或特殊场景
        
        Args:
            user_query: 用户查询
            conversation_history: 对话历史
            force_agent_type: 强制使用的智能体类型
            
        Returns:
            RoutingDecision: 路由决策
        """
        decision = await self.route(user_query, conversation_history)
        
        if force_agent_type in ["single", "multi"]:
            decision.agent_type = force_agent_type
            decision.context["override"] = True
            logger.warning(f"⚠️ 路由决策被覆盖为: {force_agent_type}")
        
        return decision
    
    def should_use_multi_agent(
        self,
        intent: IntentResult,
        complexity: Optional[ComplexityScore] = None
    ) -> bool:
        """
        判断是否应该使用多智能体
        
        🆕 V7.0: 优先使用 intent.complexity_score
        
        独立的判断逻辑，方便测试和扩展
        
        Args:
            intent: 意图分析结果
            complexity: 复杂度评分（可选，V7.0 后优先使用 intent.complexity_score）
            
        Returns:
            bool: 是否使用多智能体
        """
        # 条件1: 意图分析明确需要
        if intent.needs_multi_agent:
            return True
        
        # 🆕 V7.0: 优先使用 intent.complexity_score
        if hasattr(intent, 'complexity_score') and intent.complexity_score is not None:
            if intent.complexity_score > self.complexity_threshold:
                return True
            return False
        
        # Fallback: 使用 ComplexityScore（向后兼容）
        if complexity:
            # 条件2: 复杂度等级超过阈值
            if complexity.level == ComplexityLevel.COMPLEX:
                return True
            
            # 条件3: 复杂度评分超过阈值
            if complexity.score > self.complexity_threshold:
                return True
        
        return False
