# Coze API - Ontology Builder 工作流

## 用途
**Ontology Builder** 工作流：基于 Mermaid 流程图生成系统配置（实体、属性、关系）。

⚠️ **重要**：
- 此 API 需要一个**已生成的 Mermaid 流程图文件 URL** 作为输入
- **必须先使用 `mcp_dify_Ontology_TextToChart_zen0` 工具生成流程图**，获取图表文件 URL 后再调用此 API

## 完整接口地址
`https://api.coze.cn/v1/workflow/run`

## 认证（自动注入）
- **认证已自动配置，调用时无需填写 `headers` 参数**
- ❌ **禁止**：不要在调用参数中填写 `headers`、`Authorization` 或任何认证信息
- ✅ **正确做法**：只需指定 `api_name: "coze_api"`，**无需填写 path 参数**

## 接口

### 执行 Ontology Builder 工作流（异步轮询）
- **完整地址**：`POST https://api.coze.cn/v1/workflow/run`（已配置，无需填写 path）
- **模式**：`async_poll`（异步提交 + 自动轮询结果）
- **请求体**：
```json
{
  "workflow_id": "7579565547005837331",
  "parameters": {
    "chart_url": "https://xxx.com/xxx.txt",
    "query": "系统名称",
    "language": "中文"
  },
  "is_async": true
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `workflow_id` | string | ✅ | 固定值: `"7579565547005837331"` |
| `parameters.chart_url` | string | ✅ | **Mermaid 流程图文件的 URL 地址**（必须是可访问的 HTTP URL） |
| `parameters.query` | string | ✅ | 系统名称或主题描述 |
| `parameters.language` | string | ✅ | 输出语言，如 `"中文"` 或 `"English"` |
| `is_async` | boolean | ✅ | 必须设置为 `true`，启用异步执行模式 |

⚠️ **注意**：
- `chart_url` 必须是**真实的文件 URL**，不能是描述性文本
- 不需要 `system_description` 参数

## 使用方法

使用 `api_calling` 工具调用（**注意：不要填写 headers 和 path 参数**）：

```
api_calling(
  api_name="coze_api",
  method="POST",
  mode="async_poll",
  body={
    "workflow_id": "7579565547005837331",
    "parameters": {
      "chart_url": "流程图文件的 URL",
      "query": "个人健康记录管理系统",
      "language": "中文"
    },
    "is_async": true
  },
  poll_config={
    "execute_id_field": "execute_id",
    "status_url_template": "https://api.coze.cn/v1/workflows/{workflow_id}/run_histories/{execute_id}",
    "body_vars": ["workflow_id"],
    "status_field": "data.status",
    "result_field": "data.output",
    "success_status": "Success",
    "failed_status": "Fail"
  }
)
```

⚠️ **调用时只需要以上参数**：
- ❌ 不要添加 `path` 参数（接口地址已完整配置）
- ❌ 不要添加 `headers`、`url` 参数（认证会自动处理）

### poll_config 说明

| 参数 | 说明 |
|------|------|
| `execute_id_field` | 初始响应中 execute_id 的路径，Coze API 返回 `execute_id` 在根级别 |
| `status_url_template` | 轮询 URL 模板，`{workflow_id}` 和 `{execute_id}` 会自动替换 |
| `body_vars` | 需要从请求 body 提取的变量列表 |
| `status_field` | 轮询响应中状态字段的路径 |
| `result_field` | 最终结果字段的路径 |
| `success_status` | 成功状态值 |
| `failed_status` | 失败状态值 |

## 典型使用流程

1. **第一步**：使用 `mcp_dify_Ontology_TextToChart_zen0` 工具生成 Mermaid 流程图
2. **第二步**：从返回结果中获取图表文件 URL（`chart_url`）
3. **第三步**：使用 `api_calling` 调用此 API，将图表 URL 传入 `chart_url` 参数

## 返回格式

异步轮询模式会自动等待任务完成，最终返回 `data.output` 中的结果（系统配置信息）。

### 执行流程
1. 提交任务 → 返回 `execute_id`
2. 自动轮询 `/workflows/{workflow_id}/run_histories/{execute_id}`
3. 状态变为 `Success` 时返回结果

