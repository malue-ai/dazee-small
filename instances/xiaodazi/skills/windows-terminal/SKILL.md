---
name: windows-terminal
description: Manage Windows Terminal tabs, profiles, and sessions via wt command. Open terminals with specific profiles, split panes, and configure settings.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
    bins: ["wt"]
---

# Windows Terminal 管理

通过 `wt` 命令行操作 Windows Terminal：打开新标签页、选择配置文件、分屏、管理会话。
Windows 11 内置，Windows 10 可通过 Microsoft Store 安装。

## 使用场景

- 用户说「打开一个终端」「开个 PowerShell 窗口」「开个 WSL 终端」
- 需要同时运行多个命令（分屏操作）
- 需要以特定配置文件打开终端
- 执行长时间任务需要独立终端窗口

## 命令参考

### 打开新终端

```powershell
# 打开默认终端
wt

# 打开 PowerShell
wt -p "PowerShell"

# 打开 CMD
wt -p "命令提示符"

# 打开 WSL（如果已安装）
wt -p "Ubuntu"
```

### 指定工作目录

```powershell
# 在指定目录打开
wt -d "C:\Users\%USERNAME%\Projects"

# 在当前目录打开新终端
wt -d .
```

### 运行命令

```powershell
# 打开并执行命令
wt -- powershell -NoExit -Command "Get-Process | Sort-Object CPU -Descending | Select-Object -First 10"

# 打开 CMD 并执行
wt -p "命令提示符" -- cmd /k "dir C:\"

# 打开并运行 Python 脚本
wt -- python "C:\scripts\monitor.py"
```

### 标签页管理

```powershell
# 打开多个标签页
wt -p "PowerShell" `; new-tab -p "命令提示符" `; new-tab -p "Ubuntu"

# 带标题的标签页
wt --title "前端开发" -d "C:\project\frontend" `; new-tab --title "后端" -d "C:\project\backend"
```

### 分屏（Split Pane）

```powershell
# 水平分屏
wt -p "PowerShell" `; split-pane -H -p "命令提示符"

# 垂直分屏
wt -p "PowerShell" `; split-pane -V -p "命令提示符"

# 指定分屏比例
wt -p "PowerShell" `; split-pane -V --size 0.3 -p "命令提示符"

# 复杂布局：左右分屏 + 右侧再上下分
wt -p "PowerShell" `; split-pane -V -p "命令提示符" `; split-pane -H -p "Ubuntu"
```

### 窗口控制

```powershell
# 全屏启动
wt --fullscreen

# 最大化启动
wt --maximized

# 指定窗口大小和位置
wt --pos 100,100 --size 120,40

# 聚焦到指定标签
wt focus-tab -t 0
```

### 配置管理

```powershell
# 打开设置界面
wt settings

# 列出已有配置文件
Get-Content "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json" |
    ConvertFrom-Json |
    Select-Object -ExpandProperty profiles |
    Select-Object -ExpandProperty list |
    ForEach-Object { Write-Output "$($_.name) — $($_.commandline)" }
```

## 常用开发场景

### 前后端开发环境

```powershell
# 一键开启开发环境：前端 + 后端 + 数据库日志
wt --title "Frontend" -d "C:\project\frontend" -- npm run dev `; `
   new-tab --title "Backend" -d "C:\project\backend" -- python main.py `; `
   new-tab --title "Logs" -- powershell -Command "Get-Content C:\logs\app.log -Wait"
```

### 系统监控

```powershell
# 分屏监控：进程 + 网络 + 磁盘
wt -- powershell -NoExit -Command "while(1){cls;Get-Process|Sort CPU -Desc|Select -First 10;sleep 3}" `; `
   split-pane -V -- powershell -NoExit -Command "while(1){cls;Get-NetTCPConnection|Group State|Sort Count -Desc;sleep 5}"
```

## 输出规范

- 打开终端后告知用户「已在新窗口/标签打开」
- 分屏操作说明各区域用途
- 配置文件列表展示名称和对应 Shell

## 安全规则

- **不以管理员身份启动终端**（除非用户明确要求）
- **长时间运行的命令使用 `-NoExit`** 防止窗口自动关闭
- 命令中包含路径时确保路径存在
