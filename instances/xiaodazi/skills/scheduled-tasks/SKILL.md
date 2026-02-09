---
name: scheduled-tasks
description: Create and manage scheduled recurring tasks using OS-native schedulers (cron/launchd/Task Scheduler). Enable the agent to perform tasks at specified times.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 定时任务

帮助用户创建定时/周期性任务：定时整理文件、定期生成报告、每天早上汇总信息。

## 使用场景

- 用户说「每天早上 8 点帮我整理邮件」「每周五生成本周工作汇报」
- 用户说「每天提醒我吃药」「每月 1 号整理发票」
- 用户说「查看我有哪些定时任务」「取消那个每周的任务」

## 执行方式

使用操作系统原生调度器创建定时任务。

### macOS: launchd

```bash
# 创建 plist 文件
cat > ~/Library/LaunchAgents/com.xiaodazi.task.weekly-report.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.xiaodazi.task.weekly-report</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>echo "generate weekly report" >> ~/xiaodazi_tasks.log</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>5</integer>
    <key>Hour</key>
    <integer>17</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
EOF

# 加载任务
launchctl load ~/Library/LaunchAgents/com.xiaodazi.task.weekly-report.plist
```

### Linux: cron

```bash
# 编辑 crontab
# 格式: 分 时 日 月 周 命令
# 每周五 17:00
(crontab -l 2>/dev/null; echo "0 17 * * 5 echo 'weekly report' >> ~/xiaodazi_tasks.log") | crontab -
```

### Windows: Task Scheduler

```powershell
# 创建定时任务
schtasks /create /tn "XiaodaziWeeklyReport" /tr "echo weekly report" /sc weekly /d FRI /st 17:00
```

### 查看已有任务

```bash
# macOS
ls ~/Library/LaunchAgents/com.xiaodazi.task.* 2>/dev/null

# Linux
crontab -l | grep xiaodazi

# Windows
# schtasks /query /tn "Xiaodazi*"
```

### 删除任务

```bash
# macOS
launchctl unload ~/Library/LaunchAgents/com.xiaodazi.task.weekly-report.plist
rm ~/Library/LaunchAgents/com.xiaodazi.task.weekly-report.plist

# Linux
crontab -l | grep -v "weekly report" | crontab -
```

## 安全规则

- **所有定时任务前缀统一**：macOS 用 `com.xiaodazi.task.*`，Linux cron 加 `# xiaodazi:` 注释标记
- **创建前确认**：展示任务详情让用户确认
- **不创建 root 级别任务**：只操作用户级调度器
- **任务动作限制**：只执行用户明确要求的操作

## 输出规范

- 创建后确认任务详情（名称、频率、下次执行时间）
- 列出任务时用表格展示
- 删除前确认任务名称
