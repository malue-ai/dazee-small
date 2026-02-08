---
name: outlook-cli
description: Manage Microsoft Outlook on Windows via PowerShell COM objects. Read, send, and search emails and calendar events.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [win32]
    backend_type: local
    user_facing: true
    requires_app: "Microsoft Outlook"
---

# Outlook 邮件管理（Windows）

通过 PowerShell COM 对象控制 Windows 上的 Microsoft Outlook。

## 使用场景

- 用户说「帮我看看今天有没有新邮件」「发一封邮件给 XXX」
- 用户需要搜索历史邮件
- 用户需要查看日历

## 命令参考

### 读取收件箱

```powershell
$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNamespace("MAPI")
$inbox = $namespace.GetDefaultFolder(6)  # 6 = 收件箱

# 最近 10 封邮件
$inbox.Items | Sort-Object ReceivedTime -Descending | Select-Object -First 10 | ForEach-Object {
    Write-Output "$($_.ReceivedTime) | $($_.SenderName) | $($_.Subject)"
}
```

### 发送邮件

```powershell
$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)  # 0 = 邮件
$mail.To = "recipient@example.com"
$mail.Subject = "邮件主题"
$mail.Body = "邮件正文"
# $mail.Attachments.Add("C:\path\to\file.pdf")
$mail.Send()
```

### 搜索邮件

```powershell
$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNamespace("MAPI")
$inbox = $namespace.GetDefaultFolder(6)

# 按主题搜索
$results = $inbox.Items.Restrict("[Subject] = '关键词'")
$results | ForEach-Object { Write-Output "$($_.ReceivedTime) | $($_.Subject)" }
```

### 读取日历

```powershell
$outlook = New-Object -ComObject Outlook.Application
$namespace = $outlook.GetNamespace("MAPI")
$calendar = $namespace.GetDefaultFolder(9)  # 9 = 日历

$today = Get-Date -Format "yyyy/MM/dd"
$tomorrow = (Get-Date).AddDays(1).ToString("yyyy/MM/dd")

$events = $calendar.Items.Restrict("[Start] >= '$today' AND [Start] < '$tomorrow'")
$events | ForEach-Object { Write-Output "$($_.Start) - $($_.End) | $($_.Subject)" }
```

## 安全规则

- **发送邮件前必须 HITL 确认**：展示收件人、主题、正文，用户确认后发送
- **不自动打开附件**
- **不删除邮件**（只读操作）
