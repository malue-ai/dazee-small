---
name: feishu
description: Feishu (Lark) full integration — messages, documents, calendars, tasks, approvals, and meeting minutes via lark-oapi SDK.
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: local
    user_facing: true
---

# 飞书 (Feishu/Lark)

通过 lark-oapi SDK 操作飞书全生态：消息、文档、日历、任务、审批、妙记。中国团队的核心协作工具。

## 使用场景

### 消息
- 用户说「在飞书上给 xxx 发个消息」「在 xxx 群里发个通知」
- 用户说「飞书上有没有新消息？」「看看飞书群里最新的讨论」

### 文档
- 用户说「帮我在飞书文档里创建一个周报」「搜索飞书里那个技术方案文档」
- 用户说「把这段内容追加到飞书文档末尾」「读一下飞书知识库里的 XX」

### 日历
- 用户说「帮我在飞书日历上建个会议」「看看我飞书日历上今天的安排」
- 用户说「把会议改到周五」「取消明天的周会」

### 任务
- 用户说「看看我飞书上有什么待办」「帮我加个飞书任务：周五前交报告」
- 用户说「把飞书上那个任务标记为完成」

### 审批
- 用户说「查看待我审批的流程」「我的请假申请审批到哪了？」

### 妙记（会议纪要）
- 用户说「帮我看看上次周会的会议纪要」「把昨天的会议纪要总结一下」
- 用户说「提取会议的行动项」

## 前置条件

1. 在飞书开放平台（https://open.feishu.cn/）创建应用
2. 获取 App ID 和 App Secret（如已配置飞书 Gateway 通道则可复用）
3. 设置环境变量：
   ```bash
   export FEISHU_APP_ID="cli_xxxx"
   export FEISHU_APP_SECRET="xxxx"
   ```
4. 在飞书管理后台为应用授权对应权限

## 执行方式

项目已安装 `lark-oapi` SDK，优先使用 SDK 而非原始 HTTP 调用。

### 初始化客户端

```python
import lark_oapi as lark
import os

client = lark.Client.builder() \
    .app_id(os.environ["FEISHU_APP_ID"]) \
    .app_secret(os.environ["FEISHU_APP_SECRET"]) \
    .build()
```

### 发送消息

```python
from lark_oapi.api.im.v1 import *
import json

request = CreateMessageRequest.builder() \
    .receive_id_type("chat_id") \
    .request_body(CreateMessageRequestBody.builder()
        .receive_id("目标群聊或用户ID")
        .msg_type("text")
        .content(json.dumps({"text": "消息内容"}))
        .build()) \
    .build()

response = client.im.v1.message.create(request)
```

富文本消息：
```python
content = {
    "zh_cn": {
        "title": "周报通知",
        "content": [
            [{"tag": "text", "text": "请各位提交本周周报"}],
            [{"tag": "a", "text": "点击填写", "href": "https://..."}],
        ]
    }
}
# msg_type = "post"
```

获取群聊列表：
```python
request = ListChatRequest.builder().build()
response = client.im.v1.chat.list(request)
```

### 文档操作

```python
from lark_oapi.api.docx.v1 import *

# 读取文档内容
request = RawContentDocumentRequest.builder() \
    .document_id("文档ID") \
    .build()
response = client.docx.v1.document.raw_content(request)

# 创建文档
request = CreateDocumentRequest.builder() \
    .request_body(CreateDocumentRequestBody.builder()
        .title("文档标题")
        .folder_token("目标文件夹token")
        .build()) \
    .build()
response = client.docx.v1.document.create(request)
```

搜索文档（REST API）：
```python
import httpx

token = get_tenant_access_token()
resp = await httpx.AsyncClient().post(
    "https://open.feishu.cn/open-apis/suite/docs-api/search/object",
    headers={"Authorization": f"Bearer {token}"},
    json={"search_key": "搜索关键词", "count": 10},
)
```

### 日历操作

```python
from lark_oapi.api.calendar.v4 import *
import time

# 查询今日日程
now = int(time.time())
request = ListCalendarEventRequest.builder() \
    .calendar_id("primary") \
    .start_time(str(now)) \
    .end_time(str(now + 86400)) \
    .build()
response = client.calendar.v4.calendar_event.list(request)

# 创建日程
request = CreateCalendarEventRequest.builder() \
    .calendar_id("primary") \
    .request_body(CalendarEvent.builder()
        .summary("产品评审会")
        .start_time(TimeInfo.builder().timestamp("1709000000").build())
        .end_time(TimeInfo.builder().timestamp("1709003600").build())
        .build()) \
    .build()
response = client.calendar.v4.calendar_event.create(request)
```

### 任务操作

```python
from lark_oapi.api.task.v2 import *

# 获取任务列表
request = ListTaskRequest.builder().page_size(50).build()
response = client.task.v2.task.list(request)

# 创建任务
request = CreateTaskRequest.builder() \
    .request_body(InputTask.builder()
        .summary("周五前交产品报告")
        .due(Due.builder().timestamp("1709251200").is_all_day(False).build())
        .build()) \
    .build()
response = client.task.v2.task.create(request)

# 完成任务
request = CompleteTaskRequest.builder().task_id("任务ID").build()
response = client.task.v2.task.complete(request)
```

### 审批查询

```python
# 获取待审批列表（REST API）
token = get_tenant_access_token()
resp = await httpx.AsyncClient().get(
    "https://open.feishu.cn/open-apis/approval/v4/tasks/query",
    headers={"Authorization": f"Bearer {token}"},
    params={"status": "PENDING"},
)
```

### 妙记（会议纪要）

```python
from lark_oapi.api.minutes.v1 import *

# 获取妙记列表
request = ListMinuteRequest.builder().page_size(20).build()
response = client.minutes.v1.minute.list(request)

# 获取转写文本
request = GetMinuteTranscriptRequest.builder() \
    .minute_token("妙记token") \
    .build()
response = client.minutes.v1.minute_transcript.get(request)
if response.success():
    for paragraph in response.data.paragraphs:
        speaker = paragraph.speaker.user_name if paragraph.speaker else "未知"
        print(f"[{speaker}] {paragraph.content}")
```

妙记获取后可调用 `meeting-insights-analyzer` 做深度分析，或 `meeting-notes-to-action-items` 提取行动项。

## 何时使用此 Skill

```
用户提到飞书/Lark/Feishu → feishu ✅
用户需要操作中文协作文档 → feishu ✅（如果用户用飞书）
日历相关
  ├── Google Calendar → google-workspace
  ├── Apple Calendar → apple-calendar
  └── 飞书日历 → feishu ✅
即时消息
  ├── Slack → slack
  ├── Discord → discord
  └── 飞书/企业沟通 → feishu ✅
任务待办
  ├── Todoist → todoist
  ├── Things → things-mac
  └── 飞书任务 → feishu ✅
会议纪要
  └── 飞书妙记 → feishu ✅（获取后可交给 meeting 组 skill 分析）
```

## 输出规范

- 发送消息前展示草稿并通过 `hitl` 确认
- 日历操作确认时间（含时区）和参与者
- 文档搜索结果附上链接和最后修改时间
- 任务列表按截止日期排序，过期任务标红
- 审批列表以表格呈现（标题、申请人、时间、状态）
- 妙记转写按发言人分段，标注时间戳
- API 错误时解析错误码，给出具体修复建议（如权限不足→提示去管理后台授权）
