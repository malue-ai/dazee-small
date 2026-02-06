"""
任务分解器

V10.3 拆分自 orchestrator.py

职责：
- 调用 LeadAgent 进行任务分解
- 分解结果处理和事件通知
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

if TYPE_CHECKING:
    from core.agent.components.lead_agent import LeadAgent, TaskDecompositionPlan
    from core.agent.models import AgentConfig
    from core.routing import IntentResult

logger = get_logger(__name__)


class TaskDecomposer:
    """
    任务分解器

    封装 LeadAgent 的任务分解能力。
    """

    def __init__(
        self,
        lead_agent: Optional["LeadAgent"] = None,
        usage_tracker=None,
    ):
        self.lead_agent = lead_agent
        self.usage_tracker = usage_tracker

    @property
    def enabled(self) -> bool:
        return self.lead_agent is not None

    async def decompose(
        self,
        user_query: str,
        messages: List[Dict[str, Any]],
        agent_configs: List["AgentConfig"],
        intent: Optional["IntentResult"] = None,
    ) -> Optional["TaskDecompositionPlan"]:
        """
        使用 LeadAgent 进行任务分解

        Args:
            user_query: 用户查询
            messages: 消息历史
            agent_configs: Agent 配置列表
            intent: 意图分析结果

        Returns:
            TaskDecompositionPlan 或 None（如果分解失败）
        """
        if not self.enabled:
            logger.warning("⚠️ LeadAgent 未启用，跳过任务分解")
            return None

        try:
            available_tools = list(
                set(tool for agent in agent_configs for tool in agent.tools)
            )

            plan = await self.lead_agent.decompose_task(
                user_query=user_query,
                conversation_history=messages,
                available_tools=available_tools,
                intent_info=intent.to_dict() if intent else None,
            )

            # 累积 usage
            if self.usage_tracker and hasattr(self.lead_agent, "last_llm_response"):
                self.usage_tracker.accumulate(self.lead_agent.last_llm_response)

            logger.info(
                f"✅ 任务分解完成: plan_id={plan.plan_id}, "
                f"subtasks={len(plan.subtasks)}, "
                f"mode={plan.execution_mode.value}"
            )

            return plan

        except Exception as e:
            logger.warning(f"⚠️ 任务分解失败: {e}，使用默认配置")
            return None
