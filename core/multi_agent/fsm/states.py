"""
FSM 状态定义

定义 Multi-Agent 任务的生命周期状态

状态机设计（参考白皮书 1.3 节）：

┌─────────┐
│ PENDING │ ─────── create_task() ──────▶ ┌─────────────┐
└─────────┘                               │ DECOMPOSING │
                                          └──────┬──────┘
                                                 │ decompose_complete
                                                 ▼
                                          ┌─────────────┐
                                          │  PLANNING   │
                                          └──────┬──────┘
                                                 │ plan_ready
                                                 ▼
                                          ┌─────────────┐
                                          │ DISPATCHING │
                                          └──────┬──────┘
                                                 │ workers_assigned
                                                 ▼
                                          ┌─────────────┐
   ┌───── retry ◀─────────────────────────│  EXECUTING  │◀─── partial ───┐
   │                                      └──────┬──────┘                │
   │                                             │ all_complete          │
   │                                             ▼                       │
   │                                      ┌─────────────┐                │
   │                                      │  OBSERVING  │ ───────────────┘
   │                                      └──────┬──────┘
   │                                             │
   │                                             ▼
   │                                      ┌─────────────┐
   └──────────────────────────────────────│ VALIDATING  │
                                          └──────┬──────┘
                                                 │ validation_pass
                                                 ▼
                                          ┌─────────────┐
                                          │ AGGREGATING │
                                          └──────┬──────┘
                                                 │
                           ┌─────────────────────┴─────────────────────┐
                           ▼                                           ▼
                    ┌─────────────┐                             ┌─────────────┐
                    │  COMPLETED  │                             │   FAILED    │
                    └─────────────┘                             └─────────────┘
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class TaskStatus(str, Enum):
    """
    Multi-Agent 任务主状态
    """
    # 初始状态
    PENDING = "pending"              # 等待处理
    
    # 分解阶段
    DECOMPOSING = "decomposing"      # LLM 正在分解任务
    
    # 规划阶段
    PLANNING = "planning"            # 构建依赖图和执行计划
    
    # 调度阶段
    DISPATCHING = "dispatching"      # 分配 Worker
    
    # 执行阶段
    EXECUTING = "executing"          # Worker 正在执行
    
    # 观察阶段
    OBSERVING = "observing"          # 观察执行结果
    
    # 验证阶段
    VALIDATING = "validating"        # 验证结果质量
    
    # 聚合阶段
    AGGREGATING = "aggregating"      # 聚合所有 Worker 结果
    
    # 终态
    COMPLETED = "completed"          # 成功完成
    FAILED = "failed"                # 失败
    CANCELLED = "cancelled"          # 被取消


class SubTaskStatus(str, Enum):
    """
    子任务状态
    """
    PENDING = "pending"              # 等待执行
    BLOCKED = "blocked"              # 被依赖阻塞
    ASSIGNED = "assigned"            # 已分配 Worker
    RUNNING = "running"              # 正在执行
    COMPLETED = "completed"          # 成功完成
    FAILED = "failed"                # 执行失败
    RETRYING = "retrying"            # 重试中
    SKIPPED = "skipped"              # 被跳过


@dataclass
class SubTaskState:
    """
    子任务状态
    
    对应一个 Worker 执行的原子任务
    """
    id: str                                     # 子任务 ID
    action: str                                 # 任务描述
    specialization: str                         # Worker 专业化类型
    status: SubTaskStatus = SubTaskStatus.PENDING
    
    # 依赖关系
    dependencies: List[str] = field(default_factory=list)
    
    # Worker 信息
    worker_id: Optional[str] = None             # 分配的 Worker ID
    worker_prompt: Optional[str] = None         # Worker 系统提示词
    
    # 执行结果
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    # 重试信息
    attempt_count: int = 0
    max_retries: int = 3
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "action": self.action,
            "specialization": self.specialization,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "worker_id": self.worker_id,
            "result": self.result,
            "error": self.error,
            "attempt_count": self.attempt_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubTaskState":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            action=data["action"],
            specialization=data["specialization"],
            status=SubTaskStatus(data.get("status", "pending")),
            dependencies=data.get("dependencies", []),
            worker_id=data.get("worker_id"),
            worker_prompt=data.get("worker_prompt"),
            result=data.get("result"),
            error=data.get("error"),
            attempt_count=data.get("attempt_count", 0),
            max_retries=data.get("max_retries", 3),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class TaskState:
    """
    Multi-Agent 任务状态
    
    包含主任务状态和所有子任务状态
    持久化到 PlanMemory，支持检查点恢复
    """
    # 基本信息
    task_id: str                                # 任务 ID
    session_id: str                             # 会话 ID
    user_query: str                             # 用户原始请求
    
    # 主状态
    status: TaskStatus = TaskStatus.PENDING
    
    # 子任务
    sub_tasks: List[SubTaskState] = field(default_factory=list)
    
    # 分解信息
    decomposition_reasoning: str = ""           # LLM 分解推理过程
    parallelizable_groups: List[List[str]] = field(default_factory=list)  # 可并行的子任务组
    
    # 执行信息
    current_phase: str = ""                     # 当前执行阶段描述
    progress: float = 0.0                       # 总体进度 (0-1)
    
    # 聚合结果
    final_result: Optional[Dict[str, Any]] = None
    final_error: Optional[str] = None
    
    # 检查点信息
    checkpoint_version: int = 0                 # 检查点版本号
    last_checkpoint_at: Optional[datetime] = None
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # ==================== 状态查询方法 ====================
    
    def get_sub_task(self, sub_task_id: str) -> Optional[SubTaskState]:
        """获取子任务"""
        for st in self.sub_tasks:
            if st.id == sub_task_id:
                return st
        return None
    
    def get_pending_sub_tasks(self) -> List[SubTaskState]:
        """获取待执行的子任务"""
        return [st for st in self.sub_tasks if st.status == SubTaskStatus.PENDING]
    
    def get_runnable_sub_tasks(self) -> List[SubTaskState]:
        """
        获取可执行的子任务（无阻塞依赖）
        """
        completed_ids = {st.id for st in self.sub_tasks if st.status == SubTaskStatus.COMPLETED}
        
        runnable = []
        for st in self.sub_tasks:
            if st.status != SubTaskStatus.PENDING:
                continue
            
            # 检查所有依赖是否已完成
            deps_satisfied = all(dep_id in completed_ids for dep_id in st.dependencies)
            if deps_satisfied:
                runnable.append(st)
        
        return runnable
    
    def get_running_sub_tasks(self) -> List[SubTaskState]:
        """获取正在执行的子任务"""
        return [st for st in self.sub_tasks if st.status == SubTaskStatus.RUNNING]
    
    def get_completed_sub_tasks(self) -> List[SubTaskState]:
        """获取已完成的子任务"""
        return [st for st in self.sub_tasks if st.status == SubTaskStatus.COMPLETED]
    
    def get_failed_sub_tasks(self) -> List[SubTaskState]:
        """获取失败的子任务"""
        return [st for st in self.sub_tasks if st.status == SubTaskStatus.FAILED]
    
    def is_all_completed(self) -> bool:
        """检查是否所有子任务都已完成"""
        return all(st.status == SubTaskStatus.COMPLETED for st in self.sub_tasks)
    
    def has_failed(self) -> bool:
        """检查是否有子任务失败且不可重试"""
        for st in self.sub_tasks:
            if st.status == SubTaskStatus.FAILED and st.attempt_count >= st.max_retries:
                return True
        return False
    
    def calculate_progress(self) -> float:
        """计算总体进度"""
        if not self.sub_tasks:
            return 0.0
        
        completed = len(self.get_completed_sub_tasks())
        total = len(self.sub_tasks)
        return completed / total
    
    # ==================== 序列化方法 ====================
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于持久化）"""
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "user_query": self.user_query,
            "status": self.status.value,
            "sub_tasks": [st.to_dict() for st in self.sub_tasks],
            "decomposition_reasoning": self.decomposition_reasoning,
            "parallelizable_groups": self.parallelizable_groups,
            "current_phase": self.current_phase,
            "progress": self.progress,
            "final_result": self.final_result,
            "final_error": self.final_error,
            "checkpoint_version": self.checkpoint_version,
            "last_checkpoint_at": self.last_checkpoint_at.isoformat() if self.last_checkpoint_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskState":
        """从字典反序列化（用于检查点恢复）"""
        sub_tasks = [SubTaskState.from_dict(st) for st in data.get("sub_tasks", [])]
        
        return cls(
            task_id=data["task_id"],
            session_id=data["session_id"],
            user_query=data["user_query"],
            status=TaskStatus(data.get("status", "pending")),
            sub_tasks=sub_tasks,
            decomposition_reasoning=data.get("decomposition_reasoning", ""),
            parallelizable_groups=data.get("parallelizable_groups", []),
            current_phase=data.get("current_phase", ""),
            progress=data.get("progress", 0.0),
            final_result=data.get("final_result"),
            final_error=data.get("final_error"),
            checkpoint_version=data.get("checkpoint_version", 0),
            last_checkpoint_at=datetime.fromisoformat(data["last_checkpoint_at"]) if data.get("last_checkpoint_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )
    
    def to_plan_event(self) -> Dict[str, Any]:
        """
        转换为 plan_update 事件格式
        
        兼容 V5.1 的 SSE 事件格式
        """
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "current_phase": self.current_phase,
            "sub_tasks": [
                {
                    "id": st.id,
                    "action": st.action,
                    "status": st.status.value,
                    "worker_id": st.worker_id,
                }
                for st in self.sub_tasks
            ],
        }
