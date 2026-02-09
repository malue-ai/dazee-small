---
name: task-scheduler
description: Create and manage Windows Task Scheduler jobs via PowerShell. Schedule recurring automations, startup tasks, and timed triggers.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
---

# Windows 任务计划程序

通过 PowerShell 操作 Windows 任务计划程序：创建定时任务、管理计划、查看执行历史。
适用于需要定期自动执行的操作（如备份、清理、同步）。

## 使用场景

- 用户说「每天定时帮我备份一下文件」「每周一提醒我整理桌面」
- 需要设置开机自启任务
- 需要定期执行 PowerShell 脚本
- 需要查看已有的计划任务

## 命令参考

### 查看已有任务

```powershell
# 列出小搭子创建的任务
Get-ScheduledTask -TaskPath "\xiaodazi\" -ErrorAction SilentlyContinue |
    Select-Object TaskName, State, @{N='NextRun';E={($_ | Get-ScheduledTaskInfo).NextRunTime}} |
    Format-Table -AutoSize

# 列出所有用户任务
Get-ScheduledTask | Where-Object { $_.TaskPath -notlike "\Microsoft\*" } |
    Select-Object TaskName, TaskPath, State |
    Format-Table -AutoSize

# 查看任务详情
Get-ScheduledTask -TaskName "xiaodazi_backup" | Format-List *
```

### 创建定时任务

```powershell
# ===== 每天定时执行 =====
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -File `"C:\scripts\daily_backup.ps1`""
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName "xiaodazi_daily_backup" -TaskPath "\xiaodazi\" -Action $action -Trigger $trigger -Settings $settings -Description "小搭子：每日文件备份"

# ===== 每周执行 =====
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "08:00"
Register-ScheduledTask -TaskName "xiaodazi_weekly_cleanup" -TaskPath "\xiaodazi\" -Action $action -Trigger $trigger -Settings $settings -Description "小搭子：每周桌面整理"

# ===== 开机启动 =====
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "xiaodazi_startup" -TaskPath "\xiaodazi\" -Action $action -Trigger $trigger -Settings $settings -Description "小搭子：开机启动任务"

# ===== 间隔执行（每 30 分钟） =====
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "xiaodazi_sync" -TaskPath "\xiaodazi\" -Action $action -Trigger $trigger -Settings $settings -Description "小搭子：定时同步"
```

### 管理任务

```powershell
# 手动执行
Start-ScheduledTask -TaskName "xiaodazi_daily_backup" -TaskPath "\xiaodazi\"

# 暂停任务
Disable-ScheduledTask -TaskName "xiaodazi_daily_backup" -TaskPath "\xiaodazi\"

# 恢复任务
Enable-ScheduledTask -TaskName "xiaodazi_daily_backup" -TaskPath "\xiaodazi\"

# 删除任务
Unregister-ScheduledTask -TaskName "xiaodazi_daily_backup" -TaskPath "\xiaodazi\" -Confirm:$false
```

### 查看执行历史

```powershell
# 最近执行记录
Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TaskScheduler/Operational'; ID=102,201} -MaxEvents 20 |
    Select-Object TimeCreated, @{N='TaskName';E={$_.Properties[0].Value}}, @{N='Result';E={$_.Properties[1].Value}} |
    Format-Table -AutoSize
```

## 命名规范

- 任务路径统一为 `\xiaodazi\`
- 任务名以 `xiaodazi_` 前缀
- 描述以「小搭子：」开头

## 输出规范

- 创建后展示任务名、触发条件、下次执行时间
- 列表展示用表格，包含名称、状态、下次执行时间
- 执行历史展示最近 5 条记录

## 安全规则

- **创建任务前必须 HITL 确认**：展示完整的执行命令和触发条件
- **删除任务前必须 HITL 确认**
- **不创建管理员权限任务**：`-RunLevel Limited`
- **只操作 `\xiaodazi\` 路径下的任务**：不修改系统任务和其他应用任务
- 执行脚本路径必须是用户目录下的文件
