---
name: windows-explorer-advanced
description: Advanced File Explorer operations on Windows including Quick Access management, file properties, disk analysis, recent files, and folder statistics.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
---

# Windows 文件资源管理器高级操作

文件资源管理器高级操作：快速访问管理、文件属性查看、磁盘分析、最近文件、文件夹统计。
等同于 macOS 的 Finder 高级操作（macos-finder）。

## 使用场景

- 用户说「看看最近打开的文件」「这个文件多大」「磁盘还剩多少空间」
- 用户需要整理快速访问/收藏夹
- 用户需要查看文件夹占用统计
- 用户需要清理大文件或过期文件

## 命令参考

### 文件详细信息

```powershell
# 查看文件属性
Get-Item "C:\path\to\file.pdf" | Select-Object Name, Length, CreationTime, LastWriteTime, LastAccessTime, Attributes

# 人类可读的文件大小
$file = Get-Item "C:\path\to\file.pdf"
$size = switch ($file.Length) {
    { $_ -gt 1GB } { "{0:N2} GB" -f ($_ / 1GB); break }
    { $_ -gt 1MB } { "{0:N2} MB" -f ($_ / 1MB); break }
    { $_ -gt 1KB } { "{0:N2} KB" -f ($_ / 1KB); break }
    default { "$_ bytes" }
}
Write-Output "$($file.Name): $size, 修改于 $($file.LastWriteTime.ToString('yyyy-MM-dd HH:mm'))"

# 文件哈希（验证完整性）
Get-FileHash "C:\path\to\file.zip" -Algorithm SHA256
```

### 最近使用的文件

```powershell
# 最近打开的文件（Windows Recent 文件夹）
Get-ChildItem "$env:APPDATA\Microsoft\Windows\Recent\*.lnk" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 20 |
    ForEach-Object {
        $shell = New-Object -ComObject WScript.Shell
        $target = $shell.CreateShortcut($_.FullName).TargetPath
        Write-Output "$($_.LastWriteTime.ToString('MM-dd HH:mm')) — $target"
    }

# 最近修改的文件（指定目录）
Get-ChildItem "$env:USERPROFILE\Documents" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-7) } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 20 Name, @{N='Size';E={'{0:N1} KB' -f ($_.Length/1KB)}}, LastWriteTime, DirectoryName
```

### 快速访问管理

```powershell
# 将文件夹固定到快速访问
$shell = New-Object -ComObject Shell.Application
$shell.Namespace("C:\Users\$env:USERNAME\Projects").Self.InvokeVerb("pintohome")

# 列出快速访问项目
$shell = New-Object -ComObject Shell.Application
$quickAccess = $shell.Namespace("shell:::{679f85cb-0220-4080-b29b-5540cc05aab6}")
$quickAccess.Items() | ForEach-Object { Write-Output "$($_.Name) — $($_.Path)" }
```

### 磁盘空间分析

```powershell
# 磁盘总体使用情况
Get-PSDrive -PSProvider FileSystem | Select-Object Name,
    @{N='Total(GB)';E={[math]::Round(($_.Used+$_.Free)/1GB,1)}},
    @{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}},
    @{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}},
    @{N='Usage%';E={[math]::Round($_.Used/($_.Used+$_.Free)*100,1)}}

# 子目录大小排序（前 10 大目录）
Get-ChildItem "C:\Users\$env:USERNAME" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    [PSCustomObject]@{
        Name = $_.Name
        SizeGB = [math]::Round($size/1GB, 2)
    }
} | Sort-Object SizeGB -Descending | Select-Object -First 10

# 查找大文件（>100MB）
Get-ChildItem "C:\Users\$env:USERNAME" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -gt 100MB } |
    Sort-Object Length -Descending |
    Select-Object -First 20 Name, @{N='Size(MB)';E={[math]::Round($_.Length/1MB,1)}}, FullName
```

### 文件夹统计

```powershell
# 文件数量和类型分布
$path = "C:\Users\$env:USERNAME\Documents"
Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue |
    Group-Object Extension |
    Sort-Object Count -Descending |
    Select-Object -First 15 @{N='类型';E={if($_.Name){"*$($_.Name)"}else{'无扩展名'}}}, Count,
        @{N='Total(MB)';E={[math]::Round(($_.Group | Measure-Object Length -Sum).Sum/1MB,1)}}

# 文件总数和总大小
$stats = Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum
Write-Output "共 $($stats.Count) 个文件，总大小 $([math]::Round($stats.Sum/1GB,2)) GB"
```

### 回收站操作

```powershell
# 查看回收站内容和大小
$shell = New-Object -ComObject Shell.Application
$recycleBin = $shell.Namespace(0xA)
$items = $recycleBin.Items()
Write-Output "回收站中有 $($items.Count) 个项目"
$items | ForEach-Object { Write-Output "$($_.Name) — $($_.Size) bytes" }

# 清空回收站（需确认）
Clear-RecycleBin -Force
```

## 输出规范

- 文件大小用人类可读格式（KB/MB/GB）
- 时间用自然语言（「3 天前」「刚刚」「上周五」）
- 磁盘空间用条形图直观展示使用比例
- 统计结果格式化为简洁表格

## 安全规则

- **清空回收站前必须 HITL 确认**
- **不删除系统文件**（`C:\Windows`、`C:\Program Files` 下的文件）
- 大文件清理建议仅列出，用户确认后再操作
- 文件属性查看为只读操作，不修改文件
