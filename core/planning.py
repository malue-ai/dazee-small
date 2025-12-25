"""
⚠️ DEPRECATED - 此模块已废弃！

Planning Layer - 任务规划层 (V2) - 已被 plan_todo_tool.py 替代

替代方案：
- 使用 tools.plan_todo_tool.PlanTodoTool
- 使用 core.memory.WorkingMemory 的 plan_json/todo_md 属性

新架构（V3.6）：
```
User Query
    │
    ▼
┌─────────────────────────────────────────┐
│               Agent                      │
│  ┌───────────────────────────────────┐  │
│  │     WorkingMemory (Short Memory)   │  │
│  │  ┌──────────┐  ┌──────────┐       │  │
│  │  │plan.json │  │ todo.md  │       │  │
│  │  └─────↑────┘  └────↑─────┘       │  │
│  └────────┴────────────┴─────────────┘  │
│           │ CRUD (via tool)             │
│  ┌────────┴────────────────────────────┐│
│  │      plan_todo Tool                 ││
│  │  - create_plan → 写入 Memory        ││
│  │  - get_plan → 读取 Memory           ││
│  │  - update_step → 更新 Memory        ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘

LLM 通过 plan_todo 工具管理计划，避免多轮 input/output 的 token 浪费
```

如果仍需使用此模块（向后兼容），请注意：
- PlanningManager 会将 plan 持久化到文件（不推荐）
- 新架构使用 WorkingMemory 存储（会话级，自动清除）

迁移指南：
1. 将 `from core.planning import PlanningManager` 
   改为 `from tools.plan_todo_tool import create_plan_todo_tool`
2. 将 `PlanningManager` 的调用改为 `plan_todo_tool.execute(operation, data)`

保留此文件仅为向后兼容。新代码请使用 plan_todo_tool.py
"""

import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field, asdict


# ==================== 枚举定义 ====================

class TaskPhase(Enum):
    """任务阶段（单向流转）"""
    PLANNING = "planning"      # 规划阶段
    EXECUTING = "executing"    # 执行阶段
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"        # ❓ 待执行
    IN_PROGRESS = "in_progress"  # 🔄 执行中
    COMPLETED = "completed"    # ✅ 已完成
    FAILED = "failed"          # ❌ 失败
    SKIPPED = "skipped"        # ⏭️ 跳过
    RETRY = "retry"            # 🔁 重试中


class StepAction(Enum):
    """步骤动作类型"""
    WEB_SEARCH = "web_search"
    FILE_READ = "file_read"
    CODE_EXECUTION = "code_execution"
    TOOL_CALL = "tool_call"
    ASK_USER = "ask_user"
    SKILL_LOAD = "skill_load"
    CONFIG_GENERATE = "config_generate"
    VALIDATE = "validate"
    RENDER = "render"


# ==================== 数据结构 ====================

@dataclass
class PlanStep:
    """
    计划步骤
    
    对应 system_prompt_v3.py 中的步骤结构
    """
    step_id: int
    action: str                    # 动作类型
    query: str                     # 具体查询/内容
    purpose: str                   # 目的
    expected_output: str           # 预期输出
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None   # 实际结果
    insight: Optional[str] = None  # 洞察/发现
    retry_count: int = 0           # 重试次数
    max_retries: int = 3           # 最大重试次数
    error_message: Optional[str] = None  # 错误信息
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "query": self.query,
            "purpose": self.purpose,
            "expected_output": self.expected_output,
            "status": self.status.value,
            "result": self.result,
            "insight": self.insight,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanStep':
        return cls(
            step_id=data["step_id"],
            action=data["action"],
            query=data["query"],
            purpose=data["purpose"],
            expected_output=data["expected_output"],
            status=StepStatus(data.get("status", "pending")),
            result=data.get("result"),
            insight=data.get("insight"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error_message=data.get("error_message"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at")
        )
    
    def get_status_icon(self) -> str:
        """获取状态图标"""
        icons = {
            StepStatus.PENDING: "❓",
            StepStatus.IN_PROGRESS: "🔄",
            StepStatus.COMPLETED: "✅",
            StepStatus.FAILED: "❌",
            StepStatus.SKIPPED: "⏭️",
            StepStatus.RETRY: "🔁"
        }
        return icons.get(self.status, "❓")


@dataclass
class Plan:
    """
    任务计划
    
    对应 system_prompt_v3.py 中的 Plan 结构：
    plan = {
        "goal": "最终目标",
        "information_gaps": [...],
        "steps": [...],
        "total_steps": N
    }
    """
    plan_id: str
    goal: str                      # 最终目标
    user_query: str                # 原始用户查询
    information_gaps: List[str] = field(default_factory=list)  # 信息缺口
    steps: List[PlanStep] = field(default_factory=list)        # 步骤列表
    phase: TaskPhase = TaskPhase.PLANNING
    current_step: int = 1          # 当前步骤（1-based）
    metadata: Dict[str, Any] = field(default_factory=dict)     # 额外元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: int = 1               # 计划版本（每次修改+1）
    change_log: List[Dict[str, Any]] = field(default_factory=list)  # 变更记录
    
    @property
    def total_steps(self) -> int:
        return len(self.steps)
    
    def add_step(
        self,
        action: str,
        query: str,
        purpose: str,
        expected_output: str
    ) -> PlanStep:
        """添加步骤"""
        step = PlanStep(
            step_id=len(self.steps) + 1,
            action=action,
            query=query,
            purpose=purpose,
            expected_output=expected_output
        )
        self.steps.append(step)
        self._update_timestamp()
        return step
    
    def get_step(self, step_id: int) -> Optional[PlanStep]:
        """获取指定步骤"""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
    
    def get_current_step(self) -> Optional[PlanStep]:
        """获取当前步骤"""
        return self.get_step(self.current_step)
    
    def update_step_status(
        self,
        step_id: int,
        status: StepStatus,
        result: Optional[str] = None,
        insight: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """更新步骤状态"""
        step = self.get_step(step_id)
        if not step:
            return False
        
        old_status = step.status
        step.status = status
        
        if result:
            step.result = result
        if insight:
            step.insight = insight
        if error_message:
            step.error_message = error_message
        
        if status == StepStatus.IN_PROGRESS and not step.started_at:
            step.started_at = datetime.now().isoformat()
        elif status in [StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED]:
            step.completed_at = datetime.now().isoformat()
        elif status == StepStatus.RETRY:
            step.retry_count += 1
        
        self._update_timestamp()
        
        # 记录变更
        self._log_change(
            "step_status_update",
            f"Step {step_id}: {old_status.value} → {status.value}"
        )
        
        return True
    
    def advance_to_next_step(self) -> Optional[PlanStep]:
        """前进到下一步"""
        if self.current_step < self.total_steps:
            self.current_step += 1
            self._update_timestamp()
            return self.get_current_step()
        return None
    
    def update_phase(self, new_phase: TaskPhase):
        """更新任务阶段"""
        old_phase = self.phase
        self.phase = new_phase
        self._update_timestamp()
        self._log_change(
            "phase_update",
            f"Phase: {old_phase.value} → {new_phase.value}"
        )
    
    def modify_plan(
        self,
        new_steps: Optional[List[Dict]] = None,
        new_gaps: Optional[List[str]] = None,
        reason: str = "Plan adjustment"
    ):
        """
        修改计划（动态调整）
        
        会增加版本号并记录变更
        """
        if new_steps:
            # 保留已完成的步骤，替换未完成的步骤
            completed_steps = [s for s in self.steps if s.status == StepStatus.COMPLETED]
            new_step_objs = [
                PlanStep(
                    step_id=len(completed_steps) + i + 1,
                    action=s["action"],
                    query=s["query"],
                    purpose=s["purpose"],
                    expected_output=s["expected_output"]
                )
                for i, s in enumerate(new_steps)
            ]
            self.steps = completed_steps + new_step_objs
            self.current_step = len(completed_steps) + 1
        
        if new_gaps:
            self.information_gaps = new_gaps
        
        self.version += 1
        self._update_timestamp()
        self._log_change("plan_modification", reason)
    
    def _update_timestamp(self):
        self.updated_at = datetime.now().isoformat()
    
    def _log_change(self, change_type: str, description: str):
        self.change_log.append({
            "type": change_type,
            "description": description,
            "version": self.version,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_progress(self) -> Dict[str, Any]:
        """获取进度统计"""
        total = self.total_steps
        if total == 0:
            return {"total": 0, "completed": 0, "progress": 0.0}
        
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.steps if s.status == StepStatus.FAILED)
        in_progress = sum(1 for s in self.steps if s.status == StepStatus.IN_PROGRESS)
        pending = sum(1 for s in self.steps if s.status == StepStatus.PENDING)
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "pending": pending,
            "progress": completed / total if total > 0 else 0.0,
            "current_step": self.current_step
        }
    
    def is_completed(self) -> bool:
        """判断计划是否完成"""
        return all(
            s.status in [StepStatus.COMPLETED, StepStatus.SKIPPED]
            for s in self.steps
        )
    
    def has_failed_steps(self) -> bool:
        """是否有失败的步骤"""
        return any(s.status == StepStatus.FAILED for s in self.steps)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 plan.json）"""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "user_query": self.user_query,
            "information_gaps": self.information_gaps,
            "steps": [s.to_dict() for s in self.steps],
            "total_steps": self.total_steps,
            "phase": self.phase.value,
            "current_step": self.current_step,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "change_log": self.change_log
        }
    
    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    def to_markdown(self) -> str:
        """
        生成 Markdown 格式的 Todo 列表
        
        格式参考 system_prompt_v3.py 中的 Todo 跟踪机制
        """
        lines = [
            f"# 📋 Task Plan: {self.goal}",
            "",
            f"> 用户查询: {self.user_query}",
            f"> 计划版本: v{self.version}",
            f"> 更新时间: {self.updated_at}",
            ""
        ]
        
        # 进度条
        progress = self.get_progress()
        progress_bar = self._generate_progress_bar(progress['progress'])
        lines.append(f"## 📊 Progress: {progress['completed']}/{progress['total']} ({progress['progress']*100:.0f}%)")
        lines.append(f"```")
        lines.append(f"{progress_bar}")
        lines.append(f"```")
        lines.append("")
        
        # 信息缺口
        if self.information_gaps:
            lines.append("## 🔍 Information Gaps")
            for gap in self.information_gaps:
                lines.append(f"- {gap}")
            lines.append("")
        
        # 步骤列表
        lines.append("## 📝 Todo List")
        lines.append("")
        
        for step in self.steps:
            icon = step.get_status_icon()
            checkbox = "x" if step.status == StepStatus.COMPLETED else " "
            
            # 主步骤行
            lines.append(f"- [{checkbox}] **Step {step.step_id}**: {step.action}")
            lines.append(f"  - 📌 Purpose: {step.purpose}")
            lines.append(f"  - 🎯 Query: `{step.query}`")
            lines.append(f"  - 📤 Expected: {step.expected_output}")
            lines.append(f"  - 🏷️ Status: {icon} {step.status.value}")
            
            # 结果（如果有）
            if step.result:
                result_preview = step.result[:200] + "..." if len(step.result) > 200 else step.result
                lines.append(f"  - 📥 Result: {result_preview}")
            
            # 洞察（如果有）
            if step.insight:
                lines.append(f"  - 💡 Insight: {step.insight}")
            
            # 错误（如果有）
            if step.error_message:
                lines.append(f"  - ⚠️ Error: {step.error_message}")
            
            # 重试信息
            if step.retry_count > 0:
                lines.append(f"  - 🔁 Retries: {step.retry_count}/{step.max_retries}")
            
            lines.append("")
        
        # 变更记录
        if self.change_log:
            lines.append("## 📜 Change Log")
            for change in self.change_log[-5:]:  # 只显示最近5条
                lines.append(f"- [{change['timestamp']}] v{change['version']}: {change['description']}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_progress_bar(self, progress: float, width: int = 30) -> str:
        """生成进度条"""
        filled = int(width * progress)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}] {progress*100:.0f}%"
    
    def to_simple_display(self) -> str:
        """
        生成简洁的 TODO 展示（类似 Cursor 风格）
        
        格式：
        🎯 任务目标
        📋 To-dos N
        
        ⊙ 已完成的步骤
        ○ 未完成的步骤
        """
        progress = self.get_progress()
        
        lines = [
            f"🎯 {self.goal}",
            f"📋 To-dos {self.total_steps}",
            ""
        ]
        
        for step in self.steps:
            # 状态图标（Cursor 风格）
            if step.status == StepStatus.COMPLETED:
                icon = "⊙"  # 填充圆点 - 完成
            elif step.status == StepStatus.IN_PROGRESS:
                icon = "◐"  # 半圆 - 进行中
            elif step.status == StepStatus.FAILED:
                icon = "⊗"  # 叉圆 - 失败
            elif step.status == StepStatus.RETRY:
                icon = "↻"  # 循环 - 重试
            else:
                icon = "○"  # 空心圆 - 待处理
            
            lines.append(f"{icon} {step.purpose}")
        
        # 添加进度摘要
        lines.append("")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"进度: {progress['completed']}/{progress['total']} ({progress['progress']*100:.0f}%)")
        
        return "\n".join(lines)
    
    def to_realtime_status(self) -> str:
        """
        生成实时状态更新（适合流式输出）
        
        格式：
        [Step 2/5] 🔄 正在获取技术细节...
        """
        current = None
        for s in self.steps:
            if s.status == StepStatus.IN_PROGRESS:
                current = s
                break
        
        if not current:
            if self.is_completed():
                return f"✅ 任务完成 ({self.total_steps}/{self.total_steps})"
            else:
                return f"⏸️ 任务暂停"
        
        icon = {
            StepStatus.IN_PROGRESS: "🔄",
            StepStatus.RETRY: "🔁",
        }.get(current.status, "🔄")
        
        return f"[Step {current.step_id}/{self.total_steps}] {icon} {current.purpose}..."
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Plan':
        """从字典创建"""
        plan = cls(
            plan_id=data["plan_id"],
            goal=data["goal"],
            user_query=data["user_query"],
            information_gaps=data.get("information_gaps", []),
            phase=TaskPhase(data.get("phase", "planning")),
            current_step=data.get("current_step", 1),
            metadata=data.get("metadata", {}),
            version=data.get("version", 1),
            change_log=data.get("change_log", [])
        )
        plan.steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        plan.created_at = data.get("created_at", plan.created_at)
        plan.updated_at = data.get("updated_at", plan.updated_at)
        return plan


# ==================== 计划管理器 ====================

class PlanningManager:
    """
    规划管理器 (V2)
    
    职责：
    1. 管理 Plan 的生命周期
    2. 持久化到 plan.json 和 todo.md
    3. 提供进度回调机制
    4. 支持动态计划调整
    """
    
    def __init__(
        self,
        workspace_dir: Optional[str] = None,
        on_progress_update: Optional[Callable[[Plan], None]] = None,
        on_plan_change: Optional[Callable[[Plan, str], None]] = None
    ):
        """
        初始化规划管理器
        
        Args:
            workspace_dir: 工作目录（用于持久化）
            on_progress_update: 进度更新回调
            on_plan_change: 计划变更回调
        """
        self.workspace_dir = Path(workspace_dir) if workspace_dir else None
        self.current_plan: Optional[Plan] = None
        self.on_progress_update = on_progress_update
        self.on_plan_change = on_plan_change
        
        # 如果workspace存在且有plan.json，加载它
        if self.workspace_dir:
            plan_file = self.workspace_dir / "plan.json"
            if plan_file.exists():
                self.load_plan(str(plan_file))
    
    def create_plan(
        self,
        user_query: str,
        goal: str,
        information_gaps: List[str] = None,
        steps: List[Dict[str, str]] = None
    ) -> Plan:
        """
        创建新的任务计划
        
        Args:
            user_query: 用户原始查询
            goal: 最终目标
            information_gaps: 信息缺口列表
            steps: 步骤列表，每个步骤是字典 {action, query, purpose, expected_output}
        """
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.current_plan = Plan(
            plan_id=plan_id,
            goal=goal,
            user_query=user_query,
            information_gaps=information_gaps or []
        )
        
        # 添加步骤
        if steps:
            for step_data in steps:
                self.current_plan.add_step(
                    action=step_data["action"],
                    query=step_data["query"],
                    purpose=step_data["purpose"],
                    expected_output=step_data["expected_output"]
                )
        
        # 保存
        self._save()
        
        # 触发回调
        self._notify_progress()
        
        return self.current_plan
    
    def add_step(
        self,
        action: str,
        query: str,
        purpose: str,
        expected_output: str
    ) -> Optional[PlanStep]:
        """向当前计划添加步骤"""
        if not self.current_plan:
            return None
        
        step = self.current_plan.add_step(action, query, purpose, expected_output)
        self._save()
        self._notify_progress()
        return step
    
    def start_step(self, step_id: int) -> bool:
        """开始执行步骤"""
        if not self.current_plan:
            return False
        
        # 更新阶段到执行中
        if self.current_plan.phase == TaskPhase.PLANNING:
            self.current_plan.update_phase(TaskPhase.EXECUTING)
        
        success = self.current_plan.update_step_status(step_id, StepStatus.IN_PROGRESS)
        if success:
            self._save()
            self._notify_progress()
        return success
    
    def complete_step(
        self,
        step_id: int,
        result: str,
        insight: Optional[str] = None
    ) -> bool:
        """完成步骤"""
        if not self.current_plan:
            return False
        
        success = self.current_plan.update_step_status(
            step_id,
            StepStatus.COMPLETED,
            result=result,
            insight=insight
        )
        
        if success:
            # 自动前进到下一步
            self.current_plan.advance_to_next_step()
            
            # 检查是否所有步骤完成
            if self.current_plan.is_completed():
                self.current_plan.update_phase(TaskPhase.COMPLETED)
            
            self._save()
            self._notify_progress()
        
        return success
    
    def fail_step(
        self,
        step_id: int,
        error_message: str,
        can_retry: bool = True
    ) -> bool:
        """步骤失败"""
        if not self.current_plan:
            return False
        
        step = self.current_plan.get_step(step_id)
        if not step:
            return False
        
        # 检查是否可以重试
        if can_retry and step.retry_count < step.max_retries:
            status = StepStatus.RETRY
        else:
            status = StepStatus.FAILED
        
        success = self.current_plan.update_step_status(
            step_id,
            status,
            error_message=error_message
        )
        
        if success:
            self._save()
            self._notify_progress()
        
        return success
    
    def skip_step(self, step_id: int, reason: str = "Skipped") -> bool:
        """跳过步骤"""
        if not self.current_plan:
            return False
        
        success = self.current_plan.update_step_status(
            step_id,
            StepStatus.SKIPPED,
            result=reason
        )
        
        if success:
            self.current_plan.advance_to_next_step()
            self._save()
            self._notify_progress()
        
        return success
    
    def modify_plan(
        self,
        new_steps: Optional[List[Dict]] = None,
        new_gaps: Optional[List[str]] = None,
        reason: str = "Plan adjustment based on new information"
    ):
        """修改计划"""
        if not self.current_plan:
            return
        
        self.current_plan.modify_plan(new_steps, new_gaps, reason)
        self._save()
        
        # 触发计划变更回调
        if self.on_plan_change:
            self.on_plan_change(self.current_plan, reason)
        
        self._notify_progress()
    
    def get_current_step(self) -> Optional[PlanStep]:
        """获取当前步骤"""
        if not self.current_plan:
            return None
        return self.current_plan.get_current_step()
    
    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        if not self.current_plan:
            return {"total": 0, "completed": 0, "progress": 0.0}
        return self.current_plan.get_progress()
    
    def get_progress_display(self) -> str:
        """获取用户友好的进度显示"""
        if not self.current_plan:
            return "No active plan"
        
        progress = self.get_progress()
        current_step = self.get_current_step()
        
        lines = [
            f"📊 Progress: {progress['completed']}/{progress['total']} ({progress['progress']*100:.0f}%)",
            f"🎯 Goal: {self.current_plan.goal}",
            f"📍 Phase: {self.current_plan.phase.value}",
        ]
        
        if current_step:
            lines.append(f"🔄 Current: Step {current_step.step_id} - {current_step.action}")
            lines.append(f"   Purpose: {current_step.purpose}")
        
        # 简要步骤列表
        lines.append("")
        lines.append("Steps:")
        for step in self.current_plan.steps:
            icon = step.get_status_icon()
            lines.append(f"  {icon} Step {step.step_id}: {step.action} ({step.status.value})")
        
        return "\n".join(lines)
    
    def get_simple_display(self) -> str:
        """
        获取简洁的 TODO 展示（Cursor 风格）
        
        返回格式：
        🎯 任务目标
        📋 To-dos N
        
        ⊙ 已完成步骤
        ○ 未完成步骤
        """
        if not self.current_plan:
            return "No active plan"
        return self.current_plan.to_simple_display()
    
    def get_realtime_status(self) -> str:
        """
        获取实时状态（适合流式输出到用户界面）
        
        返回格式：
        [Step 2/5] 🔄 正在获取技术细节...
        """
        if not self.current_plan:
            return "No active plan"
        return self.current_plan.to_realtime_status()
    
    def is_completed(self) -> bool:
        """判断当前计划是否完成"""
        if not self.current_plan:
            return True
        return self.current_plan.is_completed()
    
    def _save(self):
        """保存计划到文件"""
        if not self.workspace_dir or not self.current_plan:
            return
        
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存 plan.json
        plan_file = self.workspace_dir / "plan.json"
        with open(plan_file, 'w', encoding='utf-8') as f:
            f.write(self.current_plan.to_json())
        
        # 保存 todo.md
        todo_file = self.workspace_dir / "todo.md"
        with open(todo_file, 'w', encoding='utf-8') as f:
            f.write(self.current_plan.to_markdown())
    
    def load_plan(self, plan_file: str):
        """从文件加载计划"""
        with open(plan_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.current_plan = Plan.from_dict(data)
    
    def _notify_progress(self):
        """通知进度更新"""
        if self.on_progress_update and self.current_plan:
            self.on_progress_update(self.current_plan)
    
    def get_metadata_for_llm(self) -> Dict[str, Any]:
        """
        获取 LLM 需要的 metadata 对象
        
        对应 system_prompt_v3.py 中的 metadata 结构
        """
        if not self.current_plan:
            return {
                "task_phase": "planning",
                "current_step": 1,
                "total_steps": 0,
                "step_retry_count": 0,
                "last_action": "initial",
                "skill_in_use": None,
                "config_ready": False,
                "quality_score": None
            }
        
        current_step = self.get_current_step()
        
        return {
            "task_phase": self.current_plan.phase.value,
            "current_step": self.current_plan.current_step,
            "total_steps": self.current_plan.total_steps,
            "step_retry_count": current_step.retry_count if current_step else 0,
            "last_action": self.current_plan.metadata.get("last_action", "initial"),
            "skill_in_use": self.current_plan.metadata.get("skill_in_use"),
            "config_ready": self.current_plan.metadata.get("config_ready", False),
            "quality_score": self.current_plan.metadata.get("quality_score")
        }
    
    def update_metadata(self, key: str, value: Any):
        """更新 metadata"""
        if self.current_plan:
            self.current_plan.metadata[key] = value
            self._save()


# ==================== 便捷函数 ====================

def create_planning_manager(
    workspace_dir: Optional[str] = None,
    on_progress_update: Optional[Callable] = None,
    on_plan_change: Optional[Callable] = None
) -> PlanningManager:
    """
    创建规划管理器
    
    Args:
        workspace_dir: 工作目录（用于持久化 plan.json 和 todo.md）
        on_progress_update: 进度更新回调函数
        on_plan_change: 计划变更回调函数
        
    Returns:
        配置好的 PlanningManager 实例
    """
    return PlanningManager(
        workspace_dir=workspace_dir,
        on_progress_update=on_progress_update,
        on_plan_change=on_plan_change
    )


# ==================== 兼容旧接口 ====================

# 保持向后兼容
TaskStatus = StepStatus
Task = PlanStep
TaskPlan = Plan


# ==================== 测试 ====================

if __name__ == "__main__":
    # 测试创建计划
    manager = create_planning_manager(workspace_dir="./test_workspace")
    
    # 创建计划
    plan = manager.create_plan(
        user_query="创建AI产品介绍PPT",
        goal="生成高质量AI产品介绍PPT",
        information_gaps=[
            "缺少市场数据",
            "缺少技术细节",
            "缺少案例支撑"
        ],
        steps=[
            {
                "action": "web_search",
                "query": "AI产品 市场规模 2024",
                "purpose": "获取市场数据",
                "expected_output": "市场规模、增长率等数据"
            },
            {
                "action": "web_search",
                "query": "AI产品 技术架构 大模型",
                "purpose": "获取技术细节",
                "expected_output": "技术架构、核心能力"
            },
            {
                "action": "skill_load",
                "query": "slidespeak-generator",
                "purpose": "加载PPT生成Skill",
                "expected_output": "Skill加载成功"
            },
            {
                "action": "config_generate",
                "query": "生成PPT配置",
                "purpose": "生成SlideSpeak配置",
                "expected_output": "验证通过的配置对象"
            },
            {
                "action": "render",
                "query": "slidespeak_render",
                "purpose": "渲染PPT",
                "expected_output": "PPT下载链接"
            }
        ]
    )
    
    print("=" * 60)
    print("📋 Plan Created")
    print("=" * 60)
    print(plan.to_markdown())
    
    # 模拟执行
    print("\n" + "=" * 60)
    print("🚀 Simulating Execution")
    print("=" * 60)
    
    # Step 1: 完成
    manager.start_step(1)
    manager.complete_step(1, "市场规模1500亿，增长25%", "企业AI渗透率提升")
    print(f"\n{manager.get_progress_display()}")
    
    # Step 2: 完成
    manager.start_step(2)
    manager.complete_step(2, "大模型+RAG+Agent架构", "私有化部署需求增长")
    print(f"\n{manager.get_progress_display()}")
    
    # Step 3: 完成
    manager.start_step(3)
    manager.complete_step(3, "Skill加载成功", None)
    print(f"\n{manager.get_progress_display()}")
    
    print("\n" + "=" * 60)
    print("📋 Final Todo.md")
    print("=" * 60)
    print(plan.to_markdown())
