---
name: everything-search
description: Blazing-fast full-disk file search on Windows using Everything by voidtools. Millisecond search across millions of files with regex, wildcards, and advanced filters.
metadata:
  xiaodazi:
    dependency_level: external
    os: [win32]
    backend_type: local
    user_facing: true
    bins: ["es"]
    install_hint: "https://www.voidtools.com/downloads/ 安装 Everything，并勾选安装 ES 命令行工具"
---

# Everything 极速文件搜索（Windows）

使用 Everything（voidtools）在 Windows 上进行毫秒级全盘文件搜索。
比 Windows Search 快数百倍，基于 NTFS 索引实时更新。

## 使用场景

- 用户说「帮我找一下那个 XX 文件」「电脑上有没有叫 XX 的文件」
- 需要按文件类型、大小、修改日期快速过滤
- 需要在整个磁盘中搜索特定内容
- 桌面整理前需要查找重复或分散的文件

## 命令参考（ES 命令行）

### 基础搜索

```powershell
# 按文件名搜索
es "季度报告"

# 搜索特定扩展名
es "*.xlsx"

# 搜索特定目录下
es "path:C:\Users\%USERNAME%\Documents *.pdf"
```

### 通配符和正则

```powershell
# 通配符搜索
es "报告_202*.xlsx"

# 正则搜索
es -regex "报告_\d{4}Q[1-4]\.xlsx"

# 文件名包含多个关键词（AND）
es "报告 季度 2025"
```

### 按属性过滤

```powershell
# 按大小过滤（大于 100MB 的文件）
es "size:>100mb"

# 按修改时间（最近 7 天）
es "dm:last7days"

# 按修改时间（指定日期范围）
es "dm:2025-01-01..2025-06-30"

# 按文件类型
es "ext:pdf;docx;xlsx"

# 组合过滤：Documents 目录下最近修改的大文件
es "path:Documents size:>10mb dm:lastweek"
```

### 排序和限制

```powershell
# 按大小降序（找大文件）
es "ext:mp4;mkv;avi" -sort-size-descending -n 20

# 按修改时间降序（找最近的文件）
es "*.docx" -sort-date-modified-descending -n 10

# 只输出完整路径
es "*.pdf" -path-column
```

### 高级搜索

```powershell
# 查找重复文件名
es "dupe:"

# 查找空文件夹
es "empty:"

# 查找特定父目录
es "parent:Downloads *.zip"

# 排除目录
es "*.py" "!path:node_modules" "!path:.git"
```

### 统计

```powershell
# 统计某类文件数量和总大小
es "ext:jpg;png;gif" -size -n 0 | Measure-Object -Property Length -Sum
```

## PowerShell 回退方案（未安装 Everything 时）

```powershell
# 使用 Windows 内置搜索（较慢但无需安装）
Get-ChildItem -Path "C:\Users\$env:USERNAME" -Recurse -Filter "*.pdf" -ErrorAction SilentlyContinue |
    Select-Object Name, FullName, Length, LastWriteTime |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 20
```

## 输出规范

- 搜索结果展示：文件名、完整路径、大小（人类可读）、修改时间
- 结果超过 20 条时只展示前 20 条 + 总数
- 大文件搜索结果附带大小排名
- 提供「用 Explorer 打开所在文件夹」的快捷操作

## 安全规则

- **只读操作**：只搜索和展示，不删除、不移动
- 系统目录（`C:\Windows`）的结果默认折叠，除非用户明确要求
