# Coze API - Ontology Builder 工作流

## 用途
基于 Mermaid 流程图生成系统配置（实体、属性、关系）。

## 前置条件
**必须先调用 `mcp_dify_Ontology_TextToChart_zen0` 获取 chart_url**

---

## 调用方式

```json
{
  "api_name": "coze_api",
  "parameters": {
    "chart_url": "【第一步获取的 URL】",
    "query": "【系统名称】",
    "language": "中文"
  }
}
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `chart_url` | ✅ | 第一步获取的流程图 URL |
| `query` | ✅ | 系统名称或描述 |
| `language` | ✅ | `"中文"` 或 `"English"` |

---

## 预计耗时
5-10 分钟（请提前告知用户）
