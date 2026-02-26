---
name: todoist
description: Manage Todoist tasks and projects via REST API.
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: local
    user_facing: true
---

# Todoist 任务管理

通过 Todoist REST API 管理任务、项目和标签。

## 使用场景

- 用户说「帮我在 Todoist 添加一个任务」「查看我的待办」
- 用户说「Todoist 里今天有什么任务」「把这个任务标记为完成」

## 前置条件

需要设置环境变量 `TODOIST_API_TOKEN`：
1. 访问 https://todoist.com/app/settings/integrations/developer → 复制 API Token
2. 设置：`export TODOIST_API_TOKEN="your-token"`

## 执行方式

### 获取任务

```bash
curl -s "https://api.todoist.com/rest/v2/tasks" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" | python3 -m json.tool
```

过滤今天的任务：
```bash
curl -s "https://api.todoist.com/rest/v2/tasks?filter=today" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```

### 创建任务

```bash
curl -s -X POST "https://api.todoist.com/rest/v2/tasks" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"任务内容","due_string":"tomorrow","priority":3}'
```

`priority`：1（普通）→ 4（紧急）。`due_string` 支持自然语言（"tomorrow", "next monday", "every day"）。

### 完成任务

```bash
curl -s -X POST "https://api.todoist.com/rest/v2/tasks/{task_id}/close" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```

### 获取项目

```bash
curl -s "https://api.todoist.com/rest/v2/projects" \
  -H "Authorization: Bearer $TODOIST_API_TOKEN"
```

## 输出规范

- 任务列表按截止日期和优先级排序
- 显示项目归属和标签
- 创建任务后确认并显示截止日期
