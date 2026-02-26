---
name: apple-mail
description: Search, read, and compose emails in Apple Mail on macOS via AppleScript/JXA.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
---

# Apple 邮件

通过 AppleScript/JXA 操作 macOS 内置的 Apple Mail 应用，支持搜索、阅读、撰写邮件。

## 使用场景

- 用户说「帮我查看最新的邮件」「有没有来自 XX 的邮件」
- 用户说「帮我写一封邮件给…」「回复刚才那封邮件」
- 用户说「搜索关于项目进度的邮件」
- 用户说「帮我总结今天的未读邮件」

## 执行方式

### 获取未读邮件

```bash
osascript -e '
tell application "Mail"
    set unreadMessages to (messages of inbox whose read status is false)
    set output to ""
    repeat with msg in (items 1 thru (min of {10, count of unreadMessages}) of unreadMessages)
        set output to output & "From: " & (sender of msg) & linefeed
        set output to output & "Subject: " & (subject of msg) & linefeed
        set output to output & "Date: " & (date received of msg) & linefeed
        set output to output & "---" & linefeed
    end repeat
    return output
end tell'
```

### 读取邮件内容

```bash
osascript -e '
tell application "Mail"
    set msgs to (messages of inbox whose subject contains "关键词")
    if (count of msgs) > 0 then
        set msg to item 1 of msgs
        return "From: " & (sender of msg) & linefeed & ¬
               "Subject: " & (subject of msg) & linefeed & ¬
               "Date: " & (date received of msg) & linefeed & ¬
               "Content: " & linefeed & (content of msg)
    end if
end tell'
```

### 搜索邮件

```bash
osascript -e '
tell application "Mail"
    set results to (messages of inbox whose subject contains "搜索词" or sender contains "搜索词")
    set output to ""
    repeat with msg in (items 1 thru (min of {20, count of results}) of results)
        set output to output & (sender of msg) & " | " & (subject of msg) & " | " & (date received of msg) & linefeed
    end repeat
    return output
end tell'
```

### 创建新邮件

```bash
osascript -e '
tell application "Mail"
    set newMessage to make new outgoing message with properties ¬
        {subject:"邮件主题", content:"邮件正文", visible:true}
    tell newMessage
        make new to recipient at end of to recipients ¬
            with properties {address:"recipient@example.com"}
    end tell
    -- 不自动发送，让用户确认
end tell'
```

### 安全规则

- **不自动发送邮件**：创建草稿后让用户在 Mail 中确认发送
- **不删除邮件**：只读取和搜索
- **隐私保护**：不记录邮件内容到日志

## 输出规范

- 邮件列表以表格格式展示（发件人、主题、日期）
- 邮件内容保留原始格式
- 摘要未读邮件时按重要性排序（已知联系人优先）
