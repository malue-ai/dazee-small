---
name: invoice-organizer
description: Automatically organize invoices and receipts by reading files, extracting key information, renaming consistently, and sorting into categorized folders.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages:
      - pypdf
      - Pillow
    setup:
      user_hint: "需要装一个 PDF 读取小工具，30 秒就能搞定"
      auto_install: "pip install pypdf Pillow"
---

# 发票整理助手

自动整理发票和收据：读取文件、提取关键信息、统一命名、分类归档。

## 使用场景

- 用户说「帮我整理一下发票」「把下载文件夹里的发票分类」
- 报税前需要整理全年发票
- 日常收据管理，按月份/类别归档

## 依赖安装

首次使用时自动安装：

```bash
pip install pypdf Pillow
```

## 执行方式

通过 Python 脚本扫描文件夹，识别发票文件，提取信息并归档。

### 1. 扫描目标文件夹

```python
import os
from pathlib import Path

def scan_invoices(folder: str) -> list:
    """Scan folder for invoice files (PDF/image)."""
    extensions = {'.pdf', '.png', '.jpg', '.jpeg'}
    invoices = []
    for f in Path(folder).rglob('*'):
        if f.suffix.lower() in extensions:
            invoices.append(f)
    return invoices
```

### 2. 提取发票信息

对于 PDF 发票：

```python
from pypdf import PdfReader

def extract_pdf_text(path: str) -> str:
    """Extract text from PDF invoice."""
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text
```

对于图片发票，使用 LLM 视觉能力识别内容。

### 3. 信息结构化

从提取的文本中识别：

- **日期**：开票日期
- **金额**：总金额
- **商家/供应商**：开票方名称
- **类型**：餐饮/交通/办公用品/住宿等
- **发票号**：如有

### 4. 统一命名和归档

```python
# 命名规则：日期_商家_金额_类型.ext
# 示例：20250115_星巴克_35.00_餐饮.pdf

# 目录结构
# 发票整理/
# ├── 2025-01/
# │   ├── 餐饮/
# │   ├── 交通/
# │   └── 办公用品/
# └── 2025-02/
```

## 输出规范

- 操作前先列出发现的发票清单，请求用户确认
- 整理完成后输出汇总表格（数量、总金额、分类统计）
- 保留原始文件不删除，只复制到新目录结构
- 无法识别的发票单独放入「待分类」文件夹
