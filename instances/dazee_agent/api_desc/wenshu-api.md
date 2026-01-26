# 问数平台 API - 数据分析问答

## 用途
数据分析和问答接口，支持上传文件、自然语言查询、返回分析报告和图表。

⚠️ **意图2（BI智能问数）必须使用此 API**

---

## 调用方式

### 首次提问（带文件）
```json
{
  "api_name": "wenshu_api",
  "parameters": {
    "question": "2024年销售额是多少？",
    "files": [
      {"file_name": "销售数据.xlsx", "file_url": "https://..."}
    ]
  }
}
```

### 追问（无需文件）
```json
{
  "api_name": "wenshu_api",
  "parameters": {
    "question": "按月份拆分看看"
  }
}
```

---

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `question` | ✅ | 用户的数据分析问题 |
| `files` | ⬜ | 数据文件列表（首次提问时需要） |
| `files[].file_name` | ✅ | 文件名 |
| `files[].file_url` | ✅ | 文件 URL |

---

## 返回字段

| 字段 | 说明 |
|------|------|
| `report.title` | 分析报告标题 |
| `report.content` | 分析报告内容 |
| `chart` | 图表配置（前端自动渲染） |
| `sql` | 生成的 SQL |
| `data` | 查询结果数据 |

---

## 使用场景

1. **首次分析**：传入 `question` + `files`
2. **追问**：只传 `question`
3. **追加数据**：再次传入 `files`

