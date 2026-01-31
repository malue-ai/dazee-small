# Dify API - Text2Flowchart 工作流

## 用途
**text2flowchart** 工作流：分析文本中的实体、属性和关系，生成 Mermaid flowchart 图表。

⚠️ **重要**：当用户提到"生成流程图"、"flowchart"、"实体关系图" 时，**必须**使用此 API。

## Base URL
`https://api.dify.ai/v1`

## 认证
- Header: `Authorization: Bearer {DIFY_API_KEY}`
- 环境变量已配置: `DIFY_API_KEY`

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

当用户需要生成 flowchart 时，使用 `api_calling` 工具：

```
api_calling(
  method="POST",
  url="https://api.dify.ai/v1/workflows/run",
  headers={"Authorization": "Bearer ${DIFY_API_KEY}", "Content-Type": "application/json"},
  body={"inputs": {"query": "用户输入的文本"}, "response_mode": "blocking", "user": "agent"}
)
```

返回的 `data.outputs.text` 包含 Mermaid 格式的 flowchart。
