---
name: elegant-reports
description: Generate beautifully designed PDF reports with Nordic-style typography, charts, tables, and multi-page layouts using reportlab or fpdf2.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages:
      - fpdf2
      - matplotlib
    setup:
      user_hint: "需要装一个报告生成小工具，30 秒就能搞定"
      auto_install: "pip install fpdf2 matplotlib"
---

# 精美报告生成

生成设计感强的专业 PDF 报告，支持图表、表格、多页排版，Nordic 简约风格。

## 使用场景

- 用户说「帮我做一份漂亮的报告」「把这些数据生成 PDF 报告」
- 用户需要美观的分析报告、调研报告、项目报告
- 用户觉得普通 PDF 太素，想要有设计感

## 依赖安装

首次使用时自动安装：

```bash
pip install fpdf2 matplotlib
```

## 执行方式

通过 Python 脚本使用 fpdf2 生成 PDF，matplotlib 生成图表。

### 设计风格：Nordic 简约

- **配色**：以深蓝 `#2C3E50` + 白色为主，琥珀黄 `#F39C12` 作强调色
- **字体**：衬线体标题 + 无衬线正文（中文使用系统字体）
- **留白**：大量留白，不要塞满
- **排版**：左对齐为主，标题居中

### 报告结构模板

```python
from fpdf import FPDF

class ElegantReport(FPDF):
    """Nordic-style PDF report generator."""

    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(44, 62, 80)
        self.cell(0, 10, self.title, align='R')
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(149, 165, 166)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

    def chapter_title(self, title: str):
        self.set_font('Helvetica', 'B', 18)
        self.set_text_color(44, 62, 80)
        self.cell(0, 15, title)
        self.ln(20)

    def body_text(self, text: str):
        self.set_font('Helvetica', '', 11)
        self.set_text_color(52, 73, 94)
        self.multi_cell(0, 7, text)
        self.ln(5)
```

### 支持的内容元素

1. **封面页**：标题、副标题、日期、作者
2. **目录**：自动生成章节目录
3. **正文**：标题层级、段落、列表
4. **表格**：带交替行背景色的数据表
5. **图表**：matplotlib 生成的统计图
6. **页眉页脚**：标题 + 页码

### 图表生成

```python
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

def create_chart(data: dict, output_path: str):
    """Generate chart image for embedding in PDF."""
    fig, ax = plt.subplots(figsize=(8, 4))
    # Nordic color palette
    colors = ['#2C3E50', '#E74C3C', '#F39C12', '#27AE60', '#3498DB']
    ax.bar(data.keys(), data.values(), color=colors[:len(data)])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
```

## 输出规范

- 默认 A4 纵向，留足页边距
- 中文内容自动使用系统中文字体
- 图表清晰度不低于 150 DPI
- 生成完成后告知用户文件路径
- 复杂报告先确认大纲结构，再生成
