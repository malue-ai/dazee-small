---
name: web-search
description: Local web search (Tavily/Exa, requires API Key). For quick searches. If no Key configured or deep research needed, use cloud_agent instead.
metadata:
  xiaodazi:
    backend_type: tool
    tool_name: web_search
    dependency_level: builtin
    os: [common]
    user_facing: true

---

# Web Search

本地搜索工具，直接调用 `web_search`，自动选择 Tavily 或 Exa。

## 与 cloud_agent 的区别

| | web_search | cloud_agent |
|---|---|---|
| 运行位置 | 本地 | 云端 |
| API Key | 需用户自行配置 | 云端已有 |
| 适合场景 | 快速搜索、简单查询 | 深度调研、多步分析、长任务 |
| 速度 | 快（200ms-3s） | 慢（1-5 分钟） |

**决策规则**：本地有 Key → `web_search`；本地无 Key 或需要深度调研 → `cloud_agent`。

## 使用场景

- 用户说「帮我搜一下…」「查查…」「最新消息」
- 快速搜索、简单查询（本地有 Key 时）

## 调用方式

参数只需 `query`，其他可选：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `query` | string | **必填** | 搜索关键词 |
| `max_results` | integer | 5 | 最大结果数（上限 20） |
| `search_depth` | string | basic | `basic`（快速）或 `advanced`（深度） |
| `time_range` | string | any | `day` / `week` / `month` / `any` |

## 搜索后端

| 后端 | Key | 免费额度 | 特点 |
|---|---|---|---|
| Tavily | `TAVILY_API_KEY` | 1000 次/月 | AI 优化，200ms 响应 |
| Exa | `EXA_API_KEY` | 1000 次/月 | 语义搜索，含全文 |

至少配置一个 API Key 即可使用。

## 输出规范

- 回答时标注信息来源（附链接）
- 区分「事实」和「推测/观点」
- 搜索结果不充分时告知用户
- 时效性信息标注日期
