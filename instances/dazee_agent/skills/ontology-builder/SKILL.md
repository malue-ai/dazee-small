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
| 认证方式 | Bearer Token（自动注入） |
| 响应模式 | **异步轮询**（async_poll） |
| 预计耗时 | **5-10 分钟** |

## 工作流程

```
┌─────────────────┐     ┌─────────────┐     ┌─────────────────┐
│  自然语言描述    │ ──▶ │ Mermaid图表  │ ──▶ │  最终配置JSON   │
│     (query)     │     │ (chart_url) │     │(ontology_json)  │
└─────────────────┘     └─────────────┘     └─────────────────┘
         │                    │                     │
mcp_dify_Ontology_    Coze Workflow           完成
TextToChart_zen0       (api_calling)
    (MCP工具)
```

## 核心能力

- **多语言支持**：中文、英文
- **结构化输出**：生成标准化的 JSON 配置文件
- **长时任务**：支持 5-10 分钟的处理时间

## API 调用方式（简化版）

使用 `api_calling` 工具调用 Coze 工作流：

```json
{
  "api_name": "coze_api",
  "parameters": {
    "chart_url": "流程图文件的 URL",
    "query": "系统名称或主题描述",
    "language": "中文"
  }
}
```

**关键点**：
- ✅ 只需传 `api_name` 和 `parameters`
- ✅ 其他配置（method、mode、poll_config 等）由系统自动注入
- ❌ **不要填写** `headers`、`url`、`path`、`body`、`poll_config` 等参数

## 输入参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| chart_url | string | 是 | Mermaid 流程图的 URL（由 mcp_dify_Ontology_TextToChart_zen0 生成） |
| query | string | 是 | 自然语言描述（业务流程、实体关系等） |
| language | string | 是 | 输出语言：`"中文"` 或 `"English"` |

## 输出格式

异步轮询模式会自动等待任务完成，最终返回 `data.output` 中的结果。

### 执行流程
1. 提交任务 → 返回 `execute_id`
2. 自动轮询 `/workflows/{workflow_id}/run_histories/{execute_id}`
3. 状态变为 `Success` 时返回结果

### 错误响应
```json
{
  "code": 1,
  "msg": "error message"
}
```

## ⚠️ 重要规则

### 前置步骤（mcp_dify_Ontology_TextToChart_zen0）

在调用本工作流之前，**必须先调用 `mcp_dify_Ontology_TextToChart_zen0`** 生成流程图：

```
1. mcp_dify_Ontology_TextToChart_zen0(query) → chart_url
2. api_calling(coze_api, chart_url, query, language) → ontology_json_url
```

### 禁止行为

- ❌ 禁止跳过 mcp_dify_Ontology_TextToChart_zen0 阶段
- ❌ 禁止使用空的 chart_url
- ❌ 禁止下载和解析 ontology_json_url 内容
- ❌ 禁止填写 `headers`、`url`、`path` 参数（认证自动处理）

## 使用示例

### 完整流程

```python
# Step 1: 生成 Mermaid 流程图
flowchart_result = await mcp_dify_Ontology_TextToChart_zen0(
    query="电商订单处理流程，包含用户、订单、商品、支付、物流等实体及其关系"
)
chart_url = flowchart_result["chart_url"]

# Step 2: 调用 Coze 工作流生成配置（简化调用方式）
result = await api_calling(
    api_name="coze_api",
    parameters={
        "chart_url": chart_url,
        "query": "电商订单处理流程，包含用户、订单、商品、支付、物流等实体及其关系",
        "language": "中文"
    }
)

# 结果自动返回完整响应
ontology_json_url = result.get("data", [{}])[0].get("output")
```

## 环境变量配置

| 变量名 | 说明 |
|--------|------|
| `COZE_API_KEY` | Coze API 访问令牌（自动注入，无需手动配置） |

## 用户交互指引

| 时机 | 话术 |
|------|------|
| 开始前 | "好的，我来帮您构建系统配置，预计需要 5-10 分钟，请稍候..." |
| mcp_dify_Ontology_TextToChart_zen0 完成 | "流程图生成完成！正在构建系统配置..." |
| 配置完成 | "系统配置构建完成！" |

### 禁止使用的术语
- ❌ "本体论" / "ontology"（对用户不可见）

## 预计耗时

| 阶段 | 耗时 |
|------|------|
| mcp_dify_Ontology_TextToChart_zen0 | 1-2 分钟 |
| Coze 工作流 | 5-10 分钟 |
| **总计** | **约 6-12 分钟** |
