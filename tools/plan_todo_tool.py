"""
Plan/Todo Tool - 任务规划和待办管理工具

设计原则（参考图示架构）：
1. Plan/Todo CRUD 作为工具能力，在 capabilities.yaml 中定义
2. 存储到 WorkingMemory（Short Memory），避免多轮 LLM tokens 消耗
3. Agent 只提供工具，不做业务判断
4. LLM 通过系统提示词指导，自主调用工具管理任务

架构关系：
```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                      Agent                               │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │            WorkingMemory (Short)                   │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │ │
│  │  │ messages │  │plan.json │  │ todo.md  │         │ │
│  │  └──────────┘  └──────────┘  └──────────┘         │ │
│  └──────────────────────────────↑─────────────────────┘ │
│                                 │ (CRUD)                 │
│  ┌──────────────────────────────┴──────────────────────┐│
│  │              plan_todo Tool (CRUD)                  ││
│  │  - create_plan → 写入 Memory                        ││
│  │  - update_step → 更新 Memory                        ││
│  │  - get_plan → 读取 Memory                           ││
│  │  - clear → 清空 Memory                              ││
│  └─────────────────────────────────────────────────────┘│
│                                                          │
│  LLM 通过调用 plan_todo 工具来管理计划                    │
│  不需要每次都在 input/output 中传递完整计划                │
└─────────────────────────────────────────────────────────┘
```

会话生命周期：
- 会话开始时 Agent 传入 WorkingMemory 实例
- 会话期间 LLM 通过 plan_todo 工具 CRUD
- 会话结束后 WorkingMemory 自动清除
"""

from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime

# 避免循环导入
if TYPE_CHECKING:
    from agent_v3.core.memory import WorkingMemory


class PlanTodoTool:
    """
    Plan/Todo 工具 - 与 WorkingMemory 集成
    
    关键改进：
    1. 数据存储在 WorkingMemory（Short Memory）中
    2. 避免多轮 LLM input/output 的 tokens 消耗
    3. Agent 通过传入 memory 实例来共享状态
    """
    
    name = "plan_todo"
    description = """任务规划和待办管理工具 - 存储到 Short Memory。

核心功能：
- 将 plan.json 和 todo.md 存储到会话级短期记忆
- 避免每次 LLM 调用都需要传递完整计划
- 支持 CRUD 操作

操作类型:
- create_plan: 创建任务计划 {"goal": "目标", "steps": [{"action": "动作", "purpose": "目的"}]}
- update_step: 更新步骤状态 {"step_index": 0, "status": "completed|failed|in_progress", "result": "结果"}
- get_plan: 获取当前计划（从 Short Memory 读取）
- add_step: 动态添加步骤 {"action": "动作", "purpose": "目的"}
- clear: 清除计划

返回格式：
- plan_json: JSON 格式的计划（内部 RVR 调度）
- todo_md: Markdown 格式的进度（用户展示 + 状态追踪）
- display: 终端友好的即时反馈

示例:
1. 创建计划: {"operation": "create_plan", "data": {"goal": "生成报告", "steps": [{"action": "search", "purpose": "收集信息"}]}}
2. 更新步骤: {"operation": "update_step", "data": {"step_index": 0, "status": "completed", "result": "找到5篇文章"}}
3. 获取计划: {"operation": "get_plan"}
"""
    
    def __init__(self, memory: 'WorkingMemory' = None, registry = None):
        """
        初始化工具
        
        Args:
            memory: WorkingMemory 实例（可选，不传则使用内部存储）
            registry: CapabilityRegistry 实例（用于动态生成 Schema）
        """
        self._memory = memory  # 外部 Memory 实例
        self._registry = registry  # 🆕 Registry 实例（用于获取分类）
        # 内部存储（当没有传入 memory 时使用）
        self._plan: Optional[Dict] = None
        self._created_at: Optional[str] = None
    
    def set_memory(self, memory: 'WorkingMemory'):
        """设置 Memory 实例（Agent 初始化时调用）"""
        self._memory = memory
    
    def reset(self):
        """重置（新会话开始时调用）"""
        if self._memory:
            self._memory.clear_plan()
        else:
            self._plan = None
            self._created_at = None
    
    def get_input_schema(self) -> Dict:
        """
        🆕 动态生成 input_schema（从 Registry 获取分类列表）
        
        这样只需修改 capabilities.yaml，Schema 会自动更新。
        
        Returns:
            Tool 的 input_schema（Claude API 格式）
        """
        # 🆕 从 Registry 动态获取分类 ID（如果可用）
        capability_enum = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capability_enum = self._registry.get_category_ids()
        
        # 如果没有 Registry，使用默认值
        if not capability_enum:
            capability_enum = [
                "web_search", "ppt_generation", "document_creation",
                "data_analysis", "file_operations", "code_execution",
                "api_calling", "task_planning"
            ]
        
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": ["create_plan", "get_plan", "update_step", "add_step", "clear"]
                },
                "data": {
                    "type": "object",
                    "description": "操作数据",
                    "properties": {
                        "goal": {
                            "type": "string",
                            "description": "任务目标（create_plan 时必需）"
                        },
                        "steps": {
                            "type": "array",
                            "description": "步骤列表（create_plan 时必需）",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string",
                                        "description": "步骤动作描述"
                                    },
                                    "capability": {
                                        "type": "string",
                                        "description": "所需能力分类（从 capability_categories 中选择）",
                                        "enum": capability_enum  # 🆕 动态生成
                                    },
                                    "purpose": {
                                        "type": "string",
                                        "description": "步骤目的"
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed", "failed"]
                                    }
                                },
                                "required": ["action", "capability"]
                            }
                        },
                        "step_index": {
                            "type": "integer",
                            "description": "步骤索引（update_step 时必需）"
                        },
                        "status": {
                            "type": "string",
                            "description": "步骤状态（update_step 时必需）",
                            "enum": ["pending", "in_progress", "completed", "failed"]
                        },
                        "result": {
                            "type": "string",
                            "description": "步骤结果（update_step 时可选）"
                        }
                    }
                }
            },
            "required": ["operation"]
        }
    
    @property
    def _current_plan(self) -> Optional[Dict]:
        """获取当前计划（从 Memory 或内部存储）"""
        if self._memory:
            return self._memory.get_plan()
        return self._plan
    
    @_current_plan.setter
    def _current_plan(self, value: Optional[Dict]):
        """设置当前计划（写入 Memory 或内部存储）"""
        if self._memory:
            if value is None:
                self._memory.clear_plan()
            else:
                # 同时生成 todo_md 并写入
                todo_md = self._generate_todo_md(value)
                self._memory.set_plan(value, todo_md)
        else:
            self._plan = value
    
    def _generate_todo_md(self, plan: Dict) -> str:
        """
        根据 plan.json 生成 todo.md
        
        首行包含状态元数据，供 Agent 快速读取
        """
        if not plan:
            return "<!-- Status: none | Step: 0/0 | Retry: 0 -->\n\n# 📋 任务进度\n\n无活跃计划"
        
        total = plan.get('total_steps', len(plan.get('steps', [])))
        current = plan.get('current_step', 0)
        retry = plan.get('retry_count', 0)
        status = plan.get('status', 'executing')
        completed = sum(1 for s in plan.get('steps', []) if s.get('status') == 'completed')
        
        # 状态元数据（首行注释）
        meta_line = f"<!-- Status: {status} | Step: {current + 1}/{total} | Retry: {retry} -->"
        
        lines = [
            meta_line,
            "",
            "# 📋 任务进度",
            "",
            f"🎯 **目标**: {plan.get('goal', '')}",
            "",
            "## To-do List",
            ""
        ]
        
        # 步骤列表
        for step in plan.get('steps', []):
            step_status = step.get('status', 'pending')
            result = step.get('result', '')
            
            # 状态图标和复选框
            if step_status == 'completed':
                icon = "✅"
                checkbox = "[x]"
                suffix = f" - {result}" if result else ""
            elif step_status == 'in_progress':
                icon = "🔄"
                checkbox = "[ ]"
                suffix = " - 执行中..."
            elif step_status == 'failed':
                icon = "❌"
                checkbox = "[ ]"
                suffix = f" - 失败: {result}" if result else " - 失败"
            else:  # pending
                icon = "○"
                checkbox = "[ ]"
                suffix = ""
            
            # 显示文本
            action = step.get('action', '')
            purpose = step.get('purpose', '')
            display_text = f"{action}" if action else purpose
            if purpose and action:
                display_text = f"{action} → {purpose}"
            
            step_num = step.get('step_id', step.get('index', 0) + 1)
            lines.append(f"- {checkbox} {icon} Step {step_num}: {display_text}{suffix}")
        
        # 进度条
        progress = completed / total if total > 0 else 0
        bar_width = 20
        filled = int(bar_width * progress)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        lines.extend([
            "",
            "---",
            f"**进度**: [{bar}] {progress*100:.0f}% ({completed}/{total})",
            f"**阶段**: {status}"
        ])
        
        return "\n".join(lines)
    
    def execute(self, operation: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行工具操作（CRUD）
        
        数据写入 WorkingMemory（Short Memory），避免多轮 tokens 消耗
        
        Args:
            operation: 操作类型
            data: 操作数据
            
        Returns:
            操作结果（包含 plan_json 和 todo_md）
        """
        data = data or {}
        
        try:
            if operation == "create_plan":
                return self._create_plan(data)
            elif operation == "update_step":
                return self._update_step(data)
            elif operation == "get_plan":
                return self._get_plan()
            elif operation == "add_step":
                return self._add_step(data)
            elif operation == "clear":
                return self._clear()
            else:
                return {
                    "status": "error",
                    "message": f"Unknown operation: {operation}",
                    "available": ["create_plan", "update_step", "get_plan", "add_step", "clear"]
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _create_plan(self, data: Dict) -> Dict:
        """
        创建任务计划（Create）
        
        写入 WorkingMemory：
        - plan.json 结构（内部 RVR 调度）
        - todo.md 展示（状态 + 用户进度）
        """
        goal = data.get('goal', '')
        steps = data.get('steps', [])
        information_gaps = data.get('information_gaps', [])
        user_query = data.get('user_query', '')
        
        if not goal:
            return {"status": "error", "message": "Goal is required"}
        
        self._created_at = datetime.now().isoformat()
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 构建 plan.json 结构
        plan = {
            "task_id": task_id,
            "goal": goal,
            "user_query": user_query,
            "created_at": self._created_at,
            "information_gaps": information_gaps,
            "status": "executing",
            "current_step": 0,
            "total_steps": len(steps),
            "retry_count": 0,
            "steps": []
        }
        
        for i, step in enumerate(steps):
            plan["steps"].append({
                "step_id": i + 1,
                "index": i,
                "action": step.get('action', ''),
                "query": step.get('query', ''),
                "purpose": step.get('purpose', ''),
                "expected_output": step.get('expected_output', ''),
                "status": "pending",
                "result": None,
                "retry_count": 0
            })
        
        # 标记第一步为 in_progress
        if plan["steps"]:
            plan["steps"][0]["status"] = "in_progress"
        
        # 写入 Memory（通过 property setter）
        self._current_plan = plan
        
        # 生成 todo_md
        todo_md = self._generate_todo_md(plan)
        
        return {
            "status": "success",
            "message": f"Plan created and stored in Short Memory: {goal}",
            "plan_json": plan,
            "todo_md": todo_md,
            "display": self._get_display()
        }
    
    def _update_step(self, data: Dict) -> Dict:
        """
        更新步骤状态（Update）
        
        更新 WorkingMemory 中的 plan.json 和 todo.md
        """
        plan = self._current_plan
        if not plan:
            return {"status": "error", "message": "No active plan in Short Memory"}
        
        step_index = data.get('step_index')
        status = data.get('status', 'completed')
        result = data.get('result', '')
        
        if step_index is None:
            return {"status": "error", "message": "step_index is required"}
        
        if step_index >= len(plan['steps']):
            return {"status": "error", "message": f"Invalid step_index: {step_index}"}
        
        # 更新步骤
        step = plan['steps'][step_index]
        old_status = step['status']
        step['status'] = status
        step['result'] = result
        step['updated_at'] = datetime.now().isoformat()
        
        # 处理重试
        if status == 'failed' and old_status != 'failed':
            step['retry_count'] = step.get('retry_count', 0) + 1
            plan['retry_count'] = plan.get('retry_count', 0) + 1
        
        # 自动推进 current_step
        if status == 'completed' and step_index == plan['current_step']:
            plan['current_step'] = min(step_index + 1, len(plan['steps']))
            # 标记下一步为 in_progress
            if plan['current_step'] < len(plan['steps']):
                plan['steps'][plan['current_step']]['status'] = 'in_progress'
        
        # 检查是否全部完成
        all_done = all(s['status'] in ['completed', 'failed'] for s in plan['steps'])
        if all_done:
            completed = sum(1 for s in plan['steps'] if s['status'] == 'completed')
            plan['status'] = 'completed' if completed == len(plan['steps']) else 'partial'
        
        # 写回 Memory
        self._current_plan = plan
        
        # 生成 todo_md
        todo_md = self._generate_todo_md(plan)
        
        return {
            "status": "success",
            "message": f"Step {step_index + 1} → {status} (updated in Short Memory)",
            "plan_json": plan,
            "todo_md": todo_md,
            "display": self._get_display()
        }
    
    def _get_plan(self) -> Dict:
        """
        获取当前计划（Read）
        
        从 WorkingMemory 读取 plan.json 和 todo.md
        """
        plan = self._current_plan
        
        if not plan:
            return {
                "status": "success",
                "has_plan": False,
                "message": "No active plan in Short Memory. Use create_plan to start.",
                "todo_md": "<!-- Status: none | Step: 0/0 | Retry: 0 -->\n\n# 📋 任务进度\n\n无活跃计划"
            }
        
        todo_md = self._generate_todo_md(plan)
        
        return {
            "status": "success",
            "has_plan": True,
            "plan_json": plan,
            "todo_md": todo_md,
            "display": self._get_display(),
            "context": self._get_plan_context()  # 🆕 精简上下文给 LLM
        }
    
    def _get_plan_context(self) -> str:
        """
        获取精简的 Plan 上下文给 LLM
        
        避免传递完整的 plan.json，减少 tokens 消耗
        """
        plan = self._current_plan
        if not plan:
            return "[Plan Context] No active plan"
        
        total = len(plan.get("steps", []))
        current_idx = plan.get("current_step", 0)
        status = plan.get("status", "executing")
        
        current_step = None
        if 0 <= current_idx < total:
            current_step = plan["steps"][current_idx]
        
        lines = [
            f"[Plan Context]",
            f"Goal: {plan.get('goal', '')}",
            f"Status: {status} | Step: {current_idx + 1}/{total}"
        ]
        
        if current_step:
            action = current_step.get("action", "")
            purpose = current_step.get("purpose", "")
            lines.append(f"Current: {action} → {purpose}")
        
        return "\n".join(lines)
    
    def _add_step(self, data: Dict) -> Dict:
        """动态添加步骤（Update）"""
        plan = self._current_plan
        if not plan:
            return {"status": "error", "message": "No active plan in Short Memory"}
        
        action = data.get('action', '')
        purpose = data.get('purpose', '')
        
        new_index = len(plan['steps'])
        plan['steps'].append({
            "step_id": new_index + 1,
            "index": new_index,
            "action": action,
            "purpose": purpose,
            "status": "pending",
            "result": None
        })
        plan['total_steps'] = len(plan['steps'])
        
        # 写回 Memory
        self._current_plan = plan
        
        return {
            "status": "success",
            "message": f"Step {new_index + 1} added to Short Memory",
            "plan_json": plan,
            "todo_md": self._generate_todo_md(plan),
            "display": self._get_display()
        }
    
    def _clear(self) -> Dict:
        """清除计划（Delete）"""
        self._current_plan = None
        self._created_at = None
        return {"status": "success", "message": "Plan cleared from Short Memory"}
    
    # _get_todo_md 已被 _generate_todo_md 替代，保留为兼容方法
    def _get_todo_md(self) -> str:
        """获取 todo.md（兼容方法，已被 _generate_todo_md 替代）"""
        plan = self._current_plan
        return self._generate_todo_md(plan)
    
    def _get_display(self) -> str:
        """
        生成进度显示（终端友好格式）
        
        用于即时反馈，与 todo.md 内容一致但格式不同
        """
        plan = self._current_plan
        if not plan:
            return "No active plan in Short Memory"
        
        total = plan.get('total_steps', len(plan.get('steps', [])))
        completed = sum(1 for s in plan.get('steps', []) if s.get('status') == 'completed')
        
        lines = [
            "┌─────────────────────────────────────",
            f"│ 🎯 Plan: {plan.get('goal', '')}",
            "├─────────────────────────────────────",
            f"│ 📋 To-dos ({completed}/{total})",
            "│"
        ]
        
        for step in plan.get('steps', []):
            status = step.get('status', 'pending')
            icon = {
                'completed': '✅',
                'in_progress': '🔄',
                'failed': '❌',
                'pending': '○'
            }.get(status, '○')
            
            # 显示 action 或 purpose
            action = step.get('action', '')
            purpose = step.get('purpose', '')
            display_text = f"{action}" if action else purpose
            if purpose and action:
                display_text = f"{action} → {purpose}"
            
            lines.append(f"│ {icon} {display_text}")
        
        # 进度条
        progress = completed / total if total > 0 else 0
        bar_width = 20
        filled = int(bar_width * progress)
        bar = '█' * filled + '░' * (bar_width - filled)
        
        lines.extend([
            "│",
            f"│ [{bar}] {progress*100:.0f}%",
            "└─────────────────────────────────────"
        ])
        
        return "\n".join(lines)
    
    def has_plan(self) -> bool:
        """检查是否有活跃计划"""
        return self._current_plan is not None
    
    def get_current_step(self) -> Optional[Dict]:
        """获取当前步骤"""
        plan = self._current_plan
        if not plan:
            return None
        idx = plan.get('current_step', 0)
        steps = plan.get('steps', [])
        if idx < len(steps):
            return steps[idx]
        return None
    
    def get_full_display(self) -> str:
        """获取完整的进度展示（包含 todo.md）"""
        plan = self._current_plan
        if not plan:
            return "No active plan in Short Memory"
        
        return self._generate_todo_md(plan)
    
    def __call__(self, **kwargs) -> Dict[str, Any]:
        """支持直接调用"""
        operation = kwargs.get('operation', 'get_plan')
        data = kwargs.get('data', {})
        return self.execute(operation, data)


# 工具Schema（用于Claude API注册）
PLAN_TODO_TOOL_SCHEMA = {
    "name": "plan_todo",
    "description": """任务规划工具 - 双文件状态管理。

生成两种格式：
- plan.json: JSON格式，用于内部RVR调度
- todo.md: Markdown格式，用于状态追踪和用户进度展示

何时使用：
- 复杂任务需要分步骤执行（Complexity = medium/complex）
- 需要跟踪多个步骤的进度
- 需要记录中间结果和状态

操作：
- create_plan: 创建计划 {"goal": "目标", "steps": [{"action": "...", "purpose": "..."}]}
- update_step: 更新步骤 {"step_index": 0, "status": "completed|failed|in_progress", "result": "..."}
- get_plan: 获取计划（返回 plan_json + todo_md）
- add_step: 动态添加步骤 {"action": "...", "purpose": "..."}
- clear: 清除计划

返回格式：
- plan_json: 完整的 JSON 计划结构
- todo_md: Markdown 格式的进度展示（首行包含状态元数据）
- display: 终端友好的即时反馈

注意：计划存储在会话内存中，会话结束后自动清除。""",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型",
                "enum": ["create_plan", "update_step", "get_plan", "add_step", "clear"]
            },
            "data": {
                "type": "object",
                "description": "操作数据",
                "properties": {
                    "goal": {"type": "string", "description": "任务目标（create_plan）"},
                    "steps": {"type": "array", "description": "步骤列表（create_plan）"},
                    "information_gaps": {"type": "array", "description": "缺失信息列表（create_plan）"},
                    "step_index": {"type": "integer", "description": "步骤索引（update_step）"},
                    "status": {"type": "string", "description": "步骤状态（update_step）"},
                    "result": {"type": "string", "description": "步骤结果（update_step）"},
                    "action": {"type": "string", "description": "动作（add_step）"},
                    "purpose": {"type": "string", "description": "目的（add_step）"}
                }
            }
        },
        "required": ["operation"]
    }
}


def create_plan_todo_tool(memory: 'WorkingMemory' = None, registry = None) -> PlanTodoTool:
    """
    创建 Plan/Todo 工具实例
    
    Args:
        memory: WorkingMemory 实例（可选）
                传入后，数据将存储到 Short Memory，避免多轮 tokens 消耗
        registry: CapabilityRegistry 实例（用于动态生成 Schema）
    
    Returns:
        PlanTodoTool 实例
    """
    return PlanTodoTool(memory=memory, registry=registry)
