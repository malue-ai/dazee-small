---
name: reminder
description: Set reminders using natural language. Integrates with platform-native reminder systems.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 自然语言提醒

用自然语言设置提醒，自动对接平台原生提醒系统（macOS 提醒事项 / Windows 任务计划 / 系统通知）。

## 使用场景

- 用户说「下午 3 点提醒我开会」「明天早上提醒我买牛奶」
- 用户说「半小时后提醒我喝水」「10 分钟后提醒我看邮件」
- 用户说「每天早上 9 点提醒我吃药」
- 用户说「周五前提醒我交报告」

## 执行方式

### 时间解析

将自然语言时间转换为具体时间点：

| 用户表达 | 解析结果 |
|---|---|
| 「下午 3 点」 | 今天 15:00 |
| 「明天早上」 | 明天 09:00 |
| 「半小时后」 | 当前时间 + 30min |
| 「周五」 | 本周五 09:00 |
| 「每天早上 9 点」 | 循环提醒，每日 09:00 |

### 平台对接

**macOS** — 优先使用 Apple Reminders（需 apple-reminders skill）：
```bash
osascript -e '
tell application "Reminders"
    set newReminder to make new reminder in list "提醒事项" with properties ¬
        {name:"开会", due date:date "2026-02-26 15:00:00", body:"下午 3 点的会议"}
end tell'
```

**Windows** — 使用任务计划程序（需 task-scheduler skill）或系统通知。

**通用回退** — 使用 `scheduled-tasks` skill 设置延时通知：
```
→ 到时间后调用系统通知 skill 发送提醒
```

### 流程

```
用户：下午 3 点提醒我开会
→ 解析：今天 15:00，提醒内容「开会」
→ 确认：好的，已设置提醒 ⏰ 今天 15:00 提醒你「开会」
→ 到时间后发送系统通知
```

## 输出规范

- 设置后立即确认，显示具体时间
- 模糊时间（如「下午」）默认为合理时间点并告知用户
- 循环提醒明确说明频率
- 提醒到期时通过系统通知推送，不仅在聊天中显示
