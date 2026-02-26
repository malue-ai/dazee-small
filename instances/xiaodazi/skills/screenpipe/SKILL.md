---
name: screenpipe
description: AI screen memory — search everything you've seen or heard on your computer. Integrates with Screenpipe's local MCP server for OCR text, audio transcripts, and app usage history.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: mcp
    user_facing: true
---

# Screenpipe — AI 屏幕记忆

24/7 记录屏幕内容和音频，让 AI 拥有「记忆」。用户可以回溯任何看过的内容、说过的话、用过的应用。所有数据本地存储，隐私优先。

## 使用场景

- 用户说「我昨天在哪个网页上看到那篇关于…的文章？」
- 用户说「上周开会时谁说了什么？」
- 用户说「今天我在电脑上花了多少时间在哪些应用上？」
- 用户说「帮我找一下之前看到的那个代码片段」
- 用户说「我这周总共写了多少代码？看了多少邮件？」
- 结合 `daily-briefing` 自动生成基于真实屏幕活动的每日回顾

## 前置条件

1. 安装 Screenpipe：https://screenpi.pe/ （macOS / Windows / Linux）
2. 启动 Screenpipe 后，本地 API 运行在 `http://localhost:3030`
3. Screenpipe 内置 MCP Server，通过 MCP 协议自动连接

## 执行方式

### 通过 MCP 工具调用

Screenpipe MCP 提供以下核心能力：

#### 搜索屏幕内容（OCR 文字）

```
工具: search_screen_content
参数:
  query: "搜索关键词"
  start_time: "2026-02-25T00:00:00Z"  # 可选，时间范围
  end_time: "2026-02-26T00:00:00Z"
  app_name: "Chrome"  # 可选，限定应用
  limit: 10
```

#### 搜索音频转录

```
工具: search_audio_transcripts
参数:
  query: "会议讨论内容"
  start_time: "2026-02-25T09:00:00Z"
  limit: 5
```

#### 获取应用使用统计

```
工具: get_app_usage
参数:
  start_time: "2026-02-25T00:00:00Z"
  end_time: "2026-02-26T00:00:00Z"
```

### 直接 API 调用（备选）

如果 MCP 不可用，可通过 HTTP API 访问：

```bash
# 搜索屏幕 OCR 内容
curl "http://localhost:3030/search?q=关键词&content_type=ocr&limit=10"

# 搜索音频转录
curl "http://localhost:3030/search?q=关键词&content_type=audio&limit=5"

# 获取最近活动
curl "http://localhost:3030/search?limit=20&start_time=2026-02-25T00:00:00Z"
```

### 典型工作流

**回溯查找**：
```
用户：我昨天下午看到一个很好的 Python 库，名字里有 pipe
→ 搜索 OCR 内容，时间限定为昨天下午
→ 返回匹配的屏幕截图和上下文
→ 告诉用户：你在 Chrome 中浏览了 GitHub 上的 xxx 项目（14:32）
```

**会议回顾**：
```
用户：今天上午的会议讨论了什么？
→ 搜索音频转录，时间限定为今天上午
→ 提取关键讨论点和行动项
→ 结构化输出会议摘要
```

**时间追踪**：
```
用户：我今天在各个应用上花了多少时间？
→ 获取应用使用统计
→ 生成时间分布报告（可结合 chart-image 生成图表）
```

## 与其他 Skills 的协作

| 组合 | 效果 |
|------|------|
| screenpipe + daily-briefing | 基于真实屏幕活动生成每日回顾 |
| screenpipe + meeting-insights-analyzer | 自动回顾会议录音和屏幕共享内容 |
| screenpipe + habit-tracker | 基于真实应用使用数据追踪习惯 |
| screenpipe + pomodoro | 回顾专注时段内的实际工作内容 |

## 输出规范

- 搜索结果附上时间戳和来源应用
- 涉及屏幕内容时描述上下文（哪个应用、哪个页面）
- 音频转录标注说话人（如果 Screenpipe 提供了说话人标签）
- 时间统计使用表格/图表呈现
- 尊重隐私：不主动提及用户未询问的敏感内容
