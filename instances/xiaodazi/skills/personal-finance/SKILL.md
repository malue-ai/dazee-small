---
name: personal-finance
description: Track personal income and expenses, generate spending reports, manage budgets. All data stored locally for privacy.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 个人记账

帮助用户记录收支、生成消费报告、管理预算。所有数据存储在本地，保护财务隐私。

## 使用场景

- 用户说「记一笔：午餐 35 元」「今天买衣服花了 500」
- 用户说「这个月花了多少钱」「看看我的消费报告」
- 用户说「设个每月餐饮预算 3000」「预算还剩多少」

## 执行方式

通过本地 JSON 文件存储账目数据，LLM 解析自然语言记账指令。

### 数据存储

账目文件：`~/Documents/xiaodazi_finance/records.json`

```json
{
  "records": [
    {
      "date": "2026-02-09",
      "type": "expense",
      "amount": 35.00,
      "category": "dining",
      "description": "lunch",
      "currency": "CNY"
    }
  ],
  "budgets": {
    "dining": { "monthly_limit": 3000, "currency": "CNY" }
  }
}
```

### 记账

```bash
# 读取现有记录
cat ~/Documents/xiaodazi_finance/records.json 2>/dev/null || echo '{"records":[],"budgets":{}}'

# 追加记录（通过 Python）
python3 -c "
import json, os
path = os.path.expanduser('~/Documents/xiaodazi_finance/records.json')
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    data = json.load(open(path))
except:
    data = {'records': [], 'budgets': {}}
data['records'].append({
    'date': '2026-02-09',
    'type': 'expense',
    'amount': 35.00,
    'category': 'dining',
    'description': 'lunch',
    'currency': 'CNY'
})
json.dump(data, open(path, 'w'), ensure_ascii=False, indent=2)
print('recorded')
"
```

### 生成报告

```python
import json
from collections import defaultdict

data = json.load(open("~/Documents/xiaodazi_finance/records.json"))

# 按类别汇总
by_category = defaultdict(float)
for r in data["records"]:
    if r["type"] == "expense":
        by_category[r["category"]] += r["amount"]

for cat, total in sorted(by_category.items(), key=lambda x: -x[1]):
    print(f"{cat}: {total:.2f}")
```

### 支出分类

| 类别 | 关键词示例 |
|---|---|
| dining | 午餐、晚饭、外卖、咖啡 |
| transport | 打车、地铁、加油、停车 |
| shopping | 衣服、电子产品、日用品 |
| housing | 房租、水电、物业 |
| entertainment | 电影、游戏、旅游 |
| education | 课程、书籍、培训 |
| health | 医药、体检、健身 |

## 安全规则

- **数据本地存储**：财务数据只存在本地，不上传
- **不自动分享**：不将财务信息写入其他文件或发送

## 输出规范

- 记账后确认：类别、金额、日期
- 报告用表格展示，按金额降序
- 预算超支时主动提醒
- 支持多币种（根据用户习惯自动选择）
