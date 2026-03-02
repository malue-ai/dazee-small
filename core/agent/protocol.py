"""
Agent 统一接口协议（Protocol）

V7.8 新增模块
V10.0 更新：统一 Agent 架构，执行策略通过 Executor 实现

设计原则：
1. 使用 Python Protocol 实现结构化子类型（Structural Subtyping）
2. 统一的 Agent 类实现此协议，执行策略由 Executor 提供
3. 上层调用方只依赖 Protocol，不依赖具体实现
4. 支持 runtime_checkable，可用于 isinstance 检查

架构：
- AgentProtocol: 接口定义（Protocol）
- Agent: 统一实现类（core/agent/base.py），实现 AgentProtocol
- Executor: 执行策略（RVRExecutor, RVRBExecutor）

核心方法：
- execute(): 统一执行入口（替代 chat() 和 _execute_dag()）
- clone_for_session(): 从原型克隆 Session 级实例

参考：
- docs/architecture/00-ARCHITECTURE-OVERVIEW.md
- PEP 544 – Protocols: Structural subtyping
"""

import uuid
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from core.events.broadcaster import EventBroadcaster
    from core.routing.types import IntentResult
    from core.schemas import AgentSchema


@runtime_checkable
class AgentProtocol(Protocol):
    """
    Agent 统一接口协议

    统一的 Agent 类实现此协议，执行策略由 Executor 提供。

    设计哲学：
    - 面向接口编程，上层不依赖具体实现
    - 支持 isinstance 检查（runtime_checkable）
    - 最小化接口，只包含核心方法

    使用示例：
        def process(agent: AgentProtocol, messages: List[Dict]):
            # 无需知道底层使用哪个 Executor（RVR/RVR-B/Multi）
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
        - Agent 类委托给 Executor 执行（RVRExecutor, RVRBExecutor）
        - 执行策略由 Agent.schema.execution_strategy 决定，Factory 负责注入对应的 Executor
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


# ==================== 多智能体协作协议（接口预留） ====================


class AgentRole(str, Enum):
    """智能体角色"""

    COORDINATOR = "coordinator"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    WRITER = "writer"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"


class InterAgentMessage(BaseModel):
    """
    智能体间消息（跨 Agent 通信载体）

    用于多智能体协作场景：
    - Coordinator 向 Researcher 分派研究任务
    - Researcher 向 Analyst 传递数据
    - Reviewer 向 Writer 返回修改意见
    """

    message_id: str = Field(default_factory=lambda: f"iam_{uuid.uuid4().hex[:8]}")
    from_agent: str = Field(..., description="发送方 Agent ID")
    to_agent: str = Field(..., description="接收方 Agent ID")
    role: AgentRole = Field(default=AgentRole.EXECUTOR, description="发送方角色")
    message_type: str = Field(default="task", description="消息类型: task / result / feedback / error")
    content: str = Field(..., description="消息正文")
    context: Dict[str, Any] = Field(default_factory=dict, description="附加上下文")
    reply_to: Optional[str] = Field(None, description="回复的消息 ID")
    timestamp: Optional[str] = Field(default=None)

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            from datetime import datetime
            self.timestamp = datetime.now().isoformat()


@runtime_checkable
class CollaborationProtocol(Protocol):
    """
    多智能体协作协议（接口预留）

    当前单智能体架构下不启用，为未来多智能体协作预留扩展点。
    实现此协议的 Agent 可以参与多智能体工作流。

    设计原则：
    - 最小化接口，只定义通信原语
    - 与 AgentProtocol 解耦，可选实现
    - 消息驱动，无共享状态
    """

    @property
    def agent_id(self) -> str:
        """Agent 唯一标识"""
        ...

    @property
    def role(self) -> AgentRole:
        """Agent 在协作中的角色"""
        ...

    async def receive_message(self, message: InterAgentMessage) -> Optional[InterAgentMessage]:
        """
        接收来自其他 Agent 的消息并返回响应

        Args:
            message: 收到的消息

        Returns:
            响应消息，或 None（无需回复）
        """
        ...

    async def delegate_task(
        self,
        target_agent_id: str,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> InterAgentMessage:
        """
        向目标 Agent 委派任务

        Args:
            target_agent_id: 目标 Agent ID
            task_description: 任务描述
            context: 任务上下文

        Returns:
            目标 Agent 的响应消息
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
        Agent 类名（通常是 "Agent"）或执行策略名称
    """
    if hasattr(agent, "schema") and hasattr(agent.schema, "execution_strategy"):
        strategy = agent.schema.execution_strategy
        if strategy:
            return strategy
    return type(agent).__name__
