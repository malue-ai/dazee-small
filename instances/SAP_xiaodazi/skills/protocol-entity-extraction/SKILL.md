---
name: protocol-entity-extraction
description: Extract structured entities from clinical trial Protocol PDF/DOCX for SAP authoring. Multi-pass parsing with Unstructured API, entity merging, and confidence scoring.
requires:
  env: [UNSTRUCTURED_API_KEY]
---
# Protocol 实体抽取
从 Protocol PDF/DOCX 中抽取 SAP 所需的全部关键实体，输出结构化 JSON。
## Quick Start
```python
from utils.document_parser import get_document_parser
parser = get_document_parser()
synopsis = await parser.parse(protocol_path, page_range=[1, 15])
stats = await parser.parse(protocol_path, page_range=[90, 115])
```
## 解析策略
多段定向解析：Synopsis(p1-15,高表格) → Design(p30-50) → Statistics(p90-115,纯文本) → SAP Appendix(p240+)
## References
- [prompts/](prompts/) — 6 个专用抽取 Prompt
- [scripts/parse_protocol.py](scripts/parse_protocol.py) — 多段解析编排
- [scripts/merge_entities.py](scripts/merge_entities.py) — 实体合并与交叉验证
- [schemas/protocol_entities.json](schemas/protocol_entities.json) — 输出 JSON Schema
- [reference/section_mapping.md](reference/section_mapping.md) — 章节分类规则
