"""
Agent 协调器（AgentCoordinator）

V7.8 新增模块

职责：
1. 整合 AgentRouter 和 AgentFactory
2. 提供单一执行入口 route_and_execute()
3. 管理 Agent 原型池（可选）
4. 统一 SimpleAgent 和 MultiAgentOrchestrator 的调用

设计原则：
- 路由决策由 AgentRouter 完成（集中管理）
- Agent 创建由 AgentFactory 完成（无路由逻辑）
- 调用方只需与 Coordinator 交互，无需感知具体 Agent 类型

调用链：
    ChatService
        ↓
    AgentCoordinator.route_and_execute()
        ↓
    ┌─────────────────────────────────────────┐
    │  1. AgentRouter.route() → 路由决策       │
    │  2. AgentFactory.create() → Agent 实例   │
    │  3. agent.execute() → 统一执行           │
    └─────────────────────────────────────────┘

参考：
- docs/architecture/00-ARCHITECTURE-OVERVIEW.md
- core/routing/router.py
- core/agent/factory.py
"""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from core.agent.protocol import AgentProtocol, get_agent_type
from core.routing import AgentRouter, RoutingDecision

if TYPE_CHECKING:
    from core.events.broadcaster import EventBroadcaster
    from core.agent.types import IntentResult

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Agent 协调器
    
    整合路由和工厂，提供单一执行入口。
    
    架构位置：
    - 位于 ChatService 和 Agent 之间
    - 封装路由决策和 Agent 创建逻辑
    - 统一 SimpleAgent 和 MultiAgentOrchestrator 的调用
    
    使用方式：
        coordinator = AgentCoordinator(router=router)
        
        async for event in coordinator.route_and_execute(
            messages=messages,
            session_id=session_id,
            event_manager=event_manager
        ):
            yield event
    
    V7.8 设计原则：
    1. 路由逻辑集中在 AgentRouter（不在 Factory）
    2. Factory 只负责创建，不负责路由决策
    3. 统一调用 agent.execute()，无需类型判断
    """
    
    def __init__(
        self,
        router: Optional[AgentRouter] = None,
        prototype_pool: Optional[Dict[str, AgentProtocol]] = None,
        enable_prototype_cache: bool = True,
    ):
        """
        初始化协调器
        
        Args:
            router: AgentRouter 实例（延迟初始化如果为 None）
            prototype_pool: Agent 原型池（用于 clone_for_session）
            enable_prototype_cache: 是否启用原型缓存
        """
        self._router = router
        self._prototype_pool = prototype_pool or {}
        self.enable_prototype_cache = enable_prototype_cache
        
        logger.info(
            f"✅ AgentCoordinator 初始化: "
            f"prototype_cache={enable_prototype_cache}"
        )
    
    @property
    def router(self) -> AgentRouter:
        """
        获取路由器（延迟初始化）
        """
        if self._router is None:
            from core.agent.factory import AgentFactory
            self._router = AgentFactory.create_router()
            logger.debug("🔀 AgentRouter 延迟初始化完成")
        return self._router
    
    def set_router(self, router: AgentRouter) -> None:
        """
        设置路由器（支持注入 prompt_cache）
        
        Args:
            router: 配置好的 AgentRouter
        """
        self._router = router
    
    async def route_and_execute(
        self,
        messages: List[Dict[str, Any]],
        session_id: str,
        event_manager: "EventBroadcaster",
        user_id: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        conversation_service: Optional[Any] = None,
        system_prompt: Optional[str] = None,
        base_schema: Optional[Any] = None,
        prompt_cache: Optional[Any] = None,
        previous_intent: Optional["IntentResult"] = None,
        enable_stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        单一执行入口：路由 → 创建 → 执行
        
        这是 Coordinator 的核心方法，整合了完整的执行流程。
        
        核心设计（V7.8）：
        1. base_schema 来自实例配置（config.yaml + prompt.md）
        2. 根据 complexity_score 微调运行时参数
        3. 选择对应复杂度的提示词（从 prompt_cache）
        
        流程：
        1. 提取用户查询
        2. 调用 AgentRouter.route() 获取路由决策
        3. 根据决策创建/获取 Agent（在 base_schema 基础上微调）
        4. 调用 agent.execute() 统一执行
        
        Args:
            messages: 消息列表
            session_id: 会话 ID
            event_manager: 事件管理器
            user_id: 用户 ID（用于预算检查）
            workspace_dir: 工作目录
            conversation_service: 会话服务
            system_prompt: 系统提示词
            base_schema: 实例级 Schema（来自 config.yaml + prompt.md）
            prompt_cache: InstancePromptCache（包含分层提示词）
            previous_intent: 上一轮意图结果
            enable_stream: 是否流式输出
            **kwargs: 其他参数
            
        Yields:
            SSE 事件流
        """
        # 1. 提取用户查询
        user_query = self._extract_user_query(messages)
        conversation_history = messages[:-1] if len(messages) > 1 else []
        
        logger.info(f"🎯 AgentCoordinator.route_and_execute: query={user_query[:50]}...")
        
        # 2. 路由决策
        decision = await self.router.route(
            user_query=user_query,
            conversation_history=conversation_history,
            user_id=user_id,
            previous_intent=previous_intent,
        )
        
        logger.info(
            f"🔀 路由决策完成: agent_type={decision.agent_type}, "
            f"complexity={decision.intent.complexity_score if decision.intent else 'N/A'}"
        )
        
        # 3. 获取/创建 Agent（在 base_schema 基础上微调）
        agent = await self._get_or_create_agent(
            decision=decision,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service,
            system_prompt=system_prompt,
            base_schema=base_schema,
            prompt_cache=prompt_cache,
            **kwargs
        )
        
        logger.info(f"🤖 Agent 就绪: {get_agent_type(agent)}")
        
        # 4. 统一执行（无需类型判断）
        async for event in agent.execute(
            messages=messages,
            session_id=session_id,
            intent=decision.intent,
            enable_stream=enable_stream,
            **kwargs
        ):
            yield event
    
    async def _get_or_create_agent(
        self,
        decision: RoutingDecision,
        event_manager: "EventBroadcaster",
        workspace_dir: Optional[str] = None,
        conversation_service: Optional[Any] = None,
        system_prompt: Optional[str] = None,
        base_schema: Optional[Any] = None,
        prompt_cache: Optional[Any] = None,
        **kwargs
    ) -> AgentProtocol:
        """
        获取或创建 Agent
        
        核心设计（V7.8）：
        1. base_schema 来自实例配置（保留工具、技能、APIs 等）
        2. 根据 complexity_score 微调运行时参数
        3. 选择对应复杂度的提示词
        
        优先级：
        1. 从原型池获取并 clone
        2. 创建新 Agent（在 base_schema 基础上微调）
        
        Args:
            decision: 路由决策
            event_manager: 事件管理器
            base_schema: 实例级 Schema
            prompt_cache: 分层提示词缓存
            其他参数
            
        Returns:
            Agent 实例
        """
        from core.agent.factory import AgentFactory
        
        # 生成原型键（包含实例名和复杂度）
        prototype_key = self._get_prototype_key(decision, base_schema)
        
        # 尝试从原型池获取
        if self.enable_prototype_cache and prototype_key in self._prototype_pool:
            prototype = self._prototype_pool[prototype_key]
            logger.debug(f"📦 从原型池获取: {prototype_key}")
            
            return prototype.clone_for_session(
                event_manager=event_manager,
                workspace_dir=workspace_dir,
                conversation_service=conversation_service,
            )
        
        # 创建新 Agent（在 base_schema 基础上微调）
        agent = await AgentFactory.create_from_decision(
            decision=decision,
            event_manager=event_manager,
            base_schema=base_schema,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service,
            system_prompt=system_prompt,
            prompt_cache=prompt_cache,
            **kwargs
        )
        
        # 缓存原型（如果启用）
        if self.enable_prototype_cache:
            self._prototype_pool[prototype_key] = agent
            logger.debug(f"📦 缓存原型: {prototype_key}")
        
        return agent
    
    def _get_prototype_key(
        self, 
        decision: RoutingDecision,
        base_schema: Optional[Any] = None
    ) -> str:
        """
        生成原型缓存键
        
        基于 instance_name + agent_type + complexity_level 生成键。
        
        Args:
            decision: 路由决策
            base_schema: 实例级 Schema（用于获取实例名）
            
        Returns:
            缓存键
        """
        agent_type = decision.agent_type
        
        # 获取实例名
        instance_name = "default"
        if base_schema and hasattr(base_schema, 'name'):
            instance_name = base_schema.name
        
        # 根据复杂度评分分级
        if decision.intent and decision.intent.complexity_score:
            score = decision.intent.complexity_score
            if score <= 3.0:
                level = "simple"
            elif score <= 6.0:
                level = "medium"
            else:
                level = "complex"
        else:
            level = "default"
        
        return f"{instance_name}_{agent_type}_{level}"
    
    def _extract_user_query(self, messages: List[Dict[str, Any]]) -> str:
        """
        从消息列表中提取用户查询
        
        Args:
            messages: 消息列表
            
        Returns:
            用户查询文本
        """
        if not messages:
            return ""
        
        last_message = messages[-1]
        
        # 处理 Claude API 格式
        content = last_message.get("content", "")
        
        if isinstance(content, str):
            return content
        
        if isinstance(content, list):
            # 提取 text 类型的内容
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return " ".join(text_parts)
        
        return str(content)
    
    def clear_prototype_pool(self) -> None:
        """清空原型池"""
        self._prototype_pool.clear()
        logger.info("🧹 原型池已清空")
    
    def get_prototype_stats(self) -> Dict[str, Any]:
        """
        获取原型池统计
        
        Returns:
            {
                "size": int,
                "keys": List[str],
            }
        """
        return {
            "size": len(self._prototype_pool),
            "keys": list(self._prototype_pool.keys()),
        }


# ==================== 便捷函数 ====================

_default_coordinator: Optional[AgentCoordinator] = None


def get_agent_coordinator() -> AgentCoordinator:
    """
    获取全局 AgentCoordinator 实例
    
    Returns:
        AgentCoordinator 单例
    """
    global _default_coordinator
    if _default_coordinator is None:
        _default_coordinator = AgentCoordinator()
    return _default_coordinator


def create_agent_coordinator(
    router: Optional[AgentRouter] = None,
    **kwargs
) -> AgentCoordinator:
    """
    创建 AgentCoordinator 实例
    
    Args:
        router: AgentRouter 实例
        **kwargs: 其他参数
        
    Returns:
        AgentCoordinator 实例
    """
    return AgentCoordinator(router=router, **kwargs)
