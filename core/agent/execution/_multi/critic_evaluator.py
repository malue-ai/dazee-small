"""
Critic 评估器

V10.3 拆分自 orchestrator.py

职责：
- 执行 + 评估循环（execute -> critique -> retry/replan）
- Replan 触发逻辑
- SubTask -> PlanStep 转换
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from core.agent.models import (
    AgentConfig,
    AgentResult,
    CriticAction,
    CriticConfidence,
    CriticResult,
    PlanAdjustmentHint,
)
from core.planning.protocol import Plan, PlanStep, StepStatus
from logger import get_logger

if TYPE_CHECKING:
    from core.agent.components.critic import CriticAgent
    from core.agent.components.lead_agent import SubTask
    from core.agent.execution._multi.worker_runner import WorkerRunner
    from core.agent.models import CriticConfig

logger = get_logger(__name__)


class CriticEvaluator:
    """
    Critic 评估器

    在 Worker 执行后调用 CriticAgent 评估结果，
    根据评估结果决定 pass/retry/replan/ask_human。
    """

    def __init__(
        self,
        critic: Optional["CriticAgent"] = None,
        critic_config: Optional["CriticConfig"] = None,
    ):
        self.critic = critic
        self.critic_config = critic_config
        self.plan: Optional[Plan] = None
        self.plan_todo_tool = None

    @property
    def enabled(self) -> bool:
        return self.critic is not None and self.critic_config is not None

    @staticmethod
    def subtask_to_plan_step(subtask: "SubTask", step_id: str) -> PlanStep:
        """将 SubTask 转换为 PlanStep（用于 Critic 评估）"""
        return PlanStep(
            id=step_id,
            description=subtask.description,
            status=StepStatus.IN_PROGRESS,
            metadata={
                "subtask_id": subtask.subtask_id,
                "title": subtask.title,
                "expected_output": subtask.expected_output,
                "success_criteria": subtask.success_criteria,
                "tools_required": subtask.tools_required,
                "constraints": subtask.constraints,
            },
        )

    async def execute_with_critique(
        self,
        worker_runner: "WorkerRunner",
        agent_config: AgentConfig,
        subtask: Optional["SubTask"],
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
        build_system_prompt=None,
        build_orchestrator_summary=None,
        summarize_previous_output=None,
    ) -> AgentResult:
        """
        执行步骤（带 Critic 评估）

        如果未启用 Critic，直接执行 Worker。
        """
        # 如果未启用 Critic，直接执行
        if not self.enabled:
            return await worker_runner.execute_worker(
                agent_config,
                messages,
                previous_output,
                session_id,
                subtask,
                build_system_prompt=build_system_prompt,
                build_orchestrator_summary=build_orchestrator_summary,
                summarize_previous_output=summarize_previous_output,
            )

        # 创建 PlanStep
        step_id = subtask.subtask_id if subtask else f"step_{agent_config.agent_id}"
        plan_step = (
            self.subtask_to_plan_step(subtask, step_id)
            if subtask
            else PlanStep(
                id=step_id,
                description=f"执行 {agent_config.role.value} 任务",
                status=StepStatus.IN_PROGRESS,
            )
        )

        max_retries = self.critic_config.max_retries
        retry_count = 0

        while retry_count <= max_retries:
            # 1. Execute
            result = await worker_runner.execute_worker(
                agent_config,
                messages,
                previous_output,
                session_id,
                subtask,
                build_system_prompt=build_system_prompt,
                build_orchestrator_summary=build_orchestrator_summary,
                summarize_previous_output=summarize_previous_output,
            )

            if not result.success:
                plan_step.fail(result.error or "执行失败")
                return result

            # 2. Critique
            success_criteria = (
                subtask.success_criteria
                if subtask and subtask.success_criteria
                else plan_step.metadata.get("success_criteria", [])
            )

            critic_result = await self.critic.critique(
                executor_output=result.output,
                plan_step=plan_step,
                success_criteria=success_criteria,
                retry_count=retry_count,
                max_retries=max_retries,
            )

            # 3. 记录 Critic 反馈
            plan_step.metadata["critic"] = {
                "action": critic_result.recommended_action.value,
                "confidence": critic_result.confidence.value,
                "reasoning": critic_result.reasoning,
                "retry_count": retry_count,
            }

            can_auto_execute = self.critic.should_auto_execute(critic_result)

            # 4. 根据 recommended_action 处理
            if critic_result.recommended_action == CriticAction.PASS:
                plan_step.complete(result.output)
                logger.info(
                    f"✅ Critic PASS: step_id={step_id}, "
                    f"confidence={critic_result.confidence.value}"
                )
                return result

            elif critic_result.recommended_action == CriticAction.ASK_HUMAN:
                logger.info(f"👤 Critic ASK_HUMAN: step_id={step_id}")
                result.metadata["needs_human_review"] = True
                result.metadata["critic_result"] = critic_result.model_dump()
                return result

            elif critic_result.recommended_action == CriticAction.RETRY:
                if not can_auto_execute and self.critic_config.require_human_on_low_confidence:
                    result.metadata["needs_human_review"] = True
                    result.metadata["critic_result"] = critic_result.model_dump()
                    return result

                retry_count += 1
                plan_step.metadata["retry_count"] = retry_count

                logger.info(
                    f"🔄 Critic RETRY: step_id={step_id}, "
                    f"retry_count={retry_count}/{max_retries}"
                )

                if subtask:
                    subtask.context = (
                        f"{subtask.context}\n\n"
                        f"【改进建议（重试 {retry_count}/{max_retries}）】\n"
                        + "\n".join(f"- {s}" for s in critic_result.suggestions)
                    )
                continue

            elif critic_result.recommended_action == CriticAction.REPLAN:
                logger.warning(f"⚠️ Critic REPLAN: step_id={step_id}")

                if critic_result.plan_adjustment:
                    await self._trigger_replan(plan_step, critic_result.plan_adjustment)

                plan_step.fail("需要调整计划")
                return AgentResult(
                    result_id=f"result_{uuid4()}",
                    agent_id=agent_config.agent_id,
                    success=False,
                    output=result.output,
                    error="Critic 建议调整计划",
                    metadata={
                        "needs_replan": True,
                        "critic_result": critic_result.model_dump(),
                    },
                )

        # 超过最大重试次数
        plan_step.fail(f"超过最大重试次数 ({max_retries})")
        return AgentResult(
            result_id=f"result_{uuid4()}",
            agent_id=agent_config.agent_id,
            success=False,
            output=result.output if "result" in locals() else "",
            error=f"超过最大重试次数 ({max_retries})",
        )

    async def _trigger_replan(
        self,
        plan_step: PlanStep,
        adjustment: PlanAdjustmentHint,
    ) -> None:
        """触发计划调整"""
        logger.info(f"🔄 触发计划调整: step_id={plan_step.id}, action={adjustment.action}")

        if self.plan_todo_tool is None:
            try:
                from tools.plan_todo_tool import PlanTodoTool

                self.plan_todo_tool = PlanTodoTool()
            except ImportError:
                logger.warning("⚠️ plan_todo_tool 未找到，跳过 replan")
                return

        if self.plan is None:
            self.plan = Plan(goal="多智能体任务执行", execution_mode="dag")

        if adjustment.action == "skip":
            plan_step.status = StepStatus.SKIPPED
        elif adjustment.action == "insert_before":
            if adjustment.new_step:
                new_step = self.plan.add_step(
                    description=adjustment.new_step,
                    dependencies=plan_step.dependencies,
                )
                plan_step.dependencies = [new_step.id]
        elif adjustment.action == "modify":
            if adjustment.context_for_replan:
                try:
                    await self.plan_todo_tool.replan(
                        plan=self.plan,
                        context=adjustment.context_for_replan,
                        failed_step_id=plan_step.id,
                    )
                except Exception as e:
                    logger.error(f"❌ replan 失败: {e}", exc_info=True)
