---
name: protocol-entity-extraction
description: Extract structured entities from clinical trial Protocol PDF/DOCX for SAP authoring. Use when user uploads a Protocol and requests SAP generation.
---
# Protocol 实体抽取

从 Protocol PDF/DOCX 中抽取 SAP 所需的全部关键实体，输出结构化 JSON。

## Quick Start

你收到的是文件路径，用脚本解析（内部自动走 Unstructured API 优先，降级 pdfplumber/PyPDF2）：

```bash
python scripts/parse_protocol.py <protocol_path> <output_dir>
```

## 执行流程

1. **先读目录**：解析前 20-30 页获取 Table of Contents，确定各章节的实际页码范围
2. **按目录定向解析**：只解析需要的章节，不全文解析
3. 对每段解析结果，用 [prompts/](prompts/) 中的专用 Prompt 抽取实体
4. 运行 `scripts/merge_entities.py` 合并实体、交叉验证
5. 输出 `protocol_entities.json`

## 需要抽取的章节

根据目录定位以下章节（页码因文档而异，必须从 TOC 动态确定）：

| 目标章节 | 常见标题关键词 | 目标实体 |
|---------|-------------|---------|
| 试验概要 | Synopsis, Summary, Study Overview | study_id, design, endpoints |
| 目标与设计 | Objectives, Study Design, Treatment Arms | treatment_arms, populations |
| 统计方法 | Statistical Considerations, Sample Size, Analysis | stat_methods, sample_size, multiplicity |
| SAP 附录 | SAP, Statistical Analysis Plan (如有) | 层次检验表、分析方法表 |

## References
- [prompts/](prompts/) — 6 个专用抽取 Prompt
- [scripts/parse_protocol.py](scripts/parse_protocol.py) — 多段解析编排
- [scripts/merge_entities.py](scripts/merge_entities.py) — 实体合并与交叉验证
- [schemas/protocol_entities.json](schemas/protocol_entities.json) — 输出 JSON Schema
- [reference/section_mapping.md](reference/section_mapping.md) — 章节分类规则
