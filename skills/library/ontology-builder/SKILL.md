---
name: ontology-builder
description: 系统配置构建（三阶段原子操作），从自然语言描述生成结构化配置文件
---

# 系统配置构建 Skill

这个 Skill 帮助你从自然语言描述构建系统配置文件，采用三阶段原子操作确保数据完整性。

## Dify Workflow 配置

| 阶段 | App ID | 说明 |
|------|--------|------|
| text2flowchart | `a83e8b00-a94e-4cdf-b5f7-ef721e7238c1` | 自然语言 → Mermaid 流程图 |
| Part1 | `8b372c40-0b3f-4108-b7a8-3a5ef29af729` | 预处理 Mermaid 图表 |
| Part2 | `c3046a09-1833-4914-ace3-7548844d1c35` | 生成最终配置文件 |

**API 端点**: `POST https://api.dify.ai/v1/workflows/run`

## 完整流程

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│  自然语言描述    │ ──▶ │ Mermaid图表  │ ──▶ │   中间结果   │ ──▶ │  最终配置JSON   │
│     (query)     │     │ (chart_url) │     │(intermediate)│     │(ontology_json)  │
└─────────────────┘     └─────────────┘     └─────────────┘     └─────────────────┘
         │                    │                   │                     │
    text2flowchart        Part1               Part2                  完成
```

## 核心能力

- **三阶段处理**：text2flowchart → part1 → part2
- **多语言支持**：中文、英文、自动检测
- **结构化输出**：生成标准化的 JSON 配置文件
- **自动重试**：失败时自动重试，指数退避
- **内置 Claude**：text2flowchart 阶段使用 Claude 分析业务逻辑

## text2flowchart 功能说明

第一阶段 text2flowchart 内置 Claude，能够：

1. **识别核心实体**：从描述中识别所有对象实体
2. **定义实体属性**：为每个实体明确属性（最多10项）
3. **梳理实体关系**：用"主语-谓语-宾语"结构定义关系
4. **分类与样式**：对实体进行归类并应用样式
5. **生成 Mermaid 代码**：输出标准 flowchart 格式

## ⚠️ 重要规则

### 固定流程（禁止跳过任何步骤）

```
1. text2flowchart(query) → chart_url
2. build_ontology_part1(chart_url, query) → intermediate_url
3. build_ontology_part2(intermediate_url, query) → ontology_json_url
```

### 禁止行为

- ❌ 禁止跳过任何阶段
- ❌ 禁止将中间结果当作最终结果
- ❌ 禁止下载和解析 ontology_json_url 内容

## 输入参数

### build_ontology_full（完整流程）

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | - | 自然语言描述（业务流程、实体关系等） |
| language | string | 否 | auto | 语言代码：`zh_CN`/`en_US`/`auto` |
| user_id | string | 否 | default_user | 用户标识 |
| max_retries | int | 否 | 2 | 每个阶段的最大重试次数 |

### 分步调用参数

#### text_to_flowchart
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| query | string | 是 | 自然语言描述 |

#### build_ontology_part1
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| chart_url | string | 是 | Mermaid 图表 URL |
| query | string | 是 | 与 text2flowchart 一致 |

#### build_ontology_part2
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| intermediate_url | string | 是 | Part1 的输出 URL |
| query | string | 是 | 与 Part1 一致 |

## 输出格式

### 完整流程输出
```json
{
  "success": true,
  "ontology_json_url": "https://...",
  "chart_url": "https://...",
  "intermediate_url": "https://...",
  "message": "系统配置构建完成"
}
```

## 使用示例

### 完整流程（推荐）

```python
from skills.library.ontology_builder import build_ontology_full

result = await build_ontology_full(
    query="电商订单处理流程，包含用户、订单、商品、支付、物流等实体及其关系",
    language="zh_CN",
    user_id="user_123"
)

if result["success"]:
    print(f"配置 URL: {result['ontology_json_url']}")
    print(f"流程图 URL: {result['chart_url']}")
```

### 分步调用

```python
from skills.library.ontology_builder import (
    text_to_flowchart,
    build_ontology_part1,
    build_ontology_part2
)

# Step 0: 生成 Mermaid 流程图
result0 = await text_to_flowchart(
    query="电商订单处理流程...",
    language="zh_CN"
)
chart_url = result0["chart_url"]

# Step 1: 预处理
result1 = await build_ontology_part1(
    chart_url=chart_url,
    query="电商订单处理流程...",  # 保持一致！
    language="zh_CN"
)
intermediate_url = result1["intermediate_url"]

# Step 2: 生成最终配置
result2 = await build_ontology_part2(
    intermediate_url=intermediate_url,
    query="电商订单处理流程...",  # 保持一致！
    language="zh_CN"
)
ontology_json_url = result2["ontology_json_url"]
```

### 从已有图表构建

```python
from skills.library.ontology_builder import build_ontology_from_chart

# 如果已经有 chart_url，可以跳过 text2flowchart 阶段
result = await build_ontology_from_chart(
    chart_url="https://example.com/existing_flowchart.txt",
    query="电商订单处理流程...",
    language="zh_CN"
)
```

## 环境变量配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DIFY_API_URL` | Dify API 基础 URL | `https://api.dify.ai/v1` |
| `DIFY_ONTOLOGY_API_KEY` | 共享 API Key | `app-AUhGjUpkG34Su4iUAXoUZp0z` |
| `DIFY_FLOWCHART_API_KEY` | text2flowchart App Key | 同上 |
| `DIFY_ONTOLOGY_PART1_API_KEY` | Part1 App Key | 同上 |
| `DIFY_ONTOLOGY_PART2_API_KEY` | Part2 App Key | 同上 |

## 用户交互指引

| 时机 | 话术 |
|------|------|
| 开始前 | "好的，我来帮您构建系统配置，预计需要 5-8 分钟..." |
| text2flowchart 完成 | "流程图生成完成！正在构建系统配置..." |
| Part1 完成 | "系统配置第一阶段完成！正在进行最终处理..." |
| Part2 完成 | "系统配置构建完成！" |

### 禁止使用的术语
- ❌ "本体论" / "ontology"

## 预计耗时

| 阶段 | 耗时 |
|------|------|
| text2flowchart | 30-60 秒 |
| Part1 | 60-120 秒 |
| Part2 | 60-120 秒 |
| **总计** | **约 3-5 分钟** |

## 版本历史

- v1.1.0 (2025-01-09): 添加 text2flowchart 前置步骤，支持三阶段完整流程
- v1.0.0 (2025-01-09): 初始版本，两阶段处理

