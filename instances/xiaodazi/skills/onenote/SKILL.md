---
name: onenote
description: Manage Microsoft OneNote on Windows via PowerShell COM objects. Create, search, and read notes across notebooks and sections.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [win32]
    backend_type: local
    user_facing: true
    requires_app: "OneNote"
---

# OneNote 笔记管理（Windows）

通过 PowerShell 控制 Windows 上的 Microsoft OneNote。

## 使用场景

- 用户说「帮我在 OneNote 里新建一页笔记」「搜一下 OneNote 里关于 XXX 的笔记」
- 用户需要查看或整理 OneNote 内容

## 命令参考

### 列出笔记本

```powershell
$onenote = New-Object -ComObject OneNote.Application
[xml]$hierarchy = ""
$onenote.GetHierarchy("", [Microsoft.Office.Interop.OneNote.HierarchyScope]::hsNotebooks, [ref]$hierarchy)

$hierarchy.Notebooks.Notebook | ForEach-Object {
    Write-Output "📓 $($_.name)"
    $_.Section | ForEach-Object {
        Write-Output "  📑 $($_.name)"
    }
}
```

### 搜索笔记

```powershell
$onenote = New-Object -ComObject OneNote.Application
[xml]$results = ""
$onenote.FindPages("", "搜索关键词", [ref]$results)

$results.Pages.Page | ForEach-Object {
    Write-Output "$($_.name) — $($_.dateTime)"
}
```

### 创建新页面

```powershell
$onenote = New-Object -ComObject OneNote.Application

# 获取目标 Section ID
[xml]$hierarchy = ""
$onenote.GetHierarchy("", [Microsoft.Office.Interop.OneNote.HierarchyScope]::hsSections, [ref]$hierarchy)
$sectionId = ($hierarchy.Notebooks.Notebook.Section | Where-Object { $_.name -eq "目标分区" }).ID

# 创建页面
$pageXml = @"
<?xml version="1.0"?>
<one:Page xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote">
  <one:Title>
    <one:OE><one:T><![CDATA[笔记标题]]></one:T></one:OE>
  </one:Title>
  <one:Outline>
    <one:OEChildren>
      <one:OE><one:T><![CDATA[笔记内容]]></one:T></one:OE>
    </one:OEChildren>
  </one:Outline>
</one:Page>
"@

$onenote.CreateNewPage($sectionId, [ref]$null)
```

## 注意

- 需要安装桌面版 OneNote（非 UWP 版本）
- COM 对象操作需要 OneNote 进程运行中
- 首次使用可能需要用户授权

## 安全规则

- **不删除笔记本或分区**
- 创建/修改操作前展示内容让用户确认
