"""
智能体路由器（Agent Router）

决策使用单智能体还是多智能体：
1. 接收用户请求
2. 调用 IntentAnalyzer 分析意图
3. 调用 ComplexityScorer 评估复杂度
4. 返回路由决策（包含意图和复杂度信息）

架构原则：
- 路由决策在服务层（ChatService）完成
- SimpleAgent 和 MultiAgent 是平级的，都接收路由结果
- 两个框架不互相调用

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

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from core.agent.types import IntentResult
from core.routing.complexity_scorer import ComplexityScorer, ComplexityScore, ComplexityLevel

logger = logging.getLogger(__name__)


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
        
        流程：
        1. 意图分析（IntentAnalyzer）
        2. 复杂度评分（ComplexityScorer）
        3. 路由决策
        
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
        
        # 2. 意图分析
        if previous_intent:
            intent = await self.intent_analyzer.analyze_with_context(
                messages, previous_intent
            )
        else:
            intent = await self.intent_analyzer.analyze(messages)
        
        # 3. 复杂度评分
        complexity = self.complexity_scorer.score(intent, conversation_history)
        
        # 4. 路由决策
        # 决策逻辑：
        # - 意图分析明确需要多智能体 → 使用多智能体
        # - 复杂度评分超过阈值 → 使用多智能体
        # - 其他情况 → 使用单智能体
        
        if intent.needs_multi_agent:
            agent_type = "multi"
            logger.info("🔀 路由决策: 多智能体（意图分析建议）")
        elif complexity.score > self.complexity_threshold:
            agent_type = "multi"
            logger.info(f"🔀 路由决策: 多智能体（复杂度 {complexity.score} > {self.complexity_threshold}）")
        else:
            agent_type = "single"
            logger.info(f"🔀 路由决策: 单智能体（复杂度 {complexity.score}）")
        
        decision = RoutingDecision(
            agent_type=agent_type,
            intent=intent,
            complexity=complexity,
            user_query=user_query,
            conversation_history=conversation_history,
            context={
                "user_id": user_id,
                "routing_reason": complexity.reasoning,
            }
        )
        
        return decision
    
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
        complexity: ComplexityScore
    ) -> bool:
        """
        判断是否应该使用多智能体
        
        独立的判断逻辑，方便测试和扩展
        
        Args:
            intent: 意图分析结果
            complexity: 复杂度评分
            
        Returns:
            bool: 是否使用多智能体
        """
        # 条件1: 意图分析明确需要
        if intent.needs_multi_agent:
            return True
        
        # 条件2: 复杂度超过阈值
        if complexity.level == ComplexityLevel.COMPLEX:
            return True
        
        # 条件3: 复杂度评分超过阈值
        if complexity.score > self.complexity_threshold:
            return True
        
        return False
