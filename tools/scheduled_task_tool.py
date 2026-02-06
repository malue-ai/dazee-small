"""
ScheduledTask Tool - 定时任务管理工具

职责：
- 创建、查看、管理用户的定时任务
- 对接后端调度系统 (UserTaskScheduler)

设计原则：
1. 纯工具接口，逻辑下沉到 CRUD 层
2. 支持多种触发方式 (once/cron/interval)
3. 动作抽象化 (发送消息/执行 Agent 任务)

使用示例：
- "每天早上 9 点提醒我开会" → create, trigger_type=cron, cron="0 9 * * *"
- "明天下午 3 点提醒我打电话" → create, trigger_type=once, run_at="..."
- "每隔 2 小时提醒我喝水" → create, trigger_type=interval, interval_seconds=7200
- "查看我的定时任务" → list
- "取消那个喝水提醒" → cancel, task_id="..."
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
    description = """定时任务管理（设置提醒、定期执行任务等）

支持的触发类型：
- once: 单次执行（指定具体时间）
- cron: Cron 表达式（如 "0 9 * * *" 表示每天 9 点）
- interval: 固定间隔（如每 3600 秒）

支持的动作类型：
- send_message: 发送提醒消息
- agent_task: 让 AI 执行任务"""

    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["create", "list", "cancel", "update"],
                "description": "操作类型",
            },
            "task_id": {
                "type": "string",
                "description": "任务 ID（更新/取消时必填）",
            },
            "title": {
                "type": "string",
                "description": "任务标题（创建时建议填写）",
            },
            "trigger_type": {
                "type": "string",
                "enum": ["once", "cron", "interval"],
                "description": "触发类型：once(单次), cron(Cron表达式), interval(间隔)",
            },
            "trigger_config": {
                "type": "object",
                "description": """触发配置，根据 trigger_type 填写：
- once: { "run_at": "2026-02-07T15:00:00" }
- cron: { "cron": "0 9 * * *" }
- interval: { "interval_seconds": 3600 }""",
                "properties": {
                    "run_at": {
                        "type": "string",
                        "description": "执行时间（ISO 格式），trigger_type=once 时使用",
                    },
                    "cron": {
                        "type": "string",
                        "description": "Cron 表达式，trigger_type=cron 时使用",
                    },
                    "interval_seconds": {
                        "type": "integer",
                        "description": "间隔秒数，trigger_type=interval 时使用",
                    },
                },
            },
            "action": {
                "type": "object",
                "description": """执行动作配置：
- 发送消息: { "type": "send_message", "content": "提醒内容" }
- Agent 任务: { "type": "agent_task", "prompt": "要执行的任务描述" }""",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["send_message", "agent_task"],
                        "description": "动作类型",
                    },
                    "content": {
                        "type": "string",
                        "description": "提醒内容（send_message 时使用）",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "任务描述（agent_task 时使用）",
                    },
                },
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
            context: 工具执行上下文
        """
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
        """创建定时任务"""
        title = params.get("title", "未命名任务")
        trigger_type = params.get("trigger_type", "once")
        trigger_config = params.get("trigger_config", {})
        action = params.get("action", {"type": "send_message", "content": "定时提醒"})

        logger.info(f"🕐 创建定时任务: user_id={user_id}, title={title}, trigger={trigger_type}")

        # 解析触发配置
        run_at = None
        cron_expr = None
        interval_seconds = None

        if trigger_type == "once":
            run_at_str = trigger_config.get("run_at")
            if run_at_str:
                try:
                    run_at = datetime.fromisoformat(run_at_str.replace("Z", "+00:00"))
                except ValueError as e:
                    return {"success": False, "error": f"时间格式错误: {e}"}
            else:
                return {"success": False, "error": "单次任务需要指定 run_at 时间"}

        elif trigger_type == "cron":
            cron_expr = trigger_config.get("cron")
            if not cron_expr:
                return {"success": False, "error": "Cron 任务需要指定 cron 表达式"}
            # 验证 cron 表达式
            try:
                from croniter import croniter

                croniter(cron_expr)
            except Exception as e:
                return {"success": False, "error": f"Cron 表达式无效: {e}"}

        elif trigger_type == "interval":
            interval_seconds = trigger_config.get("interval_seconds")
            if not interval_seconds or interval_seconds <= 0:
                return {"success": False, "error": "间隔任务需要指定正整数 interval_seconds"}

        # 创建任务
        try:
            from infra.local_store import get_workspace
            from infra.local_store.crud.scheduled_task import create_scheduled_task

            workspace = await get_workspace("xiaodazi")

            async with workspace._session_factory() as session:
                task = await create_scheduled_task(
                    session=session,
                    user_id=user_id,
                    title=title,
                    trigger_type=trigger_type,
                    action=action,
                    run_at=run_at,
                    cron_expr=cron_expr,
                    interval_seconds=interval_seconds,
                    conversation_id=conversation_id,
                )

                # 动态注册到调度器（立即生效，无需等待轮询）
                from services.user_task_scheduler import get_user_task_scheduler

                scheduler = get_user_task_scheduler()
                if scheduler.is_running():
                    await scheduler.register_task(task)

                # 格式化下次执行时间
                next_run_str = (
                    task.next_run_at.strftime("%Y-%m-%d %H:%M:%S")
                    if task.next_run_at
                    else "未知"
                )

                return {
                    "success": True,
                    "task_id": task.id,
                    "message": f"✅ 定时任务已创建: {title}",
                    "next_run_at": next_run_str,
                    "trigger_type": trigger_type,
                    "trigger_config": trigger_config,
                }

        except Exception as e:
            logger.error(f"❌ 创建定时任务失败: {e}", exc_info=True)
            return {"success": False, "error": f"创建任务失败: {str(e)}"}

    async def _list_tasks(self, user_id: str) -> Dict[str, Any]:
        """查看用户的定时任务"""
        logger.info(f"📋 查看定时任务: user_id={user_id}")

        try:
            from infra.local_store import get_workspace
            from infra.local_store.crud.scheduled_task import list_user_tasks

            workspace = await get_workspace("xiaodazi")

            async with workspace._session_factory() as session:
                tasks = await list_user_tasks(session, user_id, status="active")

                task_list = []
                for task in tasks:
                    # 构建触发描述
                    if task.trigger_type == "once" and task.run_at:
                        trigger_desc = f"单次: {task.run_at.strftime('%Y-%m-%d %H:%M')}"
                    elif task.trigger_type == "cron" and task.cron_expr:
                        trigger_desc = f"Cron: {task.cron_expr}"
                    elif task.trigger_type == "interval" and task.interval_seconds:
                        trigger_desc = f"间隔: 每 {task.interval_seconds} 秒"
                    else:
                        trigger_desc = task.trigger_type

                    task_list.append(
                        {
                            "id": task.id,
                            "title": task.title,
                            "trigger": trigger_desc,
                            "next_run": (
                                task.next_run_at.strftime("%Y-%m-%d %H:%M:%S")
                                if task.next_run_at
                                else None
                            ),
                            "status": task.status,
                            "run_count": task.run_count,
                            "action_type": task.action.get("type", "send_message"),
                        }
                    )

                return {
                    "success": True,
                    "tasks": task_list,
                    "count": len(task_list),
                    "message": f"共 {len(task_list)} 个活跃任务",
                }

        except Exception as e:
            logger.error(f"❌ 查询定时任务失败: {e}", exc_info=True)
            return {"success": False, "error": f"查询任务失败: {str(e)}"}

    async def _cancel_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        """取消定时任务"""
        if not task_id:
            return {"success": False, "error": "缺少 task_id"}

        logger.info(f"🛑 取消定时任务: task_id={task_id}, user_id={user_id}")

        try:
            from infra.local_store import get_workspace
            from infra.local_store.crud.scheduled_task import cancel_task, get_scheduled_task

            workspace = await get_workspace("xiaodazi")

            async with workspace._session_factory() as session:
                # 先获取任务信息
                task = await get_scheduled_task(session, task_id)
                if not task:
                    return {"success": False, "error": f"任务不存在: {task_id}"}

                task_title = task.title

                # 取消任务
                success = await cancel_task(session, task_id, user_id)

                if success:
                    # 从调度器移除（立即停止调度）
                    from services.user_task_scheduler import get_user_task_scheduler

                    scheduler = get_user_task_scheduler()
                    if scheduler.is_running():
                        await scheduler.unregister_task(task_id)

                    return {
                        "success": True,
                        "message": f"✅ 任务已取消: {task_title}",
                        "task_id": task_id,
                    }
                else:
                    return {"success": False, "error": "取消任务失败（可能无权限）"}

        except Exception as e:
            logger.error(f"❌ 取消定时任务失败: {e}", exc_info=True)
            return {"success": False, "error": f"取消任务失败: {str(e)}"}

    async def _update_task(self, params: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """更新定时任务"""
        task_id = params.get("task_id")
        if not task_id:
            return {"success": False, "error": "缺少 task_id"}

        logger.info(f"🔄 更新定时任务: task_id={task_id}, user_id={user_id}")

        try:
            from infra.local_store import get_workspace
            from infra.local_store.crud.scheduled_task import get_scheduled_task, update_task

            workspace = await get_workspace("xiaodazi")

            async with workspace._session_factory() as session:
                # 先获取任务信息
                task = await get_scheduled_task(session, task_id)
                if not task:
                    return {"success": False, "error": f"任务不存在: {task_id}"}

                # 权限校验
                if task.user_id != user_id:
                    return {"success": False, "error": "无权更新此任务"}

                # 解析更新参数
                update_kwargs = {}

                if "title" in params:
                    update_kwargs["title"] = params["title"]

                if "trigger_type" in params:
                    update_kwargs["trigger_type"] = params["trigger_type"]

                trigger_config = params.get("trigger_config", {})
                if "run_at" in trigger_config:
                    try:
                        update_kwargs["run_at"] = datetime.fromisoformat(
                            trigger_config["run_at"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
                if "cron" in trigger_config:
                    update_kwargs["cron_expr"] = trigger_config["cron"]
                if "interval_seconds" in trigger_config:
                    update_kwargs["interval_seconds"] = trigger_config["interval_seconds"]

                if "action" in params:
                    update_kwargs["action"] = params["action"]

                # 更新任务
                updated_task = await update_task(session, task_id, **update_kwargs)

                if updated_task:
                    return {
                        "success": True,
                        "message": f"✅ 任务已更新: {updated_task.title}",
                        "task_id": task_id,
                        "next_run_at": (
                            updated_task.next_run_at.strftime("%Y-%m-%d %H:%M:%S")
                            if updated_task.next_run_at
                            else None
                        ),
                    }
                else:
                    return {"success": False, "error": "更新任务失败"}

        except Exception as e:
            logger.error(f"❌ 更新定时任务失败: {e}", exc_info=True)
            return {"success": False, "error": f"更新任务失败: {str(e)}"}
