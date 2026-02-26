---
name: calorie-counter
description: Track daily calorie and protein intake, set nutrition goals, and generate diet reports. Data stored locally.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 卡路里追踪

帮助用户记录每日饮食摄入，追踪卡路里和蛋白质，生成饮食报告。数据保存在本地。

## 使用场景

- 用户说「记一下午餐吃了什么」「刚吃了一碗米饭和炒鸡蛋」
- 用户说「今天还能吃多少卡路里」「我的蛋白质够了吗」
- 用户说「看看这周的饮食报告」
- 用户说「设置每日目标 1800 卡」

## 执行方式

### 数据存储

在用户数据目录维护 `~/Documents/xiaodazi/calories.json`：

```json
{
  "goals": {
    "daily_calories": 2000,
    "daily_protein_g": 60
  },
  "logs": {
    "2026-02-26": {
      "meals": [
        {
          "time": "08:30",
          "meal": "早餐",
          "items": [
            {"name": "全麦面包 2片", "calories": 160, "protein": 6},
            {"name": "鸡蛋 1个", "calories": 70, "protein": 6},
            {"name": "牛奶 250ml", "calories": 150, "protein": 8}
          ]
        }
      ],
      "total_calories": 380,
      "total_protein": 20
    }
  }
}
```

### 食物热量估算

用户描述食物后，基于通用营养数据库估算热量：

| 常见食物 | 热量 (kcal) | 蛋白质 (g) |
|---|---|---|
| 米饭 1碗 (200g) | 230 | 4 |
| 鸡胸肉 100g | 165 | 31 |
| 鸡蛋 1个 | 70 | 6 |
| 苹果 1个 | 95 | 0.5 |
| 牛奶 250ml | 150 | 8 |

估算时说明是「估算值」，建议用户根据实际份量调整。

### 记录流程

```
用户：午餐吃了一碗米饭、红烧肉、炒青菜
→ 估算：米饭 230 + 红烧肉 350 + 炒青菜 50 = 630 kcal
→ 记录到今日日志
→ 回复：午餐已记录 ✅ 约 630 kcal
→ 今日累计：1010 / 2000 kcal，还剩 990 kcal
```

### 周报模板

```markdown
## 饮食周报（2/19 - 2/25）

| 日期 | 卡路里 | 蛋白质 | 达标 |
|---|---|---|---|
| 周一 | 1850 | 65g | ✅ |
| 周二 | 2200 | 55g | ⚠️ 超标 |
| ...  | ...  | ... | ... |

平均每日：1950 kcal / 62g 蛋白质
```

## 输出规范

- 记录后立即显示当日剩余额度
- 超标时温和提醒，不批评
- 估算值标注为「约」，不给出虚假精确度
- 数据始终本地存储，不上传
