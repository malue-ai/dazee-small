---
name: readwise-rival
description: Collect, organize, and review reading highlights from books, articles, and web pages. Generate knowledge cards and spaced repetition reviews.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 阅读高亮与知识复习

收集阅读中的高亮和笔记，生成知识卡片，支持间隔重复复习。

## 使用场景

- 用户说「帮我保存这段话」「我最近读到的关于 XX 的内容有哪些」
- 用户想定期复习之前的阅读摘录
- 用户想从阅读笔记中生成知识卡片

## 数据存储

```bash
# 高亮库存储路径
mkdir -p ~/.xiaodazi/reading/highlights
mkdir -p ~/.xiaodazi/reading/cards
```

### 高亮格式

```json
// ~/.xiaodazi/reading/highlights/2025-02.json
{
  "highlights": [
    {
      "id": "h_001",
      "text": "好的决策不是关于你知道什么，而是关于你如何思考。",
      "source": {
        "type": "book",
        "title": "思考，快与慢",
        "author": "丹尼尔·卡尼曼",
        "chapter": "第3章"
      },
      "tags": ["决策", "思维方式"],
      "note": "这个观点可以用在产品设计决策流程中",
      "created_at": "2025-02-07T14:30:00"
    }
  ]
}
```

## 核心功能

### 1. 保存高亮

用户粘贴或口述一段文字，LLM 结构化保存：

```bash
# 追加高亮
python3 -c "
import json, os
from datetime import datetime

highlights_file = os.path.expanduser('~/.xiaodazi/reading/highlights/$(date +%Y-%m).json')
# ... 读取、追加、写入
"
```

### 2. 按主题检索

```bash
# 搜索含关键词的高亮
python3 -c "
import json, glob, os

pattern = os.path.expanduser('~/.xiaodazi/reading/highlights/*.json')
query = '决策'
results = []
for f in glob.glob(pattern):
    data = json.load(open(f))
    for h in data.get('highlights', []):
        if query in h.get('text', '') or query in str(h.get('tags', [])):
            results.append(h)

for r in results[:10]:
    print(f'📌 \"{r[\"text\"][:80]}...\"')
    src = r.get('source', {})
    print(f'   — {src.get(\"title\", \"?\")}')
    print()
"
```

### 3. 生成知识卡片

从高亮中提炼问答对，用于复习：

```markdown
## 知识卡片

**Q**: 好的决策取决于什么？
**A**: 不是关于你知道什么，而是关于你如何思考。（丹尼尔·卡尼曼《思考，快与慢》）

**标签**: #决策 #思维方式
**下次复习**: 2025-02-14
```

### 4. 间隔重复复习

基于简化的 SM-2 算法安排复习：

```
首次: 1 天后
第二次: 3 天后
第三次: 7 天后
第四次: 14 天后
第五次: 30 天后
```

### 5. 每周回顾

```markdown
## 本周阅读回顾

**新增高亮**: 12 条
**来源**: 3 本书, 5 篇文章

### 高频主题
1. 决策科学（4 条）
2. 产品设计（3 条）
3. AI 应用（3 条）

### 精选高亮
> "好的决策不是关于你知道什么..."
> — 思考，快与慢

### 待复习卡片
- 5 张今日到期
- 12 张本周到期
```

## 输出规范

- 保存高亮后确认「已保存，标签: #XX #XX」
- 复习时每次展示 5 张卡片，用户回答后标记掌握程度
- 每周回顾自动生成（可配合通知 Skill 推送）
- 所有数据存储在本地 `~/.xiaodazi/reading/`
