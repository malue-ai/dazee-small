---
name: slidespeak-editor
description: Edit existing PowerPoint presentations by replacing content in specified shapes using SlideSpeak API
priority: high
capabilities: [ppt_generation, presentation]

---

# SlideSpeak Presentation Editor

编辑现有的 PowerPoint 文件，通过替换指定形状（shape）的内容来实现批量修改和个性化定制。

**API 文档**: [https://docs.slidespeak.co/basics/api-references/edit-presentation/](https://docs.slidespeak.co/basics/api-references/edit-presentation/)

## API 规范摘要

### 端点

```
POST https://api.slidespeak.co/api/v1/presentation/edit
```

### 请求格式

- **Content-Type**: `multipart/form-data`
- **Headers**: `X-API-Key: YOUR_API_KEY`

### 必需参数

1. **pptx_file** (file): 要编辑的 PowerPoint 文件
2. **config** (json): 包含替换配置的 JSON 对象

### Config 结构

```json
{
  "replacements": [
    {
      "shape_name": "TARGET_SHAPE_NAME",
      "content": "新内容"
    }
  ]
}
```

### 响应格式

```json
{
  "url": "https://slidespeak-pptx-writer.s3.amazonaws.com/xxx.pptx"
}
```

## 使用场景

### 1. **批量个性化生成**
- 模板化 PPT 批量生成（如销售提案、客户报告）
- 替换客户名称、数据、徽标等

### 2. **内容更新**
- 更新现有 PPT 的特定部分
- 修改标题、副标题、正文内容

### 3. **多语言版本生成**
- 基于一个模板生成不同语言版本
- 保持布局和设计不变

### 4. **数据驱动的报告**
- 从数据库读取数据填充到 PPT 模板
- 自动生成周期性报告

## 使用流程

### 步骤 1: 准备模板 PPT

在 PowerPoint 中为需要替换的形状命名：

1. 选择形状（文本框、标题等）
2. 右键 → "选择窗格"（Selection Pane）
3. 重命名形状为有意义的名称（如 `TARGET_TITLE`、`TARGET_SUBTITLE`、`CLIENT_NAME` 等）

**命名建议**：
- 使用清晰的前缀：`TARGET_`, `DATA_`, `CLIENT_`
- 使用描述性名称：`TITLE`, `SUBTITLE`, `CONTENT`, `DATE`
- 避免使用特殊字符和空格

### 步骤 2: 识别需要替换的形状

在使用 skill 之前，需要知道模板中的 shape 名称。可以：

1. 手动在 PowerPoint 中查看（选择窗格）
2. 使用 Python 脚本提取（见 helper scripts）
3. 与模板创建者确认约定的命名规范

### 步骤 3: 准备替换内容

根据业务需求准备替换内容：

```python
replacements = [
    {
        "shape_name": "CLIENT_NAME",
        "content": "ABC公司"
    },
    {
        "shape_name": "REPORT_DATE",
        "content": "2024年第四季度"
    },
    {
        "shape_name": "KEY_METRIC_1",
        "content": "销售额: ¥1,234,567"
    },
    {
        "shape_name": "SUMMARY_TEXT",
        "content": "本季度业绩表现优异，同比增长35%。主要驱动因素包括：新产品线推出、市场份额扩大、客户满意度提升。"
    }
]
```

### 步骤 4: 调用编辑工具

使用 `slidespeak_edit` 工具：

```python
slidespeak_edit(
    pptx_file_path="/path/to/template.pptx",  # 模板文件路径
    config={
        "replacements": [
            {
                "shape_name": "CLIENT_NAME",
                "content": "ABC公司"
            },
            {
                "shape_name": "REPORT_TITLE",
                "content": "2024 Q4 业绩报告"
            },
            # ... 更多替换
        ]
    },
    save_dir="./outputs/edited_ppt"  # 保存目录
)
```

## 最佳实践

### 1. **模板设计原则**

**清晰的命名规范**：
```
# 推荐的命名模式
TITLE_SLIDE_1          # 第一页标题
SUBTITLE_SLIDE_1       # 第一页副标题
CONTENT_SLIDE_2_MAIN   # 第二页主要内容
CONTENT_SLIDE_2_SUB    # 第二页次要内容
DATA_CHART_TITLE       # 图表标题
```

**避免的命名**：
```
# 不推荐（太通用）
TextBox1
Shape2
Rectangle3
```

### 2. **内容格式化**

**文本内容**：
- 支持换行符 `\n`
- 保持文本长度适中（避免溢出）
- 使用一致的标点符号

**数值格式**：
```python
# 推荐
"content": "销售额: ¥1,234,567"
"content": "增长率: 35.2%"
"content": "客户数: 1,234 家"

# 不推荐
"content": "1234567"  # 缺少上下文
```

**日期格式**：
```python
# 清晰的日期格式
"content": "2024年12月25日"
"content": "2024-12-25"
"content": "Q4 2024"
```

### 3. **错误处理**

**常见错误**：

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| Shape not found | shape_name 不存在 | 检查模板中的形状名称 |
| Content too long | 文本超出形状大小 | 缩短内容或调整模板 |
| Invalid file | PPT 文件损坏 | 使用有效的 .pptx 文件 |
| API error | API key 或网络问题 | 检查 API 配置 |

**容错策略**：
```python
# 建议：先验证 shape 是否存在
# 可以使用 helper script 提取所有 shape 名称

replacements = []
for shape_name, content in data.items():
    if shape_name in valid_shape_names:
        replacements.append({
            "shape_name": shape_name,
            "content": content
        })
    else:
        print(f"⚠️ Warning: Shape '{shape_name}' not found in template")
```

### 4. **批量处理模式**

```python
# 场景：为多个客户生成个性化 PPT

clients = [
    {"name": "ABC公司", "sales": "¥1M", "growth": "35%"},
    {"name": "XYZ集团", "sales": "¥2M", "growth": "42%"},
    # ...
]

for client in clients:
    slidespeak_edit(
        pptx_file_path="templates/client_report.pptx",
        config={
            "replacements": [
                {"shape_name": "CLIENT_NAME", "content": client["name"]},
                {"shape_name": "SALES_AMOUNT", "content": client["sales"]},
                {"shape_name": "GROWTH_RATE", "content": client["growth"]},
            ]
        },
        save_dir=f"./outputs/clients/{client['name']}"
    )
```

## Helper Scripts

### 1. 提取 Shape 名称

```bash
# 查看模板中所有可替换的 shape
python3 scripts/extract_shapes.py /path/to/template.pptx
```

### 2. 验证替换配置

```bash
# 验证 config 是否有效
python3 scripts/validate_config.py --template template.pptx --config config.json
```

### 3. 批量编辑

```bash
# 从 CSV 批量生成
python3 scripts/batch_edit.py --template template.pptx --data data.csv --output ./outputs
```

## 工具调用格式

```python
# 基本用法
slidespeak_edit(
    pptx_file_path="./templates/quarterly_report.pptx",
    config={
        "replacements": [
            {"shape_name": "REPORT_TITLE", "content": "2024 Q4 财务报告"},
            {"shape_name": "COMPANY_NAME", "content": "科技有限公司"},
            {"shape_name": "QUARTER", "content": "第四季度"},
            {"shape_name": "REVENUE", "content": "¥12,345,678"},
            {"shape_name": "PROFIT", "content": "¥2,345,678"},
            {"shape_name": "GROWTH", "content": "+35.2%"}
        ]
    },
    save_dir="./outputs/reports"
)
```

## 与 slidespeak-generator 的对比

| 特性 | slidespeak-generator | slidespeak-editor |
|------|---------------------|-------------------|
| **用途** | 从头生成新的 PPT | 编辑现有的 PPT 模板 |
| **输入** | 内容和布局配置 | 模板文件 + 替换内容 |
| **灵活性** | 高（自由创建任意布局） | 中（受模板约束） |
| **一致性** | 中（每次可能不同） | 高（基于固定模板） |
| **适用场景** | 创意性、多样化内容 | 标准化、批量生成 |
| **速度** | 较慢（需生成布局） | 较快（只替换内容） |

**使用建议**：
- 需要**灵活布局**和**创意设计** → 使用 `slidespeak-generator`
- 需要**标准化**和**批量处理** → 使用 `slidespeak-editor`
- 复杂场景：先用 generator 生成模板，再用 editor 批量个性化

## 成功标准

✅ **正确性**：
- 所有 shape_name 都存在于模板中
- 内容成功替换到对应位置
- 生成的 PPT 可正常打开

✅ **质量**：
- 文本长度适中，无溢出
- 格式保持一致（字体、颜色等）
- 内容语义清晰、准确

✅ **效率**：
- 批量处理时效率高
- 减少手动操作错误
- 可复用模板

## 故障排查

### 问题 1: Shape 找不到
```
错误信息: "Shape 'XXX' not found"
解决: 
1. 在 PowerPoint 中打开模板
2. 查看"选择窗格"确认 shape 名称
3. 确保名称拼写正确（区分大小写）
```

### 问题 2: 内容溢出
```
现象: 文本被截断或显示不全
解决:
1. 缩短替换内容
2. 调整模板中形状的大小
3. 使用自动缩放的文本框
```

### 问题 3: API 调用失败
```
检查清单:
- [ ] API key 是否正确
- [ ] 文件是否存在且可读
- [ ] 文件格式是否为 .pptx（不支持 .ppt）
- [ ] 网络连接是否正常
```

## 进阶用法

### 1. 动态内容生成

```python
# 从数据库读取数据并填充
from database import get_quarterly_data

data = get_quarterly_data(year=2024, quarter=4)

slidespeak_edit(
    pptx_file_path="templates/report.pptx",
    config={
        "replacements": [
            {"shape_name": "REVENUE", "content": f"¥{data.revenue:,.0f}"},
            {"shape_name": "PROFIT", "content": f"¥{data.profit:,.0f}"},
            {"shape_name": "GROWTH", "content": f"+{data.growth:.1f}%"},
            {"shape_name": "SUMMARY", "content": data.generate_summary()}
        ]
    }
)
```

### 2. 条件替换

```python
# 根据条件决定替换内容
if growth_rate > 30:
    status_text = "🎉 表现优异"
    status_color = "green"
elif growth_rate > 10:
    status_text = "✓ 稳步增长"
    status_color = "blue"
else:
    status_text = "⚠️ 需要关注"
    status_color = "yellow"

slidespeak_edit(
    pptx_file_path="template.pptx",
    config={
        "replacements": [
            {"shape_name": "STATUS_TEXT", "content": status_text}
        ]
    }
)
```

### 3. 多页面替换

```python
# 对模板中的多个页面进行替换
slidespeak_edit(
    pptx_file_path="multi_page_template.pptx",
    config={
        "replacements": [
            # 封面页
            {"shape_name": "COVER_TITLE", "content": "年度总结报告"},
            {"shape_name": "COVER_SUBTITLE", "content": "2024年度"},
            
            # 内容页
            {"shape_name": "SLIDE2_TITLE", "content": "业绩概览"},
            {"shape_name": "SLIDE2_CONTENT", "content": "..."},
            
            # 总结页
            {"shape_name": "CONCLUSION_TEXT", "content": "感谢观看！"}
        ]
    }
)
```

## 参考资源

- **官方文档**: [SlideSpeak Edit API](https://docs.slidespeak.co/basics/api-references/edit-presentation/)
- **API Schema**: `resources/edit_api_schema.json`
- **示例模板**: `resources/example_template.pptx`
- **批量处理脚本**: `scripts/batch_edit.py`

