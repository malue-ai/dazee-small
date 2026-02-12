"""
生成Markdown格式的Todo列表（todo.md）

这个脚本被Claude通过code_execution调用，用于创建可读的todo.md文件
"""

from typing import Dict, Any


def generate_todo_markdown(plan: Dict[str, Any]) -> str:
    """
    从plan.json生成Markdown格式的Todo列表
    
    Args:
        plan: 任务计划（来自generate_plan.py）
        
    Returns:
        Markdown格式的字符串
    """
    lines = []
    
    # 标题
    lines.append(f"# Task Plan: {plan['user_intent']}")
    lines.append("")
    
    # 进度摘要
    metadata = plan.get("metadata", {})
    total = metadata.get("total_tasks", len(plan["tasks"]))
    completed = metadata.get("completed", 0)
    progress = metadata.get("progress", 0.0)
    
    lines.append(f"Progress: {completed}/{total} ({progress*100:.0f}%)")
    lines.append("")
    
    # 统计信息
    if metadata.get("in_progress", 0) > 0:
        lines.append(f"⏳ In Progress: {metadata['in_progress']}")
    if metadata.get("failed", 0) > 0:
        lines.append(f"❌ Failed: {metadata['failed']}")
    if lines[-1] != "":
        lines.append("")
    
    # 任务列表
    lines.append("## Tasks")
    lines.append("")
    
    task_order = plan.get("task_order", list(plan["tasks"].keys()))
    
    for task_id in task_order:
        task = plan["tasks"][task_id]
        
        # 状态图标
        status = task.get("status", "pending")
        icon_map = {
            "completed": "✅",
            "in_progress": "🔄",
            "failed": "❌",
            "cancelled": "⏸️",
            "pending": "⬜"
        }
        icon = icon_map.get(status, "⬜")
        
        # 任务描述
        description = task["description"]
        lines.append(f"{icon} **{task_id}**: {description}")
        
        # 依赖关系
        dependencies = task.get("dependencies", [])
        if dependencies:
            deps_str = ", ".join(dependencies)
            lines.append(f"   - Dependencies: {deps_str}")
        
        # 状态详情
        if status != "pending":
            lines.append(f"   - Status: {status}")
        
        # 结果（如果有）
        result = task.get("result")
        if result:
            result_str = str(result)
            if len(result_str) > 100:
                result_str = result_str[:100] + "..."
            lines.append(f"   - Result: {result_str}")
        
        lines.append("")
    
    # 创建时间
    created_at = plan.get("created_at", "")
    if created_at:
        lines.append("---")
        lines.append(f"Created: {created_at}")
    
    return "\n".join(lines)


def generate_todo_with_sections(plan: Dict[str, Any]) -> str:
    """
    生成带分组的Todo列表（按状态分组）
    
    Args:
        plan: 任务计划
        
    Returns:
        分组的Markdown字符串
    """
    lines = []
    
    # 标题和进度
    lines.append(f"# Task Plan: {plan['user_intent']}")
    lines.append("")
    
    metadata = plan.get("metadata", {})
    total = metadata.get("total_tasks", len(plan["tasks"]))
    completed = metadata.get("completed", 0)
    progress = metadata.get("progress", 0.0)
    
    lines.append(f"Progress: {completed}/{total} ({progress*100:.0f}%)")
    lines.append("")
    
    # 按状态分组
    tasks_by_status = {
        "in_progress": [],
        "pending": [],
        "completed": [],
        "failed": [],
        "cancelled": []
    }
    
    for task_id, task in plan["tasks"].items():
        status = task.get("status", "pending")
        tasks_by_status[status].append((task_id, task))
    
    # 进行中的任务
    if tasks_by_status["in_progress"]:
        lines.append("## 🔄 In Progress")
        lines.append("")
        for task_id, task in tasks_by_status["in_progress"]:
            lines.append(f"- **{task_id}**: {task['description']}")
        lines.append("")
    
    # 待办任务
    if tasks_by_status["pending"]:
        lines.append("## ⬜ Pending")
        lines.append("")
        for task_id, task in tasks_by_status["pending"]:
            deps = task.get("dependencies", [])
            deps_str = f" (depends on: {', '.join(deps)})" if deps else ""
            lines.append(f"- **{task_id}**: {task['description']}{deps_str}")
        lines.append("")
    
    # 已完成的任务
    if tasks_by_status["completed"]:
        lines.append("## ✅ Completed")
        lines.append("")
        for task_id, task in tasks_by_status["completed"]:
            lines.append(f"- **{task_id}**: {task['description']}")
        lines.append("")
    
    # 失败的任务
    if tasks_by_status["failed"]:
        lines.append("## ❌ Failed")
        lines.append("")
        for task_id, task in tasks_by_status["failed"]:
            lines.append(f"- **{task_id}**: {task['description']}")
            if task.get("result"):
                lines.append(f"  - Error: {task['result']}")
        lines.append("")
    
    return "\n".join(lines)


# 使用示例（用于测试）
if __name__ == "__main__":
    import json
    
    # 模拟计划数据
    plan = {
        "plan_id": "plan_001",
        "user_intent": "制作AI产品介绍PPT，包含市场数据",
        "tasks": {
            "task_001": {
                "id": "task_001",
                "description": "搜索AI客服市场数据",
                "status": "completed",
                "dependencies": [],
                "result": {"data_found": True}
            },
            "task_002": {
                "id": "task_002",
                "description": "生成SlideSpeak配置",
                "status": "in_progress",
                "dependencies": ["task_001"],
                "result": None
            },
            "task_003": {
                "id": "task_003",
                "description": "渲染PPT",
                "status": "pending",
                "dependencies": ["task_002"],
                "result": None
            }
        },
        "task_order": ["task_001", "task_002", "task_003"],
        "metadata": {
            "total_tasks": 3,
            "completed": 1,
            "in_progress": 1,
            "progress": 0.33
        },
        "created_at": "2025-01-20T10:00:00"
    }
    
    # 生成标准格式
    print("=== Standard Format ===")
    print(generate_todo_markdown(plan))
    print()
    
    # 生成分组格式
    print("=== Grouped Format ===")
    print(generate_todo_with_sections(plan))


