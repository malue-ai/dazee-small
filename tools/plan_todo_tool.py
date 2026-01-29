"""
Plan/Todo Tool - 任务规划工具（纯存储版本）

设计原则：
1. 纯 CRUD 工具：只负责存储和管理，不调用 LLM
2. 主模型生成：plan 内容由调用本工具的主模型直接生成
3. 数据库驱动：Plan 存储在 Conversation.metadata.plan

存储位置：
- Conversation.metadata.plan（JSONB）

Plan 数据结构：
{
    "name": "计划名称",
    "overview": "一句话概述",
    "detailed_plan": "详细 Markdown 文档（问题分析、流程图、方案等）",
    "todos": [
        {"id": "1", "content": "步骤描述", "status": "pending", "result": "完成结果"},
        ...
    ],
    "created_at": "2026-01-28T10:00:00"
}

使用方式：
- 主模型分析用户任务，生成完整的 plan 数据
- 调用 plan_todo(operation="create", data={...plan数据...}) 存储
- 执行过程中调用 update_todo 更新状态
"""

from datetime import datetime
from typing import Any, Dict, Optional, List

from core.tool.base import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class PlanTodoTool(BaseTool):
    """
    任务规划工具（纯存储版本）
    
    设计原则：
    - 纯 CRUD 工具，不调用 LLM
    - plan 内容由主模型直接生成并传入
    - 本工具只负责存储、查询、更新
    
    支持操作：
    - create: 创建计划（直接保存主模型生成的完整 plan 数据）
    - update_todo: 更新单个 todo 的状态
    - get: 获取当前计划
    - add_todo: 动态添加新 todo
    """
    
    name = "plan_todo"
    
    def __init__(self):
        """初始化工具"""
        self._conversation_service = None
    
    async def _get_conversation_service(self):
        """延迟加载 ConversationService"""
        if self._conversation_service is None:
            from services.conversation_service import ConversationService
            self._conversation_service = ConversationService()
        return self._conversation_service
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行计划操作
        
        Args:
            params: 操作参数
                - operation: 操作类型 (create/update_todo/get/add_todo)
                - data: 操作数据
            context: 工具上下文（包含 conversation_id）
        
        Returns:
            操作结果
        """
        operation = params.get("operation", "get")
        data = params.get("data", {})
        
        logger.info(f"📋 Plan 操作: {operation}, conversation_id={context.conversation_id}")
        
        if operation == "create":
            return await self._create(data, context)
        elif operation == "update_todo":
            return await self._update_todo(data, context)
        elif operation == "get":
            return await self._get(context)
        elif operation == "add_todo":
            return await self._add_todo(data, context)
        else:
            return {"success": False, "error": f"未知操作: {operation}"}
    
    async def _create(self, data: Dict, context: ToolContext) -> Dict[str, Any]:
        """
        创建计划（直接存储主模型生成的 plan 数据）
        
        Args:
            data: 计划数据，支持两种形式：
                1) 直接传 plan 字段（name/overview/detailed_plan/todos）
                2) 传入 { "plan": { ... } }
        
        Returns:
            {"success": True, "plan": plan} 或 {"success": False, "error": "..."}
        """
        if data is None:
            return {"success": False, "error": "缺少计划数据 (plan)"}
        
        plan_data = data.get("plan") if isinstance(data, dict) and "plan" in data else data
        if not isinstance(plan_data, dict):
            return {"success": False, "error": "计划数据格式不正确 (plan 需为对象)"}
        
        # 校验必需字段
        name = plan_data.get("name")
        todos = plan_data.get("todos", [])
        
        if not name:
            return {"success": False, "error": "缺少计划名称 (name)"}
        if not isinstance(todos, list) or len(todos) == 0:
            return {"success": False, "error": "缺少步骤列表 (todos)"}
        
        try:
            # 构建 plan 数据（保留扩展字段）
            plan = dict(plan_data)
            plan.setdefault("overview", "")
            plan.setdefault("detailed_plan", "")
            plan.setdefault("created_at", datetime.now().isoformat())
            plan["todos"] = []
            
            # 处理 todos，确保每个 todo 有正确的结构
            for i, todo in enumerate(todos):
                if isinstance(todo, dict):
                    todo_data = todo
                else:
                    todo_data = {"content": str(todo)}
                
                processed_todo = {
                    "id": str(todo_data.get("id", str(i + 1))),
                    "content": todo_data.get("content", ""),
                    "status": todo_data.get("status", "pending")
                }
                if todo_data.get("result"):
                    processed_todo["result"] = todo_data["result"]
                plan["todos"].append(processed_todo)
            
            # 存储到数据库
            await self._save_plan(plan, context.conversation_id)
            
            logger.info(f"✅ 计划已创建: {plan.get('name')}, 共 {len(plan['todos'])} 个步骤")
            return {"success": True, "plan": plan}
            
        except Exception as e:
            logger.error(f"❌ 创建计划失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    
    async def _update_todo(self, data: Dict, context: ToolContext) -> Dict[str, Any]:
        """
        更新 todo 状态
        
        Args:
            data:
                - id: todo ID (如 "1")
                - status: 新状态 (pending/in_progress/completed)
                - result: 可选，完成结果说明
        """
        plan = await self._load_plan(context.conversation_id)
        if not plan:
            return {"success": False, "error": "计划不存在"}
        
        todo_id = data.get("id")
        new_status = data.get("status")
        result = data.get("result")
        
        # 查找并更新 todo
        updated = False
        for todo in plan.get("todos", []):
            if todo["id"] == todo_id:
                todo["status"] = new_status
                if result:
                    todo["result"] = result
                updated = True
                logger.info(f"📝 Todo 更新: {todo_id} -> {new_status}")
                break
        
        if not updated:
            return {"success": False, "error": f"未找到 todo: {todo_id}"}
        
        # 检查是否全部完成
        all_completed = all(t["status"] == "completed" for t in plan.get("todos", []))
        
        if all_completed:
            # 标记计划已完成（但不删除）
            plan["completed_at"] = datetime.now().isoformat()
            await self._save_plan(plan, context.conversation_id)
            logger.info(f"🎉 所有任务完成")
            return {"success": True, "completed": True, "message": "所有任务完成", "plan": plan}
        else:
            await self._save_plan(plan, context.conversation_id)
            return {"success": True, "plan": plan}
    
    async def _get(self, context: ToolContext) -> Dict[str, Any]:
        """获取当前计划"""
        plan = await self._load_plan(context.conversation_id)
        if not plan:
            return {"success": True, "plan": None, "message": "当前没有活动计划"}
        
        # 计算进度
        todos = plan.get("todos", [])
        total = len(todos)
        completed = sum(1 for t in todos if t.get("status") == "completed")
        progress = completed / total if total > 0 else 0
        
        return {
            "success": True,
            "plan": plan,
            "progress": {
                "total": total,
                "completed": completed,
                "percentage": round(progress * 100, 1)
            }
        }
    
    async def _add_todo(self, data: Dict, context: ToolContext) -> Dict[str, Any]:
        """
        动态添加新 todo
        
        Args:
            data:
                - content: todo 内容
                - after: 可选，插入到哪个 todo 之后 (id)
        """
        plan = await self._load_plan(context.conversation_id)
        if not plan:
            return {"success": False, "error": "计划不存在，请先创建计划"}
        
        content = data.get("content")
        if not content:
            return {"success": False, "error": "缺少 todo 内容"}
        
        # 生成新 ID
        todos = plan.get("todos", [])
        existing_ids = [t["id"] for t in todos]
        new_id = str(len(existing_ids) + 1)
        
        new_todo = {"id": new_id, "content": content, "status": "pending"}
        
        # 确定插入位置
        after_id = data.get("after")
        if after_id:
            for i, todo in enumerate(todos):
                if todo["id"] == after_id:
                    todos.insert(i + 1, new_todo)
                    break
            else:
                todos.append(new_todo)
        else:
            todos.append(new_todo)
        
        plan["todos"] = todos
        await self._save_plan(plan, context.conversation_id)
        
        logger.info(f"➕ 添加新 todo: {new_id} - {content}")
        return {"success": True, "plan": plan, "added_todo": new_todo}
    
    async def _load_plan(self, conversation_id: str) -> Optional[Dict]:
        """从数据库加载计划"""
        if not conversation_id:
            return None
        
        try:
            service = await self._get_conversation_service()
            conversation = await service.get_conversation(conversation_id)
            if conversation and conversation.metadata:
                return conversation.metadata.get("plan")
        except Exception as e:
            logger.error(f"加载计划失败: {e}", exc_info=True)
        
        return None
    
    async def _save_plan(self, plan: Dict, conversation_id: str) -> None:
        """将计划保存到数据库"""
        if not conversation_id:
            logger.warning("⚠️ 无法保存计划：缺少 conversation_id")
            return
        
        try:
            service = await self._get_conversation_service()
            
            # 获取现有 metadata
            conversation = await service.get_conversation(conversation_id)
            existing_metadata = conversation.metadata if conversation else {}
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}
            
            # 更新 plan 字段
            existing_metadata["plan"] = plan
            
            # 保存
            await service.update_conversation(
                conversation_id=conversation_id,
                metadata=existing_metadata
            )
            
            logger.debug(f"💾 计划已保存到数据库: {conversation_id}")
        except Exception as e:
            logger.error(f"保存计划失败: {e}", exc_info=True)
            raise


# ===== 辅助函数 =====

async def load_plan_for_session(conversation_id: str) -> Optional[Dict]:
    """
    会话开始时加载现有计划
    
    Args:
        conversation_id: 对话 ID
        
    Returns:
        计划数据，如果不存在则返回 None
    """
    if not conversation_id:
        return None
    
    try:
        from services.conversation_service import ConversationService
        service = ConversationService()
        conversation = await service.get_conversation(conversation_id)
        if conversation and conversation.metadata:
            plan = conversation.metadata.get("plan")
            if plan:
                logger.info(f"📋 已加载现有计划: {plan.get('name', 'Unknown')}, conversation_id={conversation_id}")
                return plan
    except Exception as e:
        logger.error(f"加载计划失败: {e}", exc_info=True)
    
    return None


def format_plan_for_prompt(plan: Dict) -> str:
    """
    将计划格式化为可注入 prompt 的文本
    
    Args:
        plan: 计划数据
        
    Returns:
        格式化的文本
    """
    if not plan:
        return ""
    
    todos = plan.get("todos", [])
    total = len(todos)
    completed = sum(1 for t in todos if t.get("status") == "completed")
    in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
    
    # 构建进度文本
    progress_lines = []
    for t in todos:
        status_icon = "✅" if t["status"] == "completed" else ("🔄" if t["status"] == "in_progress" else "⏳")
        result_text = f" - {t['result']}" if t.get("result") else ""
        progress_lines.append(f"  {status_icon} {t['content']}{result_text}")
    
    return f"""
## 当前任务计划

**目标**: {plan.get('name', '任务计划')}
**进度**: {completed}/{total} 完成, {in_progress} 进行中

**步骤**:
{chr(10).join(progress_lines)}

请继续执行未完成的步骤。完成一个步骤后，使用 plan_todo 工具更新状态。
"""


# 工厂函数
def create_plan_todo_tool(**kwargs) -> PlanTodoTool:
    """创建 PlanTodoTool 实例"""
    return PlanTodoTool()
