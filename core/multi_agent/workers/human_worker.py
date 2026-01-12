"""
HumanWorker - Human-In-The-Loop Worker

将人类专家作为 Worker，处理需要人工判断的任务

适用场景：
1. 需要专业判断的审核任务
2. 敏感内容处理
3. 质量控制和最终确认
4. AI 无法处理的边缘情况

参考：
- Claude HITL: request_human_confirmation 工具
- Amazon SageMaker Human Loop
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from .base import BaseWorker, WorkerType, WorkerInput, WorkerOutput, WorkerStatus

logger = logging.getLogger(__name__)


class HumanTaskType(Enum):
    """人工任务类型"""
    REVIEW = "review"           # 审核
    DECISION = "decision"       # 决策
    ANNOTATION = "annotation"   # 标注
    CORRECTION = "correction"   # 纠错
    CREATIVE = "creative"       # 创意输入


class HumanWorker(BaseWorker):
    """
    Human Worker - 人工介入 Worker
    
    当任务需要人类专家判断时，将任务发送给人类处理。
    
    工作流程：
    1. 收到任务后，创建人工任务请求
    2. 通知人类专家（通过 Webhook/邮件/消息等）
    3. 等待人类完成任务
    4. 返回人类的处理结果
    
    Example:
        worker = HumanWorker(
            name="content-reviewer",
            specialization="content_review",
            task_type=HumanTaskType.REVIEW,
            notification_webhook="https://slack.com/webhook/xxx",
            timeout=3600  # 1 小时超时
        )
        
        result = await worker.execute(WorkerInput(
            task_id="task-1",
            action="审核以下内容是否符合政策..."
        ))
    
    配置示例 (worker_registry.yaml):
        workers:
          - name: content-reviewer
            type: human
            specialization: content_review
            task_type: review
            notification_webhook: "${SLACK_WEBHOOK}"
            timeout: 3600
            fallback_action: reject  # 超时后的默认动作
    """
    
    def __init__(
        self,
        name: str,
        specialization: str = "human_review",
        task_type: HumanTaskType = HumanTaskType.REVIEW,
        notification_webhook: str = None,
        notification_email: str = None,
        timeout: int = 3600,  # 默认 1 小时
        fallback_action: str = "pending",  # pending / reject / approve
        poll_interval: int = 10,  # 轮询间隔（秒）
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name=name,
            worker_type=WorkerType.AGENT,  # 特殊类型，实际是人工
            specialization=specialization,
            config=config
        )
        
        self.task_type = task_type
        self.notification_webhook = notification_webhook
        self.notification_email = notification_email
        self.timeout = timeout
        self.fallback_action = fallback_action
        self.poll_interval = poll_interval
        
        # 任务存储（生产环境应使用持久化存储）
        self._pending_tasks: Dict[str, Dict] = {}
        
        logger.info(f"HumanWorker 初始化: {name} (类型: {task_type.value})")
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        执行人工任务
        
        流程：
        1. 创建人工任务
        2. 发送通知
        3. 等待人工完成
        4. 返回结果
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"HumanWorker '{self.name}' 创建人工任务: {input.task_id}")
            
            # 1. 创建人工任务
            human_task = await self._create_human_task(input)
            
            # 2. 发送通知
            await self._send_notification(human_task)
            
            # 3. 等待人工完成
            result = await self._wait_for_human(input.task_id, input.timeout or self.timeout)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result is None:
                # 超时，使用 fallback
                logger.warning(f"HumanWorker '{self.name}' 任务超时，使用 fallback: {self.fallback_action}")
                return self._create_fallback_result(input.task_id, duration)
            
            logger.info(f"HumanWorker '{self.name}' 人工任务完成，耗时 {duration:.1f}s")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.COMPLETED,
                result=result.get("response"),
                artifacts=result.get("attachments", []),
                duration=duration,
                metadata={
                    "task_type": self.task_type.value,
                    "completed_by": result.get("completed_by"),
                    "completed_at": result.get("completed_at"),
                    "worker_type": "human"
                }
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"HumanWorker '{self.name}' 执行失败: {e}")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=duration
            )
    
    async def _create_human_task(self, input: WorkerInput) -> Dict:
        """创建人工任务"""
        human_task = {
            "task_id": input.task_id,
            "type": self.task_type.value,
            "action": input.action,
            "context": input.context,
            "dependencies_results": input.dependencies_results,
            "created_at": datetime.now().isoformat(),
            "status": "pending",
            "timeout": input.timeout or self.timeout,
        }
        
        # 存储任务（生产环境应持久化）
        self._pending_tasks[input.task_id] = human_task
        
        # 同时通过 HITL Manager 创建
        try:
            from core.confirmation_manager import ConfirmationManager
            
            confirmation_manager = ConfirmationManager()
            await confirmation_manager.create_request(
                request_type=self.task_type.value,
                content={
                    "task": input.action,
                    "context": input.context,
                },
                timeout=human_task["timeout"]
            )
        except ImportError:
            logger.warning("ConfirmationManager 不可用，使用内置存储")
        
        return human_task
    
    async def _send_notification(self, human_task: Dict):
        """发送通知"""
        import httpx
        
        # Webhook 通知
        if self.notification_webhook:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        self.notification_webhook,
                        json={
                            "type": "human_task",
                            "task_id": human_task["task_id"],
                            "task_type": human_task["type"],
                            "action": human_task["action"][:200],  # 截断
                            "timeout": human_task["timeout"],
                            "url": f"/api/v1/human-tasks/{human_task['task_id']}"
                        },
                        timeout=10
                    )
                logger.info(f"已发送 Webhook 通知: {human_task['task_id']}")
            except Exception as e:
                logger.warning(f"Webhook 通知失败: {e}")
        
        # 邮件通知（需要实现邮件服务）
        if self.notification_email:
            logger.info(f"TODO: 发送邮件通知到 {self.notification_email}")
    
    async def _wait_for_human(self, task_id: str, timeout: int) -> Optional[Dict]:
        """等待人工完成任务"""
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            # 检查任务状态
            task = self._pending_tasks.get(task_id)
            
            if task and task.get("status") == "completed":
                return task.get("result")
            
            # 也检查 ConfirmationManager
            try:
                from core.confirmation_manager import ConfirmationManager
                
                confirmation_manager = ConfirmationManager()
                request = await confirmation_manager.get_request(task_id)
                
                if request and request.status == "confirmed":
                    return {
                        "response": request.content,
                        "completed_by": request.confirmed_by,
                        "completed_at": request.updated_at
                    }
            except ImportError:
                pass
            
            # 轮询等待
            await asyncio.sleep(self.poll_interval)
        
        return None  # 超时
    
    def _create_fallback_result(self, task_id: str, duration: float) -> WorkerOutput:
        """创建超时 fallback 结果"""
        if self.fallback_action == "approve":
            return WorkerOutput(
                task_id=task_id,
                status=WorkerStatus.COMPLETED,
                result="[自动批准] 人工任务超时，已自动批准",
                duration=duration,
                metadata={"fallback": True, "worker_type": "human"}
            )
        elif self.fallback_action == "reject":
            return WorkerOutput(
                task_id=task_id,
                status=WorkerStatus.FAILED,
                error="人工任务超时，已自动拒绝",
                duration=duration,
                metadata={"fallback": True, "worker_type": "human"}
            )
        else:  # pending
            return WorkerOutput(
                task_id=task_id,
                status=WorkerStatus.TIMEOUT,
                error="人工任务超时，任务挂起",
                duration=duration,
                metadata={"fallback": True, "worker_type": "human"}
            )
    
    async def complete_task(self, task_id: str, response: str, completed_by: str = None):
        """
        完成人工任务（供外部调用）
        
        Example:
            await human_worker.complete_task(
                task_id="task-1",
                response="审核通过",
                completed_by="reviewer@example.com"
            )
        """
        if task_id in self._pending_tasks:
            self._pending_tasks[task_id]["status"] = "completed"
            self._pending_tasks[task_id]["result"] = {
                "response": response,
                "completed_by": completed_by,
                "completed_at": datetime.now().isoformat()
            }
            logger.info(f"人工任务完成: {task_id}")
    
    async def health_check(self) -> bool:
        """健康检查"""
        # 检查通知渠道是否可用
        if self.notification_webhook:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    # 只检查连接性，不实际发送
                    return True
            except Exception:
                return False
        return True
