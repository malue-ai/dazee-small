---
name: translator
description: Multi-language translator for text, documents, and conversations. Supports Chinese, English, Japanese, Korean, and more.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 翻译助手

帮助用户完成多语言翻译任务。

## 使用场景

- 用户说「翻译一下这段英文」「把这个翻成日语」
- 用户粘贴了外文内容，需要理解含义
- 用户需要翻译邮件、文档、网页内容

## 执行方式

直接使用 LLM 的多语言能力完成翻译，无需额外工具。

### 文本翻译

根据用户指定的目标语言翻译文本。未指定目标语言时：
- 输入是中文 → 翻译为英文
- 输入是其他语言 → 翻译为中文

### 文档翻译

对于较长的文档内容，分段翻译，保持格式（标题、列表、代码块等）。

### 对照翻译

当用户需要学习或校对时，提供原文和译文的对照格式。

## 输出规范

- 默认直接输出译文，不加额外解释
- 遇到专业术语时，括号标注原文：例如「机器学习（Machine Learning）」
- 保持原文的格式结构（段落、列表、标题等）
- 用户要求对照时，使用表格或并列格式
