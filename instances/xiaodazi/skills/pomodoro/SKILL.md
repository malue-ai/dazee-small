---
name: pomodoro
description: Pomodoro timer with focus sessions, break management, and task tracking. Data stored locally.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 番茄钟

帮助用户使用番茄工作法管理专注时间，追踪每日完成的番茄数和任务进度。

## 使用场景

- 用户说「开始一个番茄钟」「我要专注 25 分钟」
- 用户说「今天完成了几个番茄」「看看我的专注记录」
- 用户说「帮我用番茄钟写论文」（结合具体任务）

## 执行方式

### 数据存储

在用户数据目录维护 `~/Documents/xiaodazi/pomodoro.json`：

```json
{
  "settings": {
    "focus_minutes": 25,
    "short_break": 5,
    "long_break": 15,
    "long_break_after": 4
  },
  "today": {
    "date": "2026-02-26",
    "completed": 3,
    "total_focus_minutes": 75,
    "sessions": [
      {"task": "写论文", "start": "09:00", "end": "09:25", "completed": true},
      {"task": "写论文", "start": "09:30", "end": "09:55", "completed": true},
      {"task": "回邮件", "start": "10:15", "end": "10:40", "completed": true}
    ]
  }
}
```

### 核心流程

**开始番茄**：
```
用户：开始一个番茄钟，任务是写周报
→ 记录开始时间和任务名
→ 回复：🍅 番茄钟开始！任务：写周报，25 分钟后提醒你休息。
→ 通过 scheduled-tasks 或系统通知在 25 分钟后提醒
```

**番茄完成**：
```
→ 发送通知：🍅 番茄完成！休息 5 分钟吧。
→ 记录完成，更新计数
→ 每 4 个番茄后建议长休息（15 分钟）
```

**查看记录**：
```
用户：今天的番茄钟情况
→ 今日已完成 5 个番茄（125 分钟）
→ 任务分布：写论文 3个 | 回邮件 1个 | 代码审查 1个
```

### 通知方式

根据平台调用对应的通知 skill：
- macOS → `macos-notification`
- Windows → `windows-notification`
- Linux → `linux-notification`

## 输出规范

- 开始时简洁确认，不打断用户思路
- 完成时给予正面反馈 + 休息建议
- 日报使用表格展示任务分布
- 鼓励但不施压，中断番茄时不批评
