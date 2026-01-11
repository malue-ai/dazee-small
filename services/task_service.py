"""
任务服务层 - Task Service

职责：
1. 获取已注册的后台任务列表
2. 手动触发后台任务
3. 管理定时任务配置

设计原则：
- 任务实现复用（通过 background_tasks 模块）
- 触发机制分离（事件触发 vs 定时触发 vs 手动触发）
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from logger import get_logger
from utils.background_tasks import (
    get_background_task_service,
    get_registered_task_names,
    get_task_registry,
    TaskContext,
)

logger = get_logger("task_service")


# ==================== 数据模型 ====================

class TriggerType(str, Enum):
    """任务触发类型"""
    EVENT = "event"           # 事件触发（如对话结束）
    SCHEDULED = "scheduled"   # 定时触发
    MANUAL = "manual"         # 手动触发（API 调用）


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    """任务信息"""
    name: str
    description: str = ""
    supports_scheduled: bool = False  # 是否支持定时执行
    schedule_config: Optional[Dict[str, Any]] = None  # 定时配置（如 cron 表达式）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "supports_scheduled": self.supports_scheduled,
            "schedule_config": self.schedule_config,
        }


@dataclass
class TaskRunResult:
    """任务执行结果"""
    task_name: str
    status: TaskStatus
    trigger_type: TriggerType
    started_at: datetime
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_name": self.task_name,
            "status": self.status.value,
            "trigger_type": self.trigger_type.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": int((self.finished_at - self.started_at).total_seconds() * 1000) if self.finished_at else None,
            "error": self.error,
            "result": self.result,
        }


# ==================== 任务元数据 ====================

# 任务描述和配置（新增任务时在这里添加描述）
TASK_METADATA: Dict[str, TaskInfo] = {
    "title_generation": TaskInfo(
        name="title_generation",
        description="为新对话生成标题",
        supports_scheduled=False,
    ),
    "recommended_questions": TaskInfo(
        name="recommended_questions",
        description="生成推荐问题，帮助用户继续对话",
        supports_scheduled=False,
    ),
    "mem0_update": TaskInfo(
        name="mem0_update",
        description="更新用户的长期记忆（Mem0）",
        supports_scheduled=True,
        schedule_config={
            "default_cron": "0 2 * * *",  # 默认每天凌晨 2 点
            "description": "定时同步用户记忆到 Mem0",
        },
    ),
}


class TaskService:
    """
    任务服务
    
    统一管理后台任务的查询和触发
    
    使用方式：
        service = get_task_service()
        
        # 获取任务列表
        tasks = service.list_tasks()
        
        # 手动触发任务
        result = await service.run_task("mem0_update", user_id="user_123")
    """
    
    def __init__(self):
        self.background_service = get_background_task_service()
    
    def list_tasks(self, include_scheduled_only: bool = False) -> List[Dict[str, Any]]:
        """
        获取已注册的任务列表
        
        Args:
            include_scheduled_only: 只返回支持定时执行的任务
            
        Returns:
            任务信息列表
        """
        registered_names = get_registered_task_names()
        tasks = []
        
        for name in registered_names:
            # 获取元数据（如果有）
            if name in TASK_METADATA:
                info = TASK_METADATA[name]
            else:
                # 未配置元数据的任务
                info = TaskInfo(name=name, description=f"后台任务: {name}")
            
            if include_scheduled_only and not info.supports_scheduled:
                continue
            
            tasks.append(info.to_dict())
        
        return tasks
    
    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        """
        获取单个任务详情
        
        Args:
            task_name: 任务名称
            
        Returns:
            任务信息，或 None（任务不存在）
        """
        registered_names = get_registered_task_names()
        
        if task_name not in registered_names:
            return None
        
        if task_name in TASK_METADATA:
            return TASK_METADATA[task_name].to_dict()
        else:
            return TaskInfo(name=task_name, description=f"后台任务: {task_name}").to_dict()
    
    async def run_task(
        self,
        task_name: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        wait: bool = False
    ) -> TaskRunResult:
        """
        手动触发任务
        
        Args:
            task_name: 任务名称
            user_id: 用户 ID（部分任务需要）
            conversation_id: 对话 ID（部分任务需要）
            session_id: Session ID（用于 SSE 推送）
            extra_params: 额外参数（放入 metadata）
            wait: 是否等待任务完成（默认 False，立即返回）
            
        Returns:
            TaskRunResult 执行结果
        """
        started_at = datetime.now()
        
        # 检查任务是否存在
        registered_names = get_registered_task_names()
        if task_name not in registered_names:
            return TaskRunResult(
                task_name=task_name,
                status=TaskStatus.FAILED,
                trigger_type=TriggerType.MANUAL,
                started_at=started_at,
                finished_at=datetime.now(),
                error=f"任务不存在: {task_name}，可用任务: {registered_names}",
            )
        
        # 构建上下文
        metadata = extra_params or {}
        metadata["trigger"] = TriggerType.MANUAL.value
        metadata["triggered_at"] = started_at.isoformat()
        
        context = TaskContext(
            session_id=session_id or f"manual_{task_name}_{started_at.timestamp()}",
            conversation_id=conversation_id or "",
            user_id=user_id or "",
            message_id="",
            user_message="",
            assistant_response="",
            is_new_conversation=False,
            metadata=metadata,
        )
        
        logger.info(f"🚀 手动触发任务: {task_name}, user_id={user_id}")
        
        try:
            if wait:
                # 同步执行（等待完成）
                registry = get_task_registry()
                task_func = registry[task_name]
                await task_func(context, self.background_service)
                
                return TaskRunResult(
                    task_name=task_name,
                    status=TaskStatus.COMPLETED,
                    trigger_type=TriggerType.MANUAL,
                    started_at=started_at,
                    finished_at=datetime.now(),
                )
            else:
                # 异步执行（立即返回）
                await self.background_service.dispatch_tasks(
                    task_names=[task_name],
                    context=context
                )
                
                return TaskRunResult(
                    task_name=task_name,
                    status=TaskStatus.RUNNING,
                    trigger_type=TriggerType.MANUAL,
                    started_at=started_at,
                )
        
        except Exception as e:
            logger.error(f"❌ 手动触发任务失败: {task_name}, error={e}", exc_info=True)
            return TaskRunResult(
                task_name=task_name,
                status=TaskStatus.FAILED,
                trigger_type=TriggerType.MANUAL,
                started_at=started_at,
                finished_at=datetime.now(),
                error=str(e),
            )
    
    async def run_batch_task(
        self,
        task_name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> TaskRunResult:
        """
        触发批量任务（用于定时任务场景）
        
        如 mem0_update 的批量更新所有用户
        
        Args:
            task_name: 任务名称
            params: 任务参数
            
        Returns:
            TaskRunResult 执行结果
        """
        started_at = datetime.now()
        params = params or {}
        
        logger.info(f"🚀 触发批量任务: {task_name}, params={params}")
        
        try:
            if task_name == "mem0_update":
                # Mem0 批量更新
                result = await self.background_service.batch_update_all_memories(
                    since_hours=params.get("since_hours", 24),
                    max_concurrent=params.get("max_concurrent", 5)
                )
                
                return TaskRunResult(
                    task_name=task_name,
                    status=TaskStatus.COMPLETED if result.failed == 0 else TaskStatus.FAILED,
                    trigger_type=TriggerType.SCHEDULED,
                    started_at=started_at,
                    finished_at=datetime.now(),
                    result={
                        "total_users": result.total_users,
                        "successful": result.successful,
                        "failed": result.failed,
                        "total_memories_added": result.total_memories_added,
                    },
                )
            else:
                return TaskRunResult(
                    task_name=task_name,
                    status=TaskStatus.FAILED,
                    trigger_type=TriggerType.SCHEDULED,
                    started_at=started_at,
                    finished_at=datetime.now(),
                    error=f"任务 {task_name} 不支持批量执行",
                )
        
        except Exception as e:
            logger.error(f"❌ 批量任务失败: {task_name}, error={e}", exc_info=True)
            return TaskRunResult(
                task_name=task_name,
                status=TaskStatus.FAILED,
                trigger_type=TriggerType.SCHEDULED,
                started_at=started_at,
                finished_at=datetime.now(),
                error=str(e),
            )


# ==================== 便捷函数 ====================

_default_service: Optional[TaskService] = None


def get_task_service() -> TaskService:
    """获取默认任务服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = TaskService()
    return _default_service

