---
name: planning-task
description: Generates structured task plans and todo lists for complex multi-step projects. Use when the user needs to break down work into organized tasks with dependencies, or when creating project plans, checklists, or work breakdowns.
metadata:
  level: 1                     # L1 核心级，框架自动启用，不暴露给运营配置
  priority: medium
  preferred_for:
    - project planning
    - task breakdown
    - work organization
    - multi-step tasks
---

# Task Planning Skill

Breaks down complex user requests into structured, trackable task plans with dependencies.

## When to Use

Load this skill when:
- User has a multi-step request (e.g., "制作产品PPT需要市场数据")
- Need to organize work into phases/steps
- User mentions: "plan", "tasks", "steps", "breakdown", "organize"
- Complex deliverable requiring coordination

## Capabilities

1. **Task Decomposition**: Break complex goals into atomic tasks
2. **Dependency Management**: Identify which tasks must complete before others
3. **Progress Tracking**: Generate plan.json and todo.md for monitoring
4. **Format Generation**: Create both machine-readable (JSON) and human-readable (Markdown) formats

## Workflow

### Phase 1: Analyze User Intent

Understand the goal and identify key deliverables:
```python
# Use code_execution to analyze
user_intent = "制作AI产品介绍PPT，包含市场数据"

# Identify components
components = [
    "搜索市场数据",
    "分析竞品信息", 
    "设计PPT结构",
    "生成SlideSpeak配置",
    "验证配置",
    "渲染PPT"
]
```

### Phase 2: Generate Structured Plan

Use the helper script to create plan.json:
```python
# Load and execute the plan generator
with open('skills/library/planning-task/scripts/generate_plan.py', 'r') as f:
    exec(f.read())

plan = generate_task_plan(
    user_intent="制作AI产品介绍PPT，包含市场数据",
    tasks=[
        {"id": "task_001", "description": "搜索AI客服市场数据", "dependencies": []},
        {"id": "task_002", "description": "生成PPT配置", "dependencies": ["task_001"]},
        {"id": "task_003", "description": "渲染PPT", "dependencies": ["task_002"]}
    ]
)

# Save plan.json
import json
with open('workspace/plan.json', 'w') as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)
```

### Phase 3: Generate Human-Readable Todo

Create todo.md for user visibility:
```python
# Load and execute the todo generator
with open('skills/library/planning-task/scripts/generate_todo.py', 'r') as f:
    exec(f.read())

todo_markdown = generate_todo_markdown(plan)

# Save todo.md
with open('workspace/todo.md', 'w') as f:
    f.write(todo_markdown)
```

### Phase 4: Execute and Update

As tasks complete, update the plan:
```python
# Update task status
plan["tasks"]["task_001"]["status"] = "completed"
plan["tasks"]["task_001"]["result"] = {"data": [...]}

# Re-save
with open('workspace/plan.json', 'w') as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)

# Regenerate todo.md
todo_markdown = generate_todo_markdown(plan)
with open('workspace/todo.md', 'w') as f:
    f.write(todo_markdown)
```

## Output Files

**plan.json** (machine-readable):
```json
{
  "plan_id": "plan_001",
  "user_intent": "制作AI产品介绍PPT",
  "tasks": {
    "task_001": {
      "id": "task_001",
      "description": "搜索市场数据",
      "status": "pending",
      "dependencies": [],
      "result": null
    }
  }
}
```

**todo.md** (human-readable):
```markdown
# Task Plan: 制作AI产品介绍PPT

Progress: 0/3 (0%)

## Tasks
⬜ **task_001**: 搜索市场数据
⬜ **task_002**: 生成PPT配置
   - Dependencies: task_001
⬜ **task_003**: 渲染PPT
   - Dependencies: task_002
```

## Task Decomposition Guidelines

1. **Atomic Tasks**: Each task should be a single, executable action
2. **Dependencies**: Identify sequential vs. parallel tasks
3. **Verifiable**: Each task should have clear completion criteria
4. **Balanced**: Aim for 3-8 tasks (not too granular, not too broad)

**Good Example**:
- ✅ "搜索AI客服市场数据（2024年）"
- ✅ "使用code_execution生成SlideSpeak配置"
- ✅ "调用slidespeak_render渲染PPT"

**Bad Example**:
- ❌ "完成PPT" (too broad)
- ❌ "打开文件" (too granular)
- ❌ "准备数据" (vague)

## Scripts

- `scripts/generate_plan.py`: Creates structured plan.json from task list
- `scripts/generate_todo.py`: Converts plan.json to Markdown todo list
- `scripts/update_task.py`: Updates task status and regenerates files
- `resources/plan_template.json`: Template structure for plans

## Best Practices

1. **Always generate both formats**: plan.json for tracking, todo.md for user
2. **Update files after each task**: Keep progress visible
3. **Validate dependencies**: Ensure no circular dependencies
4. **Clear descriptions**: Use action verbs (搜索、生成、验证、渲染)
5. **Realistic granularity**: 3-8 tasks for most projects

## Limitations

- Cannot predict task duration
- Assumes linear dependencies (no complex DAGs)
- User must approve final plan before execution
- Some tasks may need further breakdown during execution

