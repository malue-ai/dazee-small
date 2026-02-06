"""
结果聚合器

V10.3 拆分自 orchestrator.py

职责：
- 多 Worker 结果聚合
- 最终摘要生成
- Content blocks 构建（用于存储到 messages 表）
- 执行 metadata 构建
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

if TYPE_CHECKING:
    from core.agent.components.checkpoint import CheckpointManager
    from core.agent.components.lead_agent import LeadAgent, TaskDecompositionPlan
    from core.agent.models import MultiAgentConfig, OrchestratorState

logger = get_logger(__name__)


class ResultAggregator:
    """
    结果聚合器

    负责将多个 Worker 的执行结果整合为最终输出。
    """

    def __init__(
        self,
        lead_agent: Optional["LeadAgent"] = None,
        usage_tracker=None,
    ):
        self.lead_agent = lead_agent
        self.usage_tracker = usage_tracker

    async def generate_summary(
        self,
        state: "OrchestratorState",
    ) -> str:
        """
        生成最终汇总（简单版本）

        将所有 Agent 的输出整合为最终结果。
        """
        if not state or not state.agent_results:
            return "没有可汇总的结果"

        summary_parts = []
        for result in state.agent_results:
            if result.success and result.output:
                summary_parts.append(f"【{result.agent_id}】\n{result.output}")

        return "\n\n".join(summary_parts) if summary_parts else "所有 Agent 执行失败"

    async def synthesize_with_lead_agent(
        self,
        state: "OrchestratorState",
        messages: List[Dict[str, Any]],
        decomposition_plan: Optional["TaskDecompositionPlan"] = None,
    ) -> str:
        """
        使用 Lead Agent 综合结果

        Args:
            state: 编排器状态
            messages: 原始消息
            decomposition_plan: 分解计划
        """
        if not self.lead_agent or not state.agent_results:
            return await self.generate_summary(state)

        # 提取用户查询
        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_query = content if isinstance(content, str) else str(content)
                break

        subtask_results = [
            {
                "agent_id": result.agent_id,
                "title": f"Agent {result.agent_id}",
                "output": result.output,
                "success": result.success,
            }
            for result in state.agent_results
        ]

        final_output = await self.lead_agent.synthesize_results(
            subtask_results=subtask_results,
            original_query=user_query,
            synthesis_strategy=(
                decomposition_plan.synthesis_strategy if decomposition_plan else None
            ),
        )

        # 累积 usage
        if self.usage_tracker and hasattr(self.lead_agent, "last_llm_response"):
            self.usage_tracker.accumulate(self.lead_agent.last_llm_response)

        return final_output

    @staticmethod
    def build_content_blocks(
        state: Optional["OrchestratorState"],
        decomposition_plan: Optional["TaskDecompositionPlan"] = None,
        final_summary: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        构建结构化的 content_blocks（用于存储到 messages 表）

        格式遵循 Claude API 标准。
        """
        blocks = []
        index = 0

        # 1. 任务规划说明
        if decomposition_plan and decomposition_plan.subtasks:
            subtask_list = "\n".join(
                [f"  {i+1}. {st.title}" for i, st in enumerate(decomposition_plan.subtasks)]
            )
            planning_text = (
                f"我将对这个任务进行多智能体协作分析：\n{subtask_list}\n\n"
                f"执行模式：{decomposition_plan.execution_mode.value}"
            )
            blocks.append({"type": "text", "text": planning_text, "index": index})
            index += 1

        # 2. 子任务执行过程
        if state and state.agent_results:
            for result in state.agent_results:
                subtask_title = result.agent_id
                subtask_role = "executor"
                if decomposition_plan:
                    for st in decomposition_plan.subtasks:
                        if st.subtask_id == result.agent_id:
                            subtask_title = st.title
                            subtask_role = st.assigned_agent_role.value
                            break

                tool_use_id = f"subtask_{result.agent_id}"
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": "multi_agent_subtask",
                        "input": {
                            "title": subtask_title,
                            "agent_role": subtask_role,
                            "agent_id": result.agent_id,
                        },
                        "index": index,
                    }
                )
                index += 1

                result_content = (
                    result.output if result.success else f"执行失败: {result.error}"
                )
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_content,
                        "is_error": not result.success,
                        "index": index,
                    }
                )
                index += 1

        # 3. 最终综合结果
        if final_summary:
            blocks.append({"type": "text", "text": final_summary, "index": index})

        return blocks

    @staticmethod
    def build_metadata(
        state: Optional["OrchestratorState"],
        config: Optional["MultiAgentConfig"],
        decomposition_plan: Optional["TaskDecompositionPlan"] = None,
        lead_agent: Optional["LeadAgent"] = None,
        worker_model: Optional[str] = None,
        execution_trace: Optional[List[Dict[str, Any]]] = None,
        checkpoint_manager: Optional["CheckpointManager"] = None,
    ) -> Dict[str, Any]:
        """
        获取多智能体执行的 metadata

        用于存储到 messages.extra_data。
        """
        metadata = {
            "multi_agent": {
                "enabled": True,
                "mode": config.mode.value if config else "sequential",
                "orchestrator_model": lead_agent.model if lead_agent else None,
                "worker_model": worker_model,
            }
        }

        if decomposition_plan:
            metadata["multi_agent"]["plan"] = {
                "plan_id": decomposition_plan.plan_id,
                "subtasks_count": len(decomposition_plan.subtasks),
                "execution_mode": decomposition_plan.execution_mode.value,
                "reasoning": (
                    decomposition_plan.reasoning[:200] if decomposition_plan.reasoning else None
                ),
            }

        if state and state.agent_results:
            subtasks_summary = []
            for result in state.agent_results:
                subtasks_summary.append(
                    {
                        "subtask_id": result.agent_id,
                        "success": result.success,
                        "duration_ms": result.duration_ms,
                        "turns_used": result.turns_used,
                        "output_length": len(result.output) if result.output else 0,
                    }
                )
            metadata["multi_agent"]["subtasks"] = subtasks_summary
            metadata["multi_agent"]["total_duration_ms"] = state.total_duration_ms

        if execution_trace:
            metadata["multi_agent"]["trace"] = execution_trace

        if checkpoint_manager:
            metadata["multi_agent"]["checkpoints_enabled"] = True

        return metadata
