---
name: writing-assistant
description: Writing assistant for polishing, rewriting, expanding, and structuring text. Handles articles, emails, reports, and social media posts.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 写作助手

帮助用户完成各类文字工作：润色、改写、扩写、缩写、结构化整理。

## 使用场景

- 用户说「帮我润色一下这段话」「把这段改得更正式」「帮我扩写」
- 用户需要写邮件、报告、文案、社交媒体文字
- 用户提供了一段文字，希望改进

## 执行方式

直接使用 LLM 能力完成，无需额外工具。

### 润色

收到文本后，改善表达流畅度和用词精准度，保持原意。

### 改写

根据用户指定的风格（正式/口语/学术/营销）重写文本。

### 扩写

根据用户提供的要点或大纲，生成完整内容。注意保持逻辑连贯。

### 缩写/摘要

将长文本压缩为指定长度的摘要，保留核心信息。

### 结构化整理

将零散文字整理为带标题、段落、列表的结构化文档。

## 输出规范

- 默认输出 Markdown 格式
- 对比修改时，用「原文 → 修改后」格式展示关键改动
- 扩写时先列大纲，确认后再展开
- 邮件类写作注意称谓、落款的格式规范
