---
name: sap-template-parser
description: Parse SAP template documents to extract chapter structure, content requirements, and statistical method decisions. Use when building SAP chapter skeleton.
---
# SAP 模板解析

解析 SAP 模板文档，生成章节骨架和统计方法决策。

## Quick Start

你收到的是文件路径，用脚本按章节分块解析（内部自动走 Unstructured API 优先，降级 pdfplumber/PyPDF2）：

```bash
python scripts/parse_template.py <template_path> <output_dir>
```

输出到 `<output_dir>/`：
- `template_parsed.md` — 完整解析的 Markdown
- `template_structure.json` — 章节结构（含 content_type 分类）

## 执行流程

1. 运行 `parse_template.py`，自动按章节标题分块解析
2. 检查 `template_structure.json` 中每个 section 的 `content_type`
3. 结合 Protocol 实体和 [reference/method_rules.md](reference/method_rules.md) 生成 `method_decisions.json`

## content_type 分类

脚本自动根据章节标题分类：

| content_type | 匹配规则 | 生成策略 |
|---|---|---|
| estimand | "Estimand"、"Objectives" | 用 estimand Prompt |
| primary_analysis | "Primary Endpoint/Analysis" | 用 primary Prompt |
| secondary_analysis | "Secondary"、"Exploratory" | 用 secondary Prompt |
| safety_analysis | "Safety"、"Adverse Event" | 用 safety Prompt |
| multiplicity | "Multiplicity"、"Alpha Control" | 用 multiplicity Prompt |
| boilerplate | "Reference"、"Appendix" | 直接复制模板文本 |

## References
- [reference/chapter_structure.md](reference/chapter_structure.md) — SAP 标准章节结构
- [reference/entity_mapping.md](reference/entity_mapping.md) — 章节 → 实体映射
- [reference/method_rules.md](reference/method_rules.md) — 终点类型 → 统计方法决策规则
- [scripts/parse_template.py](scripts/parse_template.py) — 模板解析编排
