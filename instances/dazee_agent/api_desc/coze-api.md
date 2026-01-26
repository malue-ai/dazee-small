# Coze API (coze_api)

## 用途
基于 Mermaid 流程图生成系统配置（实体、属性、关系）。

⚠️ **前置条件：必须先调用 `mcp_dify_Ontology_TextToChart_zen0` 获取 chart_url**

---

## AI 调用格式

```json
{
  "api_name": "coze_api",
  "parameters": {
    "chart_url": "流程图URL",
    "query": "系统名称",
    "language": "中文"
  }
}
```

---

## AI 需要填写的参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `chart_url` | string | ✅ | 第一步获取的 Mermaid 流程图 URL |
| `query` | string | ✅ | 系统名称或描述 |
| `language` | string | ✅ | 输出语言：`"中文"` 或 `"English"` |

> 💡 其他字段（workflow_id, is_async）由系统自动注入，AI 无需填写

---

## 调用示例

```json
{
  "api_name": "coze_api",
  "parameters": {
    "chart_url": "https://dify.ai/files/xxx/flowchart.png",
    "query": "订单管理系统",
    "language": "中文"
  }
}
```

---

## 预计耗时

5-10 分钟（请提前告知用户）

---

## 完整工作流

1. 用户描述系统需求
2. 调用 `mcp_dify_Ontology_TextToChart_zen0` 生成流程图 → 获取 `chart_url`
3. 调用 `coze_api` 生成系统配置 → 传入 `chart_url`
