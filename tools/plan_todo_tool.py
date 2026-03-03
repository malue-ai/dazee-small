"""
Plan Tool - 任务计划管理工具 v2

设计原则：
1. 纯 CRUD 工具：只负责存储和管理，不调用 LLM
2. 主模型生成：plan 内容由调用本工具的主模型直接生成
3. 数据库驱动：Plan 存储在 Conversation.metadata.plan

存储位置：
- Conversation.metadata.plan（JSONB）

Plan 数据结构 v2：
{
    "name": "计划名称",
    "overview": "一句话目标摘要（注入 prompt 用）",
    "plan": "超详细计划文档（存储用，不注入 prompt）",
    "todos": [
        {
            "id": "1",
            "title": "步骤标题（注入 prompt 用，也用于 Step-Aware 意图分析）",
            "content": "详细描述（存储用，不注入 prompt）",
            "status": "pending",
            "result": "完成结果"
        },
        ...
    ],
    "created_at": "2026-01-28T10:00:00",
    "updated_at": "2026-01-28T11:00:00",
    "completed_at": "2026-01-28T12:00:00"
}

Skill 选择策略（双信号源重召回）：
- 信号 1: Step-Aware 意图分析 — IntentAnalyzer 每轮感知当前步骤 title，LLM 推断 skill groups
- 信号 2: Plan required_skills — 主模型创建 plan 时可选声明，跨轮持久
- 两者 union 合并，漏选代价远大于多选代价

操作：
- create: 创建新计划
- update: 更新步骤状态
- rewrite: 重写整个计划
"""

from datetime import datetime
from typing import Any, Dict, Optional

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class PlanTool(BaseTool):
    """
    任务计划管理工具 v2（V12.0: 集成 ProgressTransformer）

    action:
    - create: 创建新计划，需要 name + todos，可选 overview + plan + required_skills
    - update: 更新步骤状态，需要 todo_id + status（自动触发友好进度通知）
    - rewrite: 重写整个计划，需要 name + todos，可选 overview + plan + required_skills

    数据结构：
    - 顶层：name, overview, plan, todos, required_skills, created_at, updated_at, completed_at
    - todo：id, title, content, status, result

    进度通知（架构 3.5.4 "内部复杂，外部简单"）：
    - update 完成后自动调用 ProgressTransformer.transform_and_emit()
    - 用户看到 "正在分析..." / "快好了..." 而非技术步骤
    """

    name = "plan"

    def __init__(self, progress_transformer=None):
        self._conversation_service = None
        self._progress_transformer = progress_transformer

    async def _get_service(self):
        if self._conversation_service is None:
            from services.conversation_service import ConversationService

            self._conversation_service = ConversationService()
        return self._conversation_service

    def _ensure_progress_transformer(self, context: "ToolContext") -> None:
        """
        Lazy-init ProgressTransformer from ToolContext.event_manager.

        Design:
        - ToolExecutor instantiates PlanTool() with no args (generic tool loading)
        - First time _update is called, we build ProgressTransformer from context
        - This follows the same lazy pattern as _get_service()
        """
        if self._progress_transformer is not None:
            return  # Already initialized (externally injected or previously built)

        if not context or not context.event_manager:
            return  # No event_manager available, progress notifications disabled

        try:
            from core.events.broadcaster import EventBroadcaster
            from core.planning.progress_transformer import ProgressTransformer

            broadcaster = EventBroadcaster(context.event_manager)
            self._progress_transformer = ProgressTransformer(broadcaster=broadcaster)
            logger.debug("ProgressTransformer lazy-initialized from ToolContext.event_manager")
        except Exception as e:
            logger.warning(f"ProgressTransformer 初始化失败（进度通知不可用）: {e}")

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        action = params.get("action")

        # 检查 conversation_id（框架注入）
        if not context.conversation_id:
            return {"success": False, "error": "缺少 conversation_id，无法存储计划"}

        if action in ("create", "rewrite"):
            return await self._create(params, context)
        elif action == "update":
            return await self._update(params, context)
        else:
            return {"success": False, "error": f"未知操作: {action}"}

    async def _create(self, params: Dict, context: ToolContext) -> Dict[str, Any]:
        """
        创建计划（语义 upsert）

        行为由上游 is_follow_up 信号决定：
        - 追问(is_follow_up=true) + 已有 plan → 拒绝，引导用 update
        - 新任务(is_follow_up=false) → 无论是否有旧 plan，直接创建/覆盖
        """
        name = params.get("name")
        todos = params.get("todos", [])
        overview = params.get("overview")
        plan_doc = params.get("plan")
        required_skills = params.get("required_skills")

        if not name:
            return {"success": False, "error": "缺少 name"}
        if not todos:
            return {"success": False, "error": "缺少 todos"}

        existing = await self._load(context.conversation_id)
        is_follow_up = context.get("is_follow_up", False)

        if existing and is_follow_up:
            return {
                "success": False,
                "error": "当前是追问，已有计划仍在执行中，请用 update 更新步骤状态",
                "current_plan_name": existing.get("name"),
            }

        now = datetime.now().isoformat()
        plan = self._build_plan(name, todos, overview, plan_doc, required_skills)
        plan["created_at"] = existing.get("created_at") if existing else now
        if existing:
            plan["updated_at"] = now

        await self._save(plan, context.conversation_id)

        action_word = "重写" if existing else "创建"
        logger.info(
            f"计划已{action_word}: {name}, 共 {len(plan['todos'])} 个步骤"
            + (f", required_skills={required_skills}" if required_skills else "")
        )

        return {"success": True, "plan": plan, "replaced_old": bool(existing)}

    async def _update(self, params: Dict, context: ToolContext) -> Dict[str, Any]:
        """更新步骤状态"""
        plan = await self._load(context.conversation_id)
        if not plan:
            return {"success": False, "error": "计划不存在"}

        todo_id = params.get("todo_id")
        status = params.get("status")
        result = params.get("result")

        if not todo_id:
            return {"success": False, "error": "缺少 todo_id"}
        if not status:
            return {"success": False, "error": "缺少 status"}

        # 查找并更新
        updated = False
        for todo in plan.get("todos", []):
            if todo["id"] == todo_id:
                todo["status"] = status
                if result:
                    todo["result"] = result
                updated = True
                break

        if not updated:
            return {"success": False, "error": f"未找到步骤: {todo_id}"}

        # 检查是否全部完成
        all_done = all(t["status"] == "completed" for t in plan["todos"])
        if all_done:
            plan["completed_at"] = datetime.now().isoformat()

        # 更新 updated_at
        plan["updated_at"] = datetime.now().isoformat()

        await self._save(plan, context.conversation_id)
        logger.info(f"📝 步骤更新: {todo_id} -> {status}")

        # V12: 触发 ProgressTransformer 发送友好进度通知（架构 3.5.4）
        self._ensure_progress_transformer(context)
        if self._progress_transformer and context.session_id:
            try:
                completed_count = sum(
                    1 for t in plan["todos"] if t["status"] == "completed"
                )
                total_count = len(plan["todos"])
                updated_step = next(
                    (t for t in plan["todos"] if t["id"] == todo_id), {}
                )
                await self._progress_transformer.transform_and_emit(
                    plan_step=updated_step,
                    session_id=context.session_id,
                    completed=completed_count,
                    total=total_count,
                )
            except Exception as e:
                logger.warning(f"进度通知失败（不阻断执行）: {e}")

        # 当步骤被标记为 failed 时，注入回溯引导信息
        # 这确保模型在下一轮 thinking 中看到明确的决策提示
        response = {"success": True, "plan": plan, "all_completed": all_done}
        if status == "failed":
            failed_count = sum(1 for t in plan.get("todos", []) if t.get("status") == "failed")
            response["step_failed"] = True
            response["failed_step_id"] = todo_id
            response["total_failed_steps"] = failed_count
            response["guidance"] = (
                f"步骤 {todo_id} 已标记为失败（原因: {result or '未说明'}）。"
                f"当前计划共有 {failed_count} 个失败步骤。"
                f"请在 thinking 中决定下一步行动："
                f"(1) 用完全不同的方法重试这个步骤（plan rewrite）"
                f"(2) 跳过此步骤继续后续步骤（如果不影响最终结果）"
                f"(3) 如果核心步骤无法完成，坦诚告知用户原因和建议"
            )

        return response

    def _build_plan(
        self,
        name: str,
        todos: list,
        overview: Optional[str] = None,
        plan_doc: Optional[str] = None,
        required_skills: Optional[list] = None,
    ) -> Dict:
        """
        构建标准 plan 数据结构 v2

        Args:
            name: 计划名称
            todos: 步骤列表
            overview: 一句话目标摘要（可选）
            plan_doc: 详细计划文档（可选）
            required_skills: Skills 名称列表（可选，与 Step-Aware 意图分析
                union 合并，重召回安全网）

        Returns:
            plan 数据结构
        """
        plan = {"name": name, "todos": []}

        # 可选顶层字段
        if overview:
            plan["overview"] = overview
        if plan_doc:
            plan["plan"] = plan_doc
        if required_skills:
            plan["required_skills"] = required_skills

        # 构建 todos
        for i, todo in enumerate(todos):
            if isinstance(todo, dict):
                item = {
                    "id": str(todo.get("id", i + 1)),
                    "title": todo.get("title", ""),
                    "status": todo.get("status", "pending"),
                }
                # 可选字段
                if todo.get("content"):
                    item["content"] = todo["content"]
                if todo.get("result"):
                    item["result"] = todo["result"]
            else:
                # 字符串直接作为 title
                item = {"id": str(i + 1), "title": str(todo), "status": "pending"}
            plan["todos"].append(item)

        return plan

    async def _load(self, conversation_id: str) -> Optional[Dict]:
        """加载计划"""
        if not conversation_id:
            return None
        try:
            service = await self._get_service()
            conv = await service.get_conversation(conversation_id)
            if conv and conv.metadata:
                return conv.metadata.get("plan")
        except Exception as e:
            logger.error(f"加载计划失败: {e}", exc_info=True)
        return None

    async def _save(self, plan: Dict, conversation_id: str) -> None:
        """保存计划"""
        if not conversation_id:
            raise ValueError("conversation_id 不能为空")
        try:
            service = await self._get_service()
            conv = await service.get_conversation(conversation_id)
            metadata = conv.metadata if conv else {}
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["plan"] = plan
            await service.update_conversation(conversation_id=conversation_id, metadata=metadata)
            logger.debug(f"💾 计划已保存: conversation_id={conversation_id}")
        except Exception as e:
            logger.error(f"保存计划失败: {e}", exc_info=True)
            raise


# ===== 辅助函数 =====


async def load_plan_for_session(conversation_id: str) -> Optional[Dict]:
    """会话开始时加载现有计划"""
    if not conversation_id:
        return None
    try:
        tool = PlanTool()
        plan = await tool._load(conversation_id)
        if plan:
            logger.info(f"📋 已加载计划: {plan.get('name')}")
        return plan
    except Exception as e:
        logger.error(f"加载计划失败: {e}", exc_info=True)
    return None


def format_plan_for_prompt(plan: Dict) -> str:
    """
    将计划格式化为 prompt 文本（渐进式展示 + 安全提示）

    设计参考：
    - Claude Code Checkpointing: 每步有检查点，可回退到任意步骤
    - Interactive Speculative Planning (ICLR 2025): 渐进式披露，
      突出当前步骤和下一步，降低认知负荷
    - Cocoa Co-Planning: 用户可在执行中调整剩余步骤

    注入策略（存得细，注入精简）：
    - 注入：name, overview, todos[].title
    - 不注入：plan（详细文档太长）, todos[].content（详细描述太长）
    - 渐进式：当前步骤突出显示，已完成步骤压缩为一行摘要
    """
    if not plan:
        return ""

    todos = plan.get("todos", [])
    total = len(todos)
    completed = sum(1 for t in todos if t.get("status") == "completed")
    in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
    failed = sum(1 for t in todos if t.get("status") == "failed")

    # 渐进式展示：分为已完成 / 当前 / 未来三组
    done_lines = []
    current_lines = []
    future_lines = []

    for t in todos:
        status = t.get("status", "pending")
        title = t.get("title", "")
        result_text = f" ({t['result']})" if t.get("result") else ""

        if status == "completed":
            done_lines.append(f"  ✅ {t['id']}. {title}{result_text}")
        elif status == "in_progress":
            current_lines.append(f"  ▶ {t['id']}. {title}")
        elif status == "failed":
            # 失败步骤：完整展示失败原因，帮助模型在反思时避免重复
            current_lines.append(f"  ❌ {t['id']}. {title} - 失败{result_text}")
        else:
            future_lines.append(f"  ⏳ {t['id']}. {title}")

    # 构建输出
    output_lines = ["## 当前任务计划", ""]
    output_lines.append(f"**目标**: {plan.get('name')}")

    overview = plan.get("overview")
    if overview:
        output_lines.append(f"**概要**: {overview}")

    output_lines.append(f"**进度**: {completed}/{total} 完成")
    output_lines.append("")

    # 已完成步骤：压缩显示（渐进式披露，降低认知负荷）
    if done_lines:
        if len(done_lines) <= 3:
            output_lines.extend(done_lines)
        else:
            # 超过 3 步：折叠为摘要 + 最后一步
            output_lines.append(f"  ✅ 步骤 1-{len(done_lines)-1} 已完成")
            output_lines.append(done_lines[-1])

    # 当前步骤：突出显示
    if current_lines:
        output_lines.extend(current_lines)

    # 下一步：只显示最近 2 步（渐进式披露）
    if future_lines:
        for line in future_lines[:2]:
            output_lines.append(line)
        if len(future_lines) > 2:
            output_lines.append(f"  ... 还有 {len(future_lines) - 2} 步")

    output_lines.append("")

    # 行动指引 —— 根据失败情况给出不同深度的反思引导
    if failed > 0:
        output_lines.append("")
        output_lines.append("⚠️ 有步骤失败。请在 thinking 中回答以下问题再行动：")
        output_lines.append("  1. 失败的根本原因是什么？（不是表面报错，是深层原因）")
        output_lines.append("  2. 换一种完全不同的方法能否解决？如果能，用 plan(action='rewrite') 调整计划。")
        output_lines.append("  3. 如果当前环境/工具确实无法完成，是否应该停止并坦诚告知用户？")
        output_lines.append("  记住：重复相同的失败方法是最差的选择。换方案或停止，都比空转好。")
    elif current_lines:
        output_lines.append("请继续执行当前步骤。完成后使用 plan 工具更新状态。")
    else:
        output_lines.append("请开始执行下一步。完成后使用 plan 工具更新状态。")

    # 文件安全提示：检测 plan 是否涉及文件操作
    file_keywords = ["文件", "修改", "替换", "写入", "删除", "重命名", "移动",
                     "config", "nginx", ".md", ".json", ".yaml", ".txt"]
    all_titles = " ".join(t.get("title", "") for t in todos)
    plan_name = plan.get("name", "")
    plan_overview = plan.get("overview", "")
    check_text = f"{all_titles} {plan_name} {plan_overview}"

    if any(kw in check_text for kw in file_keywords):
        output_lines.append("📦 文件安全网已激活：修改前自动备份，出错自动恢复，不需要手动备份。")

    return "\n".join(output_lines)


# 工厂函数
def create_plan_tool(progress_transformer=None, **kwargs) -> PlanTool:
    return PlanTool(progress_transformer=progress_transformer)


# ===== 别名（保持导入兼容）=====
PlanTodoTool = PlanTool
create_plan_todo_tool = create_plan_tool
