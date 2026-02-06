"""
ScheduledTask Tool - 定时任务管理工具

职责：
- 创建、查看、管理用户的定时任务
- 对接后端调度系统 (apscheduler)

设计原则：
1. 纯工具接口，逻辑下沉到 Service 层
2. 支持多种触发方式 (cron/date/interval)
3. 动作抽象化 (发送消息/执行 Agent 任务)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class ScheduledTaskTool(BaseTool):
    """
    定时任务管理工具

    支持操作：
    - create: 创建任务
    - list: 查看任务列表
    - cancel: 取消任务
    - update: 更新任务
    """

    name = "scheduled_task"
    description = "定时任务管理（设置提醒、定期执行任务等）"

    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["create", "list", "cancel", "update"],
                "description": "操作类型",
            },
            "task_id": {"type": "string", "description": "任务 ID（更新/取消时必填）"},
            "title": {"type": "string", "description": "任务标题（创建时建议填写）"},
            "trigger_type": {
                "type": "string",
                "enum": ["once", "cron", "interval"],
                "description": "触发类型：once(单次), cron(Cron表达式), interval(间隔)",
            },
            "trigger_config": {
                "type": "object",
                "description": "触发配置，例如 { 'run_at': '...' } 或 { 'cron': '0 9 * * *' }",
            },
            "action": {
                "type": "object",
                "description": "执行动作配置，例如 { 'type': 'send_message', 'content': '...' }",
            },
        },
        "required": ["operation"],
    }

    def __init__(self):
        """初始化工具"""
        pass

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行工具

        Args:
            params: 工具输入参数
                - operation: 操作类型（create/list/cancel/update）
                - task_id: 任务 ID
                - title: 任务标题
                - trigger_type: 触发类型
                - trigger_config: 触发配置
                - action: 执行动作
            context: 工具执行上下文
        """
        # 🔧 FIX: 从 context 获取请求级参数，不存储在实例属性中
        user_id = context.user_id
        conversation_id = context.conversation_id

        operation = params.get("operation")

        if operation == "create":
            return await self._create_task(params, user_id, conversation_id)
        elif operation == "list":
            return await self._list_tasks(user_id)
        elif operation == "cancel":
            return await self._cancel_task(params.get("task_id"), user_id)
        elif operation == "update":
            return await self._update_task(params, user_id)
        else:
            return {"success": False, "error": f"未知操作: {operation}"}

    async def _create_task(
        self, params: Dict[str, Any], user_id: str, conversation_id: str
    ) -> Dict[str, Any]:
        """
        创建定时任务

        TODO:
        - 保存到数据库
        - 注册到用户任务调度器
        - 计算 next_run_at
        """
        title = params.get("title", "未命名任务")
        trigger_type = params.get("trigger_type", "once")
        trigger_config = params.get("trigger_config", {})
        action = params.get("action", {"type": "send_message", "content": "定时提醒"})

        logger.info(f"🕐 创建定时任务: user_id={user_id}, title={title}, trigger={trigger_type}")

        # TODO: 实际实现
        # 1. 验证参数
        # 2. 保存到数据库
        # 3. 计算 next_run_at
        # 4. 注册到调度器

        # 占位返回
        task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        return {
            "success": True,
            "task_id": task_id,
            "message": f"定时任务已创建: {title}",
            "next_run_at": "2026-01-12T09:00:00+08:00",  # 占位
            "note": "⚠️ 当前为占位实现，任务不会实际执行",
        }

    async def _list_tasks(self, user_id: str) -> Dict[str, Any]:
        """
        查看用户的定时任务

        TODO: 从数据库查询
        """
        logger.info(f"📋 查看定时任务: user_id={user_id}")

        # TODO: 实际实现

        return {
            "success": True,
            "tasks": [
                {
                    "id": "task_demo_1",
                    "title": "示例：每日早报",
                    "trigger": "cron: 0 9 * * *",
                    "next_run": "2026-01-12T09:00:00+08:00",
                    "status": "active",
                }
            ],
            "count": 1,
        }

    async def _cancel_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        """取消定时任务"""
        if not task_id:
            return {"success": False, "error": "缺少 task_id"}

        logger.info(f"🛑 取消定时任务: task_id={task_id}, user_id={user_id}")

        # TODO: 实际实现

        return {"success": True, "message": f"任务 {task_id} 已取消"}

    async def _update_task(self, params: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """更新定时任务"""
        task_id = params.get("task_id")
        if not task_id:
            return {"success": False, "error": "缺少 task_id"}

        logger.info(f"🔄 更新定时任务: task_id={task_id}, user_id={user_id}")

        # TODO: 实际实现

        return {"success": True, "message": f"任务 {task_id} 已更新"}
