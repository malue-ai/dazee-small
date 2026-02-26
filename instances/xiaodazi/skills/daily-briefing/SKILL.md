---
name: daily-briefing
description: Generate a personalized daily briefing with weather, calendar events, tasks, and news highlights.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 每日简报

生成个性化的每日简报，整合天气、日程、待办、新闻要点，帮助用户快速了解今日安排。

## 使用场景

- 用户说「今天有什么安排」「早安」「帮我看看今天的日程」
- 用户在早上打开应用，希望快速了解当天概况
- 用户说「今天需要关注什么」

## 执行方式

按以下模块逐步收集信息，然后整合为简报。

### 信息收集流程

```
1. 天气 → 调用 weather skill（wttr.in）
2. 日历 → 调用 apple-calendar / outlook-cli / gog（按平台）
3. 待办 → 调用 apple-reminders / things-mac / trello / todoist（按用户配置）
4. 新闻 → 调用 ddg-search 搜索当日热点（可选）
```

每个模块独立获取，某个模块失败不影响其他模块。

### 简报模板

```markdown
# 早安，[用户名]！ ☀️

**[日期] [星期]**

---

## 🌤️ 天气
[城市]：[天气状况] [温度]，[湿度] [风速]
今日建议：[穿衣/出行建议]

## 📅 今日日程
| 时间 | 事项 |
|---|---|
| 09:00 | [事项1] |
| 14:00 | [事项2] |

（无日程时显示：今天没有预约的日程，可以自由安排 ✨）

## ✅ 待办事项
- [ ] [任务1]（截止：今天）
- [ ] [任务2]（截止：明天）

（共 X 项待办，Y 项今日到期）

## 📰 今日要闻（可选）
1. [新闻标题1]
2. [新闻标题2]
```

### 个性化

- 通过 MEMORY.md 记住用户偏好（城市、关注领域、常用待办工具）
- 首次使用时询问用户所在城市和偏好
- 根据用户反馈调整简报内容（如关闭新闻模块）

## 输出规范

- 语气亲切但简洁，像朋友打招呼
- 所有时间使用用户本地时区
- 日程按时间排序
- 待办按紧急程度排序（今日到期 > 明日 > 本周）
- 整体长度控制在一屏内可读完
