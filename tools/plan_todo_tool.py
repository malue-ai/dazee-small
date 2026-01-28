"""
Plan/Todo Tool - 任务规划工具（Cursor 风格）

设计原则：
1. 文件驱动：本地 Markdown 文件是唯一状态源
2. 简单 CRUD：工具只做读写，不调用 LLM
3. 自动清理：所有 todos 完成后自动删除文件
4. 格式：YAML front matter + Markdown body

文件格式示例：
```markdown
---
name: 制作 AI PPT
overview: 为用户生成一份 AI 技术分享 PPT
todos:
  - id: step-0
    content: 搜索 AI 相关资料
    status: completed
    result: 找到 5 篇文章
  - id: step-1
    content: 整理内容大纲
    status: in_progress
  - id: step-2
    content: 生成 PPT 文件
    status: pending
created_at: 2026-01-27T10:00:00
---

# 制作 AI PPT

## 目标
为用户生成一份 AI 技术分享 PPT

## 进度
- [x] 搜索 AI 相关资料（找到 5 篇文章）
- [ ] 整理内容大纲
- [ ] 生成 PPT 文件
```
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles
import yaml

from core.tool.base import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)

# 计划文件存储目录
PLANS_DIR = Path("workspace/plans")


class PlanTodoTool(BaseTool):
    """
    Cursor 风格的任务规划工具
    
    支持操作：
    - create: 创建计划文件
    - update_todo: 更新单个 todo 的状态
    - get: 读取当前计划
    - add_todo: 动态添加新 todo
    """
    
    name = "plan_todo"
    
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
    
    def _get_plan_path(self, context: ToolContext) -> Path:
        """获取计划文件路径"""
        return PLANS_DIR / f"{context.conversation_id}.plan.md"
    
    async def _create(self, data: Dict, context: ToolContext) -> Dict[str, Any]:
        """
        创建计划文件
        
        Args:
            data:
                - name: 计划名称
                - overview: 计划概述
                - steps: 步骤列表 [{"content": "步骤描述"}, ...]
        """
        name = data.get("name", "任务计划")
        overview = data.get("overview", "")
        steps = data.get("steps", [])
        
        # 构建 plan 结构
        plan = {
            "name": name,
            "overview": overview,
            "todos": [
                {"id": f"step-{i}", "content": step.get("content", step) if isinstance(step, dict) else step, "status": "pending"}
                for i, step in enumerate(steps)
            ],
            "created_at": datetime.now().isoformat()
        }
        
        # 生成 Markdown 内容
        md_content = self._generate_markdown(plan)
        
        # 写入文件
        path = self._get_plan_path(context)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(md_content)
        
        logger.info(f"✅ 计划已创建: {path}")
        return {"success": True, "plan": plan, "path": str(path)}
    
    async def _update_todo(self, data: Dict, context: ToolContext) -> Dict[str, Any]:
        """
        更新 todo 状态
        
        Args:
            data:
                - id: todo ID (如 "step-0")
                - status: 新状态 (pending/in_progress/completed)
                - result: 可选，完成结果说明
        """
        plan = await self._read_plan(context)
        if not plan:
            return {"success": False, "error": "计划不存在"}
        
        todo_id = data.get("id")
        new_status = data.get("status")
        result = data.get("result")
        
        # 查找并更新 todo
        updated = False
        for todo in plan["todos"]:
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
        all_completed = all(t["status"] == "completed" for t in plan["todos"])
        
        if all_completed:
            # 自动删除文件
            path = self._get_plan_path(context)
            if path.exists():
                path.unlink()
            logger.info(f"🎉 所有任务完成，计划已清理: {path}")
            return {"success": True, "completed": True, "message": "所有任务完成，计划已清理"}
        else:
            # 更新文件
            await self._write_plan(plan, context)
            return {"success": True, "plan": plan}
    
    async def _get(self, context: ToolContext) -> Dict[str, Any]:
        """获取当前计划"""
        plan = await self._read_plan(context)
        if not plan:
            return {"success": True, "plan": None, "message": "当前没有活动计划"}
        
        # 计算进度
        total = len(plan["todos"])
        completed = sum(1 for t in plan["todos"] if t["status"] == "completed")
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
        plan = await self._read_plan(context)
        if not plan:
            return {"success": False, "error": "计划不存在，请先创建计划"}
        
        content = data.get("content")
        if not content:
            return {"success": False, "error": "缺少 todo 内容"}
        
        # 生成新 ID
        existing_ids = [t["id"] for t in plan["todos"]]
        new_id = f"step-{len(existing_ids)}"
        
        new_todo = {"id": new_id, "content": content, "status": "pending"}
        
        # 确定插入位置
        after_id = data.get("after")
        if after_id:
            for i, todo in enumerate(plan["todos"]):
                if todo["id"] == after_id:
                    plan["todos"].insert(i + 1, new_todo)
                    break
            else:
                plan["todos"].append(new_todo)
        else:
            plan["todos"].append(new_todo)
        
        await self._write_plan(plan, context)
        logger.info(f"➕ 添加新 todo: {new_id} - {content}")
        return {"success": True, "plan": plan, "added_todo": new_todo}
    
    async def _read_plan(self, context: ToolContext) -> Optional[Dict]:
        """从文件读取计划"""
        path = self._get_plan_path(context)
        if not path.exists():
            return None
        
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        # 解析 YAML front matter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    return yaml.safe_load(parts[1])
                except yaml.YAMLError as e:
                    logger.error(f"YAML 解析失败: {e}")
                    return None
        return None
    
    async def _write_plan(self, plan: Dict, context: ToolContext) -> None:
        """将计划写入文件"""
        md_content = self._generate_markdown(plan)
        path = self._get_plan_path(context)
        
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(md_content)
    
    def _generate_markdown(self, plan: Dict) -> str:
        """生成 Markdown 文件内容"""
        # YAML front matter
        front_matter = yaml.dump(plan, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        # Markdown body - 进度列表
        todos_md = "\n".join([
            f"- [{'x' if t['status'] == 'completed' else ' '}] {t['content']}" +
            (f"（{t.get('result', '')}）" if t.get('result') else "")
            for t in plan["todos"]
        ])
        
        return f"""---
{front_matter}---

# {plan['name']}

## 目标
{plan['overview']}

## 进度
{todos_md}
"""


# ===== 辅助函数 =====

def get_plan_path(conversation_id: str) -> Path:
    """获取计划文件路径"""
    return PLANS_DIR / f"{conversation_id}.plan.md"


async def load_plan_for_session(conversation_id: str) -> Optional[Dict]:
    """
    会话开始时加载现有计划（异步版本）
    
    Args:
        conversation_id: 会话 ID
        
    Returns:
        计划数据，如果不存在则返回 None
    """
    path = get_plan_path(conversation_id)
    if not path.exists():
        return None
    
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        # 解析 YAML front matter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                plan = yaml.safe_load(parts[1])
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


# 工厂函数（兼容旧接口）
def create_plan_todo_tool(**kwargs) -> PlanTodoTool:
    """创建 PlanTodoTool 实例"""
    return PlanTodoTool()
