# Coze API - Ontology Builder 工作流

## 用途
**Ontology Builder** 工作流：基于 Mermaid 流程图生成系统配置（实体、属性、关系）。

⚠️ **重要**：
- 此 API 需要一个**已生成的 Mermaid 流程图文件 URL** 作为输入
- **必须先使用 `text2flowchart` 工具生成流程图**，获取图表文件 URL 后再调用此 API

## Base URL
`https://api.coze.cn/v1`

## 认证（自动注入）
- **认证已自动配置，调用时无需填写 `headers` 参数**
- ❌ **禁止**：不要在调用参数中填写 `headers`、`Authorization` 或任何认证信息
- ✅ **正确做法**：只需指定 `api_name: "coze_api"`，认证头会自动注入

## 接口

### 执行 Ontology Builder 工作流（流式）
- **路径**：`POST /workflow/stream_run`
- **请求体**：
```json
{
  "workflow_id": "7579565547005837331",
  "parameters": {
    "chart_url": "https://xxx.com/xxx.txt",
    "query": "系统名称",
    "language": "中文"
  }
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `workflow_id` | string | ✅ | 固定值: `"7579565547005837331"` |
| `parameters.chart_url` | string | ✅ | **Mermaid 流程图文件的 URL 地址**（必须是可访问的 HTTP URL） |
| `parameters.query` | string | ✅ | 系统名称或主题描述 |
| `parameters.language` | string | ✅ | 输出语言，如 `"中文"` 或 `"English"` |

⚠️ **注意**：
- `chart_url` 必须是**真实的文件 URL**，不能是描述性文本
- 不需要 `system_description` 参数

## 使用方法

使用 `api_calling` 工具调用（**注意：不要填写 headers 参数**）：

```
api_calling(
  api_name="coze_api",
  path="/workflow/stream_run",
  method="POST",
  mode="stream",
  body={
    "workflow_id": "7579565547005837331",
    "parameters": {
      "chart_url": "流程图文件的 URL",
      "query": "个人健康记录管理系统",
      "language": "中文"
    }
  }
)
```

⚠️ **调用时只需要以上参数，不要添加 `headers`、`url` 等参数，认证会自动处理。**

## 典型使用流程

1. **第一步**：使用 `text2flowchart` 工具生成 Mermaid 流程图
2. **第二步**：从返回结果中获取图表文件 URL
3. **第三步**：使用 `api_calling` 调用此 API，将图表 URL 传入 `chart_url` 参数

## 返回格式

SSE 流式返回，最终结果包含生成的系统配置信息。

