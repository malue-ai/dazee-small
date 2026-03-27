---
name: pomodoro
description: "Pomodoro timer with focus sessions, break management, and daily task tracking in local JSON. Use when a user wants to start a focus timer, track completed pomodoros, or review daily productivity."
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 番茄钟

番茄工作法定时器：专注 → 休息 → 追踪。数据存储在 `~/Documents/xiaodazi/pomodoro.json`。

## 数据结构

```json
{
  "settings": {"focus_minutes": 25, "short_break": 5, "long_break": 15, "long_break_after": 4},
  "today": {
    "date": "2026-02-26", "completed": 3, "total_focus_minutes": 75,
    "sessions": [
      {"task": "写论文", "start": "09:00", "end": "09:25", "completed": true}
    ]
  }
}
```

## 工作流程

### 1. 开始番茄

```python
import json, os, datetime

data_path = os.path.expanduser("~/Documents/xiaodazi/pomodoro.json")
os.makedirs(os.path.dirname(data_path), exist_ok=True)

# 读取或初始化
if os.path.exists(data_path):
    with open(data_path) as f:
        data = json.load(f)
else:
    data = {"settings": {"focus_minutes": 25, "short_break": 5, "long_break": 15, "long_break_after": 4},
            "today": {"date": "", "completed": 0, "total_focus_minutes": 0, "sessions": []}}

today = datetime.date.today().isoformat()
if data["today"]["date"] != today:
    data["today"] = {"date": today, "completed": 0, "total_focus_minutes": 0, "sessions": []}

# 记录新番茄
now = datetime.datetime.now().strftime("%H:%M")
data["today"]["sessions"].append({"task": "写周报", "start": now, "end": "", "completed": False})

with open(data_path, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

**回复用户:** `🍅 番茄钟开始！任务：写周报，25 分钟后提醒你休息。`

### 2. 设置定时通知

根据平台调用对应通知 Skill：

**macOS:** 参考 [macos-notification](../macos-notification/SKILL.md)
```bash
# 25 分钟后发送通知
sleep 1500 && osascript -e 'display notification "🍅 番茄完成！休息 5 分钟吧。" with title "小搭子番茄钟"'
```

**Windows:** 参考 [windows-notification](../windows-notification/SKILL.md)
```powershell
Start-Sleep -Seconds 1500; [System.Windows.Forms.MessageBox]::Show("🍅 番茄完成！休息 5 分钟吧。")
```

**Linux:** 参考 [linux-notification](../linux-notification/SKILL.md)
```bash
sleep 1500 && notify-send "小搭子番茄钟" "🍅 番茄完成！休息 5 分钟吧。"
```

### 3. 番茄完成

更新 JSON 记录，标记 `completed: true`，累加计数。每 4 个番茄后建议长休息（15 分钟）。

### 4. 查看记录

```
用户: 今天的番茄钟情况

今日已完成 5 个番茄（125 分钟）:
| 任务 | 番茄数 | 总时间 |
|------|--------|--------|
| 写论文 | 3 | 75 分钟 |
| 回邮件 | 1 | 25 分钟 |
| 代码审查 | 1 | 25 分钟 |
```

## 输出规范

- 开始时简洁确认，不打断用户思路
- 完成时给予正面反馈 + 休息建议
- 日报使用表格展示任务分布
- 鼓励但不施压，中断番茄时不批评
