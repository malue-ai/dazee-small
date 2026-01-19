# Dify API - Text2Flowchart 工作流

## 用途
**text2flowchart** 工作流：分析文本中的实体、属性和关系，生成 Mermaid flowchart 图表。

⚠️ **重要**：当用户提到"生成流程图"、"flowchart"、"实体关系图" 时，**必须**使用此 API。

## Base URL
`https://api.dify.ai/v1`

## 认证（自动注入）
- **认证已自动配置，调用时无需填写 `headers` 参数**
- ❌ **禁止**：不要在调用参数中填写 `headers`、`Authorization` 或任何认证信息
- ✅ **正确做法**：只需指定 `api_name: "dify_api"`，认证头会自动注入

## 接口

### 执行 text2flowchart 工作流
- **路径**：`POST /workflows/run`
- **请求体**：
```json
{
  "inputs": {
    "query": "用户描述的文本内容"
  },
  "response_mode": "blocking",
  "user": "agent_user"
}
```
- **返回示例**：
```json
{
  "workflow_run_id": "xxx",
  "data": {
    "outputs": {
      "text": "```mermaid\nflowchart TD\n  User[用户] --> Role[角色]\n  Role --> Permission[权限]\n```"
    }
  }
}
```

## 使用方法

当用户需要生成 flowchart 时，使用 `api_calling` 工具（**不要填写 headers**）：

```
api_calling(
  api_name="dify_api",
  path="/workflows/run",
  method="POST",
  body={"inputs": {"query": "用户输入的文本"}, "response_mode": "blocking", "user": "agent"}
)
```

⚠️ **不要填写 `url`、`headers`、`Authorization`，认证会自动处理。**

返回的 `data.outputs.text` 包含 Mermaid 格式的 flowchart。
