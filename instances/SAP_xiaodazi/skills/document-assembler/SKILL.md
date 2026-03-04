---
name: document-assembler
description: Assemble SAP chapter content and statistical code into regulatory-formatted Word/PDF documents with proper styling.
---
# 文档组装与渲染

将 SAP 各章节 Markdown 内容组装为格式规范的 Word 文档 + 人工审核清单。

## 渲染策略（两级方案）

1. **Pandoc（主方案）**：Markdown → Word 工业级转换，表格/公式/脚注/目录原生渲染，通过 sap_reference.docx 模板控制样式
2. **python-docx（降级）**：无 Pandoc 时自动回退到纯 Python 构建

Pandoc 转换后，python-docx 做后处理：扫描 [AI-INFERRED] / [PLACEHOLDER] 标记并添加高亮。

## Scripts

- [scripts/assemble_docx.py](scripts/assemble_docx.py) — 主组装脚本（Pandoc 优先 + python-docx 降级 + 标记后处理）
- [scripts/create_reference_docx.py](scripts/create_reference_docx.py) — 生成 Pandoc reference.docx 模板
- [scripts/generate_checklist.py](scripts/generate_checklist.py) — 审核清单生成

## Styles

- [styles/sap_reference.docx](styles/sap_reference.docx) — Pandoc 参考模板（ICH E9 / EU-PEARL 规范）
- [styles/formatting_rules.md](styles/formatting_rules.md) — 样式规格说明

## 标记处理

- `[AI-INFERRED]` → 黄色高亮（AI 推断内容，需人工确认）
- `[PLACEHOLDER]` → 红色高亮（占位符，需人工填写）
