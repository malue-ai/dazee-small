"""
用户定时任务数据模型（占位）

TODO: 完整实现
- [ ] 数据库模型 (SQLAlchemy)
- [ ] Pydantic 模型 (API 请求/响应)
- [ ] CRUD 操作
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel, Field


# ==================== 枚举 ====================

class TaskTriggerType(str, Enum):
    """任务触发类型"""
    ONCE = "once"           # 一次性（指定时间执行）
    DAILY = "daily"         # 每天（指定时间）
    WEEKLY = "weekly"       # 每周（指定星期和时间）
    MONTHLY = "monthly"     # 每月（指定日期和时间）
    CRON = "cron"           # Cron 表达式（高级）


class TaskActionType(str, Enum):
    """任务动作类型"""
    SEND_MESSAGE = "send_message"  # 发送消息给用户
    RUN_AGENT = "run_agent"        # 触发 AI 对话
    CALL_WEBHOOK = "call_webhook"  # 调用外部 Webhook
    RUN_WORKFLOW = "run_workflow"  # 执行工作流（未来扩展）


class TaskStatus(str, Enum):
    """任务状态"""
    ACTIVE = "active"       # 活跃
    PAUSED = "paused"       # 暂停
    COMPLETED = "completed" # 已完成（一次性任务执行后）
    CANCELLED = "cancelled" # 已取消


# ==================== Pydantic 模型 ====================

class TriggerConfig(BaseModel):
    """触发配置"""
    # 时间（HH:MM 格式）
    time: Optional[str] = Field(None, description="执行时间，如 '09:00'")
    
    # 时区
    timezone: str = Field("Asia/Shanghai", description="时区")
    
    # 日期（ONCE 类型）
    date: Optional[str] = Field(None, description="执行日期，如 '2026-01-15'")
    
    # 星期（WEEKLY 类型）
    days_of_week: Optional[List[str]] = Field(
        None, 
        description="星期几，如 ['monday', 'wednesday', 'friday']"
    )
    
    # 日期（MONTHLY 类型）
    day_of_month: Optional[int] = Field(None, ge=1, le=31, description="每月几号")
    
    # Cron 表达式（CRON 类型）
    cron_expression: Optional[str] = Field(None, description="Cron 表达式")


class TaskAction(BaseModel):
    """任务动作"""
    type: TaskActionType = Field(..., description="动作类型")
    
    # send_message 类型的配置
    content: Optional[str] = Field(None, description="消息内容")
    
    # run_agent 类型的配置
    prompt: Optional[str] = Field(None, description="AI 对话的初始 prompt")
    
    # call_webhook 类型的配置
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    webhook_payload: Optional[Dict[str, Any]] = Field(None, description="Webhook 请求体")


class ScheduledTaskCreate(BaseModel):
    """创建定时任务请求"""
    title: str = Field(..., max_length=100, description="任务标题")
    description: Optional[str] = Field(None, max_length=500, description="任务描述")
    trigger_type: TaskTriggerType = Field(..., description="触发类型")
    trigger_config: TriggerConfig = Field(..., description="触发配置")
    action: TaskAction = Field(..., description="执行动作")


class ScheduledTaskUpdate(BaseModel):
    """更新定时任务请求"""
    title: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    trigger_config: Optional[TriggerConfig] = None
    action: Optional[TaskAction] = None
    status: Optional[TaskStatus] = None


class ScheduledTaskResponse(BaseModel):
    """定时任务响应"""
    id: str
    user_id: str
    title: str
    description: Optional[str]
    trigger_type: TaskTriggerType
    trigger_config: TriggerConfig
    action: TaskAction
    status: TaskStatus
    created_at: datetime
    updated_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    run_count: int = 0
    created_by_ai: bool = False
    conversation_id: Optional[str] = None


class ScheduledTaskListResponse(BaseModel):
    """定时任务列表响应"""
    tasks: List[ScheduledTaskResponse]
    total: int
    page: int = 1
    page_size: int = 20


# ==================== 数据库模型（占位） ====================
# TODO: 在 infra/database/models.py 中实现

"""
class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    description = Column(String(500))
    trigger_type = Column(String(20), nullable=False)
    trigger_config = Column(JSON, nullable=False)
    action = Column(JSON, nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    next_run_at = Column(DateTime, index=True)  # 用于查询即将执行的任务
    last_run_at = Column(DateTime)
    run_count = Column(Integer, default=0)
    created_by_ai = Column(Boolean, default=False)
    conversation_id = Column(String(36))  # 关联的对话
    
    # 关系
    user = relationship("User", back_populates="scheduled_tasks")
"""

