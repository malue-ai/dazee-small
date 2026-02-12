---
name: windows-notification
description: Send Windows system notifications using PowerShell and BurntToast module.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
---

# Windows 系统通知

使用 PowerShell 发送 Windows 10/11 系统通知。

## 使用场景

- 长时间任务完成后通知用户
- 定时提醒
- 需要引起用户注意的重要消息

## 命令参考

### 方式 1：BurntToast 模块（推荐，功能丰富）

```powershell
# 首次安装
Install-Module -Name BurntToast -Force

# 基础通知
New-BurntToastNotification -Text "小搭子", "任务已完成"

# 带按钮的通知
$button = New-BTButton -Content "查看" -Arguments "explorer.exe"
New-BurntToastNotification -Text "小搭子", "文件整理完毕" -Button $button
```

### 方式 2：.NET 原生（无需安装，兼容性好）

```powershell
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>小搭子</text>
      <text>任务已完成</text>
    </binding>
  </visual>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("小搭子").Show($toast)
```

### 方式 3：msg 命令（最简单，弹窗式）

```powershell
msg * "任务已完成 — 小搭子"
```

## 使用规范

- 通知标题统一为「小搭子」
- 仅在耗时 > 10 秒的任务完成时、错误警告、定时任务触发时发送
- 同一任务最多 1 次完成通知
