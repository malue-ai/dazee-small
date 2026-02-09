---
name: macos-notification
description: Send macOS system notifications using osascript. Useful for alerting users when long tasks complete.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
    bins: ["osascript"]
---

# macOS 系统通知

使用 osascript 发送 macOS 系统通知。

## 使用场景

- 长时间任务完成后通知用户
- 定时提醒
- 需要引起用户注意的重要消息

## 命令参考

### 发送基础通知

```bash
osascript -e 'display notification "任务已完成" with title "小搭子"'
```

### 带副标题的通知

```bash
osascript -e 'display notification "3 个文件已整理完毕" with title "小搭子" subtitle "文件整理"'
```

### 带声音的通知

```bash
osascript -e 'display notification "注意：操作需要确认" with title "小搭子" sound name "default"'
```

### 弹窗对话框（需要用户响应）

```bash
osascript -e 'display dialog "确认删除这 5 个文件吗？" with title "小搭子" buttons {"取消", "删除"} default button "取消"'
```

## 使用规范

- 通知标题统一为「小搭子」
- 通知内容简洁，不超过一行
- 仅在以下场景发送通知：
  - 耗时 > 10 秒的任务完成时
  - 需要用户注意的错误或警告
  - 定时任务触发时
- 不要频繁发送通知（同一任务最多 1 次完成通知）
