---
name: google-workspace
description: Google Calendar, Gmail, Drive, and Docs via official Google MCP. Create events, manage emails, access files — all through natural language.
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: mcp
    user_facing: true
---

# Google Workspace — 日历、邮件、云盘、文档

通过 Google 官方 MCP Server 操作 Google Calendar、Gmail、Drive 和 Docs。比第三方 CLI 工具更稳定可靠，支持 OAuth2 安全授权。

## 使用场景

### 日历
- 用户说「明天下午 3 点帮我加个会议」
- 用户说「这周有什么安排？」「下周三有空吗？」
- 用户说「把今天的会议推迟一小时」
- 用户说「帮我安排和 Alice 的 1-on-1，找个我们都有空的时间」

### 邮件
- 用户说「有没有新邮件？」「今天收到了什么重要邮件？」
- 用户说「帮我回复 Bob 的邮件，说同意他的方案」
- 用户说「把这封邮件标记为重要」
- 用户说「搜索上个月来自 xxx@gmail.com 的邮件」

### 云盘
- 用户说「帮我在 Drive 里找那个季度报告」
- 用户说「把这个文件上传到 Drive」
- 用户说「共享那个文件给 team@example.com」

## 前置条件

### 方式一：Google 官方 MCP Server（推荐）

1. 安装 Google MCP Server：`npm install -g @anthropic/google-mcp`
2. 首次运行时完成 OAuth2 授权（浏览器弹出 Google 登录页面）
3. 授权后令牌自动存储，后续无需重复授权

### 方式二：Google API Key + Service Account

1. 在 Google Cloud Console 创建项目并启用 Calendar/Gmail API
2. 创建 OAuth 2.0 凭据或 Service Account
3. 设置环境变量：`export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"`

## 执行方式

### 日历操作

#### 查询日程

```
工具: google_calendar_list_events
参数:
  calendar_id: "primary"
  time_min: "2026-02-26T00:00:00Z"
  time_max: "2026-02-27T00:00:00Z"
  max_results: 10
```

#### 创建日程

```
工具: google_calendar_create_event
参数:
  calendar_id: "primary"
  summary: "产品评审会议"
  description: "讨论 Q1 产品路线图"
  start: "2026-02-27T15:00:00+08:00"
  end: "2026-02-27T16:00:00+08:00"
  attendees: ["alice@example.com", "bob@example.com"]
  location: "3 楼会议室 A"
```

#### 修改日程

```
工具: google_calendar_update_event
参数:
  calendar_id: "primary"
  event_id: "xxx"
  start: "2026-02-27T16:00:00+08:00"  # 推迟一小时
  end: "2026-02-27T17:00:00+08:00"
```

### 邮件操作

#### 搜索邮件

```
工具: gmail_search
参数:
  query: "from:bob@example.com after:2026/01/01 subject:报告"
  max_results: 10
```

#### 阅读邮件

```
工具: gmail_get_message
参数:
  message_id: "xxx"
```

#### 发送邮件

```
工具: gmail_send_message
参数:
  to: "alice@example.com"
  subject: "Re: 项目进度"
  body: "你好 Alice，附件是最新的进度报告..."
  cc: "bob@example.com"
```

### 云盘操作

#### 搜索文件

```
工具: google_drive_search
参数:
  query: "季度报告 2026"
  mime_type: "application/pdf"  # 可选
```

#### 获取文件信息

```
工具: google_drive_get_file
参数:
  file_id: "xxx"
```

## 何时使用此 Skill

```
判断逻辑：

日历相关
  ├── macOS 用户 + Apple Calendar → apple-calendar
  ├── Google Calendar 用户 → google-workspace ✅
  └── 需要跨平台日历 → google-workspace ✅

邮件相关
  ├── macOS + Apple Mail → apple-mail
  ├── Outlook 用户 → outlook-cli
  ├── Gmail 用户 → google-workspace ✅
  └── 通用 IMAP → himalaya

文件存储
  ├── 本地文件 → file-manager
  ├── Google Drive → google-workspace ✅
  └── 百度网盘 → 暂无
```

## 输出规范

- 日程查询以时间线格式呈现，标注时区
- 邮件列表显示发件人、主题、时间、是否已读
- 创建/修改操作后确认具体变更内容
- 发送邮件前先展示完整草稿，通过 `hitl` 确认后发送
- 涉及多人会议的创建需确认参与者列表
