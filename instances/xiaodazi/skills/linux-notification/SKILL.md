---
name: linux-notification
description: Send Linux desktop notifications using notify-send.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [linux]
    backend_type: local
    user_facing: true
    bins: ["notify-send"]
---

# Linux 系统通知

使用 notify-send 发送 Linux 桌面通知。

## 使用场景

- 长时间任务完成后通知用户
- 定时提醒
- 需要引起用户注意的重要消息

## 安装

```bash
# Debian/Ubuntu
sudo apt install libnotify-bin

# Fedora
sudo dnf install libnotify

# Arch
sudo pacman -S libnotify
```

## 命令参考

### 基础通知

```bash
notify-send "小搭子" "任务已完成"
```

### 带图标的通知

```bash
notify-send -i dialog-information "小搭子" "文件整理完毕"
```

### 带紧急程度的通知

```bash
# 低优先级
notify-send -u low "小搭子" "后台任务完成"

# 普通
notify-send -u normal "小搭子" "任务已完成"

# 紧急
notify-send -u critical "小搭子" "操作需要确认！"
```

### 设置显示时长（毫秒）

```bash
notify-send -t 5000 "小搭子" "5 秒后自动消失"
```

## 使用规范

- 通知标题统一为「小搭子」
- 仅在耗时 > 10 秒的任务完成时、错误警告、定时任务触发时发送
- 同一任务最多 1 次完成通知
