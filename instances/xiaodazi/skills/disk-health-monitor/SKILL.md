---
name: disk-health-monitor
description: Analyze disk usage, find large files and duplicates, clean caches, and generate system health reports.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 磁盘健康检查

帮助用户分析磁盘空间、发现大文件、清理缓存，生成系统健康报告。

## 使用场景

- 用户说「电脑空间不够了」「帮我看看什么占了这么多空间」
- 用户说「清理一下系统缓存」「找出最大的文件」
- 用户说「我的电脑变慢了，帮我检查一下」

## 执行方式

通过 shell 命令分析系统状态。**根据操作系统选择对应命令集：macOS/Linux 用 bash，Windows 用 PowerShell。**

---

## macOS / Linux 命令集

### 磁盘空间概览

```bash
# 各分区使用情况
df -h

# 用户主目录下各子目录占用（按大小降序）
du -sh ~/* 2>/dev/null | sort -rh | head -20
```

### 大文件发现

```bash
# 找出 > 100MB 的文件（排除隐藏目录）
find ~ -type f -size +100M -not -path '*/.*' -exec ls -lhS {} + 2>/dev/null | head -20

# 找出 > 1GB 的文件
find ~ -type f -size +1G -not -path '*/.*' -exec ls -lh {} + 2>/dev/null
```

### 缓存分析

```bash
# macOS 应用缓存
du -sh ~/Library/Caches/* 2>/dev/null | sort -rh | head -10

# Linux 用户缓存
du -sh ~/.cache/* 2>/dev/null | sort -rh | head -10

# 系统临时文件
du -sh /tmp/* 2>/dev/null | sort -rh | head -10

# 开发工具缓存
du -sh ~/.npm/_cacache 2>/dev/null
du -sh ~/Library/Caches/pip 2>/dev/null   # macOS
du -sh ~/.cache/pip 2>/dev/null           # Linux
```

### 重复文件检测

```bash
# macOS：使用 md5 -r（输出格式与 md5sum 兼容）
find <target_dir> -type f -not -empty -not -path '*/.*' -exec md5 -r {} + 2>/dev/null | sort | uniq -w32 -dD

# Linux：使用 md5sum
find <target_dir> -type f -not -empty -not -path '*/.*' -exec md5sum {} + 2>/dev/null | sort | uniq -w32 -dD
```

> `<target_dir>` 替换为用户指定的目录，未指定时默认 `~/Documents`。

### 旧文件发现

```bash
# 180 天未修改的大文件（> 50MB）
# 注意：用 -mtime（修改时间），不要用 -atime（macOS 默认 noatime，访问时间不更新）
find ~ -type f -size +50M -mtime +180 -not -path '*/.*' 2>/dev/null | head -20
```

---

## Windows 命令集（PowerShell）

### 磁盘空间概览

```powershell
# 各分区使用情况
Get-PSDrive -PSProvider FileSystem | Select-Object Name,
  @{N='Used(GB)';E={[math]::Round($_.Used/1GB,2)}},
  @{N='Free(GB)';E={[math]::Round($_.Free/1GB,2)}},
  @{N='Total(GB)';E={[math]::Round(($_.Used+$_.Free)/1GB,2)}}

# 用户主目录下各子目录占用（按大小降序）
Get-ChildItem $HOME -Directory | ForEach-Object {
  [PSCustomObject]@{
    Name = $_.Name
    SizeMB = [math]::Round((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue |
      Measure-Object Length -Sum).Sum / 1MB, 2)
  }
} | Sort-Object SizeMB -Descending | Select-Object -First 20
```

### 大文件发现

```powershell
# 找出 > 100MB 的文件
Get-ChildItem $HOME -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Length -gt 100MB -and $_.Attributes -notmatch 'Hidden' } |
  Sort-Object Length -Descending |
  Select-Object FullName, @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}}, LastWriteTime -First 20

# 找出 > 1GB 的文件
Get-ChildItem $HOME -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Length -gt 1GB } |
  Select-Object FullName, @{N='SizeGB';E={[math]::Round($_.Length/1GB,2)}}, LastWriteTime
```

### 缓存分析

```powershell
# Windows 临时文件
$tempPaths = @($env:TEMP, "$env:LOCALAPPDATA\Temp")
foreach ($p in $tempPaths) {
  if (Test-Path $p) {
    $size = (Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue |
      Measure-Object Length -Sum).Sum
    "$p : $([math]::Round($size/1MB, 2)) MB"
  }
}

# npm 缓存
$npmCache = "$env:APPDATA\npm-cache"
if (Test-Path $npmCache) {
  $size = (Get-ChildItem $npmCache -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object Length -Sum).Sum
  "npm cache: $([math]::Round($size/1MB, 2)) MB"
}

# pip 缓存
$pipCache = "$env:LOCALAPPDATA\pip\Cache"
if (Test-Path $pipCache) {
  $size = (Get-ChildItem $pipCache -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object Length -Sum).Sum
  "pip cache: $([math]::Round($size/1MB, 2)) MB"
}
```

### 重复文件检测

```powershell
# 按 MD5 哈希查找重复文件
Get-ChildItem <target_dir> -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Length -gt 0 -and $_.Attributes -notmatch 'Hidden' } |
  ForEach-Object {
    [PSCustomObject]@{
      Hash = (Get-FileHash $_.FullName -Algorithm MD5).Hash
      Path = $_.FullName
      SizeMB = [math]::Round($_.Length/1MB, 2)
    }
  } | Group-Object Hash | Where-Object { $_.Count -gt 1 } |
  ForEach-Object { $_.Group }
```

> `<target_dir>` 替换为用户指定的目录，未指定时默认 `$HOME\Documents`。

### 旧文件发现

```powershell
# 180 天未修改的大文件（> 50MB）
Get-ChildItem $HOME -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Length -gt 50MB -and $_.LastWriteTime -lt (Get-Date).AddDays(-180) } |
  Sort-Object Length -Descending |
  Select-Object FullName, @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}}, LastWriteTime -First 20
```

---

## 安全规则

- **不自动删除任何文件**：列出建议后使用 HITL 工具请求用户确认
- **缓存清理前确认**：某些缓存清理后需重新下载，必须提醒用户影响
- **不触碰系统核心目录**：
  - macOS：跳过 `/System`、`/Library`（注意 `~/Library` 可以扫描）
  - Windows：跳过 `C:\Windows`、`C:\Program Files`、`C:\Program Files (x86)`
  - Linux：跳过 `/usr`、`/lib`、`/boot`、`/proc`、`/sys`
- **不扫描敏感目录**：跳过 `.ssh`、`.gnupg`、`.aws`、`.kube` 等安全相关目录
- **隐藏文件默认跳过**：bash 中 `find` 添加 `-not -path '*/.*'`，PowerShell 排除 Hidden 属性

## 输出规范

生成结构化健康报告：

```
## 磁盘健康报告

### 空间概览
- 总空间: XXX GB
- 已用: XXX GB (XX%)
- 可用: XXX GB

### Top 10 大文件
| 文件 | 大小 | 最后修改 |
|---|---|---|

### 缓存占用
| 目录 | 大小 | 建议 |
|---|---|---|

### 清理建议
- 可回收空间: 约 XX GB
- 建议操作: ...（列出具体操作，等用户确认后执行）
```
