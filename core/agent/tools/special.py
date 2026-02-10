"""
特殊工具处理器

提供 plan_todo 等特殊工具的处理逻辑。

Agent 工具处理 — 特殊工具（plan/hitl/termination）
"""

from typing import Any, Dict, List

from core.agent.tools.flow import (
    SpecialToolHandler,
    ToolExecutionContext,
    ToolExecutionResult,
)
from logger import get_logger

logger = get_logger(__name__)

# ---------- Plan 收敛控制 ----------
# 连续 plan 调用超过此次数后，注入强制执行提示
MAX_CONSECUTIVE_PLANS = 2
# 两次 plan create 的 todos 标题集合 Jaccard > 此阈值视为收敛
PLAN_CONVERGENCE_THRESHOLD = 0.8

PLAN_FORCE_EXECUTE_HINT = (
    "[SYSTEM] 你已连续规划多次，请立即执行当前 Plan 的第一个未完成步骤，不要再修改 Plan。"
)


def summarize_plan(plan: Dict[str, Any]) -> str:
    """Code-based plan summarization (zero LLM calls, <1ms).

    Extracts plan name + each todo's title and status into a one-line summary.
    Used when a new plan replaces an old one — the old plan is compressed to
    this summary in the context to save tokens.

    Args:
        plan: Plan dict with "name", "todos" list.

    Returns:
        Single-line summary, e.g.:
        "[旧计划] 季度销售分析（2/5 完成）: ✓清洗, ✓分析, →排名, ○检测, ○报告"
    """
    name = plan.get("name", "未命名计划")
    todos = plan.get("todos", [])
    if not todos:
        return f"[旧计划] {name}（无步骤）"

    status_icons = {"completed": "✓", "in_progress": "→", "failed": "✗"}
    total = len(todos)
    completed = sum(1 for t in todos if t.get("status") == "completed")

    parts = []
    for t in todos:
        icon = status_icons.get(t.get("status", "pending"), "○")
        title = t.get("title", t.get("content", ""))[:20]
        parts.append(f"{icon}{title}")

    return f"[旧计划] {name}（{completed}/{total} 完成）: {', '.join(parts)}"


def _todos_jaccard(todos_a: List[Dict], todos_b: List[Dict]) -> float:
    """Jaccard similarity of two todo lists based on title strings."""
    set_a = {t.get("title", t.get("content", "")) for t in todos_a}
    set_b = {t.get("title", t.get("content", "")) for t in todos_b}
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


class PlanTodoHandler(SpecialToolHandler):
    """
    Plan Todo 工具处理器

    处理 plan_todo 工具的执行和 plan_cache 更新。
    增加连续 plan 上限、收敛检测和旧 plan 摘要化。
    """

    def __init__(self):
        self._consecutive_plan_count: int = 0
        self._last_plan_todos: List[Dict] = []

    @property
    def tool_name(self) -> str:
        return "plan"

    def reset_consecutive_count(self) -> None:
        """Called by the execution loop when a non-plan tool is executed."""
        self._consecutive_plan_count = 0

    async def execute(
        self, tool_input: Dict[str, Any], context: ToolExecutionContext, tool_id: str
    ) -> ToolExecutionResult:
        """
        Execute plan tool with convergence detection.

        Args:
            tool_input: Tool input parameters
            context: Execution context
            tool_id: Tool call ID

        Returns:
            Execution result (may include force-execute hint)
        """
        try:
            if not context.tool_executor:
                raise ValueError("tool_executor 未配置")
            if not context.conversation_id:
                raise ValueError("conversation_id 为空，无法存储计划")

            action = tool_input.get("action", "unknown")

            # Track consecutive plan calls
            if action in ("create", "update"):
                self._consecutive_plan_count += 1
            # For "create" specifically, check convergence with previous plan
            force_execute = False
            if action == "create":
                new_todos = tool_input.get("todos", [])
                if (
                    self._last_plan_todos
                    and _todos_jaccard(self._last_plan_todos, new_todos)
                    > PLAN_CONVERGENCE_THRESHOLD
                ):
                    logger.warning(
                        f"⚠️ Plan 收敛检测: 新旧 Plan 相似度 > {PLAN_CONVERGENCE_THRESHOLD}，"
                        f"强制进入执行"
                    )
                    force_execute = True
                self._last_plan_todos = new_todos

            if self._consecutive_plan_count > MAX_CONSECUTIVE_PLANS:
                logger.warning(
                    f"⚠️ Plan 连续上限: 已连续 {self._consecutive_plan_count} 次 plan 调用，"
                    f"强制进入执行"
                )
                force_execute = True

            # Summarize old plan before replacing (zero LLM, code-based)
            old_plan = context.plan_cache.get("plan")
            old_plan_summary = None
            if old_plan and action == "create":
                old_plan_summary = summarize_plan(old_plan)
                logger.info(f"📋 旧 Plan 摘要化: {old_plan_summary}")

            # Execute the plan tool
            result = await context.tool_executor.execute(self.tool_name, tool_input)

            # Update plan cache
            if result.get("success") and "plan" in result:
                context.plan_cache["plan"] = result.get("plan")
                logger.info(f"📋 Plan 操作完成: {action}")

            # Inject old plan summary into result (so it appears in tool_result
            # instead of the full old plan text bloating context)
            if old_plan_summary:
                result["_old_plan_summary"] = old_plan_summary

            # Inject force-execute hint into result
            if force_execute:
                result["_force_execute_hint"] = PLAN_FORCE_EXECUTE_HINT

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
