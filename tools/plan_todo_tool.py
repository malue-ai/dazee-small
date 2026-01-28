"""
Plan/Todo Tool - 任务规划工具（Cursor 风格）

设计原则：
1. 数据库驱动：Plan 存储在 Conversation.extra_data.plan
2. 内部 LLM 调用：create 时调用专门的 Plan Generator 生成详细计划
3. 流式返回：支持 SSE 流式推送 plan 生成过程
4. 简单 CRUD：update/get/add 只做读写，不调用 LLM

存储位置：
- Conversation.extra_data.plan（JSONB）

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
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional, AsyncGenerator, List

from core.tool.base import BaseTool, ToolContext
from core.llm.base import Message
from logger import get_logger
from prompts.plan_generator_prompt import build_plan_generator_prompt

logger = get_logger(__name__)


class PlanTodoTool(BaseTool):
    """
    Cursor 风格的任务规划工具（数据库驱动版本）
    
    支持操作：
    - create: 创建计划（内部调用 LLM 生成详细 plan）
    - update_todo: 更新单个 todo 的状态
    - get: 获取当前计划
    - add_todo: 动态添加新 todo
    """
    
    name = "plan_todo"
    
    def __init__(self):
        """初始化工具"""
        self._llm = None
        self._conversation_service = None
    
    async def _get_llm(self):
        """延迟加载 LLM 服务"""
        if self._llm is None:
            from core.llm import create_llm_service, LLMProvider
            # 使用 Haiku 模型生成 plan（成本低、速度快）
            self._llm = create_llm_service(
                provider=LLMProvider.CLAUDE,
                model="claude-3-5-haiku-latest",
                max_tokens=4096,
                enable_thinking=False  # plan 生成不需要 thinking
            )
        return self._llm
    
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
    
    async def execute_stream(
        self, 
        params: Dict[str, Any], 
        context: ToolContext
    ) -> AsyncGenerator[str, None]:
        """
        流式执行（仅 create 操作支持流式）
        
        Yields:
            流式内容块
        """
        operation = params.get("operation", "get")
        data = params.get("data", {})
        
        if operation == "create":
            async for chunk in self._create_stream(data, context):
                yield chunk
        else:
            # 其他操作不支持流式，直接返回结果
            result = await self.execute(params, context)
            yield json.dumps(result, ensure_ascii=False)
    
    async def _create(self, data: Dict, context: ToolContext) -> Dict[str, Any]:
        """
        创建计划（非流式版本）
        
        Args:
            data:
                - task: 任务描述（必需）
                - context: 额外上下文（可选）
        """
        task = data.get("task", "")
        extra_context = data.get("context", "")
        
        if not task:
            return {"success": False, "error": "缺少任务描述 (task)"}
        
        try:
            # 调用 LLM 生成详细 plan
            plan = await self._generate_plan(task, extra_context)
            
            # 存储到数据库
            await self._save_plan(plan, context.conversation_id)
            
            logger.info(f"✅ 计划已创建: {plan.get('name')}")
            return {"success": True, "plan": plan}
            
        except Exception as e:
            logger.error(f"❌ 创建计划失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def _create_stream(
        self, 
        data: Dict, 
        context: ToolContext
    ) -> AsyncGenerator[str, None]:
        """
        流式创建计划
        
        Yields:
            工具结果 JSON 字符串（与非流式返回格式一致）
        """
        task = data.get("task", "")
        extra_context = data.get("context", "")
        
        if not task:
            yield json.dumps({"success": False, "error": "缺少任务描述 (task)"}, ensure_ascii=False)
            return
        
        try:
            # 构建 prompt
            system_prompt, user_prompt = build_plan_generator_prompt(task, extra_context)
            
            # 获取 LLM
            llm = await self._get_llm()
            
            # 流式调用 LLM
            full_content = ""
            async for chunk in llm.create_message_stream(
                messages=[Message(role="user", content=user_prompt)],
                system=system_prompt
            ):
                if chunk.content:
                    full_content += chunk.content
            
            # 解析 JSON 结果
            plan = self._parse_plan_json(full_content)
            plan["created_at"] = datetime.now().isoformat()
            
            # 初始化 todos 状态
            for todo in plan.get("todos", []):
                if "status" not in todo:
                    todo["status"] = "pending"
            
            # 存储到数据库
            await self._save_plan(plan, context.conversation_id)
            
            logger.info(f"✅ 计划已创建（流式）: {plan.get('name')}")
            yield json.dumps({"success": True, "plan": plan}, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ 流式创建计划失败: {e}", exc_info=True)
            yield json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    
    async def _generate_plan(self, task: str, extra_context: str = "") -> Dict[str, Any]:
        """
        调用 LLM 生成详细计划（非流式）
        
        Args:
            task: 任务描述
            extra_context: 额外上下文
            
        Returns:
            计划数据
        """
        # 构建 prompt
        system_prompt, user_prompt = build_plan_generator_prompt(task, extra_context)
        
        # 获取 LLM
        llm = await self._get_llm()
        
        # 调用 LLM
        response = await llm.create_message_async(
            messages=[Message(role="user", content=user_prompt)],
            system=system_prompt
        )
        
        # 解析 JSON 结果
        plan = self._parse_plan_json(response.content)
        plan["created_at"] = datetime.now().isoformat()
        
        # 初始化 todos 状态
        for todo in plan.get("todos", []):
            if "status" not in todo:
                todo["status"] = "pending"
        
        return plan
    
    def _parse_plan_json(self, content: str) -> Dict[str, Any]:
        """
        解析 LLM 返回的 JSON
        
        Args:
            content: LLM 返回的内容（可能包含 markdown 代码块）
            
        Returns:
            解析后的计划数据
        """
        if not content:
            return {
                "name": "任务计划",
                "overview": "自动生成的计划",
                "detailed_plan": "",
                "todos": []
            }

        def is_plan_dict(obj: Any) -> bool:
            return (
                isinstance(obj, dict)
                and "name" in obj
                and "overview" in obj
                and "detailed_plan" in obj
                and "todos" in obj
            )

        def extract_json_objects(text: str) -> List[str]:
            # 提取所有顶层 JSON 对象（支持多段拼接输出）
            objs: List[str] = []
            depth = 0
            start = None
            in_string = False
            escape = False

            for i, ch in enumerate(text):
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == "\"":
                        in_string = False
                    continue

                if ch == "\"":
                    in_string = True
                    continue

                if ch == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == "}":
                    if depth > 0:
                        depth -= 1
                        if depth == 0 and start is not None:
                            objs.append(text[start:i + 1])
                            start = None

            return objs

        # 尝试直接解析
        try:
            parsed = json.loads(content)
            if is_plan_dict(parsed):
                return parsed
            # 如果不是完整 plan 结构，继续尝试其他方式
        except json.JSONDecodeError:
            pass
        
        # 尝试提取 JSON 代码块
        import re
        json_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', content)
        for block in json_blocks:
            try:
                parsed = json.loads(block.strip())
                if is_plan_dict(parsed):
                    return parsed
            except json.JSONDecodeError:
                pass
        
        # 尝试解析所有顶层 JSON 对象（处理重复/拼接输出）
        first_dict = None
        for obj_text in extract_json_objects(content):
            try:
                parsed = json.loads(obj_text)
                if is_plan_dict(parsed):
                    return parsed
                if isinstance(parsed, dict) and first_dict is None:
                    first_dict = parsed
            except json.JSONDecodeError:
                continue
        if first_dict:
            return first_dict
        
        # 解析失败，返回默认结构
        logger.warning(f"⚠️ Plan JSON 解析失败，使用默认结构")
        return {
            "name": "任务计划",
            "overview": "自动生成的计划",
            "detailed_plan": content,
            "todos": []
        }
    
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
