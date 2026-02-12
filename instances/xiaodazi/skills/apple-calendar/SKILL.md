---
name: apple-calendar
description: Manage Apple Calendar events on macOS using AppleScript. Create, list, search, and delete calendar events.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [darwin]
    backend_type: local
    user_facing: true
    system_auth: calendar
    bins: ["osascript"]
---

# Apple 日历

通过 AppleScript 管理 macOS 日历应用中的事件。

## 使用场景

- 用户说「帮我看看明天有什么安排」「添加一个会议到日历」
- 用户需要查看最近几天的日程
- 用户想创建/删除日历事件

## 命令参考

### 列出日历账户

```bash
osascript -e '
tell application "Calendar"
    set calNames to {}
    repeat with c in calendars
        set end of calNames to name of c
    end repeat
    return calNames
end tell
'
```

### 查看今天的事件

```bash
osascript -e '
set today to current date
set hours of today to 0
set minutes of today to 0
set seconds of today to 0
set tomorrow to today + (1 * days)

tell application "Calendar"
    set allEvents to {}
    repeat with c in calendars
        set calEvents to (every event of c whose start date ≥ today and start date < tomorrow)
        repeat with e in calEvents
            set eventInfo to summary of e & " | " & (start date of e as string) & " - " & (end date of e as string)
            set end of allEvents to eventInfo
        end repeat
    end repeat
    return allEvents
end tell
'
```

### 查看指定日期范围的事件

```bash
# 查看未来 7 天
osascript -e '
set startDate to current date
set hours of startDate to 0
set minutes of startDate to 0
set seconds of startDate to 0
set endDate to startDate + (7 * days)

tell application "Calendar"
    set allEvents to {}
    repeat with c in calendars
        set calEvents to (every event of c whose start date ≥ startDate and start date < endDate)
        repeat with e in calEvents
            set eventInfo to summary of e & " | " & (start date of e as string)
            set end of allEvents to eventInfo
        end repeat
    end repeat
    return allEvents
end tell
'
```

### 创建新事件

```bash
# 创建一个明天下午 2 点的 1 小时会议
osascript -e '
set eventDate to (current date) + (1 * days)
set hours of eventDate to 14
set minutes of eventDate to 0
set seconds of eventDate to 0
set endDate to eventDate + (1 * hours)

tell application "Calendar"
    tell calendar "个人"
        make new event with properties {summary:"团队周会", start date:eventDate, end date:endDate, description:"每周团队同步"}
    end tell
end tell
'
```

### 搜索事件

```bash
osascript -e '
tell application "Calendar"
    set results to {}
    repeat with c in calendars
        set found to (every event of c whose summary contains "会议")
        repeat with e in found
            set end of results to summary of e & " | " & (start date of e as string)
        end repeat
    end repeat
    return results
end tell
'
```

### 删除事件

```bash
# 需要先确认后再删除
osascript -e '
tell application "Calendar"
    tell calendar "个人"
        set targetEvents to (every event whose summary is "要删除的事件名")
        repeat with e in targetEvents
            delete e
        end repeat
    end tell
end tell
'
```

## 安全规则

- **创建事件前确认**：展示事件详情（名称、时间、日历），用户确认后创建
- **删除事件必须 HITL**：使用 hitl 工具请求确认
- **默认日历**：不指定日历时使用系统默认日历
- **时区**：使用系统本地时区，不做时区转换
