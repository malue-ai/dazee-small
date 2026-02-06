"""
多智能体执行器

实现 ExecutorProtocol，提供多智能体执行策略：
- SequentialExecutor: 串行执行
- ParallelExecutor: 并行执行
- HierarchicalExecutor: 层级执行

这是适配器层，委托给 multi/ 模块的实现。
"""

from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from core.agent.execution.protocol import BaseExecutor, ExecutionContext, ExecutorConfig
from logger import get_logger

if TYPE_CHECKING:
    from core.agent.execution._multi import MultiAgentOrchestrator
    from core.agent.models import ExecutionMode, MultiAgentConfig

logger = get_logger(__name__)


class MultiAgentExecutor(BaseExecutor):
    """
    多智能体执行器

    适配器模式：将 MultiAgentOrchestrator 适配为 ExecutorProtocol。

    使用方式：
        executor = MultiAgentExecutor(mode="sequential")

        async for event in executor.execute(messages, context, config):
            yield event
    """

    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
        mode: str = "sequential",
        multi_config: Optional["MultiAgentConfig"] = None,
    ):
        """
        初始化多智能体执行器

        Args:
            config: 执行器配置
            mode: 执行模式 (sequential, parallel, hierarchical)
            multi_config: 多智能体配置
        """
        super().__init__(config)
        self._mode = mode
        self._multi_config = multi_config
        self._orchestrator: Optional["MultiAgentOrchestrator"] = None

    @property
    def name(self) -> str:
        return f"MultiAgentExecutor({self._mode})"

    def supports_backtrack(self) -> bool:
        return False  # 多智能体暂不支持回溯

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行多智能体工作流

        委托给 MultiAgentOrchestrator 的 execute() 方法。
        """
        from core.agent.execution._multi import MultiAgentOrchestrator
        from core.agent.models import ExecutionMode, MultiAgentConfig

        effective_config = config or self.config

        # 映射执行模式
        mode_map = {
            "sequential": ExecutionMode.SEQUENTIAL,
            "parallel": ExecutionMode.PARALLEL,
            "hierarchical": ExecutionMode.HIERARCHICAL,
        }
        execution_mode = mode_map.get(self._mode, ExecutionMode.SEQUENTIAL)

        # 创建或复用 Orchestrator（通过 Factory 统一入口）
        if self._orchestrator is None:
            from core.agent.factory import AgentFactory

            multi_config = self._multi_config or MultiAgentConfig(
                mode=execution_mode,
                max_agents=5,
                max_turns_per_agent=10,
            )
            self._orchestrator = AgentFactory.create_multi_agent(
                multi_agent_config=multi_config,
            )

        # V10.4: 正规依赖注入（替代直接设置私有属性）
        self._orchestrator.inject_dependencies(
            broadcaster=context.broadcaster,
            tool_executor=context.tool_executor,
            llm=context.llm,
        )

        # 委托执行
        async for event in self._orchestrator.execute(
            messages=messages,
            session_id=context.session_id,
            intent=context.intent,
            enable_stream=effective_config.enable_stream,
        ):
            yield event


class SequentialMultiExecutor(MultiAgentExecutor):
    """串行多智能体执行器"""

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config, mode="sequential")

    @property
    def name(self) -> str:
        return "SequentialMultiExecutor"


class ParallelMultiExecutor(MultiAgentExecutor):
    """并行多智能体执行器"""

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config, mode="parallel")

    @property
    def name(self) -> str:
        return "ParallelMultiExecutor"


class HierarchicalMultiExecutor(MultiAgentExecutor):
    """层级多智能体执行器"""

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config, mode="hierarchical")

    @property
    def name(self) -> str:
        return "HierarchicalMultiExecutor"
