# Dify API - 文档生成相关工作流

## 用途

Dify 平台提供多种工作流，主要用于文档处理和生成。

⚠️ **重要**：
- 流程图生成请使用 MCP 工具 `mcp_dify_Ontology_TextToChart_zen0`，不需要通过此 API 调用
- 此 API 主要用于其他 Dify 工作流（如有需要）

## Base URL
`https://api.dify.ai/v1`

## 认证（自动注入）
- **认证已自动配置，调用时无需填写 `headers` 参数**
- ❌ **禁止**：不要在调用参数中填写 `headers`、`Authorization` 或任何认证信息
- ✅ **正确做法**：只需指定 `api_name: "dify_api"`，认证头会自动注入

## 流程图生成

**⚠️ 不要使用 api_calling 调用 Dify API 来生成流程图！**

请直接使用 MCP 工具：

```
mcp_dify_Ontology_TextToChart_zen0(
  query="用户描述的文本内容"
)
```

返回结果包含流程图 URL：`chart_url`

## 使用 api_calling 调用其他 Dify 工作流（如需要）

```
api_calling(
  api_name="dify_api",
  path="/workflows/run",
  method="POST",
  body={"inputs": {"query": "用户输入的文本"}, "response_mode": "blocking", "user": "agent"}
)
```

⚠️ **不要填写 `url`、`headers`、`Authorization`，认证会自动处理。**
