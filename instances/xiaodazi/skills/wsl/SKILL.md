---
name: wsl
description: Manage Windows Subsystem for Linux (WSL) distributions and execute Linux commands from Windows. Bridge Windows and Linux workflows.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [win32]
    backend_type: local
    user_facing: true
    bins: ["wsl"]
---

# WSL（Windows Subsystem for Linux）

通过 WSL 在 Windows 上运行 Linux 命令和工具，实现 Windows + Linux 混合工作流。
适用于开发者用户和需要 Linux 工具的场景。

## 使用场景

- 用户说「用 Linux 的 grep 搜索一下」「在 WSL 里跑个脚本」
- 需要使用 Linux 特有的命令行工具（awk、sed、grep、curl）
- 需要管理 WSL 发行版
- 需要在 Windows 和 Linux 文件系统之间交互

## 命令参考

### WSL 管理

```powershell
# 查看已安装的发行版
wsl --list --verbose

# 查看可安装的发行版
wsl --list --online

# 安装发行版
wsl --install -d Ubuntu

# 设置默认发行版
wsl --set-default Ubuntu

# 关闭所有 WSL 实例
wsl --shutdown

# 查看 WSL 版本
wsl --version
```

### 执行 Linux 命令

```powershell
# 执行单个命令
wsl ls -la /home

# 指定发行版执行
wsl -d Ubuntu -- ls -la

# 执行带管道的命令
wsl -- cat /etc/os-release | grep -i version

# 在当前 Windows 目录下执行 Linux 命令
wsl -- find . -name "*.py" -type f | wsl -- wc -l
```

### Windows ↔ Linux 文件交互

```powershell
# 从 Windows 访问 Linux 文件
explorer.exe \\wsl$\Ubuntu\home\user

# 在 WSL 中访问 Windows 文件
wsl -- ls /mnt/c/Users/$env:USERNAME/Documents

# 复制文件：Windows → Linux
wsl -- cp /mnt/c/Users/$env:USERNAME/Desktop/data.csv /home/user/

# 复制文件：Linux → Windows
wsl -- cp /home/user/result.txt /mnt/c/Users/$env:USERNAME/Desktop/
```

### 常用 Linux 工具（通过 WSL）

```powershell
# 文本搜索（grep 比 findstr 强大得多）
wsl -- grep -rn "pattern" /mnt/c/Users/$env:USERNAME/Projects/

# 文本处理
wsl -- awk -F',' '{print $1, $3}' /mnt/c/path/to/data.csv

# JSON 处理
wsl -- cat /mnt/c/path/to/config.json | wsl -- jq '.key.subkey'

# 批量重命名（find + rename）
wsl -- find /mnt/c/path -name "*.txt" -exec rename 's/old/new/' {} \;

# 磁盘使用（比 PowerShell 的 Get-ChildItem 更快）
wsl -- du -sh /mnt/c/Users/$env:USERNAME/* 2>/dev/null | sort -rh | head -10
```

### 开发工具链

```powershell
# 在 WSL 中运行 Python
wsl -- python3 /mnt/c/scripts/process.py

# 在 WSL 中运行 Node.js
wsl -- node /mnt/c/project/server.js

# 在 WSL 中使用 Docker
wsl -- docker ps
wsl -- docker-compose up -d
```

## 路径转换

| Windows 路径 | WSL 路径 |
|-------------|----------|
| `C:\Users\name` | `/mnt/c/Users/name` |
| `D:\Data` | `/mnt/d/Data` |
| WSL 内部 | `\\wsl$\Ubuntu\home\user` |

## 输出规范

- 执行结果原样输出（Linux 命令风格）
- 路径涉及 Windows/Linux 转换时说明两种路径
- 管理命令执行后展示当前状态

## 安全规则

- **不执行 `rm -rf /`** 或类似危险命令
- **不修改 WSL 系统文件**（`/etc/` 下的关键配置）
- 涉及删除操作必须 HITL 确认
- WSL 未安装时提示用户安装方式（`wsl --install`）
