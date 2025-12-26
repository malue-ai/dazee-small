# SlideSpeak Editor Skill

编辑现有的 PowerPoint 文件，通过替换指定形状（shape）的内容来实现批量修改和个性化定制。

## 📋 目录

- [功能概述](#功能概述)
- [使用场景](#使用场景)
- [快速开始](#快速开始)
- [文件结构](#文件结构)
- [API 参考](#api-参考)
- [最佳实践](#最佳实践)
- [故障排查](#故障排查)

## 功能概述

`slidespeak-editor` skill 提供了编辑现有 PowerPoint 文件的能力，基于 [SlideSpeak Edit Presentation API](https://docs.slidespeak.co/basics/api-references/edit-presentation/)。

### 核心特性

- ✅ **批量个性化生成** - 基于一个模板为多个客户/场景生成定制化 PPT
- ✅ **内容更新** - 快速更新现有 PPT 的特定部分
- ✅ **多语言版本** - 从一个模板生成不同语言版本
- ✅ **数据驱动** - 从数据库/CSV 自动填充 PPT 内容
- ✅ **保持设计** - 只修改内容，保留原有布局和设计

### 与 slidespeak-generator 的对比

| 特性 | slidespeak-generator | slidespeak-editor |
|------|---------------------|-------------------|
| **用途** | 从头生成新的 PPT | 编辑现有的 PPT 模板 |
| **输入** | 内容和布局配置 | 模板文件 + 替换内容 |
| **灵活性** | 高（自由创建任意布局） | 中（受模板约束） |
| **一致性** | 中（每次可能不同） | 高（基于固定模板） |
| **适用场景** | 创意性、多样化内容 | 标准化、批量生成 |
| **速度** | 较慢（需生成布局） | 较快（只替换内容） |

## 使用场景

### 1. 批量个性化报告

为每个客户生成定制化的季度报告：

```python
clients = [
    {"name": "ABC公司", "revenue": "¥1.2M", "growth": "35%"},
    {"name": "XYZ集团", "revenue": "¥2.5M", "growth": "42%"},
]

for client in clients:
    slidespeak_edit(
        pptx_file_path="templates/quarterly_report.pptx",
        config={
            "replacements": [
                {"shape_name": "CLIENT_NAME", "content": client["name"]},
                {"shape_name": "REVENUE", "content": client["revenue"]},
                {"shape_name": "GROWTH", "content": client["growth"]}
            ]
        }
    )
```

### 2. 多语言版本生成

从一个模板生成中英文版本：

```python
translations = {
    "en": {"TITLE": "Annual Report", "SUBTITLE": "2024 Q4"},
    "zh": {"TITLE": "年度报告", "SUBTITLE": "2024年第四季度"}
}

for lang, texts in translations.items():
    slidespeak_edit(
        pptx_file_path="template.pptx",
        config={
            "replacements": [
                {"shape_name": "TITLE", "content": texts["TITLE"]},
                {"shape_name": "SUBTITLE", "content": texts["SUBTITLE"]}
            ]
        },
        save_dir=f"./outputs/{lang}"
    )
```

### 3. 数据驱动的周报

从数据库自动生成周报：

```python
# 从数据库获取本周数据
weekly_data = get_weekly_metrics()

slidespeak_edit(
    pptx_file_path="templates/weekly_report.pptx",
    config={
        "replacements": [
            {"shape_name": "WEEK_NUMBER", "content": f"第{weekly_data.week}周"},
            {"shape_name": "SALES", "content": f"¥{weekly_data.sales:,.0f}"},
            {"shape_name": "ORDERS", "content": str(weekly_data.orders)},
            {"shape_name": "CONVERSION", "content": f"{weekly_data.conversion:.1f}%"}
        ]
    }
)
```

## 快速开始

### 步骤 1: 准备模板

在 PowerPoint 中为需要替换的形状命名：

1. 打开 PowerPoint
2. 选择要编辑的文本框/形状
3. 右键 → "选择窗格"（Selection Pane）
4. 重命名形状为有意义的名称（如 `TITLE`, `CLIENT_NAME`, `DATA_VALUE`）

**命名建议**：
- 使用清晰的前缀：`TARGET_`, `DATA_`, `CLIENT_`
- 使用描述性名称：`TITLE`, `SUBTITLE`, `CONTENT`
- 避免特殊字符和空格

### 步骤 2: 提取形状名称

使用辅助脚本查看模板中的所有形状：

```bash
cd skills/library/slidespeak-editor
python3 scripts/extract_shapes.py /path/to/template.pptx
```

输出示例：

```
📄 文件: template.pptx
📊 总计 3 页幻灯片

📍 幻灯片 1
  • TITLE_SLIDE_1
    └─ 内容: 季度业绩报告
  • SUBTITLE_SLIDE_1
    └─ 内容: 2024 Q4
  • COMPANY_LOGO
    └─ 内容: 

📝 可编辑的形状名称列表:
  • TITLE_SLIDE_1 (幻灯片 1)
  • SUBTITLE_SLIDE_1 (幻灯片 1)
  • CONTENT_SLIDE_2 (幻灯片 2)
```

### 步骤 3: 编辑 PPT

通过 Agent 调用：

```
用户: 请帮我编辑 quarterly_report.pptx 模板，替换以下内容：
- TITLE → "2024年第四季度财务报告"
- COMPANY_NAME → "科技创新有限公司"
- REVENUE → "¥12,345,678"

Agent: [调用 slidespeak_edit 工具完成编辑]
```

或直接调用工具：

```python
slidespeak_edit(
    pptx_file_path="./templates/quarterly_report.pptx",
    config={
        "replacements": [
            {"shape_name": "TITLE", "content": "2024年第四季度财务报告"},
            {"shape_name": "COMPANY_NAME", "content": "科技创新有限公司"},
            {"shape_name": "REVENUE", "content": "¥12,345,678"}
        ]
    },
    save_dir="./outputs/reports"
)
```

## 文件结构

```
slidespeak-editor/
├── SKILL.md                    # Skill 详细文档
├── README.md                   # 本文件
├── __init__.py                 # Python 包初始化
├── resources/
│   ├── edit_api_schema.json    # API Schema 定义
│   └── example_template.pptx   # 示例模板（可选）
└── scripts/
    ├── extract_shapes.py       # 提取模板中的形状名称
    ├── validate_config.py      # 验证编辑配置
    └── batch_edit.py           # 批量编辑脚本（待实现）
```

## API 参考

### slidespeak_edit 工具

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pptx_file_path` | string | ✅ | 要编辑的 PPT 文件路径 |
| `config` | object | ✅ | 编辑配置对象 |
| `config.replacements` | array | ✅ | 替换列表 |
| `config.replacements[].shape_name` | string | ✅ | 形状名称 |
| `config.replacements[].content` | string | ✅ | 新内容 |
| `save_dir` | string | ❌ | 保存目录（默认：`./outputs/edited_ppt`） |

**返回值**：

```json
{
  "success": true,
  "download_url": "https://slidespeak-pptx-writer.s3.amazonaws.com/xxx.pptx",
  "local_path": "./outputs/edited_ppt/edited_20241225_120000.pptx",
  "replacements_count": 3,
  "message": "成功替换 3 个形状的内容"
}
```

### 辅助脚本

#### extract_shapes.py

提取 PPT 中所有形状的名称：

```bash
python3 scripts/extract_shapes.py template.pptx
```

#### validate_config.py

验证编辑配置是否有效：

```bash
python3 scripts/validate_config.py --template template.pptx --config config.json
```

## 最佳实践

### 1. 模板设计

**推荐的命名规范**：

```
# 按页面和类型组织
SLIDE1_TITLE          # 第1页标题
SLIDE1_SUBTITLE       # 第1页副标题
SLIDE2_CONTENT_MAIN   # 第2页主要内容
SLIDE2_CONTENT_SUB    # 第2页次要内容

# 按数据类型组织
DATA_REVENUE          # 收入数据
DATA_PROFIT           # 利润数据
DATA_GROWTH           # 增长率

# 按业务对象组织
CLIENT_NAME           # 客户名称
CLIENT_LOGO           # 客户徽标
PROJECT_TITLE         # 项目标题
```

**避免的命名**：

```
TextBox1              # 太通用
Shape2                # 无意义
矩形3                 # 使用中文（可能有兼容性问题）
```

### 2. 内容格式化

**文本内容**：

```python
# ✅ 推荐：清晰的格式
"销售额: ¥1,234,567"
"增长率: +35.2%"
"客户数: 1,234 家"

# ❌ 不推荐：缺少上下文
"1234567"
"35.2"
```

**日期格式**：

```python
# 清晰的日期格式
"2024年12月25日"
"2024-12-25"
"Q4 2024"
"第四季度"
```

### 3. 错误处理

```python
# 建议：先验证 shape 是否存在
template_shapes = extract_shapes(template_path)

replacements = []
for shape_name, content in data.items():
    if shape_name in template_shapes:
        replacements.append({
            "shape_name": shape_name,
            "content": content
        })
    else:
        print(f"⚠️ Warning: Shape '{shape_name}' not found")
```

### 4. 批量处理

```python
# 批量处理模式
for item in data_list:
    try:
        result = slidespeak_edit(
            pptx_file_path="template.pptx",
            config=generate_config(item),
            save_dir=f"./outputs/{item.id}"
        )
        if result["success"]:
            print(f"✅ {item.name}: 成功")
        else:
            print(f"❌ {item.name}: {result['error']}")
    except Exception as e:
        print(f"❌ {item.name}: 异常 - {e}")
        continue  # 继续处理下一个
```

## 故障排查

### 问题 1: Shape 找不到

```
错误: "Shape 'XXX' not found"

解决方案:
1. 使用 extract_shapes.py 查看模板中的所有形状
2. 确认 shape_name 拼写正确（区分大小写）
3. 在 PowerPoint 中检查"选择窗格"
```

### 问题 2: 内容溢出

```
现象: 文本被截断或显示不全

解决方案:
1. 缩短替换内容
2. 调整模板中形状的大小
3. 使用自动缩放的文本框
4. 分段显示长文本
```

### 问题 3: API 调用失败

```
检查清单:
- [ ] SLIDESPEAK_API_KEY 环境变量是否设置
- [ ] 文件路径是否正确
- [ ] 文件格式是否为 .pptx（不支持 .ppt）
- [ ] 网络连接是否正常
- [ ] API 配额是否充足
```

### 问题 4: 编码问题

```
现象: 中文显示乱码

解决方案:
1. 确保配置文件使用 UTF-8 编码
2. Python 脚本中使用 encoding='utf-8'
3. 模板文件使用标准字体（如微软雅黑）
```

## 测试

运行测试：

```bash
# 测试 skill 是否被正确加载
python3 tests/test_slidespeak_editor.py

# 测试单个编辑操作
python3 -c "
from tools.slidespeak_edit import SlideSpeakEditTool
tool = SlideSpeakEditTool()
result = tool.execute(
    pptx_file_path='template.pptx',
    config={'replacements': [{'shape_name': 'TITLE', 'content': '测试'}]}
)
print(result)
"
```

## 参考资源

- **官方 API 文档**: [SlideSpeak Edit Presentation](https://docs.slidespeak.co/basics/api-references/edit-presentation/)
- **Skill 详细文档**: [SKILL.md](./SKILL.md)
- **API Schema**: [resources/edit_api_schema.json](./resources/edit_api_schema.json)
- **架构文档**: [docs/00-ARCHITECTURE-OVERVIEW.md](../../../docs/00-ARCHITECTURE-OVERVIEW.md)

## 许可证

与项目主许可证相同。

