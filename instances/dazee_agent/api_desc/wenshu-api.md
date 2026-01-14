# 问数平台 API - 数据分析问答

## 用途
**问数平台 V3**：数据分析和问答接口，支持上传文件、自然语言查询、返回分析报告和图表。

⚠️ **重要**：当识别为 **意图2（BI智能问数）** 时，必须使用此 API。

## Base URL
`${WENSHU_API_BASE_URL}`（环境变量配置）

## 认证
- Header: `Authorization: Bearer {WENSHU_API_KEY}`
- 环境变量已配置: `WENSHU_API_KEY`
- **使用 `api_name: "wenshu_api"` 时认证自动注入**

## 接口

### 数据分析问答
- **路径**：`POST /api/v3/ask`
- **请求体**：
```json
{
  "user_id": "用户ID",
  "task_id": "任务ID（等于conversation_id）",
  "question": "用户的数据分析问题",
  "lg_code": "zh-CN",
  "files": [
    {
      "file_name": "销售数据.xlsx",
      "file_url": "https://example.com/data.xlsx"
    }
  ]
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 用户标识（框架自动注入） |
| `task_id` | string | ✅ | 任务标识，使用 conversation_id |
| `question` | string | ✅ | 用户的数据分析问题 |
| `lg_code` | string | ⬜ | 语言代码，默认 `zh-CN` |
| `files` | array | ⬜ | 数据文件列表（首次提问时上传） |

### 返回示例
```json
{
  "success": true,
  "message_id": "msg_xxx",
  "conversation_id": "conv_xxx",
  "intent": 1,
  "intent_name": "智能分析",
  "report": {
    "title": "销售数据分析报告",
    "content": "根据数据分析，2024年总销售额为..."
  },
  "sql": "SELECT SUM(amount) FROM sales WHERE year = 2024",
  "chart": {
    "chart_type": "bar",
    "x_axis": "month",
    "y_axis": "amount"
  },
  "data": {
    "columns": ["month", "amount"],
    "rows": [["1月", 10000], ["2月", 12000]]
  }
}
```

### 返回字段说明

| 字段 | 说明 |
|------|------|
| `success` | 是否成功 |
| `report` | 分析报告，包含 title 和 content |
| `intent_name` | 识别的意图类型 |
| `sql` | 生成的 SQL 查询语句 |
| `chart` | 图表配置（chart_type 等） |
| `data` | 查询结果数据（columns + rows） |

## 使用方法

使用 `api_calling` 工具调用：

```
api_calling(
  api_name="wenshu_api",
  path="/api/v3/ask",
  method="POST",
  body={
    "user_id": "${user_id}",
    "task_id": "${conversation_id}",
    "question": "2024年销售额是多少？",
    "lg_code": "zh-CN",
    "files": [
      {"file_name": "销售数据.xlsx", "file_url": "https://..."}
    ]
  }
)
```

## 使用场景

1. **首次上传文件并提问**：传入 files 参数
2. **追问（已有数据）**：只传 question，复用已上传的数据
3. **文件追加**：再次传入 files 会追加到数据源

## 注意事项

- `task_id` 使用 `conversation_id`，一个对话对应一个数据分析会话
- 文件解析可能需要较长时间，超时设置为 180 秒
- 如果 `success` 为 false，查看 `error` 字段获取错误信息

