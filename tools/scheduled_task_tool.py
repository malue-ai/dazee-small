"""
定时任务工具 - Scheduled Task Tool

让 AI 可以为用户创建、查询、删除定时任务

场景示例：
- 用户："每天早上 9 点提醒我查看销售数据"
- AI 调用 scheduled_task 工具创建定时任务
- 到时间后，系统触发任务，AI 主动给用户发消息

设计：
- 任务存储在数据库（用户级）
- 任务触发时，通过 Webhook 或 SSE 推送给前端
- AI 可以创建、查询、取消任务

TODO: 完整实现
- [ ] 数据库模型 (infra/database/models.py)
- [ ] CRUD 操作 (infra/database/crud.py)
- [ ] 用户任务调度器 (与系统调度器分离)
- [ ] Webhook/SSE 推送
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from logger import get_logger
from core.tool.base import BaseTool, ToolContext

logger = get_logger("tools.scheduled_task")


# ==================== 数据模型（占位） ====================

class TaskTriggerType(str, Enum):
    """任务触发类型"""
    ONCE = "once"           # 一次性（指定时间执行）
    DAILY = "daily"         # 每天（指定时间）
    WEEKLY = "weekly"       # 每周（指定星期和时间）
    CRON = "cron"           # Cron 表达式（高级用户）


class UserScheduledTask:
    """
    用户定时任务模型（占位）
    
    TODO: 迁移到 infra/database/models.py
    """
    def __init__(
        self,
        task_id: str,
        user_id: str,
        title: str,
        description: str,
        trigger_type: TaskTriggerType,
        trigger_config: Dict[str, Any],  # 如 {"time": "09:00", "timezone": "Asia/Shanghai"}
        action: Dict[str, Any],          # 如 {"type": "send_message", "content": "该查看销售数据了"}
        created_at: datetime = None,
        next_run_at: datetime = None,
        is_active: bool = True,
        created_by_ai: bool = False,     # 是否由 AI 创建
        conversation_id: Optional[str] = None,  # 关联的对话（用于 AI 回复）
    ):
        self.task_id = task_id
        self.user_id = user_id
        self.title = title
        self.description = description
        self.trigger_type = trigger_type
        self.trigger_config = trigger_config
        self.action = action
        self.created_at = created_at or datetime.now()
        self.next_run_at = next_run_at
        self.is_active = is_active
        self.created_by_ai = created_by_ai
        self.conversation_id = conversation_id


# ==================== 工具实现 ====================

class ScheduledTaskTool(BaseTool):
    """
    定时任务工具（input_schema 由 capabilities.yaml 定义）
    
    让 AI 可以为用户管理定时任务。
    """
    
    name = "scheduled_task"
    
    def __init__(self, user_id: str = None, conversation_id: str = None):
        self.user_id = user_id
        self.conversation_id = conversation_id
    
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
        # 从 context 获取用户信息（如果 __init__ 没有设置）
        if not self.user_id:
            self.user_id = context.user_id
        if not self.conversation_id:
            self.conversation_id = context.conversation_id
        
        operation = params.get("operation")
        
        if operation == "create":
            return await self._create_task(params)
        elif operation == "list":
            return await self._list_tasks()
        elif operation == "cancel":
            return await self._cancel_task(params.get("task_id"))
        elif operation == "update":
            return await self._update_task(params)
        else:
            return {"success": False, "error": f"未知操作: {operation}"}
    
    async def _create_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
        
        logger.info(f"🕐 创建定时任务: user_id={self.user_id}, title={title}, trigger={trigger_type}")
        
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
            "note": "⚠️ 当前为占位实现，任务不会实际执行"
        }
    
    async def _list_tasks(self) -> Dict[str, Any]:
        """
        查看用户的定时任务
        
        TODO: 从数据库查询
        """
        logger.info(f"📋 查看定时任务: user_id={self.user_id}")
        
        # TODO: 实际实现
        # 从数据库查询用户的所有活跃任务
        
        # 占位返回
        return {
            "success": True,
            "tasks": [],
            "total": 0,
            "message": "暂无定时任务",
            "note": "⚠️ 当前为占位实现"
        }
    
    async def _cancel_task(self, task_id: str) -> Dict[str, Any]:
        """
        取消定时任务
        
        TODO:
        - 从数据库软删除
        - 从调度器移除
        """
        if not task_id:
            return {"success": False, "error": "缺少 task_id"}
        
        logger.info(f"❌ 取消定时任务: user_id={self.user_id}, task_id={task_id}")
        
        # TODO: 实际实现
        
        return {
            "success": True,
            "task_id": task_id,
            "message": f"定时任务已取消: {task_id}",
            "note": "⚠️ 当前为占位实现"
        }
    
    async def _update_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新定时任务
        
        TODO:
        - 更新数据库
        - 重新计算 next_run_at
        - 更新调度器
        """
        task_id = params.get("task_id")
        if not task_id:
            return {"success": False, "error": "缺少 task_id"}
        
        logger.info(f"✏️ 更新定时任务: user_id={self.user_id}, task_id={task_id}")
        
        # TODO: 实际实现
        
        return {
            "success": True,
            "task_id": task_id,
            "message": f"定时任务已更新: {task_id}",
            "note": "⚠️ 当前为占位实现"
        }


# ==================== 用户任务调度器（占位） ====================

class UserTaskScheduler:
    """
    用户任务调度器（占位）
    
    与系统级调度器分离，专门处理用户创建的定时任务
    
    TODO: 完整实现
    - [ ] 从数据库加载所有活跃的用户任务
    - [ ] 注册到 APScheduler
    - [ ] 任务触发时执行 action
    - [ ] 支持动态添加/移除任务
    """
    
    def __init__(self):
        self._scheduler = None
        self._running = False
    
    async def start(self):
        """
        启动用户任务调度器
        
        TODO:
        1. 从数据库加载所有用户的活跃任务
        2. 注册到 APScheduler
        3. 启动调度器
        """
        logger.info("🕐 用户任务调度器启动（占位实现）")
        # TODO: 实际实现
        pass
    
    async def shutdown(self):
        """关闭调度器"""
        logger.info("🛑 用户任务调度器关闭（占位实现）")
        pass
    
    async def add_task(self, task: UserScheduledTask):
        """
        添加用户任务
        
        TODO: 
        - 根据 trigger_type 和 trigger_config 创建触发器
        - 注册到调度器
        """
        pass
    
    async def remove_task(self, task_id: str):
        """移除用户任务"""
        pass
    
    async def execute_task(self, task: UserScheduledTask):
        """
        执行用户任务
        
        TODO:
        - 根据 action.type 执行不同操作
        - send_message: 通过 Webhook/SSE 推送消息给用户
        - run_agent: 触发 AI 对话
        - call_api: 调用外部 API
        """
        action_type = task.action.get("type", "send_message")
        
        if action_type == "send_message":
            # 推送消息给用户
            # TODO: 通过 WebSocket/SSE/Webhook 推送
            logger.info(f"📤 推送定时消息: user_id={task.user_id}, content={task.action.get('content')}")
        
        elif action_type == "run_agent":
            # 触发 AI 对话
            # TODO: 创建新会话，AI 主动发起对话
            logger.info(f"🤖 触发 AI 对话: user_id={task.user_id}")
        
        else:
            logger.warning(f"⚠️ 未知的 action type: {action_type}")


# ==================== 便捷函数 ====================

def create_scheduled_task_tool(user_id: str, conversation_id: str = None) -> ScheduledTaskTool:
    """创建定时任务工具实例"""
    return ScheduledTaskTool(user_id=user_id, conversation_id=conversation_id)


_user_scheduler: Optional[UserTaskScheduler] = None


def get_user_task_scheduler() -> UserTaskScheduler:
    """获取用户任务调度器单例"""
    global _user_scheduler
    if _user_scheduler is None:
        _user_scheduler = UserTaskScheduler()
    return _user_scheduler

