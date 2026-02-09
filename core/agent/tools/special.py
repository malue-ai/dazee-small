"""
特殊工具处理器

提供 plan_todo 等特殊工具的处理逻辑。

Agent 工具处理 — 特殊工具（plan/hitl/termination）
"""

from typing import Any, Dict

from core.agent.tools.flow import (
    SpecialToolHandler,
    ToolExecutionContext,
    ToolExecutionResult,
)
from logger import get_logger

logger = get_logger(__name__)


class PlanTodoHandler(SpecialToolHandler):
    """
    Plan Todo 工具处理器

    处理 plan_todo 工具的执行和 plan_cache 更新。
    """

    @property
    def tool_name(self) -> str:
        return "plan"

    async def execute(
        self, tool_input: Dict[str, Any], context: ToolExecutionContext, tool_id: str
    ) -> ToolExecutionResult:
        """
        执行 plan

        Args:
            tool_input: 工具输入参数
            context: 执行上下文
            tool_id: 工具调用 ID

        Returns:
            执行结果
        """
        try:
            if not context.tool_executor:
                raise ValueError("tool_executor 未配置")
            if not context.conversation_id:
                raise ValueError("conversation_id 为空，无法存储计划")

            # 直接通过 ToolExecutor 执行（PlanTool 会自行持久化到 Conversation.metadata.plan）
            result = await context.tool_executor.execute(self.tool_name, tool_input)

            # 更新 plan 缓存
            action = tool_input.get("action", "unknown")
            if result.get("success") and "plan" in result:
                context.plan_cache["plan"] = result.get("plan")
                logger.info(f"📋 Plan 操作完成: {action}")

            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=self.tool_name,
                tool_input=tool_input,
                result=result,
                is_error=False,
            )

        except Exception as e:
            logger.error(f"❌ plan 执行失败: {e}")
            return ToolExecutionResult(
                tool_id=tool_id,
                tool_name=self.tool_name,
                tool_input=tool_input,
                result={"error": str(e), "success": False},
                is_error=True,
                error_msg=str(e),
            )



# NOTE: HumanConfirmationHandler 已删除
# 原因：
# 1. tool_name 使用旧名 "request_human_confirmation"，但工具已改名为 "hitl"，导致此 handler 永远不会被调用
# 2. 调用了不存在的 broadcaster.emit_confirmation_request() 方法
# 3. HITL 功能已由 tools/request_human_confirmation.py 的 HITLTool 完整实现
# 4. broadcaster._emit_hitl_request_event() 在 content_stop 时自动发送表单事件给前端
