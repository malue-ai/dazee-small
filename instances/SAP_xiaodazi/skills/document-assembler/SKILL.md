---
name: document-assembler
description: Assemble SAP chapter content and statistical code into regulatory-formatted Word/PDF documents with proper styling.
---
# 文档组装与渲染

将 SAP 各章节内容组装为格式规范的 Word 文档 + 人工审核清单。

## 渲染策略（三级方案）

1. **Pandoc（主方案）**：Markdown -> Word 工业级转换，通过 sap_reference.docx 模板控制样式
2. **python-docx 组装**：无 Pandoc 时回退到 assemble_docx.py 的纯 Python 构建
3. **python-docx 直写**：Agent 直接用 python-docx API 创建 Word（见下方代码模板）

## python-docx 直写代码模板（关键）

当你直接用 `nodes` 工具创建 Word 文档时，**必须使用以下原生 API**，禁止在文本中嵌入 Markdown 语法。

```python
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT

doc = Document()
doc.styles["Normal"].font.name = "Times New Roman"
doc.styles["Normal"].font.size = Pt(11)

# 标题（禁止用 # Markdown 标题）
doc.add_heading("1. Objectives, Endpoints, and Estimands", level=1)
doc.add_heading("1.1 Primary Estimands", level=2)

# 加粗文本（禁止用 **bold**）
para = doc.add_paragraph()
run = para.add_run("Primary Estimand 1: ")
run.bold = True
para.add_run("Annualized rate of severe exacerbation events")

# 列表
doc.add_paragraph("ITT population", style="List Bullet")
doc.add_paragraph("Safety population", style="List Bullet")

# 表格（禁止用 Markdown | col1 | col2 | 语法）
table = doc.add_table(rows=3, cols=3)
table.style = "Table Grid"
table.alignment = WD_TABLE_ALIGNMENT.CENTER
# 表头
for j, text in enumerate(["Attribute", "Description", "Source"]):
    cell = table.rows[0].cells[j]
    cell.text = text
    for run in cell.paragraphs[0].runs:
        run.bold = True
        run.font.size = Pt(9)
# 数据行
table.rows[1].cells[0].text = "Population"
table.rows[1].cells[1].text = "ITT population (all randomized patients)"

# 分页
doc.add_page_break()

# AI 标记高亮
from docx.oxml.ns import qn
para = doc.add_paragraph()
run = para.add_run("[AI-INFERRED] ")
rpr = run._element.get_or_add_rPr()
hl = rpr.makeelement(qn("w:highlight"), {qn("w:val"): "yellow"})
rpr.append(hl)
para.add_run("DSMB will review safety data periodically")

doc.save(output_path)
```

## 禁止事项

- 禁止在 Word 段落文本中使用 `**bold**` Markdown 语法 -> 用 `run.bold = True`
- 禁止在 Word 段落文本中使用 `# Title` -> 用 `doc.add_heading()`
- 禁止在 Word 段落文本中使用 `| col |` 表格 -> 用 `doc.add_table()`
- 禁止在 Word 段落文本中使用 `---` 分隔线 -> 用 `doc.add_page_break()`
- 禁止在 Word 段落文本中使用 `- item` 列表 -> 用 `style="List Bullet"`

## Scripts

- [scripts/assemble_docx.py](scripts/assemble_docx.py) — 主组装脚本（Pandoc 优先 + python-docx 降级 + bold/标记后处理）
- [scripts/create_reference_docx.py](scripts/create_reference_docx.py) — 生成 Pandoc reference.docx 模板
- [scripts/generate_checklist.py](scripts/generate_checklist.py) — 审核清单生成

## Styles

- [styles/sap_reference.docx](styles/sap_reference.docx) — Pandoc 参考模板（ICH E9 / EU-PEARL 规范）
- [styles/formatting_rules.md](styles/formatting_rules.md) — 样式规格说明

## 标记处理

- `[AI-INFERRED]` -> 黄色高亮（AI 推断内容，需人工确认）
- `[PLACEHOLDER]` -> 红色高亮（占位符，需人工填写）
