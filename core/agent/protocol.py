"""
Agent 统一接口协议（Protocol）

V7.8 新增模块

设计原则：
1. 使用 Python Protocol 实现结构化子类型（Structural Subtyping）
2. SimpleAgent 和 MultiAgentOrchestrator 都实现此协议
3. 上层调用方只依赖 Protocol，不依赖具体实现
4. 支持 runtime_checkable，可用于 isinstance 检查

核心方法：
- execute(): 统一执行入口（替代 chat() 和 _execute_dag()）
- clone_for_session(): 从原型克隆 Session 级实例

参考：
- docs/architecture/00-ARCHITECTURE-OVERVIEW.md
- PEP 544 – Protocols: Structural subtyping
"""

from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Protocol,
    TYPE_CHECKING,
    runtime_checkable,
)

if TYPE_CHECKING:
    from core.agent.types import IntentResult
    from core.events.broadcaster import EventBroadcaster
    from core.schemas import AgentSchema


@runtime_checkable
class AgentProtocol(Protocol):
    """
    Agent 统一接口协议
    
    所有 Agent 实现（SimpleAgent, MultiAgentOrchestrator）都应符合此协议。
    
    设计哲学：
    - 面向接口编程，上层不依赖具体实现
    - 支持 isinstance 检查（runtime_checkable）
    - 最小化接口，只包含核心方法
    
    使用示例：
        def process(agent: AgentProtocol, messages: List[Dict]):
            # 无需知道是 SimpleAgent 还是MultiAgentOrchestrator
            async for event in agent.execute(messages, session_id):
                yield event
    """
    
    # ==================== 属性 ====================
    
    @property
    def model(self) -> str:
        """主模型名称"""
        ...
    
    @property
    def schema(self) -> "AgentSchema":
        """Agent Schema 配置"""
        ...
    
    @property
    def usage_stats(self) -> Dict[str, int]:
        """
        Token 使用统计
        
        Returns:
            {
                "input_tokens": int,
                "output_tokens": int,
                "total_tokens": int,
                "cache_read_tokens": int,
                "cache_creation_tokens": int,
            }
        """
        ...
    
    # ==================== 核心方法 ====================
    
    async def execute(
        self,
        messages: List[Dict[str, Any]],
        session_id: str,
        intent: Optional["IntentResult"] = None,
        enable_stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        统一执行入口
        
        这是 Agent 的核心方法，所有执行都通过此入口。
        
        Args:
            messages: 消息列表（Claude API 格式）
            session_id: 会话 ID
            intent: 路由层传入的意图结果（由 AgentRouter 提供）
            enable_stream: 是否启用流式输出
            **kwargs: 其他参数
                - message_id: 消息 ID
                - variables: 前端上下文变量
                - workspace_dir: 工作目录
            
        Yields:
            SSE 事件流，格式：
            {
                "event": "content_start" | "content_delta" | "content_stop" | ...,
                "data": {...}
            }
            
        实现说明：
        - SimpleAgent: 内部调用 _run_rvr_loop()
        - MultiAgentOrchestrator: 内部调用 _execute_with_dag_scheduler()
        """
        ...
    
    def clone_for_session(
        self,
        event_manager: "EventBroadcaster",
        workspace_dir: Optional[str] = None,
        conversation_service: Optional[Any] = None,
        **kwargs
    ) -> "AgentProtocol":
        """
        从原型克隆 Session 级实例
        
        V7.1 原型池优化的核心方法：
        - 浅拷贝重量级组件（共享 LLM Services, ToolExecutor 等）
        - 重置 Session 级状态（EventBroadcaster, UsageTracker 等）
        
        Args:
            event_manager: EventBroadcaster 实例
            workspace_dir: 工作目录（可选）
            conversation_service: 会话服务（可选）
            **kwargs: 其他参数
            
        Returns:
            克隆后的 Agent 实例
            
        性能：
        - 原型创建：50-100ms
        - clone_for_session：<5ms（90%+ 提升）
        """
        ...


# ==================== 类型别名 ====================

# Agent 执行结果生成器类型
AgentEventGenerator = AsyncGenerator[Dict[str, Any], None]

# Agent 创建工厂函数类型
AgentFactoryFunc = Any  # Callable[..., Awaitable[AgentProtocol]]


# ==================== 辅助函数 ====================

def is_agent(obj: Any) -> bool:
    """
    检查对象是否是 Agent 实例
    
    Args:
        obj: 待检查对象
        
    Returns:
        True 如果对象实现了 AgentProtocol
    """
    return isinstance(obj, AgentProtocol)


def get_agent_type(agent: AgentProtocol) -> str:
    """
    获取 Agent 类型名称
    
    Args:
        agent: Agent 实例
        
    Returns:
        "SimpleAgent" | "MultiAgentOrchestrator" | 类名
    """
    return type(agent).__name__
