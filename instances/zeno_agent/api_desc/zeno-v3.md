# ZenO V3 问答接口

## 接口概述

V3 提问接口提供 JSON 响应（非 SSE 流式），整合了对话创建和问答功能。

### 接口地址

```
POST http://183.6.79.71:40202/api/v3/zeno/chat/question
```

### 认证方式

```
Header: API-KEY: <your_api_key>
```

## 功能特性

- ✅ JSON 响应（非 SSE 流式）
- ✅ 整合创建和提问（task_id 不存在时自动创建）
- ✅ 支持文件追加
- ✅ 包含 report 字段（结构化数据）
- ✅ 文件解析等待机制（超时 120 秒）
- ✅ task_id == chat_id（简化参数）

## 自动化行为

1. **task_id 不存在**：自动创建用户、任务、数据源、对话、仪表板
2. **task_id 已存在且提供 files**：追加文件到数据源
3. **文件解析**：自动等待解析完成（最长 120 秒）

## 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | ZenO 用户 ID |
| `task_id` | string | ✅ | ZenO 任务 ID（同时也是 chat_id） |
| `question` | string | ✅ | 用户问题 |
| `files` | array | ⬜ | 文件列表（首次创建或追加文件时使用） |
| `lg_code` | string | ⬜ | 语言代码，默认 `zh-CN` |

### files 数组结构

```json
{
  "files": [
    {
      "file_name": "2024年销售数据.xlsx",
      "file_url": "https://example.com/data.xlsx"
    }
  ]
}
```

## 请求示例

```json
{
  "user_id": "user123",
  "task_id": "task001",
  "question": "2024年销售额是多少？",
  "files": [
    {
      "file_name": "2024年销售数据.xlsx",
      "file_url": "https://example.com/data.xlsx"
    }
  ],
  "lg_code": "zh-CN"
}
```

## 响应参数

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 执行成功标识 |
| `message_id` | string | 消息 ID |
| `conversation_id` | string | 对话 ID（值同 task_id） |
| `dashboard_id` | string | 仪表板 ID |
| `intent` | number | 意图 ID |
| `intent_name` | string | 意图名称（如"智能分析"） |
| `report` | object | 分析报告（含 title + content） |
| `sql` | string | 生成的 SQL 语句 |
| `chart` | object | 图表配置对象 |
| `data` | object | 查询结果数据（含 columns + rows） |
| `error` | object | 错误信息（失败时提供） |

### report 结构

```json
{
  "report": {
    "title": "2024年销售数据分析",
    "content": "## 总体情况\n\n2024年总销售额为1000万元..."
  }
}
```

### data 结构

```json
{
  "data": {
    "columns": ["month", "amount"],
    "rows": [
      ["1月", 100000],
      ["2月", 120000]
    ]
  }
}
```

## 成功响应示例

```json
{
  "success": true,
  "message_id": "msg_123",
  "conversation_id": "task001",
  "dashboard_id": "dashboard_456",
  "intent": 2,
  "intent_name": "智能分析",
  "report": {
    "title": "2024年销售数据分析",
    "content": "## 总体情况\n\n2024年总销售额为1000万元..."
  },
  "sql": "SELECT SUM(amount) FROM sales WHERE year=2024",
  "chart": {
    "chart_type": "bar"
  },
  "data": {
    "columns": ["month", "amount"],
    "rows": []
  }
}
```

## 错误响应示例

```json
{
  "success": false,
  "error": {
    "code": "FILE_PARSE_TIMEOUT",
    "message": "文件解析超时，请重试"
  }
}
```

## api_calling 调用示例

**重要**：调用时必须传入 `auth` 参数，认证头会自动注入。

```json
{
  "url": "http://183.6.79.71:40202/api/v3/zeno/chat/question",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": {
    "user_id": "user123",
    "task_id": "task001",
    "question": "2024年销售额是多少？",
    "lg_code": "zh-CN"
  },
  "auth": {
    "type": "api_key",
    "credentials": {
      "header_name": "API-KEY",
      "env_var": "ZENO_API_KEY"
    }
  }
}
```

**auth 参数说明**：
- `type`: 固定为 `"api_key"`
- `credentials.header_name`: 认证头名称，固定为 `"API-KEY"`
- `credentials.env_var`: 环境变量名，固定为 `"ZENO_API_KEY"`（系统会自动读取）

## 注意事项

1. **首次对话**：首次使用某个 task_id 时，建议提供 files 参数创建数据源
2. **追加文件**：在已有 task_id 基础上再次提供 files，会追加到现有数据源
3. **解析等待**：上传文件后 API 会自动等待解析，可能需要较长时间
4. **超时处理**：解析超时（120秒）会返回错误，建议提示用户重试

