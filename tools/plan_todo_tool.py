"""
Plan/Todo Tool - 任务规划工具（纯计算版本）

设计原则：
1. Tool 只做计算，不持有状态
2. Plan 状态由上层（Service/Agent）管理，存储在 Conversation.metadata
3. 返回纯 JSON，前端自己渲染 UI
4. 解耦：Tool 不知道数据存在哪里

架构关系：
```
┌─────────────────────────────────────────────────────────────┐
│  Frontend                                                    │
│  └── 接收 JSON，自己渲染 UI（进度条/看板/时间线）             │
└─────────────────────────────────────────────────────────────┘
                              ↑ plan_json (纯数据)
┌─────────────────────────────────────────────────────────────┐
│  Service 层 (ChatService)                                    │
│  ├── 接收 Tool 输出                                          │
│  ├── 更新 Conversation.metadata.plan                         │
│  └── 持久化到数据库                                          │
└─────────────────────────────────────────────────────────────┘
                              ↑ tool_result (纯计算结果)
┌─────────────────────────────────────────────────────────────┐
│  plan_todo_tool (瘦工具)                                     │
│  └── 纯函数：接收参数 → 返回结果（不持有状态）                │
└─────────────────────────────────────────────────────────────┘
```

数据流：
1. LLM 调用 plan_todo tool: {"operation": "create_plan", "data": {...}}
2. Tool 执行（纯计算）：返回 plan_json
3. Service 层：更新 Conversation.metadata.plan，持久化
4. 前端：接收 JSON，自己渲染
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class PlanTodoTool:
    """
    Plan/Todo 工具 - 纯计算版本
    
    关键设计：
    1. 不持有状态：所有操作都是纯函数
    2. 接收 current_plan 作为参数
    3. 返回新的 plan_json
    4. 不生成 todo_md（前端自己渲染）
    """
    
    name = "plan_todo"
    description = """任务规划工具 - 纯计算版本。

操作类型:
- create_plan: 创建任务计划
  data 格式: {
    "goal": "任务目标（必需）",
    "steps": [
      {"action": "步骤1描述", "capability": "web_search"},
      {"action": "步骤2描述", "capability": "ppt_generation"}
    ]
  }
  ⚠️ steps 必须是对象数组，每个对象至少包含 action 字段！

- update_step: 更新步骤状态
  data 格式: {"step_index": 0, "status": "completed|failed|in_progress", "result": "结果"}

- add_step: 动态添加步骤
  data 格式: {"action": "动作", "purpose": "目的"}

- get_plan: 获取当前计划状态（无需 data）

返回格式:
- status: success/error
- plan: 更新后的计划 JSON（由调用方存储）

注意：此工具不持有状态，plan 由调用方管理。
"""
    
    def __init__(self, registry=None):
        """
        初始化工具
        
        Args:
            registry: CapabilityRegistry 实例（用于动态生成 Schema）
        """
        self._registry = registry
    
    def get_input_schema(self) -> Dict:
        """
        动态生成 input_schema
        
        Returns:
            Tool 的 input_schema（Claude API 格式）
        """
        # 从 Registry 动态获取分类 ID
        capability_enum = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capability_enum = self._registry.get_category_ids()
        
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
                    "enum": ["create_plan", "update_step", "add_step"]
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
                                        "description": "所需能力分类",
                                        "enum": capability_enum
                                    },
                                    "purpose": {
                                        "type": "string",
                                        "description": "步骤目的"
                                    }
                                },
                                "required": ["action"]
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
    
    async def execute(
        self,
        operation: str,
        data: Dict[str, Any] = None,
        current_plan: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行工具操作（纯计算）
        
        Args:
            operation: 操作类型
            data: 操作数据
            current_plan: 当前计划（从 Conversation.metadata 传入）
            
        Returns:
            {
                "status": "success/error",
                "plan": {...},  # 新的计划 JSON
                "message": "..."
            }
        """
        data = data or {}
        
        try:
            if operation == "create_plan":
                return self._create_plan(data)
            elif operation == "update_step":
                return self._update_step(data, current_plan)
            elif operation == "add_step":
                return self._add_step(data, current_plan)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown operation: {operation}",
                    "available": ["create_plan", "update_step", "add_step"]
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _create_plan(self, data: Dict) -> Dict:
        """
        创建任务计划
        
        Args:
            data: {goal, steps, information_gaps, user_query}
            
        Returns:
            {status, plan, message}
            
        Note:
            steps 支持两种格式：
            1. 字典数组: [{"action": "...", "purpose": "..."}, ...]
            2. 字符串数组: ["步骤1描述", "步骤2描述", ...] （会自动转换）
        """
        goal = data.get('goal', '')
        steps = data.get('steps', [])
        information_gaps = data.get('information_gaps', [])
        user_query = data.get('user_query', '')
        
        if not goal:
            return {"status": "error", "message": "Goal is required"}
        
        created_at = datetime.now().isoformat()
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 构建 plan 结构
        plan = {
            "task_id": task_id,
            "goal": goal,
            "user_query": user_query,
            "created_at": created_at,
            "updated_at": created_at,
            "information_gaps": information_gaps,
            "status": "executing",
            "current_step": 0,
            "total_steps": len(steps),
            "completed_steps": 0,
            "failed_steps": 0,
            "retry_count": 0,
            "steps": []
        }
        
        for i, step in enumerate(steps):
            # 兼容字符串和字典两种格式
            if isinstance(step, str):
                # 字符串格式：自动转换为标准字典格式
                step_data = {
                    "action": step,
                    "capability": "",
                    "query": "",
                    "purpose": "",
                    "expected_output": ""
                }
            else:
                # 字典格式：直接使用
                step_data = step
            
            plan["steps"].append({
                "step_id": i + 1,
                "index": i,
                "action": step_data.get('action', ''),
                "capability": step_data.get('capability', ''),
                "query": step_data.get('query', ''),
                "purpose": step_data.get('purpose', ''),
                "expected_output": step_data.get('expected_output', ''),
                "status": "pending" if i > 0 else "in_progress",
                "result": None,
                "retry_count": 0,
                "started_at": None,
                "completed_at": None
            })
        
        return {
            "status": "success",
            "message": f"Plan created: {goal}",
            "plan": plan
        }
    
    def _update_step(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        更新步骤状态
        
        Args:
            data: {step_index, status, result}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message}
        """
        if not current_plan:
            return {"status": "error", "message": "No active plan"}
        
        step_index = data.get('step_index')
        status = data.get('status', 'completed')
        result = data.get('result', '')
        
        if step_index is None:
            return {"status": "error", "message": "step_index is required"}
        
        if step_index >= len(current_plan.get('steps', [])):
            return {"status": "error", "message": f"Invalid step_index: {step_index}"}
        
        # 复制 plan（不修改原对象）
        plan = self._deep_copy_plan(current_plan)
        now = datetime.now().isoformat()
        plan["updated_at"] = now
        
        # 更新步骤
        step = plan['steps'][step_index]
        old_status = step['status']
        step['status'] = status
        step['result'] = result
        
        if status == 'in_progress' and not step.get('started_at'):
            step['started_at'] = now
        elif status in ['completed', 'failed']:
            step['completed_at'] = now
        
        # 处理重试
        if status == 'failed' and old_status != 'failed':
            step['retry_count'] = step.get('retry_count', 0) + 1
            plan['retry_count'] = plan.get('retry_count', 0) + 1
        
        # 统计
        plan['completed_steps'] = sum(1 for s in plan['steps'] if s['status'] == 'completed')
        plan['failed_steps'] = sum(1 for s in plan['steps'] if s['status'] == 'failed')
        
        # 自动推进 current_step
        if status == 'completed' and step_index == plan['current_step']:
            plan['current_step'] = min(step_index + 1, len(plan['steps']))
            # 标记下一步为 in_progress
            if plan['current_step'] < len(plan['steps']):
                plan['steps'][plan['current_step']]['status'] = 'in_progress'
                plan['steps'][plan['current_step']]['started_at'] = now
        
        # 检查是否全部完成
        all_done = all(s['status'] in ['completed', 'failed'] for s in plan['steps'])
        if all_done:
            if plan['completed_steps'] == len(plan['steps']):
                plan['status'] = 'completed'
            elif plan['failed_steps'] > 0:
                plan['status'] = 'partial'
        
        return {
            "status": "success",
            "message": f"Step {step_index + 1} → {status}",
            "plan": plan
        }
    
    def _add_step(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        动态添加步骤
        
        Args:
            data: {action, capability, purpose}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message}
        """
        if not current_plan:
            return {"status": "error", "message": "No active plan"}
        
        action = data.get('action', '')
        capability = data.get('capability', '')
        purpose = data.get('purpose', '')
        
        if not action:
            return {"status": "error", "message": "action is required"}
        
        # 复制 plan
        plan = self._deep_copy_plan(current_plan)
        now = datetime.now().isoformat()
        plan["updated_at"] = now
        
        new_index = len(plan['steps'])
        plan['steps'].append({
            "step_id": new_index + 1,
            "index": new_index,
            "action": action,
            "capability": capability,
            "purpose": purpose,
            "status": "pending",
            "result": None,
            "retry_count": 0,
            "started_at": None,
            "completed_at": None
        })
        plan['total_steps'] = len(plan['steps'])
        
        return {
            "status": "success",
            "message": f"Step {new_index + 1} added",
            "plan": plan
        }
    
    def _deep_copy_plan(self, plan: Dict) -> Dict:
        """深拷贝 plan 对象"""
        import copy
        return copy.deepcopy(plan)
    
    # ==================== 辅助方法（静态，供外部使用）====================
    
    @staticmethod
    def get_progress(plan: Optional[Dict]) -> Dict[str, Any]:
        """
        获取计划进度信息
        
        Args:
            plan: 计划对象
            
        Returns:
            {
                "has_plan": bool,
                "total": int,
                "completed": int,
                "failed": int,
                "progress": float (0-1),
                "current_step": int,
                "status": str
            }
        """
        if not plan:
            return {
                "has_plan": False,
                "total": 0,
                "completed": 0,
                "failed": 0,
                "progress": 0.0,
                "current_step": 0,
                "status": "none"
            }
        
        total = plan.get('total_steps', len(plan.get('steps', [])))
        completed = plan.get('completed_steps', 0)
        failed = plan.get('failed_steps', 0)
        
        return {
            "has_plan": True,
            "total": total,
            "completed": completed,
            "failed": failed,
            "progress": completed / total if total > 0 else 0.0,
            "current_step": plan.get('current_step', 0),
            "status": plan.get('status', 'executing'),
            "goal": plan.get('goal', '')
        }
    
    @staticmethod
    def get_current_step(plan: Optional[Dict]) -> Optional[Dict]:
        """获取当前步骤"""
        if not plan:
            return None
        idx = plan.get('current_step', 0)
        steps = plan.get('steps', [])
        if 0 <= idx < len(steps):
            return steps[idx]
        return None
    
    @staticmethod
    def get_context_for_llm(plan: Optional[Dict]) -> str:
        """
        获取精简的 Plan 上下文给 LLM
        
        减少 tokens 消耗
        """
        if not plan:
            return "[Plan] No active plan"
        
        total = plan.get('total_steps', 0)
        current_idx = plan.get('current_step', 0)
        completed = plan.get('completed_steps', 0)
        status = plan.get('status', 'executing')
        
        current_step = None
        steps = plan.get('steps', [])
        if 0 <= current_idx < len(steps):
            current_step = steps[current_idx]
        
        lines = [
            f"[Plan] {plan.get('goal', '')}",
            f"Status: {status} | Progress: {completed}/{total}"
        ]
        
        if current_step:
            lines.append(f"Current: {current_step.get('action', '')} → {current_step.get('purpose', '')}")
        
        return "\n".join(lines)


# 工具 Schema（用于 Claude API 注册）
PLAN_TODO_TOOL_SCHEMA = {
    "name": "plan_todo",
    "description": """任务规划工具。

操作：
- create_plan: 创建计划 {"goal": "目标", "steps": [{"action": "...", "purpose": "..."}]}
- update_step: 更新步骤 {"step_index": 0, "status": "completed|failed|in_progress", "result": "..."}
- add_step: 添加步骤 {"action": "...", "purpose": "..."}

返回新的 plan JSON，由调用方决定如何存储。""",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型",
                "enum": ["create_plan", "update_step", "add_step"]
            },
            "data": {
                "type": "object",
                "description": "操作数据"
            }
        },
        "required": ["operation"]
    }
}


def create_plan_todo_tool(registry=None) -> PlanTodoTool:
    """
    创建 Plan/Todo 工具实例
    
    Args:
        registry: CapabilityRegistry 实例（用于动态生成 Schema）
    
    Returns:
        PlanTodoTool 实例
    """
    return PlanTodoTool(registry=registry)
