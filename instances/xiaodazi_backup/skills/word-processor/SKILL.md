---
name: word-processor
description: Create and edit Word documents (.docx) using python-docx. Supports formatting, tables, images, headers, and template-based generation.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["python-docx"]
    auto_install: true
---

# Word 文档处理

使用 python-docx 创建和编辑 Word 文档（.docx）。

## 使用场景

- 用户说「帮我生成一份 Word 报告」「把这些内容写成 Word」
- 用户需要创建格式化的文档（标题、表格、列表）
- 用户需要修改现有 Word 文件

## 依赖安装

```bash
pip install python-docx
```

## 创建文档

```python
from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()

# 标题
doc.add_heading('报告标题', level=0)

# 段落
p = doc.add_paragraph('这是正文内容。')
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

# 加粗和斜体
p = doc.add_paragraph()
p.add_run('加粗文本').bold = True
p.add_run('，')
p.add_run('斜体文本').italic = True

# 列表
doc.add_paragraph('要点一', style='List Bullet')
doc.add_paragraph('要点二', style='List Bullet')

# 编号列表
doc.add_paragraph('第一步', style='List Number')
doc.add_paragraph('第二步', style='List Number')

# 表格
table = doc.add_table(rows=3, cols=3, style='Table Grid')
table.cell(0, 0).text = '姓名'
table.cell(0, 1).text = '部门'
table.cell(0, 2).text = '职位'

# 分页
doc.add_page_break()

# 保存
output_path = '/tmp/report.docx'
doc.save(output_path)
print(f'文档已保存: {output_path}')
```

## 读取文档

```python
from docx import Document

doc = Document('/path/to/input.docx')

# 读取所有段落
for para in doc.paragraphs:
    print(f'[{para.style.name}] {para.text}')

# 读取表格
for table in doc.tables:
    for row in table.rows:
        print([cell.text for cell in row.cells])
```

## 修改文档

```python
from docx import Document

doc = Document('/path/to/input.docx')

# 修改段落文本
for para in doc.paragraphs:
    if '旧内容' in para.text:
        for run in para.runs:
            run.text = run.text.replace('旧内容', '新内容')

doc.save('/path/to/output.docx')
```

## 输出规范

- 默认保存到 `/tmp/` 或用户指定路径
- 生成后告知用户文件路径
- 如果在 macOS 上，用 `open` 命令打开文件预览
