"""
RVR-B Agent - 带回溯能力的单智能体

V8.0 架构

设计：
- 继承 SimpleAgent 获得所有基础能力
- 混入 BacktrackMixin 获得回溯能力
- 只重写 _run_rvr_loop，其他方法全部复用

RVR-B 循环：
React → Validate → Reflect → Backtrack Decision
                                    ↓
                    ┌───────────────┴───────────────┐
                    ↓               ↓               ↓
               继续执行         需要回溯         无法恢复
                    ↓               ↓               ↓
               下一轮 RVR      策略调整→重试     优雅失败

回溯类型：
- PLAN_REPLAN: Plan 重规划
- TOOL_REPLACE: 工具替换
- PARAM_ADJUST: 参数调整
- CONTEXT_ENRICH: 上下文补充
- INTENT_CLARIFY: 意图澄清
"""

from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING

from core.agent.simple.simple_agent import SimpleAgent
from core.agent.simple.mixins.backtrack_mixin import BacktrackMixin, RVRBState
from logger import get_logger

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext
    from core.agent.types import IntentResult

logger = get_logger(__name__)


class RVRBAgent(SimpleAgent, BacktrackMixin):
    """
    RVR-B Agent - 带回溯能力的单智能体
    
    通过 Mixin 组合获得能力：
    - SimpleAgent: 完整的初始化、工具执行、流式处理
    - BacktrackMixin: 业务逻辑层错误回溯
    
    使用方式：
        agent = RVRBAgent(
            model="claude-sonnet-4-5-20250929",
            event_manager=event_manager,
            max_backtracks=3
        )
        
        async for event in agent.chat(messages, session_id):
            yield event
    """
    
    STRATEGY_NAME = "rvr-b"
    
    def __init__(
        self,
        max_backtracks: int = 3,
        **kwargs
    ):
        """
        初始化 RVR-B Agent
        
        Args:
            max_backtracks: 最大回溯次数（默认 3）
            **kwargs: 传递给 SimpleAgent 的所有参数
        """
        # 初始化 SimpleAgent
        SimpleAgent.__init__(self, **kwargs)
        
        # 初始化 BacktrackMixin
        BacktrackMixin._init_backtrack(self, max_backtracks)
        
        logger.info(
            f"✅ RVRBAgent 初始化完成: strategy={self.STRATEGY_NAME}, "
            f"max_backtracks={max_backtracks}"
        )
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.STRATEGY_NAME
    
    async def _run_rvr_loop(
        self,
        messages: List,
        system_prompt,
        tools_for_llm: List,
        ctx: "RuntimeContext",
        session_id: str,
        intent: "IntentResult",
        enable_stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        重写 RVR 循环，使用带回溯的版本
        
        委托给 BacktrackMixin._run_rvr_loop_with_backtrack
        """
        async for event in self._run_rvr_loop_with_backtrack(
            messages=messages,
            system_prompt=system_prompt,
            tools_for_llm=tools_for_llm,
            ctx=ctx,
            session_id=session_id,
            intent=intent,
            enable_stream=enable_stream
        ):
            yield event
    
    def clone_for_session(
        self,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None
    ) -> "RVRBAgent":
        """
        从原型克隆 Agent 实例
        
        重写以确保正确初始化回溯组件
        """
        # 调用父类克隆
        clone = SimpleAgent.clone_for_session(
            self,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service
        )
        
        # 转换类型
        clone.__class__ = RVRBAgent
        
        # 初始化回溯组件
        clone._max_backtracks = self._max_backtracks
        clone._error_classifier = None
        clone._backtrack_manager = None
        clone._rvrb_states = {}
        
        return clone
