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
多段定向解析：Synopsis(p1-15,高表格) -> Design(p30-50) -> Statistics(p90-115,纯文本) -> SAP Appendix(p240+)

## 解析引擎（四级降级）
DocumentParser 自动选择最优引擎：
1. **Unstructured API** (云端) — 需要 UNSTRUCTURED_API_KEY，表格+OCR 最强
2. **Docling** (本地 AI) — IBM 开源，视觉+语言模型做表格识别，无需 API Key，推荐本地首选
3. **pdfplumber** (本地) — 文本+简单表格
4. **PyPDF2** (本地) — 仅纯文本兜底

如果 UNSTRUCTURED_API_KEY 未配置且 Docling 已安装，会自动使用 Docling（表格识别精度远高于 pdfplumber）。
## References
- [prompts/](prompts/) — 6 个专用抽取 Prompt
- [scripts/parse_protocol.py](scripts/parse_protocol.py) — 多段解析编排
- [scripts/merge_entities.py](scripts/merge_entities.py) — 实体合并与交叉验证
- [schemas/protocol_entities.json](schemas/protocol_entities.json) — 输出 JSON Schema
- [reference/section_mapping.md](reference/section_mapping.md) — 章节分类规则
