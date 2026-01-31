"""
智能体路由器（Agent Router）

LLM-First 架构：所有判断完全由 LLM 语义推理驱动

决策使用单智能体还是多智能体：
1. 接收用户请求
2. 调用 IntentAnalyzer 分析意图
3. 直接使用 LLM 输出的 intent 字段
4. 返回路由决策

架构原则：
- 所有规则在 instance 系统提示词中用自然语言定义
- LLM 通过语义理解和深度推理输出判断结果
- 代码只负责传递 LLM 的判断，不做任何规则逻辑
- 不同场景只需修改提示词，代码无需变动

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

from core.agent.types import IntentResult, Complexity

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """
    路由决策结果
    
    包含 LLM 意图分析结果，供单智能体或多智能体框架使用。
    所有判断来自 LLM 语义推理，代码只传递结果。
    """
    agent_type: str = "single"
    execution_strategy: str = "rvr"
    intent: Optional[IntentResult] = None
    user_query: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_type": self.agent_type,
            "execution_strategy": self.execution_strategy,
            "intent": self._intent_to_dict(),
            "user_query": self.user_query,
            "has_history": len(self.conversation_history) > 0,
            "context": self.context,
        }
    
    def _intent_to_dict(self) -> Optional[Dict[str, Any]]:
        """将 IntentResult 转换为字典"""
        if not self.intent:
            return None
        if hasattr(self.intent, 'to_dict'):
            return self.intent.to_dict()
        return {
            "task_type": self.intent.task_type.value,
            "complexity": self.intent.complexity.value,
            "needs_plan": self.intent.needs_plan,
            "needs_multi_agent": self.intent.needs_multi_agent,
            "is_follow_up": self.intent.is_follow_up,
        }
    
    def to_agent_context(self) -> Dict[str, Any]:
        """转换为智能体上下文"""
        return {
            "user_query": self.user_query,
            "conversation_history": self.conversation_history,
            "intent_result": self.intent,
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
        enable_llm: bool = True
    ):
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
        
        LLM-First：直接使用 LLM 语义判断，不做额外规则处理
        
        流程：
        1. 意图分析（IntentAnalyzer）
        2. 直接使用 intent.complexity 和 intent.needs_multi_agent
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
        
        # 2. 意图分析（LLM 语义推理，规则在提示词中定义）
        if previous_intent:
            intent = await self.intent_analyzer.analyze_with_context(
                messages, previous_intent
            )
        else:
            intent = await self.intent_analyzer.analyze(messages)
        
        logger.info(
            f"📊 LLM 意图分析: complexity={intent.complexity.value}, "
            f"needs_multi_agent={intent.needs_multi_agent}"
        )
        
        # 3. 路由决策：直接使用 LLM 输出
        if intent.needs_multi_agent:
            agent_type = "multi"
            routing_reason = "LLM 语义判断: 需要多智能体协作"
            logger.info("🔀 路由决策: 多智能体")
        else:
            agent_type = "single"
            routing_reason = "LLM 语义判断: 单智能体即可"
            logger.info("🔀 路由决策: 单智能体")
        
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
        
        # 从 intent 获取执行策略（由 LLM 语义判断）
        execution_strategy = getattr(intent, 'execution_strategy', 'rvr') if intent else 'rvr'
        
        decision = RoutingDecision(
            agent_type=agent_type,
            execution_strategy=execution_strategy,
            intent=intent,
            user_query=user_query,
            conversation_history=conversation_history,
            context={
                "user_id": user_id,
                "routing_reason": routing_reason,
                "budget_check_passed": budget_check_passed,
                "budget_warning": budget_warning,
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
