---
name: ontology-builder
description: 系统配置构建，从自然语言描述生成结构化配置文件（基于 Coze 工作流）
---

# 系统配置构建 Skill

这个 Skill 帮助你从自然语言描述构建系统配置文件，使用 Coze 工作流实现。

## Coze Workflow 配置

| 配置项 | 值 |
|--------|------|
| API 端点 | `https://api.coze.cn/v1/workflow/run` |
| Workflow ID | `7579565547005837331` |
| 认证方式 | Bearer Token |
| 预计耗时 | **5-10 分钟** |

## 工作流程

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────────┐
│  自然语言描述    │ ──▶ │ Mermaid图表  │ ──▶ │  最终配置JSON   │
│     (query)     │     │ (chart_url) │     │(ontology_json)  │
└─────────────────┘     └─────────────┘     └─────────────────┘
         │                    │                     │
    text2flowchart      Coze Workflow           完成
      (MCP工具)          (api_calling)
```

## 核心能力

- **一步处理**：通过 Coze 工作流完成全部处理
- **多语言支持**：中文、英文
- **结构化输出**：生成标准化的 JSON 配置文件
- **长时任务**：支持 5-10 分钟的处理时间

## API 调用方式

使用 `api_calling` 工具调用 Coze 工作流：

```python
# 使用 api_calling 工具调用
result = await api_calling(
    url="https://api.coze.cn/v1/workflow/run",
    method="POST",
    headers={
        "Authorization": "Bearer ${COZE_API_KEY}",
        "Content-Type": "application/json"
    },
    body={
        "workflow_id": "7579565547005837331",
        "parameters": {
            "chart_url": "https://example.com/flowchart.txt",  # 流程图 URL
            "query": "电商订单处理流程...",                      # 业务描述
            "language": "zh_CN"                                 # 语言代码
        }
    }
)
```

## 输入参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| chart_url | string | 是 | Mermaid 流程图的 URL（由 text2flowchart 生成） |
| query | string | 是 | 自然语言描述（业务流程、实体关系等） |
| language | string | 是 | 语言代码：`zh_CN` / `en_US` |

## 输出格式

### 成功响应
```json
{
  "code": 0,
  "msg": "success",
  "data": "{\"ontology_json_url\": \"https://...\"}"
}
```

### 错误响应
```json
{
  "code": 1,
  "msg": "error message"
}
```

## ⚠️ 重要规则

### 前置步骤（text2flowchart）

在调用本工作流之前，**必须先调用 `text2flowchart`** 生成流程图：

```
1. text2flowchart(query) → chart_url
2. coze_workflow(chart_url, query, language) → ontology_json_url
```

### 禁止行为

- ❌ 禁止跳过 text2flowchart 阶段
- ❌ 禁止使用空的 chart_url
- ❌ 禁止下载和解析 ontology_json_url 内容

## 使用示例

### 完整流程

```python
# Step 1: 生成 Mermaid 流程图
flowchart_result = await text2flowchart(
    query="电商订单处理流程，包含用户、订单、商品、支付、物流等实体及其关系"
)
chart_url = flowchart_result["chart_url"]

# Step 2: 调用 Coze 工作流生成配置
result = await api_calling(
    url="https://api.coze.cn/v1/workflow/run",
    method="POST",
    headers={
        "Authorization": "Bearer ${COZE_API_KEY}",
        "Content-Type": "application/json"
    },
    body={
        "workflow_id": "7579565547005837331",
        "parameters": {
            "chart_url": chart_url,
            "query": "电商订单处理流程，包含用户、订单、商品、支付、物流等实体及其关系",
            "language": "zh_CN"
        }
    }
)

# 解析结果
if result.get("code") == 0:
    data = json.loads(result["data"])
    ontology_json_url = data["ontology_json_url"]
```

## 环境变量配置

| 变量名 | 说明 |
|--------|------|
| `COZE_API_KEY` | Coze API 访问令牌 |

## 用户交互指引

| 时机 | 话术 |
|------|------|
| 开始前 | "好的，我来帮您构建系统配置，预计需要 5-10 分钟，请稍候..." |
| text2flowchart 完成 | "流程图生成完成！正在构建系统配置..." |
| 配置完成 | "系统配置构建完成！" |

### 禁止使用的术语
- ❌ "本体论" / "ontology"（对用户不可见）

## 预计耗时

| 阶段 | 耗时 |
|------|------|
| text2flowchart | 1-2 分钟 |
| Coze 工作流 | 5-10 分钟 |
| **总计** | **约 6-12 分钟** |

## 与旧版 Dify API 的对比

| 对比项 | 旧版 (Dify) | 新版 (Coze) |
|--------|-------------|-------------|
| API 调用次数 | 3 次（Part1 + Part2 + Part3） | 1 次 |
| 预计耗时 | 3-5 分钟 | 5-10 分钟 |
| 复杂度 | 需要串联三个步骤 | 单一工作流 |
| 中间状态 | 有 intermediate_url | 无 |
