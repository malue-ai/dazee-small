---
name: reading-companion
description: Manage reading notes, extract key insights from books, create cross-book theme connections, and generate review flashcards.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 阅读伴侣

帮助用户管理读书笔记：提取核心观点、跨书籍主题关联、生成复习卡片。

## 使用场景

- 用户说「帮我整理这本书的核心观点」「总结一下关键笔记」
- 用户说「这本书和上次那本有什么关联」「这个主题下我读过哪些书」
- 用户说「帮我做读书笔记的复习卡片」「推荐下一本读什么」

## 执行方式

直接使用 LLM 能力分析和整理，读书笔记存储在本地文件中。

### 读书笔记模板

```markdown
# 《[书名]》读书笔记

**作者**: [作者名]
**阅读日期**: YYYY-MM-DD
**评分**: ⭐⭐⭐⭐ (4/5)

## 一句话总结
[用一句话概括这本书的核心]

## 核心观点 (Top 3-5)
1. [观点 1] — [简要解释]
2. [观点 2] — [简要解释]
3. [观点 3] — [简要解释]

## 金句摘录
> "[原文摘录]" — p.XX
> 我的理解：[个人思考]

## 实践行动
- [ ] [读完这本书我要做什么]

## 关联书籍
- 《[相关书名]》: [关联点]
```

### 笔记存储

```
~/Documents/xiaodazi_reading/
├── books/
│   ├── thinking-fast-and-slow.md
│   ├── atomic-habits.md
│   └── ...
├── themes/
│   ├── productivity.md      # 主题汇总
│   └── decision-making.md
└── flashcards/
    └── review-cards.md
```

### 跨书籍主题关联

当用户读完多本书后，自动发现主题关联：

```markdown
## 主题: 习惯养成

### 相关书籍
1. 《Atomic Habits》 — 习惯的四步法则
2. 《The Power of Habit》 — 习惯回路
3. 《Thinking, Fast and Slow》 — 系统 1 与自动化行为

### 核心洞察
不同作者从不同角度论证了...

### 综合行动建议
结合多本书的建议，最有效的做法是...
```

### 复习卡片

```markdown
Q: 《Atomic Habits》的四步法则是什么？
A: Cue → Craving → Response → Reward

Q: Daniel Kahneman 的"系统 1"和"系统 2"有什么区别？
A: 系统 1: 快速、直觉、自动；系统 2: 慢速、分析、费力
```

## 输出规范

- 笔记保存到本地 `~/Documents/xiaodazi_reading/` 目录
- 核心观点精炼到 3-5 个
- 金句摘录标注页码或章节
- 复习卡片使用 Q/A 格式
- 主题关联至少涉及 2 本书
