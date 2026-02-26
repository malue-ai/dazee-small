---
name: mineru-pdf
description: Parse PDF documents locally into structured Markdown/JSON using MinerU. CPU-only, privacy-first.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["magic-pdf"]
---

# MinerU PDF 解析

本地解析 PDF 文档为结构化 Markdown 或 JSON，保留标题层级、表格、列表等结构。CPU 运行，数据不出本机。

## 使用场景

- 用户说「帮我把这个 PDF 转成 Markdown」「提取这个 PDF 的内容」
- 需要从 PDF 中提取结构化文本用于后续分析
- 扫描件 PDF 需要 OCR 提取文字（配合 multi-lang-ocr）
- 批量处理多个 PDF 文件

## 与 pdf-toolkit / nano-pdf 的区别

| 工具 | 擅长 | 局限 |
|---|---|---|
| nano-pdf | 简单文本提取、PDF 元数据 | 不保留结构 |
| pdf-toolkit | 合并/拆分/加密/水印 | 不做内容解析 |
| **mineru-pdf** | **结构化解析（标题/表格/列表）** | 安装包较大 |

优先使用 mineru-pdf 做内容提取，pdf-toolkit 做文件操作。

## 执行方式

### 安装

```bash
pip install magic-pdf
```

### 基本用法

```bash
magic-pdf -p /path/to/document.pdf -o /path/to/output/ -m auto
```

参数说明：
- `-p`：输入 PDF 路径
- `-o`：输出目录
- `-m`：模式选择
  - `auto`：自动判断（推荐）
  - `txt`：纯文本 PDF
  - `ocr`：扫描件 PDF

### Python API

```python
from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
from magic_pdf.pipe.UNIPipe import UNIPipe

reader = FileBasedDataReader("")
writer = FileBasedDataWriter(output_dir)

pdf_bytes = reader.read(pdf_path)
pipe = UNIPipe(pdf_bytes, model_list=[], image_writer=writer)
pipe.pipe_classify()
pipe.pipe_analyze()
pipe.pipe_parse()
md_content = pipe.pipe_mk_markdown(image_dir, drop_mode="none")
```

### 输出内容

解析后在输出目录生成：
- `*.md`：Markdown 格式的结构化内容
- `images/`：提取的图片
- `*.json`：结构化元数据

## 输出规范

- 保留原文档的标题层级（H1-H6）
- 表格转换为 Markdown 表格
- 图片提取并以 `![](path)` 引用
- 页码标注在章节末尾
