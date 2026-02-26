---
name: system-info
description: Quick system diagnostics — CPU, memory, disk, uptime, and running processes.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 系统信息诊断

快速获取系统状态：CPU、内存、磁盘、运行时间、进程信息。帮助用户了解电脑运行状况。

## 使用场景

- 用户说「我的电脑什么配置」「看看系统信息」
- 用户说「内存占用多少了」「CPU 使用率高不高」
- 用户说「电脑开了多久了」「什么进程最占资源」
- 系统变慢时的初步诊断

## 执行方式

根据操作系统选择对应命令集。

### macOS / Linux

```bash
# 系统概览
uname -a

# CPU 信息
# macOS
sysctl -n machdep.cpu.brand_string
sysctl -n hw.ncpu
# Linux
lscpu | head -20

# 内存使用
# macOS
vm_stat | head -10
sysctl -n hw.memsize | awk '{printf "Total: %.1f GB\n", $1/1073741824}'
# Linux
free -h

# 磁盘使用
df -h /

# 系统运行时间
uptime

# Top 10 内存占用进程
ps aux --sort=-%mem 2>/dev/null | head -11 || ps aux -m | head -11

# Top 10 CPU 占用进程
ps aux --sort=-%cpu 2>/dev/null | head -11 || ps aux -r | head -11

# macOS 电池状态（笔记本）
pmset -g batt 2>/dev/null
```

### Windows (PowerShell)

```powershell
# 系统概览
Get-ComputerInfo | Select-Object CsName, OsName, OsArchitecture, CsProcessors, OsTotalVisibleMemorySize

# CPU 信息
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed

# 内存使用
$os = Get-CimInstance Win32_OperatingSystem
[PSCustomObject]@{
    TotalGB = [math]::Round($os.TotalVisibleMemorySize/1MB, 1)
    FreeGB = [math]::Round($os.FreePhysicalMemory/1MB, 1)
    UsedPercent = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize * 100, 1)
}

# 磁盘使用
Get-PSDrive -PSProvider FileSystem | Select-Object Name,
    @{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}},
    @{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}}

# 运行时间
(Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime | Select-Object Days, Hours, Minutes

# Top 10 内存占用进程
Get-Process | Sort-Object WorkingSet64 -Descending |
    Select-Object -First 10 Name, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,1)}}, CPU

# Top 10 CPU 占用进程
Get-Process | Sort-Object CPU -Descending |
    Select-Object -First 10 Name, @{N='CPU(s)';E={[math]::Round($_.CPU,1)}}, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,1)}}

# 电池状态（笔记本）
Get-CimInstance Win32_Battery 2>$null | Select-Object EstimatedChargeRemaining, BatteryStatus
```

## 输出规范

生成简洁的系统状态报告：

```markdown
## 系统状态

| 项目 | 信息 |
|---|---|
| 系统 | macOS 15.3 / Windows 11 / Ubuntu 24.04 |
| CPU | Apple M3 Pro (12 核) |
| 内存 | 12.5 / 18 GB (69%) |
| 磁盘 | 187 / 512 GB 可用 (63% 已用) |
| 运行时间 | 3 天 5 小时 |
| 电池 | 78%，正在充电 |

### 资源占用 Top 5
| 进程 | 内存 | CPU |
|---|---|---|
| Chrome | 2.3 GB | 12% |
| ... | ... | ... |
```

- 内存/磁盘使用超过 80% 时标注警告
- 异常高 CPU 进程给出建议（如建议关闭/重启）
