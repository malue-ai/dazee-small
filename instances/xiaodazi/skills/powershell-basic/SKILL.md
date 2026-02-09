---
name: powershell-basic
description: Execute PowerShell commands on Windows for system info, file operations, process management, and automation.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
---

# PowerShell 基础

通过 PowerShell 执行 Windows 系统操作。

## 使用场景

- 需要获取 Windows 系统信息（磁盘、内存、进程）
- 需要批量文件操作
- 需要管理系统服务或进程
- 其他 Skill 内部调用

## 命令参考

### 系统信息

```powershell
# 系统概览
Get-ComputerInfo | Select-Object OsName, OsVersion, CsTotalPhysicalMemory

# 磁盘空间
Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}}, @{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}}

# 内存使用
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 Name, @{N='Memory(MB)';E={[math]::Round($_.WorkingSet64/1MB,1)}}

# 电池状态
Get-WmiObject Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus

# Wi-Fi 信息
netsh wlan show interfaces | Select-String "SSID|Signal"
```

### 文件操作

```powershell
# 搜索文件
Get-ChildItem -Path "$env:USERPROFILE\Documents" -Recurse -Filter "*.pdf" | Select-Object Name, FullName, Length, LastWriteTime

# 按大小排序
Get-ChildItem -Path . -Recurse -File | Sort-Object Length -Descending | Select-Object -First 20 Name, @{N='Size(MB)';E={[math]::Round($_.Length/1MB,2)}}, FullName

# 最近修改的文件
Get-ChildItem -Path "$env:USERPROFILE" -Recurse -File | Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-7) } | Sort-Object LastWriteTime -Descending | Select-Object -First 20

# 批量重命名
Get-ChildItem -Path . -Filter "*.txt" | Rename-Item -NewName { $_.Name -replace '旧名', '新名' }
```

### 进程管理

```powershell
# 列出进程
Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name, Id, CPU, @{N='Memory(MB)';E={[math]::Round($_.WorkingSet64/1MB,1)}}

# 查找进程
Get-Process -Name "*chrome*"

# 已安装应用
Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* | Select-Object DisplayName, DisplayVersion, Publisher | Sort-Object DisplayName
```

### 网络

```powershell
# 测试连通性
Test-NetConnection -ComputerName google.com -Port 443

# 公网 IP
(Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing).Content
```

## 安全规则

- **不执行管理员命令**：不使用 `Run as Administrator`
- **不修改注册表**：不操作 HKLM 等系统注册表
- **不操作系统服务**：不 Start/Stop 系统服务
- **删除操作必须 HITL 确认**
