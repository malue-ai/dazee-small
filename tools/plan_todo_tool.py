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
            "title": "步骤标题（注入 prompt 用）",
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

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        action = params.get("action")

        # 检查 conversation_id（框架注入）
        if not context.conversation_id:
            return {"success": False, "error": "缺少 conversation_id，无法存储计划"}

        if action == "create":
            return await self._create(params, context)
        elif action == "update":
            return await self._update(params, context)
        elif action == "rewrite":
            return await self._rewrite(params, context)
        else:
            return {"success": False, "error": f"未知操作: {action}"}

    async def _create(self, params: Dict, context: ToolContext) -> Dict[str, Any]:
        """创建新计划"""
        name = params.get("name")
        todos = params.get("todos", [])
        overview = params.get("overview")
        plan_doc = params.get("plan")
        required_skills = params.get("required_skills")

        if not name:
            return {"success": False, "error": "缺少 name"}
        if not todos:
            return {"success": False, "error": "缺少 todos"}

        # 检查是否已有计划
        existing = await self._load(context.conversation_id)
        if existing:
            return {"success": False, "error": "计划已存在，如需替换请使用 rewrite"}

        plan = self._build_plan(name, todos, overview, plan_doc, required_skills)
        plan["created_at"] = datetime.now().isoformat()

        await self._save(plan, context.conversation_id)
        logger.info(
            f"✅ 计划已创建: {name}, 共 {len(plan['todos'])} 个步骤"
            + (f", required_skills={required_skills}" if required_skills else "")
        )

        return {"success": True, "plan": plan}

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

        return {"success": True, "plan": plan, "all_completed": all_done}

    async def _rewrite(self, params: Dict, context: ToolContext) -> Dict[str, Any]:
        """重写整个计划"""
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

        plan = self._build_plan(name, todos, overview, plan_doc, required_skills)
        plan["created_at"] = existing.get("created_at") if existing else datetime.now().isoformat()
        plan["updated_at"] = datetime.now().isoformat()

        await self._save(plan, context.conversation_id)
        logger.info(f"✅ 计划已重写: {name}, 共 {len(plan['todos'])} 个步骤")

        return {"success": True, "plan": plan}

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
            required_skills: 此计划所需的 Skills 名称列表（可选，驱动后续轮次 Skills 注入）

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
    将计划格式化为 prompt 文本

    注入策略（存得细，注入精简）：
    - 注入：name, overview, todos[].title
    - 不注入：plan（详细文档太长）, todos[].content（详细描述太长）
    """
    if not plan:
        return ""

    todos = plan.get("todos", [])
    total = len(todos)
    completed = sum(1 for t in todos if t.get("status") == "completed")
    in_progress = sum(1 for t in todos if t.get("status") == "in_progress")

    lines = []
    for t in todos:
        status = t.get("status", "pending")
        if status == "completed":
            icon = "✅"
            suffix = " - 已完成"
        elif status == "in_progress":
            icon = "🔄"
            suffix = ""
        elif status == "failed":
            icon = "❌"
            suffix = " - 失败"
        else:
            icon = "⏳"
            suffix = ""

        # 使用 title 而不是 content
        title = t.get("title", "")
        result_text = f" ({t['result']})" if t.get("result") else ""
        lines.append(f"  {icon} {t['id']}. {title}{suffix}{result_text}")

    # 构建输出
    output_lines = ["## 当前任务计划", ""]
    output_lines.append(f"**目标**: {plan.get('name')}")

    # 如果有 overview，展示它
    overview = plan.get("overview")
    if overview:
        output_lines.append(f"**概要**: {overview}")

    output_lines.append(f"**进度**: {completed}/{total} 完成, {in_progress} 进行中")
    output_lines.append("")
    output_lines.append("**步骤**:")
    output_lines.extend(lines)
    output_lines.append("")
    output_lines.append("请继续执行未完成的步骤。完成后使用 plan 工具更新状态。")

    return "\n".join(output_lines)


# 工厂函数
def create_plan_tool(progress_transformer=None, **kwargs) -> PlanTool:
    return PlanTool(progress_transformer=progress_transformer)


# ===== 别名（保持导入兼容）=====
PlanTodoTool = PlanTool
create_plan_todo_tool = create_plan_tool
