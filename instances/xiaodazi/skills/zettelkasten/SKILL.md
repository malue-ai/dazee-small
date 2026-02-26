---
name: zettelkasten
description: Zettelkasten note-taking method — create atomic knowledge cards with bidirectional links and emergent insights.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 卡片笔记法（Zettelkasten）

用卢曼卡片笔记法管理知识：原子化笔记、双向链接、渐进式涌现洞察。

## 使用场景

- 用户说「帮我做读书笔记」「用卡片笔记法整理这个概念」
- 用户说「这个概念和之前那个有什么关联」
- 用户说「看看我的笔记之间有什么联系」
- 用户在学习新知识时想建立系统化的知识网络

## 执行方式

### 卡片结构

每张卡片存储为 Markdown 文件，放在 `~/Documents/xiaodazi/zettelkasten/` 目录：

```markdown
---
id: "202602261430"
title: "间隔重复的遗忘曲线"
tags: [学习方法, 记忆]
links: ["202602251000", "202602201530"]
created: "2026-02-26T14:30:00"
---

间隔重复基于艾宾浩斯遗忘曲线：新学的知识在 24 小时内遗忘 70%，
但每次复习都会延长记忆保持时间。

最佳复习间隔：1天 → 3天 → 7天 → 14天 → 30天

与 [[202602251000]] 主动回忆 结合效果最好。
参见 [[202602201530]] Anki 间隔算法。
```

### 核心操作

**创建卡片**：
```
用户：帮我记一个笔记——间隔重复利用遗忘曲线原理，通过在最佳时间点复习来巩固记忆
→ 生成唯一 ID（时间戳格式）
→ 提取关键概念作为标签
→ 搜索已有卡片，建议可能的关联
→ 创建 Markdown 文件
→ 回复：卡片已创建 ✅「间隔重复的遗忘曲线」
  可能相关：「主动回忆」「Anki 间隔算法」，要链接吗？
```

**发现关联**：
```
用户：看看我关于学习方法的笔记有什么联系
→ 检索标签为「学习方法」的所有卡片
→ 分析内容相关性
→ 生成知识图谱概览：

  主动回忆 ←→ 间隔重复
       ↓           ↓
  费曼技巧 ←→ 遗忘曲线
```

**搜索与浏览**：
```bash
# 全文搜索
grep -rl "间隔重复" ~/Documents/xiaodazi/zettelkasten/

# 按标签
grep -l "tags:.*学习方法" ~/Documents/xiaodazi/zettelkasten/*.md
```

### 卡片原则

1. **原子性**：每张卡片只包含一个概念
2. **用自己的话写**：不要直接复制粘贴
3. **建立链接**：每张新卡片至少链接一张已有卡片
4. **持续增长**：不追求完美，先写再完善

## 输出规范

- 创建时自动建议关联卡片
- 每张卡片简短（100-300 字）
- 链接使用 `[[ID]]` 格式
- 定期生成知识图谱概览，帮助用户发现意外关联
