"""
Plan 数据协议（Protocol）

定义统一的 Plan 数据结构，支持：
1. 单智能体的线性执行
2. 多智能体的DAG执行

设计原则：
- 数据结构共享，执行逻辑分离
- 支持依赖关系表达（DAG）
- 向下兼容简单线性执行
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class PlanStatus(str, Enum):
    """Plan 状态"""
    PENDING = "pending"         # 等待执行
    IN_PROGRESS = "in_progress" # 执行中
    COMPLETED = "completed"     # 完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 取消


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """
    Plan 步骤（单智能体和多智能体共享数据结构）
    
    支持：
    - 线性执行：dependencies 为空或仅依赖前一步
    - DAG执行：dependencies 可指向多个前置步骤
    
    Attributes:
        id: 步骤唯一标识
        description: 步骤描述
        status: 步骤状态
        dependencies: 依赖的步骤ID列表（支持DAG）
        assigned_agent: 分配的智能体ID（多智能体场景）
        tool_hint: 建议使用的工具
        result: 执行结果
        error: 错误信息
        started_at: 开始时间
        completed_at: 完成时间
        metadata: 额外元数据
    """
    id: str = Field(..., description="步骤唯一标识")
    description: str = Field(..., description="步骤描述")
    status: StepStatus = Field(default=StepStatus.PENDING, description="步骤状态")
    dependencies: List[str] = Field(default_factory=list, description="依赖的步骤ID列表")
    assigned_agent: Optional[str] = Field(None, description="分配的智能体ID")
    tool_hint: Optional[str] = Field(None, description="建议使用的工具")
    result: Optional[str] = Field(None, description="执行结果")
    error: Optional[str] = Field(None, description="错误信息")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    def is_ready(self, completed_steps: set) -> bool:
        """
        判断步骤是否可以执行
        
        Args:
            completed_steps: 已完成的步骤ID集合
            
        Returns:
            bool: 是否可以执行
        """
        if self.status != StepStatus.PENDING:
            return False
        
        # 检查所有依赖是否已完成
        return all(dep in completed_steps for dep in self.dependencies)
    
    def start(self) -> None:
        """开始执行步骤"""
        self.status = StepStatus.IN_PROGRESS
        self.started_at = datetime.now()
    
    def complete(self, result: str) -> None:
        """完成步骤"""
        self.status = StepStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()
    
    def fail(self, error: str) -> None:
        """步骤失败"""
        self.status = StepStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()


class Plan(BaseModel):
    """
    Plan 协议（统一数据结构）
    
    支持两种执行模式：
    - linear：线性执行（单智能体默认）
    - dag：DAG执行（多智能体）
    
    Attributes:
        plan_id: Plan唯一标识
        goal: 目标描述
        steps: 步骤列表
        execution_mode: 执行模式
        status: Plan状态
        created_at: 创建时间
        updated_at: 更新时间
        metadata: 额外元数据
    """
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid.uuid4()}")
    goal: str = Field(..., description="目标描述")
    steps: List[PlanStep] = Field(default_factory=list, description="步骤列表")
    execution_mode: Literal["linear", "dag"] = Field(default="linear", description="执行模式")
    status: PlanStatus = Field(default=PlanStatus.PENDING, description="Plan状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    conversation_id: Optional[str] = Field(None, description="关联的会话ID")
    user_id: Optional[str] = Field(None, description="关联的用户ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")
    
    # ===================
    # 状态查询
    # ===================
    
    @property
    def total_steps(self) -> int:
        """总步骤数"""
        return len(self.steps)
    
    @property
    def completed_steps(self) -> int:
        """已完成步骤数"""
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
    
    @property
    def progress(self) -> float:
        """进度百分比"""
        if self.total_steps == 0:
            return 0.0
        return self.completed_steps / self.total_steps
    
    @property
    def is_completed(self) -> bool:
        """是否全部完成"""
        return all(s.status == StepStatus.COMPLETED for s in self.steps)
    
    @property
    def has_failed(self) -> bool:
        """是否有失败的步骤"""
        return any(s.status == StepStatus.FAILED for s in self.steps)
    
    def get_completed_step_ids(self) -> set:
        """获取已完成的步骤ID集合"""
        return {s.id for s in self.steps if s.status == StepStatus.COMPLETED}
    
    def get_ready_steps(self) -> List[PlanStep]:
        """
        获取可以执行的步骤列表
        
        对于线性执行：返回下一个待执行步骤
        对于DAG执行：返回所有依赖已满足的步骤
        """
        completed = self.get_completed_step_ids()
        ready = [s for s in self.steps if s.is_ready(completed)]
        
        if self.execution_mode == "linear":
            # 线性模式：只返回第一个
            return ready[:1]
        else:
            # DAG模式：返回所有可执行的
            return ready
    
    # ===================
    # 步骤操作
    # ===================
    
    def get_step(self, step_id: str) -> Optional[PlanStep]:
        """获取指定步骤"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None
    
    def add_step(
        self,
        description: str,
        dependencies: Optional[List[str]] = None,
        tool_hint: Optional[str] = None
    ) -> PlanStep:
        """
        添加新步骤
        
        Args:
            description: 步骤描述
            dependencies: 依赖的步骤ID列表
            tool_hint: 建议使用的工具
            
        Returns:
            PlanStep: 新创建的步骤
        """
        step_id = str(len(self.steps) + 1)
        step = PlanStep(
            id=step_id,
            description=description,
            dependencies=dependencies or [],
            tool_hint=tool_hint,
        )
        self.steps.append(step)
        self.updated_at = datetime.now()
        return step
    
    def update_step_status(
        self,
        step_id: str,
        status: StepStatus,
        result: Optional[str] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        更新步骤状态
        
        Args:
            step_id: 步骤ID
            status: 新状态
            result: 执行结果
            error: 错误信息
            
        Returns:
            bool: 是否更新成功
        """
        step = self.get_step(step_id)
        if not step:
            return False
        
        step.status = status
        
        if status == StepStatus.IN_PROGRESS:
            step.started_at = datetime.now()
        elif status == StepStatus.COMPLETED:
            step.result = result
            step.completed_at = datetime.now()
        elif status == StepStatus.FAILED:
            step.error = error
            step.completed_at = datetime.now()
        
        self.updated_at = datetime.now()
        self._update_plan_status()
        
        return True
    
    def _update_plan_status(self) -> None:
        """根据步骤状态更新Plan状态"""
        if self.has_failed:
            self.status = PlanStatus.FAILED
        elif self.is_completed:
            self.status = PlanStatus.COMPLETED
        elif any(s.status == StepStatus.IN_PROGRESS for s in self.steps):
            self.status = PlanStatus.IN_PROGRESS
    
    # ===================
    # 序列化
    # ===================
    
    def to_summary(self) -> str:
        """生成Plan摘要（用于日志或展示）"""
        lines = [
            f"📋 Plan: {self.goal}",
            f"   模式: {self.execution_mode}",
            f"   进度: {self.completed_steps}/{self.total_steps} ({self.progress:.0%})",
            f"   状态: {self.status.value}",
        ]
        
        for step in self.steps:
            status_icon = {
                StepStatus.PENDING: "⏳",
                StepStatus.IN_PROGRESS: "🔄",
                StepStatus.COMPLETED: "✅",
                StepStatus.FAILED: "❌",
                StepStatus.SKIPPED: "⏭️",
            }.get(step.status, "❓")
            
            lines.append(f"   {status_icon} [{step.id}] {step.description}")
        
        return "\n".join(lines)
