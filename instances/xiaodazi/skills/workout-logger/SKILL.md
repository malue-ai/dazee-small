---
name: workout-logger
description: Log workouts, track exercise progress, and generate fitness reports. Data stored locally.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 健身记录

帮助用户记录运动和锻炼，追踪进步，生成健身报告。数据保存在本地。

## 使用场景

- 用户说「记录今天的运动」「跑了 5 公里」
- 用户说「今天做了卧推 60kg 3组」
- 用户说「这周运动了几次」「看看我的运动记录」
- 用户说「我的深蹲进步了多少」

## 执行方式

### 数据存储

在用户数据目录维护 `~/Documents/xiaodazi/workouts.json`：

```json
{
  "logs": {
    "2026-02-26": [
      {
        "type": "strength",
        "exercises": [
          {"name": "卧推", "sets": [{"weight": 60, "reps": 8}, {"weight": 60, "reps": 8}, {"weight": 55, "reps": 10}]},
          {"name": "深蹲", "sets": [{"weight": 80, "reps": 6}, {"weight": 80, "reps": 6}]}
        ],
        "duration_min": 45,
        "notes": "状态不错"
      }
    ],
    "2026-02-25": [
      {
        "type": "cardio",
        "activity": "跑步",
        "distance_km": 5.2,
        "duration_min": 28,
        "pace": "5:23/km"
      }
    ]
  }
}
```

### 记录流程

**力量训练**：
```
用户：今天卧推 60kg 做了 3 组，每组 8 个
→ 记录：卧推 60kg × 8 × 3 组
→ 回复：卧推已记录 ✅  60kg × 8 × 3
→ 对比上次：上次 55kg × 8，进步了 5kg 💪
```

**有氧运动**：
```
用户：刚跑了 5 公里，用了 28 分钟
→ 记录：跑步 5km / 28min / 配速 5:36/km
→ 回复：跑步已记录 ✅  5km 28分钟（配速 5:36/km）
```

### 周报模板

```markdown
## 运动周报（2/19 - 2/25）

本周运动 **4 次**，总时长 **160 分钟**

| 日期 | 类型 | 内容 | 时长 |
|---|---|---|---|
| 周一 | 力量 | 胸+三头 | 50min |
| 周三 | 有氧 | 跑步 5km | 28min |
| 周五 | 力量 | 背+二头 | 55min |
| 周六 | 有氧 | 跑步 6km | 32min |

### PR 记录（个人最佳）
- 卧推：60kg × 8（+5kg ↑）
- 跑步 5km：28:00（-1:30 ↓）
```

## 输出规范

- 记录后简洁确认，对比上次数据
- 有进步时积极鼓励
- 长时间未运动时温和提醒，不施压
- 自动计算配速、组间容量等衍生指标
