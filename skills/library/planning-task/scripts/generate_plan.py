"""
生成结构化的任务计划（plan.json）

这个脚本被Claude通过code_execution调用，用于创建plan.json文件
"""

from typing import List, Dict, Any
from datetime import datetime
from uuid import uuid4


def generate_task_plan(
    user_intent: str,
    tasks: List[Dict[str, Any]],
    plan_id: str = None
) -> Dict[str, Any]:
    """
    生成结构化的任务计划
    
    Args:
        user_intent: 用户意图描述
        tasks: 任务列表，每个任务包含 id, description, dependencies
        plan_id: 计划ID（可选，不提供则自动生成）
        
    Returns:
        完整的plan.json结构
        
    Example:
        tasks = [
            {"id": "task_001", "description": "搜索数据", "dependencies": []},
            {"id": "task_002", "description": "生成配置", "dependencies": ["task_001"]}
        ]
        plan = generate_task_plan("制作PPT", tasks)
    """
    if not plan_id:
        plan_id = str(uuid4())
    
    # 验证任务结构
    task_dict = {}
    for task in tasks:
        if "id" not in task or "description" not in task:
            raise ValueError(f"Task missing required fields: {task}")
        
        task_id = task["id"]
        task_dict[task_id] = {
            "id": task_id,
            "description": task["description"],
            "status": "pending",
            "dependencies": task.get("dependencies", []),
            "result": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": task.get("metadata", {})
        }
    
    # 验证依赖关系
    for task_id, task in task_dict.items():
        for dep_id in task["dependencies"]:
            if dep_id not in task_dict:
                raise ValueError(f"Task {task_id} depends on non-existent task {dep_id}")
    
    # 检测循环依赖
    def has_circular_dependency(task_id, visited=None):
        if visited is None:
            visited = set()
        
        if task_id in visited:
            return True
        
        visited.add(task_id)
        for dep_id in task_dict[task_id]["dependencies"]:
            if has_circular_dependency(dep_id, visited.copy()):
                return True
        
        return False
    
    for task_id in task_dict:
        if has_circular_dependency(task_id):
            raise ValueError(f"Circular dependency detected involving task {task_id}")
    
    # 生成任务执行顺序（拓扑排序）
    task_order = []
    remaining = set(task_dict.keys())
    
    while remaining:
        # 找到所有依赖已满足的任务
        ready = [
            tid for tid in remaining
            if all(dep in task_order for dep in task_dict[tid]["dependencies"])
        ]
        
        if not ready:
            raise ValueError("Cannot resolve task dependencies")
        
        # 按ID排序以保证确定性
        ready.sort()
        task_order.extend(ready)
        remaining -= set(ready)
    
    # 构建完整计划
    plan = {
        "plan_id": plan_id,
        "user_intent": user_intent,
        "tasks": task_dict,
        "task_order": task_order,
        "metadata": {
            "total_tasks": len(task_dict),
            "created_at": datetime.now().isoformat()
        },
        "created_at": datetime.now().isoformat()
    }
    
    return plan


def update_task_status(
    plan: Dict[str, Any],
    task_id: str,
    status: str,
    result: Any = None
) -> Dict[str, Any]:
    """
    更新任务状态
    
    Args:
        plan: 现有计划
        task_id: 要更新的任务ID
        status: 新状态 (pending/in_progress/completed/failed/cancelled)
        result: 任务结果（可选）
        
    Returns:
        更新后的计划
    """
    valid_statuses = ["pending", "in_progress", "completed", "failed", "cancelled"]
    if status not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")
    
    if task_id not in plan["tasks"]:
        raise ValueError(f"Task {task_id} not found in plan")
    
    plan["tasks"][task_id]["status"] = status
    plan["tasks"][task_id]["updated_at"] = datetime.now().isoformat()
    
    if result is not None:
        plan["tasks"][task_id]["result"] = result
    
    # 更新元数据
    statuses = [task["status"] for task in plan["tasks"].values()]
    plan["metadata"]["completed"] = statuses.count("completed")
    plan["metadata"]["failed"] = statuses.count("failed")
    plan["metadata"]["in_progress"] = statuses.count("in_progress")
    plan["metadata"]["progress"] = plan["metadata"]["completed"] / plan["metadata"]["total_tasks"]
    
    return plan


# 使用示例（用于测试）
if __name__ == "__main__":
    # 示例：制作PPT的任务计划
    tasks = [
        {
            "id": "task_001",
            "description": "搜索AI客服市场数据",
            "dependencies": []
        },
        {
            "id": "task_002",
            "description": "生成SlideSpeak配置",
            "dependencies": ["task_001"]
        },
        {
            "id": "task_003",
            "description": "验证配置格式",
            "dependencies": ["task_002"]
        },
        {
            "id": "task_004",
            "description": "渲染PPT",
            "dependencies": ["task_003"]
        }
    ]
    
    plan = generate_task_plan("制作AI产品介绍PPT，包含市场数据", tasks)
    
    import json
    print(json.dumps(plan, ensure_ascii=False, indent=2))


