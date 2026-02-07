---
name: nutrition-analyzer
description: Analyze food photos or descriptions to estimate nutritional content (calories, protein, carbs, fat). Provide dietary advice and meal tracking.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 食物营养分析

分析食物描述或照片，估算营养成分，提供饮食建议。

## 使用场景

- 用户说「这顿饭大概多少卡路里」「帮我分析今天吃的东西」
- 用户拍了食物照片想了解营养
- 用户在做饮食计划或减脂/增肌管理

## 分析方式

### 文字描述分析

用户描述食物，LLM 基于营养知识估算：

```
输入: "一碗白米饭 + 红烧排骨三块 + 炒青菜一盘"

输出:
┌──────────┬───────┬────────┬────────┬────────┐
│ 食物      │ 热量   │ 蛋白质  │ 碳水    │ 脂肪    │
├──────────┼───────┼────────┼────────┼────────┤
│ 白米饭    │ 230卡  │ 4g     │ 50g    │ 0.5g   │
│ 红烧排骨  │ 350卡  │ 25g    │ 8g     │ 24g    │
│ 炒青菜    │ 80卡   │ 3g     │ 5g     │ 5g     │
├──────────┼───────┼────────┼────────┼────────┤
│ 合计      │ 660卡  │ 32g    │ 63g    │ 29.5g  │
└──────────┴───────┴────────┴────────┴────────┘

评价：热量适中，蛋白质达标，碳水偏高。
建议：搭配更多蔬菜，减少米饭量至半碗。
```

### 图片分析（需多模态模型支持）

如果 LLM 支持视觉输入（如 Claude vision / GPT-4V），可直接分析食物照片。

### 每日饮食追踪

```bash
# 存储饮食记录
mkdir -p ~/.xiaodazi/nutrition

# 当日记录
cat >> ~/.xiaodazi/nutrition/$(date +%Y-%m-%d).json << 'EOF'
{"meal": "午餐", "time": "12:30", "foods": [...], "total_calories": 660}
EOF

# 查看当日汇总
cat ~/.xiaodazi/nutrition/$(date +%Y-%m-%d).json
```

### 营养数据库 API（可选）

```bash
# USDA FoodData Central（免费，无需 Key）
curl -s "https://api.nal.usda.gov/fdc/v1/foods/search?query=chicken+breast&api_key=DEMO_KEY&pageSize=3" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for food in data.get('foods', [])[:3]:
    name = food.get('description', '')
    nutrients = {n['nutrientName']: n['value'] for n in food.get('foodNutrients', [])[:10]}
    print(f'{name}:')
    for k, v in list(nutrients.items())[:5]:
        print(f'  {k}: {v}')
"
```

## 输出规范

- 营养表格用 Markdown 表格展示
- 数值为近似值，注明「仅供参考，非医学建议」
- 给出简短的饮食建议（1-2 句）
- 支持中英文食物名
