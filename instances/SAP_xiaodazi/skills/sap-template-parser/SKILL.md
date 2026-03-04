---
name: sap-template-parser
description: Parse SAP template documents to extract chapter structure, content requirements, and statistical method decisions.
---
# SAP 模板解析
解析 SAP 模板文档，生成章节骨架和统计方法决策。
## Quick Start
```python
result = await parser.parse(template_path, chunking=True, chunk_max_chars=4000)
```
## References
- [reference/chapter_structure.md](reference/chapter_structure.md) — SAP 标准章节结构
- [reference/entity_mapping.md](reference/entity_mapping.md) — 章节→实体映射
- [reference/method_rules.md](reference/method_rules.md) — 终点类型→统计方法决策规则
- [scripts/parse_template.py](scripts/parse_template.py) — 模板解析编排
