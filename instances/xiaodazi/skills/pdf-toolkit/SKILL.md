---
name: pdf-toolkit
description: Comprehensive PDF operations - merge, split, encrypt, add watermarks, extract text, and convert PDF to Word. Goes beyond basic reading.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages:
      - pypdf
      - reportlab
---

# PDF 工具箱

帮助用户完成各种 PDF 操作：合并、拆分、加密、加水印、提取文本、转换格式。

## 使用场景

- 用户说「把这 5 个 PDF 合并成一个」「拆分这个 PDF 的第 3-10 页」
- 用户说「给 PDF 加个密码」「加个水印」
- 用户说「提取 PDF 里的文字」「PDF 转 Word」

## 依赖安装

首次使用时自动安装：

```bash
pip install pypdf reportlab
```

## 执行方式

通过 Python 脚本使用 pypdf 和 reportlab 处理 PDF。

### 合并 PDF

```python
from pypdf import PdfWriter

writer = PdfWriter()
for pdf_path in ["/path/to/1.pdf", "/path/to/2.pdf", "/path/to/3.pdf"]:
    writer.append(pdf_path)

writer.write("/path/to/merged.pdf")
writer.close()
print("合并完成")
```

### 拆分 PDF

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("/path/to/input.pdf")
writer = PdfWriter()

# 提取第 3-10 页（0-indexed）
for page_num in range(2, 10):
    writer.add_page(reader.pages[page_num])

writer.write("/path/to/extracted.pdf")
writer.close()
```

### 加密 PDF

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("/path/to/input.pdf")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

writer.encrypt("user_password")
writer.write("/path/to/encrypted.pdf")
writer.close()
```

### 添加文字水印

```python
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io

# 创建水印 PDF
packet = io.BytesIO()
c = canvas.Canvas(packet, pagesize=A4)
c.setFont("Helvetica", 40)
c.setFillAlpha(0.3)
c.saveState()
c.translate(300, 400)
c.rotate(45)
c.drawCentredString(0, 0, "CONFIDENTIAL")
c.restoreState()
c.save()
packet.seek(0)

# 叠加水印
watermark = PdfReader(packet)
reader = PdfReader("/path/to/input.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark.pages[0])
    writer.add_page(page)

writer.write("/path/to/watermarked.pdf")
```

### 提取文本

```python
from pypdf import PdfReader

reader = PdfReader("/path/to/input.pdf")
text = ""
for page in reader.pages:
    text += page.extract_text() + "\n"

print(f"共 {len(reader.pages)} 页，提取文本 {len(text)} 字符")
```

## 安全规则

- **加密操作确认密码**：提醒用户牢记密码，PDF 加密后无法恢复
- **合并前确认顺序**：列出文件顺序让用户确认
- **不覆盖原文件**：输出到新文件，保留原始 PDF

## 输出规范

- 操作完成后报告：文件路径、页数、文件大小
- 合并/拆分前展示文件列表和页码范围
- 加密后提醒用户记住密码
